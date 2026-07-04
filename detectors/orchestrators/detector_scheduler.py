

from datetime import datetime, timedelta, timezone

from normalized.orchestrators.normalization_scheduler import (
    get_active_connections,
)

from detectors.orchestrators.detector_registry import detector_registry
from detectors.orchestrators.detector_state_manager import detector_state_manager
from detectors.orchestrators.detector_job_manager import detector_job_manager


class DetectorScheduler:
    def run(self):
        connections = get_active_connections()

        stats = {
            "connections": len(connections),
            "registry_entries": 0,
            "states_checked": 0,
            "jobs_created": 0,
            "jobs_skipped_existing": 0,
            "jobs_skipped_frequency": 0,
            "errors": 0,
        }

        for connection in connections:
            marketplace = connection["marketplace"]

            registry_entries = detector_registry.get_enabled_entries(
                marketplace=marketplace
            )

            stats["registry_entries"] += len(registry_entries)

            for entry in registry_entries:
                stats["states_checked"] += 1

                detector_name = entry["detector_name"]

                state = detector_state_manager.get_state(
                    connection["user_id"],
                    connection["shop_id"],
                    marketplace,
                    detector_name,
                )

                if detector_job_manager.has_pending_or_running_job(
                    connection["user_id"],
                    connection["shop_id"],
                    marketplace,
                    detector_name,
                ):
                    stats["jobs_skipped_existing"] += 1
                    continue

                run_frequency_hours = entry.get("run_frequency_hours") or 24

                if state and state.get("last_success_at"):
                    last_success_at = datetime.fromisoformat(
                        state["last_success_at"].replace("Z", "+00:00")
                    )

                    next_allowed_at = last_success_at + timedelta(
                        hours=run_frequency_hours
                    )

                    if datetime.now(timezone.utc) < next_allowed_at:
                        stats["jobs_skipped_frequency"] += 1
                        continue

                detector_job_manager.create_job(
                    {
                        "user_id": connection["user_id"],
                        "shop_id": connection["shop_id"],
                        "marketplace": marketplace,
                        "detector_name": detector_name,
                        "status": "pending",
                        "run_priority": entry.get("run_priority", 100),
                    }
                )

                stats["jobs_created"] += 1

        print("Detector scheduler finished")
        print(f"Connections: {stats['connections']}")
        print(f"Registry entries: {stats['registry_entries']}")
        print(f"States checked: {stats['states_checked']}")
        print(f"Jobs created: {stats['jobs_created']}")
        print(f"Jobs skipped existing: {stats['jobs_skipped_existing']}")
        print(f"Jobs skipped frequency: {stats['jobs_skipped_frequency']}")
        print(f"Errors: {stats['errors']}")

        return stats


if __name__ == "__main__":
    DetectorScheduler().run()