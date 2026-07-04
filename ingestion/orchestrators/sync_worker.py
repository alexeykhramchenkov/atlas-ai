from __future__ import annotations

import importlib
import socket
import traceback
from datetime import datetime, timezone
from typing import Any

from db.client import supabase
from ingestion.orchestrators.sync_event_manager import write_sync_event
from ingestion.orchestrators.sync_job_manager import get_pending_jobs, update_sync_job
from ingestion.orchestrators.sync_registry import get_sync_handler
from ingestion.orchestrators.sync_rule_manager import get_sync_rule


WORKER_ID = f"local-worker-{socket.gethostname()}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_active_connection(user_id: int, shop_id: int, marketplace: str) -> dict[str, Any] | None:
    response = (
        supabase
        .table("system_active_sync_connections")
        .select("*")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("user_is_active", True)
        .eq("connection_status", "active")
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def load_sync_function(marketplace: str, source_name: str):
    handler = get_sync_handler(marketplace, source_name)
    if not handler:
        raise RuntimeError(f"No sync handler registered for {marketplace}/{source_name}")

    module = importlib.import_module(handler["module"])
    return getattr(module, handler["function"])


# --- Rate limit rule helpers ---
def get_rate_limit_rule(marketplace: str, source_name: str) -> dict[str, Any]:
    response = (
        supabase
        .table("system_rate_limit_rules")
        .select("*")
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .eq("is_enabled", True)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else {}



def build_effective_rule(
    sync_rule: dict[str, Any] | None,
    rate_limit_rule: dict[str, Any] | None,
) -> dict[str, Any]:
    effective_rule = dict(sync_rule or {})

    min_delay_sec = int((rate_limit_rule or {}).get("min_delay_sec") or 0)
    if min_delay_sec > 0:
        effective_rule["request_sleep_sec"] = min_delay_sec

    effective_rule["rate_limit_rule"] = rate_limit_rule or {}
    return effective_rule




# --- Rate limit helpers ---
def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed




def write_sync_log(
    job: dict[str, Any],
    status: str,
    started_at: str,
    finished_at: str,
    rows_fetched: int = 0,
    rows_upserted: int = 0,
    error_message: str | None = None,
) -> None:
    supabase.table("system_sync_log").insert(
        {
            "user_id": job["user_id"],
            "shop_id": job["shop_id"],
            "marketplace": job["marketplace"],
            "source_name": job["source_name"],
            "table_name": f"{job['marketplace']}_{job['source_name']}",
            "date_from": job.get("date_from"),
            "date_to": job.get("date_to"),
            "rows_fetched": rows_fetched,
            "rows_upserted": rows_upserted,
            "status": status,
            "error_msg": error_message,
            "started_at": started_at,
            "finished_at": finished_at,
            "synced_at": finished_at,
        }
    ).execute()


def mark_connection_error(
    job: dict[str, Any],
    error_type: str,
    error_code: str,
    error_message: str,
    is_blocking: bool = True,
) -> None:
    now = utc_now_iso()
    supabase.table("system_connection_errors").insert(
        {
            "user_id": job.get("user_id"),
            "shop_id": job.get("shop_id"),
            "marketplace": job.get("marketplace"),
            "source_name": job.get("source_name"),
            "error_type": error_type,
            "error_code": error_code,
            "error_message": error_message,
            "is_blocking": is_blocking,
            "first_seen_at": now,
            "last_seen_at": now,
        }
    ).execute()


def run_job(job: dict[str, Any]) -> None:
    job_id = job["id"]
    started_at = utc_now_iso()

    update_sync_job(
        job_id,
        {
            "status": "running",
            "attempts": int(job.get("attempts") or 0) + 1,
            "locked_at": started_at,
            "locked_by": WORKER_ID,
            "started_at": started_at,
            "updated_at": started_at,
        },
    )

    write_sync_event(
        event_type="job_started",
        event_status="running",
        user_id=job.get("user_id"),
        shop_id=job.get("shop_id"),
        marketplace=job.get("marketplace"),
        source_name=job.get("source_name"),
        entity_type="sync_job",
        entity_id=job_id,
        message="Sync job started",
        payload={
            "job_type": job.get("job_type"),
            "date_from": job.get("date_from"),
            "date_to": job.get("date_to"),
            "worker_id": WORKER_ID,
        },
    )

    rows_fetched = 0
    rows_upserted = 0
    effective_rule: dict[str, Any] = {}

    try:
        connection = get_active_connection(
            user_id=job["user_id"],
            shop_id=job["shop_id"],
            marketplace=job["marketplace"],
        )
        if not connection:
            raise RuntimeError("Active connection not found or subscription is inactive")

        rule = get_sync_rule(job["marketplace"], job["source_name"])
        rate_limit_rule = get_rate_limit_rule(job["marketplace"], job["source_name"])
        effective_rule = build_effective_rule(
            sync_rule=rule,
            rate_limit_rule=rate_limit_rule,
        )
        sync_function = load_sync_function(job["marketplace"], job["source_name"])

        def progress_callback(progress: dict[str, Any]) -> None:
            progress_rows_fetched = int(progress.get("rows_fetched") or 0)
            progress_rows_upserted = int(progress.get("rows_upserted") or 0)
            now = utc_now_iso()

            update_sync_job(
                job_id,
                {
                    "rows_fetched": progress_rows_fetched,
                    "rows_upserted": progress_rows_upserted,
                    "updated_at": now,
                },
            )

        result = sync_function(
            job=job,
            connection=connection,
            rule=effective_rule,
            progress_callback=progress_callback,
        )

        rows_fetched = int(result.get("rows_fetched") or 0)
        rows_upserted = int(result.get("rows_upserted") or 0)
        finished_at = utc_now_iso()

        update_sync_job(
            job_id,
            {
                "status": "success",
                "finished_at": finished_at,
                "rows_fetched": rows_fetched,
                "rows_upserted": rows_upserted,
                "locked_at": None,
                "locked_by": None,
                "updated_at": finished_at,
            },
        )

        write_sync_log(
            job=job,
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
        )

        write_sync_event(
            event_type="job_completed",
            event_status="success",
            user_id=job.get("user_id"),
            shop_id=job.get("shop_id"),
            marketplace=job.get("marketplace"),
            source_name=job.get("source_name"),
            entity_type="sync_job",
            entity_id=job_id,
            message="Sync job completed",
            payload={
                "job_type": job.get("job_type"),
                "date_from": job.get("date_from"),
                "date_to": job.get("date_to"),
                "rows_fetched": rows_fetched,
                "rows_upserted": rows_upserted,
                "started_at": started_at,
                "finished_at": finished_at,
                "worker_id": WORKER_ID,
            },
        )

        print(
            f"Job success | id={job_id} | {job['marketplace']}/{job['source_name']} | "
            f"fetched={rows_fetched} | upserted={rows_upserted}"
        )

    except Exception as exc:
        finished_at = utc_now_iso()
        error_message = str(exc)
        error_code = exc.__class__.__name__
        traceback.print_exc()
        update_sync_job(
            job_id,
            {
                "status": "failed",
                "finished_at": finished_at,
                "error_code": error_code,
                "error_message": error_message,
                "locked_at": None,
                "locked_by": None,
                "updated_at": finished_at,
            },
        )

        write_sync_log(
            job=job,
            status="failed",
            started_at=started_at,
            finished_at=finished_at,
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
            error_message=error_message,
        )

        mark_connection_error(
            job=job,
            error_type="sync_error",
            error_code=error_code,
            error_message=error_message,
            is_blocking=False,
        )

        write_sync_event(
            event_type="job_failed",
            event_status="failed",
            user_id=job.get("user_id"),
            shop_id=job.get("shop_id"),
            marketplace=job.get("marketplace"),
            source_name=job.get("source_name"),
            entity_type="sync_job",
            entity_id=job_id,
            message="Sync job failed",
            payload={
                "job_type": job.get("job_type"),
                "date_from": job.get("date_from"),
                "date_to": job.get("date_to"),
                "rows_fetched": rows_fetched,
                "rows_upserted": rows_upserted,
                "started_at": started_at,
                "finished_at": finished_at,
                "worker_id": WORKER_ID,
                "error_code": error_code,
                "error_message": error_message,
            },
        )

        print(f"Job failed | id={job_id} | error={error_message}")
        return


def run_worker_once() -> None:
    jobs = get_pending_jobs(limit=1)
    if not jobs:
        print("No pending sync jobs")
        return

    run_job(jobs[0])


if __name__ == "__main__":
    run_worker_once()