

"""
Normalization job manager.

Responsible for:
- creating normalization jobs
- locking next pending job
- marking jobs success / failed
- basic stale running job reset
"""

from __future__ import annotations

import socket
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from db.client import supabase


JOBS_TABLE = "system_normalization_jobs"


class NormalizationJobError(RuntimeError):
    pass


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_worker_id() -> str:
    return f"normalization-worker:{socket.gethostname()}"


def create_job(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    job_type: str = "incremental",
    priority: int = 100,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """
    Create a pending normalization job.
    """
    payload = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "job_type": job_type,
        "status": "pending",
        "priority": priority,
        "attempts": 0,
        "max_attempts": max_attempts,
    }

    response = supabase.table(JOBS_TABLE).insert(payload).execute()
    rows = response.data or []

    if not rows:
        raise NormalizationJobError("Failed to create normalization job")

    return rows[0]


def has_pending_or_running_job(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
) -> bool:
    """
    Prevent duplicate jobs for the same connection + source.
    """
    response = (
        supabase.table(JOBS_TABLE)
        .select("id,status")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .in_("status", ["pending", "running"])
        .limit(1)
        .execute()
    )

    return bool(response.data)


def create_job_if_missing(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    job_type: str = "incremental",
    priority: int = 100,
    max_attempts: int = 3,
) -> Optional[Dict[str, Any]]:
    """
    Create pending job only if no pending/running job already exists.
    """
    if has_pending_or_running_job(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=source_name,
    ):
        return None

    return create_job(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=source_name,
        job_type=job_type,
        priority=priority,
        max_attempts=max_attempts,
    )


def get_next_pending_job() -> Optional[Dict[str, Any]]:
    """
    Return next pending job by priority and creation time.
    """
    response = (
        supabase.table(JOBS_TABLE)
        .select("*")
        .eq("status", "pending")
        .order("priority", desc=False)
        .order("created_at", desc=False)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def lock_job(job_id: int, worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Lock job by switching pending -> running.

    Supabase REST does not give true SELECT FOR UPDATE here, so we protect by
    updating only rows that are still pending and then reading the row back.
    For one worker this is enough. For multiple workers, prefer a DB RPC later.
    """
    worker_id = worker_id or default_worker_id()
    now = utc_now_iso()

    response = (
        supabase.table(JOBS_TABLE)
        .update(
            {
                "status": "running",
                "locked_at": now,
                "locked_by": worker_id,
                "started_at": now,
                "attempts": 1,
            }
        )
        .eq("id", job_id)
        .eq("status", "pending")
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def lock_next_pending_job(worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Find and lock next pending job.
    """
    job = get_next_pending_job()

    if not job:
        return None

    return lock_job(job_id=job["id"], worker_id=worker_id)


def mark_job_success(
    job_id: int,
    rows_read: int = 0,
    rows_upserted: int = 0,
) -> None:
    now = utc_now_iso()

    (
        supabase.table(JOBS_TABLE)
        .update(
            {
                "status": "success",
                "finished_at": now,
                "rows_read": rows_read,
                "rows_upserted": rows_upserted,
                "error_code": None,
                "error_message": None,
            }
        )
        .eq("id", job_id)
        .execute()
    )


def mark_job_failed(
    job_id: int,
    error_code: str,
    error_message: str,
) -> None:
    now = utc_now_iso()

    (
        supabase.table(JOBS_TABLE)
        .update(
            {
                "status": "failed",
                "finished_at": now,
                "error_code": error_code,
                "error_message": error_message[:5000],
            }
        )
        .eq("id", job_id)
        .execute()
    )


def reset_stale_running_jobs(stale_after_minutes: int = 60) -> int:
    """
    Reset stale running jobs back to pending.

    Useful if worker crashed and left jobs locked.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=stale_after_minutes)).isoformat()

    response = (
        supabase.table(JOBS_TABLE)
        .update(
            {
                "status": "pending",
                "locked_at": None,
                "locked_by": None,
                "started_at": None,
            }
        )
        .eq("status", "running")
        .lt("locked_at", cutoff)
        .execute()
    )

    return len(response.data or [])


if __name__ == "__main__":
    job = get_next_pending_job()

    if not job:
        print("No pending normalization jobs")
    else:
        print(
            f"Next pending normalization job: "
            f"id={job['id']} {job['marketplace']}/{job['source_name']} "
            f"user_id={job['user_id']} shop_id={job['shop_id']}"
        )