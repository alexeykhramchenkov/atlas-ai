

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.client import supabase


LOG_TABLE = "system_snapshot_log"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_snapshot_log(
    *,
    job_id: int | None,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
    status: str,
    job_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    rows_read: int = 0,
    rows_upserted: int = 0,
    duration_sec: float | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    started_at: str | None = None,
    finished_at: str | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "job_id": job_id,
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_name": snapshot_name,
        "job_type": job_type,
        "status": status,
        "rows_read": rows_read or 0,
        "rows_upserted": rows_upserted or 0,
        "error_code": error_code,
        "error_message": error_message,
        "created_at": utc_now_iso(),
    }

    if date_from is not None:
        payload["date_from"] = str(date_from)

    if date_to is not None:
        payload["date_to"] = str(date_to)

    if duration_sec is not None:
        payload["duration_sec"] = duration_sec

    if started_at is not None:
        payload["started_at"] = started_at

    if finished_at is not None:
        payload["finished_at"] = finished_at

    response = supabase.table(LOG_TABLE).insert(payload).execute()
    rows = response.data or []
    return rows[0] if rows else None


if __name__ == "__main__":
    log = write_snapshot_log(
        job_id=None,
        user_id=1,
        shop_id=1,
        marketplace="wb",
        snapshot_name="orders_daily",
        job_type="manual_test",
        status="success",
        rows_read=0,
        rows_upserted=0,
    )
    print(log)