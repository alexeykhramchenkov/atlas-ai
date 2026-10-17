from __future__ import annotations

from ingestion.orchestrators.sync_event_manager import write_sync_event
from ingestion.orchestrators.sync_job_manager import get_pending_jobs
from ingestion.orchestrators.sync_worker import run_job
from ingestion.orchestrators.sync_scheduler import run_scheduler
from ingestion.orchestrators.sync_recovery_manager import recover_stale_running_jobs


DEFAULT_MARKETPLACE = "wb"
DEFAULT_MAX_JOBS = 100


def run_sync_all(
    marketplace: str | None = DEFAULT_MARKETPLACE,
    max_jobs: int = DEFAULT_MAX_JOBS,
) -> None:
    print("Sync orchestrator started")
    print(f"Marketplace: {marketplace or 'all'}")

    write_sync_event(
        event_type="orchestrator_started",
        event_status="running",
        marketplace=marketplace,
        message="Sync orchestrator started",
        payload={"marketplace": marketplace, "max_jobs": max_jobs},
    )

    recovery_result = recover_stale_running_jobs()
    print("Recovery result:")
    print(recovery_result)

    write_sync_event(
        event_type="recovery_completed",
        event_status="success",
        marketplace=marketplace,
        entity_type="sync_recovery",
        message="Recovery check completed",
        payload=recovery_result,
    )

    scheduler_result = run_scheduler(marketplace=marketplace)
    print("Scheduler result:")
    print(scheduler_result)

    write_sync_event(
        event_type="scheduler_completed",
        event_status="success",
        marketplace=marketplace,
        message="Scheduler completed",
        payload=scheduler_result,
    )

    jobs = get_pending_jobs(limit=max_jobs)
    if not jobs:
        print("No pending sync jobs")

        write_sync_event(
            event_type="no_pending_jobs",
            event_status="success",
            marketplace=marketplace,
            message="No pending sync jobs",
            payload={"max_jobs": max_jobs},
        )

        write_sync_event(
            event_type="orchestrator_finished",
            event_status="success",
            marketplace=marketplace,
            message="Sync orchestrator finished",
            payload={"jobs_run": 0},
        )

        print("Sync orchestrator finished")
        return

    print(f"Pending jobs to run: {len(jobs)}")
    write_sync_event(
        event_type="pending_jobs_found",
        event_status="success",
        marketplace=marketplace,
        message="Pending sync jobs found",
        payload={"jobs_count": len(jobs), "job_ids": [job["id"] for job in jobs]},
    )

    for job in jobs:
        print(
            f"Running job id={job['id']} | "
            f"{job['marketplace']}/{job['source_name']} | "
            f"{job['job_type']} | "
            f"{job.get('date_from')} → {job.get('date_to')}"
        )

        write_sync_event(
            event_type="orchestrator_job_dispatch",
            event_status="running",
            user_id=job.get("user_id"),
            shop_id=job.get("shop_id"),
            marketplace=job.get("marketplace"),
            source_name=job.get("source_name"),
            entity_type="sync_job",
            entity_id=job.get("id"),
            message="Dispatching sync job from orchestrator",
            payload={
                "job_type": job.get("job_type"),
                "date_from": job.get("date_from"),
                "date_to": job.get("date_to"),
            },
        )

        run_job(job)

    final_scheduler_result = run_scheduler(marketplace=marketplace)
    print("Final coverage check:")
    print(final_scheduler_result)

    write_sync_event(
        event_type="final_coverage_check_completed",
        event_status="success",
        marketplace=marketplace,
        message="Final coverage check completed",
        payload=final_scheduler_result,
    )

    print("Sync orchestrator finished")


if __name__ == "__main__":
    run_sync_all()
