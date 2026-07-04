from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from db.client import supabase
from ingestion.orchestrators.sync_job_manager import create_sync_job_if_not_exists
from ingestion.orchestrators.sync_registry import get_registered_syncs


DEFAULT_JOB_TYPE = "auto_sync"
DEFAULT_PRIORITY = 100


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def get_active_connections(marketplace: str | None = None) -> list[dict[str, Any]]:
    query = (
        supabase
        .table("system_active_sync_connections")
        .select("*")
        .eq("connection_status", "active")
        .eq("shop_status", "active")
        .eq("user_is_active", True)
    )

    if marketplace:
        query = query.eq("marketplace", marketplace)

    response = query.execute()
    return response.data or []


def ensure_sync_state_exists(
    connection: dict[str, Any],
    source_name: str,
) -> None:
    now = utc_now_iso()

    payload = {
        "user_id": connection["user_id"],
        "shop_id": connection["shop_id"],
        "marketplace": connection["marketplace"],
        "source_name": source_name,
        "sync_status": "active",
        "updated_at": now,
    }

    (
        supabase
        .table("system_sync_state")
        .upsert(
            payload,
            on_conflict="user_id,shop_id,marketplace,source_name",
        )
        .execute()
    )


def job_exists_for_today(
    connection: dict[str, Any],
    source_name: str,
    today: date,
) -> bool:
    response = (
        supabase
        .table("system_sync_jobs")
        .select("id,status")
        .eq("user_id", connection["user_id"])
        .eq("shop_id", connection["shop_id"])
        .eq("marketplace", connection["marketplace"])
        .eq("source_name", source_name)
        .eq("job_type", DEFAULT_JOB_TYPE)
        .eq("date_from", today.isoformat())
        .eq("date_to", today.isoformat())
        .in_("status", ["pending", "running", "success"])
        .limit(1)
        .execute()
    )

    return bool(response.data)


def create_source_job(
    connection: dict[str, Any],
    source_name: str,
    today: date,
) -> list[dict[str, Any]]:
    ensure_sync_state_exists(
        connection=connection,
        source_name=source_name,
    )

    if job_exists_for_today(
        connection=connection,
        source_name=source_name,
        today=today,
    ):
        return []

    now = utc_now_iso()

    payload = {
        "user_id": connection["user_id"],
        "shop_id": connection["shop_id"],
        "marketplace": connection["marketplace"],
        "source_name": source_name,
        "job_type": DEFAULT_JOB_TYPE,
        "status": "pending",
        "date_from": today.isoformat(),
        "date_to": today.isoformat(),
        "priority": DEFAULT_PRIORITY,
        "scheduled_at": now,
        "updated_at": now,
    }

    return create_sync_job_if_not_exists(payload)


def schedule_connection_sources(connection: dict[str, Any]) -> dict[str, Any]:
    marketplace = connection["marketplace"]
    registry_sources = [
        sync for sync in get_registered_syncs()
        if sync.get("marketplace") == marketplace
        and sync.get("is_enabled", True)
    ]

    today = utc_now().date()
    created_jobs: list[dict[str, Any]] = []
    checked_sources: list[dict[str, Any]] = []

    for source in registry_sources:
        source_name = source["source_name"]
        source_jobs = create_source_job(
            connection=connection,
            source_name=source_name,
            today=today,
        )
        created_jobs.extend(source_jobs)
        checked_sources.append(
            {
                "marketplace": marketplace,
                "source_name": source_name,
                "created_jobs_count": len(source_jobs),
            }
        )

    return {
        "connection_id": connection.get("connection_id"),
        "user_id": connection.get("user_id"),
        "shop_id": connection.get("shop_id"),
        "marketplace": marketplace,
        "checked_sources": checked_sources,
        "created_jobs": created_jobs,
    }


def run_scheduler(marketplace: str | None = None) -> dict[str, Any]:
    connections = get_active_connections(marketplace=marketplace)
    results = []

    for connection in connections:
        results.append(schedule_connection_sources(connection=connection))

    return {
        "connections_checked": len(connections),
        "results": results,
    }


if __name__ == "__main__":
    result = run_scheduler(marketplace="wb")
    print(result)