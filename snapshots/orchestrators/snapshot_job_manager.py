

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from db.client import supabase


JOBS_TABLE = "system_snapshot_jobs"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def find_existing_snapshot_job(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
    job_type: str = "auto_snapshot",
    date_from: date | str | None = None,
    date_to: date | str | None = None,
) -> dict[str, Any] | None:
    query = (
        supabase.table(JOBS_TABLE)
        .select("id,status")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("snapshot_name", snapshot_name)
        .eq("job_type", job_type)
        .in_("status", ["pending", "running"])
        .limit(1)
    )

    if date_from is not None:
        query = query.eq("date_from", str(date_from))

    if date_to is not None:
        query = query.eq("date_to", str(date_to))

    response = query.execute()
    rows = response.data or []
    return rows[0] if rows else None


def create_snapshot_job(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
    job_type: str = "auto_snapshot",
    priority: int = 100,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    scheduled_for: str | None = None,
    max_attempts: int = 3,
) -> dict[str, Any] | None:
    existing = find_existing_snapshot_job(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        snapshot_name=snapshot_name,
        job_type=job_type,
        date_from=date_from,
        date_to=date_to,
    )

    if existing:
        print(
            "Snapshot job already pending/running:",
            f"snapshot_name={snapshot_name}",
            f"job_id={existing.get('id')}",
            f"status={existing.get('status')}",
            f"date_from={date_from}",
            f"date_to={date_to}",
        )
        return None

    payload: dict[str, Any] = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_name": snapshot_name,
        "job_type": job_type,
        "status": "pending",
        "priority": priority,
        "scheduled_for": scheduled_for or utc_now_iso(),
        "attempts": 0,
        "max_attempts": max_attempts,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }

    if date_from is not None:
        payload["date_from"] = str(date_from)

    if date_to is not None:
        payload["date_to"] = str(date_to)

    response = supabase.table(JOBS_TABLE).insert(payload).execute()
    rows = response.data or []
    return rows[0] if rows else None


def get_next_pending_snapshot_job(*, marketplace: str = "wb") -> dict[str, Any] | None:
    response = (
        supabase.table(JOBS_TABLE)
        .select("*")
        .eq("marketplace", marketplace)
        .eq("status", "pending")
        .lte("scheduled_for", utc_now_iso())
        .order("priority")
        .order("scheduled_for")
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def mark_snapshot_job_running(*, job_id: int, locked_by: str = "snapshot_worker") -> dict[str, Any] | None:
    response = (
        supabase.table(JOBS_TABLE)
        .update(
            {
                "status": "running",
                "started_at": utc_now_iso(),
                "locked_at": utc_now_iso(),
                "locked_by": locked_by,
                "attempts": 1,
                "updated_at": utc_now_iso(),
            }
        )
        .eq("id", job_id)
        .eq("status", "pending")
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def mark_snapshot_job_success(
    *,
    job_id: int,
    rows_read: int = 0,
    rows_upserted: int = 0,
) -> dict[str, Any] | None:
    response = (
        supabase.table(JOBS_TABLE)
        .update(
            {
                "status": "success",
                "finished_at": utc_now_iso(),
                "rows_read": rows_read or 0,
                "rows_upserted": rows_upserted or 0,
                "error_code": None,
                "error_message": None,
                "updated_at": utc_now_iso(),
            }
        )
        .eq("id", job_id)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def mark_snapshot_job_failed(
    *,
    job_id: int,
    error_code: str = "SNAPSHOT_JOB_FAILED",
    error_message: str | None = None,
) -> dict[str, Any] | None:
    response = (
        supabase.table(JOBS_TABLE)
        .update(
            {
                "status": "failed",
                "finished_at": utc_now_iso(),
                "error_code": error_code,
                "error_message": error_message,
                "updated_at": utc_now_iso(),
            }
        )
        .eq("id", job_id)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


if __name__ == "__main__":
    job = create_snapshot_job(
        user_id=1,
        shop_id=1,
        marketplace="wb",
        snapshot_name="orders_daily",
        priority=10,
    )
    print(job or "Snapshot job already exists")