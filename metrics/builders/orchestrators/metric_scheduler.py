from datetime import datetime, timezone, timedelta

from db.client import supabase

from metrics.builders.orchestrators.metric_job_manager import metric_job_manager
from metrics.builders.orchestrators.metric_registry import metric_registry
from metrics.builders.orchestrators.metric_state_manager import metric_state_manager


ACTIVE_CONNECTIONS_VIEW = "system_active_sync_connections"


def get_active_connections():
    result = (
        supabase.table(ACTIVE_CONNECTIONS_VIEW)
        .select("user_id,shop_id,marketplace")
        .execute()
    )
    return result.data or []


def parse_dt(value: str | None):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def should_create_metric_job(state: dict | None, registry_entry: dict) -> bool:
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


def run_metric_scheduler():
    result = {
        "connections": 0,
        "registry_entries": 0,
        "states_checked": 0,
        "jobs_created": 0,
        "jobs_skipped_existing": 0,
        "jobs_skipped_frequency": 0,
        "errors": 0,
    }

    connections = get_active_connections()
    result["connections"] = len(connections)

    for connection in connections:
        user_id = connection.get("user_id")
        shop_id = connection.get("shop_id")
        marketplace = connection.get("marketplace")

        if not user_id or not shop_id or not marketplace:
            result["errors"] += 1
            continue

        registry_entries = metric_registry.get_enabled_entries(marketplace=marketplace)
        result["registry_entries"] += len(registry_entries)

        for registry_entry in registry_entries:
            metric_name = registry_entry.get("metric_name")

            if not metric_name:
                result["errors"] += 1
                continue

            try:
                state = metric_state_manager.ensure_state(
                    user_id=user_id,
                    shop_id=shop_id,
                    marketplace=marketplace,
                    metric_name=metric_name,
                )
                result["states_checked"] += 1

                if not should_create_metric_job(state, registry_entry):
                    result["jobs_skipped_frequency"] += 1
                    continue

                created_job = metric_job_manager.create_job_if_not_exists(
                    user_id=user_id,
                    shop_id=shop_id,
                    marketplace=marketplace,
                    metric_name=metric_name,
                    priority=registry_entry.get("run_priority") or 100,
                    job_type="daily",
                )

                if created_job:
                    result["jobs_created"] += 1
                else:
                    result["jobs_skipped_existing"] += 1

            except Exception as exc:
                result["errors"] += 1
                print(
                    f"Metric scheduler error "
                    f"user_id={user_id} shop_id={shop_id} "
                    f"marketplace={marketplace} metric_name={metric_name}: {exc}"
                )

    print(
        f"Metric scheduler finished\n"
        f"Connections: {result['connections']}\n"
        f"Registry entries: {result['registry_entries']}\n"
        f"States checked: {result['states_checked']}\n"
        f"Jobs created: {result['jobs_created']}\n"
        f"Jobs skipped existing: {result['jobs_skipped_existing']}\n"
        f"Jobs skipped frequency: {result['jobs_skipped_frequency']}\n"
        f"Errors: {result['errors']}"
    )

    return result


if __name__ == "__main__":
    run_metric_scheduler()