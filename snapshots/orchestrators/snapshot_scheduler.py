

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from db.client import supabase
from snapshots.orchestrators.snapshot_job_manager import create_snapshot_job
from snapshots.orchestrators.snapshot_registry import get_enabled_snapshot_registry
from snapshots.orchestrators.snapshot_state_manager import ensure_snapshot_state


ACTIVE_CONNECTIONS_VIEW = "system_active_sync_connections"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def should_create_snapshot_job(*, state: dict[str, Any], registry_entry: dict[str, Any]) -> bool:
    last_success_at = state.get("last_success_at")

    if not last_success_at:
        return True

    run_frequency_hours = registry_entry.get("run_frequency_hours") or 24

    try:
        last_success_dt = datetime.fromisoformat(str(last_success_at).replace("Z", "+00:00"))
    except ValueError:
        return True

    return utc_now() - last_success_dt >= timedelta(hours=run_frequency_hours)


def get_active_snapshot_connections(*, marketplace: str = "wb") -> list[dict[str, Any]]:
    response = (
        supabase.table(ACTIVE_CONNECTIONS_VIEW)
        .select("*")
        .eq("marketplace", marketplace)
        .eq("connection_status", "active")
        .eq("shop_status", "active")
        .eq("user_is_active", True)
        .execute()
    )

    return response.data or []


def run_snapshot_scheduler(*, marketplace: str = "wb") -> dict[str, Any]:
    connections = get_active_snapshot_connections(marketplace=marketplace)
    registry_entries = get_enabled_snapshot_registry(marketplace=marketplace)

    result = {
        "connections_checked": len(connections),
        "registry_entries": len(registry_entries),
        "states_checked": 0,
        "jobs_created": 0,
        "jobs_skipped_existing": 0,
        "errors": 0,
        "created_jobs": [],
    }

    for connection in connections:
        user_id = int(connection["user_id"])
        shop_id = int(connection["shop_id"])
        connection_marketplace = connection.get("marketplace") or marketplace

        for registry_entry in registry_entries:
            snapshot_name = registry_entry["snapshot_name"]

            try:
                state = ensure_snapshot_state(
                    user_id=user_id,
                    shop_id=shop_id,
                    marketplace=connection_marketplace,
                    snapshot_name=snapshot_name,
                )
                result["states_checked"] += 1

                if not should_create_snapshot_job(state=state, registry_entry=registry_entry):
                    continue

                job = create_snapshot_job(
                    user_id=user_id,
                    shop_id=shop_id,
                    marketplace=connection_marketplace,
                    snapshot_name=snapshot_name,
                    job_type="auto_snapshot",
                    priority=registry_entry.get("run_priority") or 100,
                )

                if job:
                    result["jobs_created"] += 1
                    result["created_jobs"].append(
                        {
                            "id": job.get("id"),
                            "marketplace": connection_marketplace,
                            "snapshot_name": snapshot_name,
                        }
                    )
                else:
                    result["jobs_skipped_existing"] += 1

            except Exception as exc:
                result["errors"] += 1
                print(f"Snapshot scheduler error | {connection_marketplace}/{snapshot_name}: {exc}")

    print("Snapshot scheduler finished")
    print(f"Connections: {result['connections_checked']}")
    print(f"Registry entries: {result['registry_entries']}")
    print(f"States checked: {result['states_checked']}")
    print(f"Jobs created: {result['jobs_created']}")
    print(f"Jobs skipped existing: {result['jobs_skipped_existing']}")
    print(f"Errors: {result['errors']}")

    return result


if __name__ == "__main__":
    run_snapshot_scheduler(marketplace="wb")