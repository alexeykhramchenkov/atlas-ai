from datetime import datetime, timezone
from db.client import supabase


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_sync_job(payload: dict):
    response = (
        supabase
        .table("system_sync_jobs")
        .insert(payload)
        .execute()
    )

    return response.data or []


def create_sync_job_if_not_exists(payload: dict):
    existing_response = (
        supabase
        .table("system_sync_jobs")
        .select("*")
        .eq("user_id", payload["user_id"])
        .eq("shop_id", payload["shop_id"])
        .eq("marketplace", payload["marketplace"])
        .eq("source_name", payload["source_name"])
        .eq("job_type", payload["job_type"])
        .eq("date_from", payload.get("date_from"))
        .eq("date_to", payload.get("date_to"))
        .in_("status", ["pending", "running"])
        .limit(1)
        .execute()
    )

    existing_rows = existing_response.data or []
    if existing_rows:
        return existing_rows

    return create_sync_job(payload)


def get_pending_jobs(limit: int = 10):
    response = (
        supabase
        .table("system_sync_jobs")
        .select("*")
        .eq("status", "pending")
        .lte("scheduled_at", utc_now_iso())
        .order("priority", desc=False)
        .order("scheduled_at", desc=False)
        .limit(limit)
        .execute()
    )

    return response.data or []


def update_sync_job(job_id: int, payload: dict):
    response = (
        supabase
        .table("system_sync_jobs")
        .update(payload)
        .eq("id", job_id)
        .execute()
    )

    return response.data or []