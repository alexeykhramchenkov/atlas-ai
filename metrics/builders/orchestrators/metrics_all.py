from metrics.builders.orchestrators.metric_scheduler import run_metric_scheduler
from metrics.builders.orchestrators.metric_worker import run_metric_worker


def main():
    print("Starting metric scheduler...")

    scheduler_result = run_metric_scheduler()

    print(
        f"Metric scheduler finished\n"
        f"Connections: {scheduler_result.get('connections', 0)}\n"
        f"Registry entries: {scheduler_result.get('registry_entries', 0)}\n"
        f"States checked: {scheduler_result.get('states_checked', 0)}\n"
        f"Jobs created: {scheduler_result.get('jobs_created', 0)}\n"
        f"Jobs skipped existing: {scheduler_result.get('jobs_skipped_existing', 0)}\n"
        f"Jobs skipped frequency: {scheduler_result.get('jobs_skipped_frequency', 0)}\n"
        f"Errors: {scheduler_result.get('errors', 0)}"
    )

    print("Starting metric worker loop...")

    jobs_processed = 0

    while True:
        processed = run_metric_worker()

        if not processed:
            break

        jobs_processed += 1

    print(f"Metrics all finished. Jobs processed: {jobs_processed}")


if __name__ == "__main__":
    main()