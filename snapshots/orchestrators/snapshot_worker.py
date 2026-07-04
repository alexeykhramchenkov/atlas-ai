

from __future__ import annotations

import importlib
import time
from datetime import datetime, timezone
from typing import Any, Callable

from snapshots.orchestrators.snapshot_job_manager import (
    get_next_pending_snapshot_job,
    mark_snapshot_job_failed,
    mark_snapshot_job_running,
    mark_snapshot_job_success,
)
from snapshots.orchestrators.snapshot_log_manager import write_snapshot_log
from snapshots.orchestrators.snapshot_registry import get_snapshot_registry_entry
from snapshots.orchestrators.snapshot_state_manager import (
    get_snapshot_state,
    mark_snapshot_attempt,
    mark_snapshot_failed,
    mark_snapshot_success,
)


RUNNER_MODULE_PREFIX = "snapshots"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_snapshot_runner(runner_file_key: str) -> Callable[[dict[str, Any], dict[str, Any] | None, dict[str, Any]], dict[str, Any]]:
    module_name = f"{RUNNER_MODULE_PREFIX}.{runner_file_key}"
    module = importlib.import_module(module_name)

    runner = getattr(module, "run_snapshot_job", None)
    if runner is None:
        raise AttributeError(f"Snapshot runner {module_name} has no run_snapshot_job function")

    return runner


def run_snapshot_worker_once(*, marketplace: str = "wb") -> dict[str, Any]:
    job = get_next_pending_snapshot_job(marketplace=marketplace)

    if not job:
        return {"status": "no_pending_jobs"}

    job_id = int(job["id"])
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])
    job_marketplace = job.get("marketplace") or marketplace
    snapshot_name = job["snapshot_name"]

    locked_job = mark_snapshot_job_running(job_id=job_id)
    if not locked_job:
        return {"status": "job_already_locked", "job_id": job_id}

    started_at = utc_now_iso()
    started_ts = time.time()

    print(f"Running snapshot job id={job_id} {job_marketplace}/{snapshot_name} user_id={user_id} shop_id={shop_id}")

    registry_entry = get_snapshot_registry_entry(
        marketplace=job_marketplace,
        snapshot_name=snapshot_name,
    )

    if not registry_entry:
        error_message = f"No registry entry for {job_marketplace}/{snapshot_name}"
        mark_snapshot_job_failed(
            job_id=job_id,
            error_code="SNAPSHOT_REGISTRY_NOT_FOUND",
            error_message=error_message,
        )
        mark_snapshot_failed(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
            error_code="SNAPSHOT_REGISTRY_NOT_FOUND",
            error_message=error_message,
        )
        write_snapshot_log(
            job_id=job_id,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
            job_type=job.get("job_type"),
            status="failed",
            date_from=job.get("date_from"),
            date_to=job.get("date_to"),
            error_code="SNAPSHOT_REGISTRY_NOT_FOUND",
            error_message=error_message,
            started_at=started_at,
            finished_at=utc_now_iso(),
            duration_sec=round(time.time() - started_ts, 3),
        )
        print(error_message)
        return {"status": "failed", "job_id": job_id, "error": error_message}

    try:
        mark_snapshot_attempt(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
        )

        state = get_snapshot_state(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
        )

        runner = load_snapshot_runner(registry_entry["runner_file_key"])
        result = runner(job, state, registry_entry)

        rows_read = int(result.get("rows_read") or 0)
        rows_upserted = int(result.get("rows_upserted") or 0)
        last_processed_date = result.get("last_processed_date")

        mark_snapshot_job_success(
            job_id=job_id,
            rows_read=rows_read,
            rows_upserted=rows_upserted,
        )
        mark_snapshot_success(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
            rows_read=rows_read,
            rows_upserted=rows_upserted,
            last_processed_date=last_processed_date,
        )

        finished_at = utc_now_iso()
        duration_sec = round(time.time() - started_ts, 3)

        write_snapshot_log(
            job_id=job_id,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
            job_type=job.get("job_type"),
            status="success",
            date_from=job.get("date_from"),
            date_to=job.get("date_to"),
            rows_read=rows_read,
            rows_upserted=rows_upserted,
            duration_sec=duration_sec,
            started_at=started_at,
            finished_at=finished_at,
        )

        print(f"Snapshot job success id={job_id} rows_read={rows_read} rows_upserted={rows_upserted}")

        return {
            "status": "success",
            "job_id": job_id,
            "snapshot_name": snapshot_name,
            "rows_read": rows_read,
            "rows_upserted": rows_upserted,
        }

    except Exception as exc:
        error_message = str(exc)
        finished_at = utc_now_iso()
        duration_sec = round(time.time() - started_ts, 3)

        mark_snapshot_job_failed(
            job_id=job_id,
            error_code="SNAPSHOT_RUNNER_FAILED",
            error_message=error_message,
        )
        mark_snapshot_failed(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
            error_code="SNAPSHOT_RUNNER_FAILED",
            error_message=error_message,
        )
        write_snapshot_log(
            job_id=job_id,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=job_marketplace,
            snapshot_name=snapshot_name,
            job_type=job.get("job_type"),
            status="failed",
            date_from=job.get("date_from"),
            date_to=job.get("date_to"),
            error_code="SNAPSHOT_RUNNER_FAILED",
            error_message=error_message,
            started_at=started_at,
            finished_at=finished_at,
            duration_sec=duration_sec,
        )

        print(f"Snapshot job failed id={job_id} error={error_message}")

        return {
            "status": "failed",
            "job_id": job_id,
            "snapshot_name": snapshot_name,
            "error": error_message,
        }


if __name__ == "__main__":
    result = run_snapshot_worker_once(marketplace="wb")
    if result.get("status") == "no_pending_jobs":
        print("No pending snapshot jobs")