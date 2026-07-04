

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from db.client import supabase
from ingestion.orchestrators.sync_event_manager import write_sync_event


DEFAULT_STALE_AFTER_MINUTES = 10
FUNNEL_MAX_RECOVERABLE_DAYS = 2


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def stale_threshold_iso(stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES) -> str:
    return (utc_now() - timedelta(minutes=stale_after_minutes)).isoformat()


# --------- Coverage helpers ---------

def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"Unsupported date value: {value!r}")


def iter_days(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def get_sync_source(marketplace: str, source_name: str) -> dict[str, Any] | None:
    response = (
        supabase
        .table("system_sync_sources")
        .select("*")
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .eq("is_enabled", True)
        .eq("is_deprecated", False)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def fetch_loaded_days_for_job(job: dict[str, Any]) -> set[date]:
    source = get_sync_source(
        marketplace=job["marketplace"],
        source_name=job["source_name"],
    )
    if not source:
        return set()

    raw_table_name = source["raw_table_name"]
    date_column = source.get("date_column") or "date_from"
    date_from = parse_date(job["date_from"])
    date_to = parse_date(job["date_to"])

    response = (
        supabase
        .table(raw_table_name)
        .select(date_column)
        .eq("user_id", job["user_id"])
        .eq("shop_id", job["shop_id"])
        .eq("marketplace", job["marketplace"])
        .gte(date_column, date_from.isoformat())
        .lte(date_column, date_to.isoformat())
        .execute()
    )

    loaded_days: set[date] = set()
    for row in response.data or []:
        value = row.get(date_column)
        if value:
            loaded_days.add(parse_date(value))

    return loaded_days


def is_job_range_already_covered(job: dict[str, Any]) -> bool:
    date_from = parse_date(job["date_from"])
    date_to = parse_date(job["date_to"])
    required_days = set(iter_days(date_from, date_to))
    loaded_days = fetch_loaded_days_for_job(job)
    return bool(required_days) and required_days.issubset(loaded_days)


def get_job_days_count(job: dict[str, Any]) -> int:
    date_from = parse_date(job["date_from"])
    date_to = parse_date(job["date_to"])
    return (date_to - date_from).days + 1


def is_large_funnel_recovery_job(job: dict[str, Any]) -> bool:
    if job.get("source_name") != "funnel":
        return False

    try:
        days_count = get_job_days_count(job)
    except Exception:
        return True

    return days_count > FUNNEL_MAX_RECOVERABLE_DAYS


def find_stale_running_jobs(
    stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES,
    limit: int = 100,
) -> list[dict[str, Any]]:
    threshold = stale_threshold_iso(stale_after_minutes)

    response = (
        supabase
        .table("system_sync_jobs")
        .select("*")
        .eq("status", "running")
        .lt("updated_at", threshold)
        .order("updated_at", desc=False)
        .limit(limit)
        .execute()
    )

    return response.data or []


def mark_stale_job_as_already_covered(job: dict[str, Any]) -> dict[str, Any]:
    job_id = job["id"]
    now = utc_now_iso()

    payload = {
        "status": "success",
        "locked_at": None,
        "locked_by": None,
        "finished_at": now,
        "error_code": "skipped_already_covered",
        "error_message": "Skipped stale job because its date range is already covered in RAW",
        "updated_at": now,
    }

    response = (
        supabase
        .table("system_sync_jobs")
        .update(payload)
        .eq("id", job_id)
        .execute()
    )

    write_sync_event(
        event_type="job_skipped_already_covered",
        event_status="success",
        user_id=job.get("user_id"),
        shop_id=job.get("shop_id"),
        marketplace=job.get("marketplace"),
        source_name=job.get("source_name"),
        entity_type="sync_job",
        entity_id=job_id,
        message="Stale running sync job skipped because RAW coverage already exists",
        payload={
            "job_type": job.get("job_type"),
            "date_from": job.get("date_from"),
            "date_to": job.get("date_to"),
            "previous_status": job.get("status"),
            "previous_locked_at": job.get("locked_at"),
            "previous_locked_by": job.get("locked_by"),
            "previous_updated_at": job.get("updated_at"),
            "rows_fetched": job.get("rows_fetched"),
            "rows_upserted": job.get("rows_upserted"),
        },
    )

    rows = response.data or []
    return rows[0] if rows else {**job, **payload}


def mark_stale_job_as_not_recoverable(job: dict[str, Any]) -> dict[str, Any]:
    job_id = job["id"]
    now = utc_now_iso()

    try:
        days_count = get_job_days_count(job)
    except Exception:
        days_count = None

    payload = {
        "status": "failed",
        "locked_at": None,
        "locked_by": None,
        "finished_at": now,
        "error_code": "not_recoverable_large_funnel_job",
        "error_message": "Large stale funnel job was not recovered. Funnel must be collected only for missing days.",
        "updated_at": now,
    }

    response = (
        supabase
        .table("system_sync_jobs")
        .update(payload)
        .eq("id", job_id)
        .execute()
    )

    write_sync_event(
        event_type="job_not_recoverable",
        event_status="warning",
        user_id=job.get("user_id"),
        shop_id=job.get("shop_id"),
        marketplace=job.get("marketplace"),
        source_name=job.get("source_name"),
        entity_type="sync_job",
        entity_id=job_id,
        message="Large stale funnel job blocked from recovery",
        payload={
            "job_type": job.get("job_type"),
            "date_from": job.get("date_from"),
            "date_to": job.get("date_to"),
            "days_count": days_count,
            "max_recoverable_days": FUNNEL_MAX_RECOVERABLE_DAYS,
            "previous_status": job.get("status"),
            "previous_locked_at": job.get("locked_at"),
            "previous_locked_by": job.get("locked_by"),
            "previous_updated_at": job.get("updated_at"),
            "rows_fetched": job.get("rows_fetched"),
            "rows_upserted": job.get("rows_upserted"),
        },
    )

    rows = response.data or []
    return rows[0] if rows else {**job, **payload}


def recover_stale_job(job: dict[str, Any]) -> dict[str, Any]:
    job_id = job["id"]
    now = utc_now_iso()

    payload = {
        "status": "pending",
        "locked_at": None,
        "locked_by": None,
        "started_at": None,
        "finished_at": None,
        "error_code": "recovered_stale_running_job",
        "error_message": "Job was returned to pending because running lock became stale",
        "updated_at": now,
    }

    response = (
        supabase
        .table("system_sync_jobs")
        .update(payload)
        .eq("id", job_id)
        .execute()
    )

    write_sync_event(
        event_type="job_recovered",
        event_status="success",
        user_id=job.get("user_id"),
        shop_id=job.get("shop_id"),
        marketplace=job.get("marketplace"),
        source_name=job.get("source_name"),
        entity_type="sync_job",
        entity_id=job_id,
        message="Stale running sync job recovered to pending",
        payload={
            "job_type": job.get("job_type"),
            "date_from": job.get("date_from"),
            "date_to": job.get("date_to"),
            "previous_status": job.get("status"),
            "previous_locked_at": job.get("locked_at"),
            "previous_locked_by": job.get("locked_by"),
            "previous_updated_at": job.get("updated_at"),
            "rows_fetched": job.get("rows_fetched"),
            "rows_upserted": job.get("rows_upserted"),
        },
    )

    rows = response.data or []
    return rows[0] if rows else {**job, **payload}


def recover_stale_running_jobs(
    stale_after_minutes: int = DEFAULT_STALE_AFTER_MINUTES,
    limit: int = 100,
) -> dict[str, Any]:
    stale_jobs = find_stale_running_jobs(
        stale_after_minutes=stale_after_minutes,
        limit=limit,
    )

    recovered_jobs = []
    skipped_jobs = []
    blocked_jobs = []

    for job in stale_jobs:
        if is_job_range_already_covered(job):
            skipped_jobs.append(mark_stale_job_as_already_covered(job))
        elif is_large_funnel_recovery_job(job):
            blocked_jobs.append(mark_stale_job_as_not_recoverable(job))
        else:
            recovered_jobs.append(recover_stale_job(job))

    result = {
        "stale_after_minutes": stale_after_minutes,
        "found": len(stale_jobs),
        "recovered": len(recovered_jobs),
        "skipped_already_covered": len(skipped_jobs),
        "blocked_not_recoverable": len(blocked_jobs),
        "job_ids": [job["id"] for job in stale_jobs],
        "recovered_job_ids": [job["id"] for job in recovered_jobs],
        "skipped_job_ids": [job["id"] for job in skipped_jobs],
        "blocked_job_ids": [job["id"] for job in blocked_jobs],
    }

    if recovered_jobs or skipped_jobs or blocked_jobs:
        write_sync_event(
            event_type="stale_jobs_recovery_completed",
            event_status="success",
            entity_type="sync_recovery",
            message="Stale running sync jobs recovered or skipped",
            payload=result,
        )

    return result


if __name__ == "__main__":
    print(recover_stale_running_jobs())