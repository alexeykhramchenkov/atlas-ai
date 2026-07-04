"""
Normalization scheduler.

Responsible for:
- reading active sync connections
- reading enabled normalization registry entries
- creating missing state rows
- creating pending normalization jobs if no pending/running job exists

Scheduler does NOT:
- normalize data
- read RAW payloads
- check RAW coverage
- know source table structure
- decide whether there are new RAW rows

Each normalizer is responsible for its own coverage/watermark logic.
"""

from __future__ import annotations
from datetime import datetime, timezone, timedelta

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from db.client import supabase  # noqa: E402
from normalized.orchestrators.normalization_job_manager import create_job_if_missing  # noqa: E402
from normalized.orchestrators.normalization_registry import get_enabled_registry_entries  # noqa: E402
from normalized.orchestrators.normalization_state_manager import get_or_create_state  # noqa: E402


ACTIVE_CONNECTIONS_VIEW = "system_active_sync_connections"


class NormalizationSchedulerError(RuntimeError):
    pass


def get_active_connections(marketplace: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return active marketplace connections.
    """
    query = supabase.table(ACTIVE_CONNECTIONS_VIEW).select("*")

    if marketplace:
        query = query.eq("marketplace", marketplace)

    response = query.execute()
    return response.data or []


def parse_dt(value: Optional[str]):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def should_create_normalization_job(state: Optional[Dict[str, Any]], registry_entry: Dict[str, Any]) -> bool:
    if not state:
        return True

    if state.get("status") != "success":
        return True

    last_success_at = parse_dt(state.get("last_success_at"))
    if not last_success_at:
        return True

    run_frequency_hours = registry_entry.get("run_frequency_hours") or 24
    next_allowed_at = last_success_at + timedelta(hours=run_frequency_hours)

    return datetime.now(timezone.utc) >= next_allowed_at


def schedule_normalization_jobs(marketplace: Optional[str] = None) -> Dict[str, int]:
    """
    Create pending normalization jobs for all active connections and enabled sources.

    The scheduler is intentionally blind to RAW tables.
    It only creates orchestration tasks.

    The normalizer itself must decide:
    - what RAW rows are new
    - what watermark to use
    - whether rows_read is 0
    - what coverage/state should be updated
    """
    connections = get_active_connections(marketplace=marketplace)
    registry_entries = get_enabled_registry_entries(marketplace=marketplace)

    stats = {
        "connections": len(connections),
        "registry_entries": len(registry_entries),
        "states_checked": 0,
        "jobs_created": 0,
        "jobs_skipped_existing": 0,
        "jobs_skipped_frequency": 0,
        "errors": 0,
    }

    for connection in connections:
        user_id = int(connection["user_id"])
        shop_id = int(connection["shop_id"])
        connection_marketplace = connection["marketplace"]

        for registry_entry in registry_entries:
            if registry_entry["marketplace"] != connection_marketplace:
                continue

            source_name = registry_entry["source_name"]
            priority = registry_entry.get("priority") or 100

            try:
                state = get_or_create_state(
                    user_id=user_id,
                    shop_id=shop_id,
                    marketplace=connection_marketplace,
                    source_name=source_name,
                )
                stats["states_checked"] += 1

                if not should_create_normalization_job(state, registry_entry):
                    stats["jobs_skipped_frequency"] += 1
                    continue

                job = create_job_if_missing(
                    user_id=user_id,
                    shop_id=shop_id,
                    marketplace=connection_marketplace,
                    source_name=source_name,
                    job_type="incremental",
                    priority=priority,
                )

                if job:
                    stats["jobs_created"] += 1
                else:
                    stats["jobs_skipped_existing"] += 1

            except Exception as exc:
                stats["errors"] += 1
                print(
                    f"[normalization_scheduler] ERROR "
                    f"user_id={user_id} shop_id={shop_id} "
                    f"marketplace={connection_marketplace} source={source_name}: {exc}"
                )

    return stats


if __name__ == "__main__":
    result = schedule_normalization_jobs()

    print("Normalization scheduler finished")
    print(f"Connections: {result['connections']}")
    print(f"Registry entries: {result['registry_entries']}")
    print(f"States checked: {result['states_checked']}")
    print(f"Jobs created: {result['jobs_created']}")
    print(f"Jobs skipped existing: {result['jobs_skipped_existing']}")
    print(f"Jobs skipped frequency: {result['jobs_skipped_frequency']}")
    print(f"Errors: {result['errors']}")