

"""
Normalization worker.

Responsible for:
- locking one pending normalization job
- loading the correct normalizer from registry
- running normalizer contract:
    run_normalization_job(job, state, registry_entry) -> dict
- updating job status
- updating normalization state
- writing normalization log

Worker does NOT know RAW or normalized table structure.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any, Dict, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from normalized.orchestrators.normalization_job_manager import (  # noqa: E402
    default_worker_id,
    lock_next_pending_job,
    mark_job_failed,
    mark_job_success,
)
from normalized.orchestrators.normalization_log_manager import (  # noqa: E402
    log_failed,
    log_success,
)
from normalized.orchestrators.normalization_registry import (  # noqa: E402
    load_normalizer_by_source,
)
from normalized.orchestrators.normalization_state_manager import (  # noqa: E402
    get_or_create_state,
    mark_attempt,
    mark_failed,
    mark_success,
)


class NormalizationWorkerError(RuntimeError):
    pass


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_result(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Ensure normalizer result has stable keys.
    """
    if result is None:
        result = {}

    return {
        "rows_read": safe_int(result.get("rows_read"), 0),
        "rows_upserted": safe_int(result.get("rows_upserted"), 0),
        "last_raw_updated_at": result.get("last_raw_updated_at"),
        "last_raw_id": result.get("last_raw_id"),
    }


def run_one_normalization_job(worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Lock and run exactly one pending normalization job.

    Returns:
        None if no pending jobs exist.
        dict with execution result if a job was processed.
    """
    worker_id = worker_id or default_worker_id()
    job = lock_next_pending_job(worker_id=worker_id)

    if not job:
        print("No pending normalization jobs")
        return None

    job_id = job["id"]
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])
    marketplace = job["marketplace"]
    source_name = job["source_name"]

    state: Optional[Dict[str, Any]] = None

    try:
        print(
            f"Running normalization job id={job_id} "
            f"{marketplace}/{source_name} user_id={user_id} shop_id={shop_id}"
        )

        state = get_or_create_state(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            source_name=source_name,
        )
        mark_attempt(state_id=state["id"])

        registry_entry, normalizer_func = load_normalizer_by_source(
            marketplace=marketplace,
            source_name=source_name,
        )

        raw_result = normalizer_func(
            job=job,
            state=state,
            registry_entry=registry_entry,
        )
        result = normalize_result(raw_result)

        mark_job_success(
            job_id=job_id,
            rows_read=result["rows_read"],
            rows_upserted=result["rows_upserted"],
        )

        mark_success(
            state_id=state["id"],
            rows_read=result["rows_read"],
            rows_upserted=result["rows_upserted"],
            last_raw_updated_at=result.get("last_raw_updated_at"),
            last_raw_id=result.get("last_raw_id"),
        )

        log_success(
            job=job,
            rows_read=result["rows_read"],
            rows_upserted=result["rows_upserted"],
        )

        print(
            f"Normalization job success id={job_id} "
            f"rows_read={result['rows_read']} rows_upserted={result['rows_upserted']}"
        )

        return {
            "job_id": job_id,
            "status": "success",
            **result,
        }

    except Exception as exc:
        error_code = exc.__class__.__name__
        error_message = str(exc) or traceback.format_exc()

        mark_job_failed(
            job_id=job_id,
            error_code=error_code,
            error_message=error_message,
        )

        if state:
            mark_failed(
                state_id=state["id"],
                error_code=error_code,
                error_message=error_message,
            )

        log_failed(
            job=job,
            error_code=error_code,
            error_message=error_message,
        )

        print(
            f"Normalization job failed id={job_id} "
            f"error_code={error_code} error_message={error_message}"
        )

        return {
            "job_id": job_id,
            "status": "failed",
            "error_code": error_code,
            "error_message": error_message,
        }


if __name__ == "__main__":
    run_one_normalization_job()