

"""
Normalization log manager.

Stores immutable history of normalization job executions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from db.client import supabase


LOG_TABLE = "system_normalization_log"


class NormalizationLogError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    return None


def calculate_duration_sec(started_at: Any, finished_at: Any) -> Optional[float]:
    start_dt = parse_dt(started_at)
    finish_dt = parse_dt(finished_at)

    if not start_dt or not finish_dt:
        return None

    return round((finish_dt - start_dt).total_seconds(), 3)


def create_log_entry(
    job: Dict[str, Any],
    status: str,
    rows_read: int = 0,
    rows_upserted: int = 0,
    started_at: Any = None,
    finished_at: Any = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Insert one row into system_normalization_log.
    """
    finished_at = finished_at or utc_now_iso()
    started_at = started_at or job.get("started_at")

    payload = {
        "job_id": job.get("id"),
        "user_id": job["user_id"],
        "shop_id": job["shop_id"],
        "marketplace": job["marketplace"],
        "source_name": job["source_name"],
        "status": status,
        "rows_read": rows_read or 0,
        "rows_upserted": rows_upserted or 0,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": calculate_duration_sec(started_at, finished_at),
        "error_code": error_code,
        "error_message": error_message[:5000] if error_message else None,
    }

    response = supabase.table(LOG_TABLE).insert(payload).execute()
    rows = response.data or []

    if not rows:
        raise NormalizationLogError("Failed to create normalization log entry")

    return rows[0]


def log_success(
    job: Dict[str, Any],
    rows_read: int = 0,
    rows_upserted: int = 0,
) -> Dict[str, Any]:
    return create_log_entry(
        job=job,
        status="success",
        rows_read=rows_read,
        rows_upserted=rows_upserted,
    )


def log_failed(
    job: Dict[str, Any],
    error_code: str,
    error_message: str,
    rows_read: int = 0,
    rows_upserted: int = 0,
) -> Dict[str, Any]:
    return create_log_entry(
        job=job,
        status="failed",
        rows_read=rows_read,
        rows_upserted=rows_upserted,
        error_code=error_code,
        error_message=error_message,
    )


if __name__ == "__main__":
    print("Normalization log manager loaded")