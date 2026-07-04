

from __future__ import annotations

import argparse
import time

from snapshots.orchestrators.snapshot_scheduler import run_snapshot_scheduler
from snapshots.orchestrators.snapshot_worker import run_snapshot_worker_once


def run_snapshots_all(*, marketplace: str = "wb", max_jobs: int = 100, sleep_sec: float = 0.2) -> dict:
    print("Starting snapshot scheduler...")
    scheduler_result = run_snapshot_scheduler(marketplace=marketplace)

    print("Snapshot scheduler finished")
    print(f"Connections: {scheduler_result.get('connections_checked', 0)}")
    print(f"Registry entries: {scheduler_result.get('registry_entries', 0)}")
    print(f"States checked: {scheduler_result.get('states_checked', 0)}")
    print(f"Jobs created: {scheduler_result.get('jobs_created', 0)}")
    print(f"Jobs skipped existing: {scheduler_result.get('jobs_skipped_existing', 0)}")
    print(f"Errors: {scheduler_result.get('errors', 0)}")

    print("Starting snapshot worker loop...")
    processed_jobs = 0

    while processed_jobs < max_jobs:
        result = run_snapshot_worker_once(marketplace=marketplace)

        if not result or result.get("status") == "no_pending_jobs":
            print("No pending snapshot jobs")
            break

        processed_jobs += 1
        time.sleep(sleep_sec)

    print(f"Snapshots all finished. Jobs processed: {processed_jobs}")

    return {
        "scheduler": scheduler_result,
        "processed_jobs": processed_jobs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run snapshot scheduler and worker loop")
    parser.add_argument("--marketplace", default="wb")
    parser.add_argument("--max-jobs", type=int, default=100)
    parser.add_argument("--sleep-sec", type=float, default=0.2)
    args = parser.parse_args()

    run_snapshots_all(
        marketplace=args.marketplace,
        max_jobs=args.max_jobs,
        sleep_sec=args.sleep_sec,
    )


if __name__ == "__main__":
    main()