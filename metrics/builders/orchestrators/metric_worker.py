

import importlib
from datetime import datetime, timezone

from metrics.builders.orchestrators.metric_job_manager import metric_job_manager
from metrics.builders.orchestrators.metric_log_manager import metric_log_manager
from metrics.builders.orchestrators.metric_registry import metric_registry
from metrics.builders.orchestrators.metric_state_manager import metric_state_manager


RUNNER_MODULE_PREFIX = "metrics.builders"


def import_metric_runner(runner_file_key: str):
    module_path = f"{RUNNER_MODULE_PREFIX}.{runner_file_key}"
    module = importlib.import_module(module_path)

    if not hasattr(module, "run_metric_job"):
        raise AttributeError(f"Metric runner {module_path} has no run_metric_job(job, state, registry_entry)")

    return module.run_metric_job


def run_metric_worker():
    job = metric_job_manager.get_next_pending_job()

    if not job:
        print("No pending metric jobs")
        return False

    job_id = job.get("id")
    user_id = job.get("user_id")
    shop_id = job.get("shop_id")
    marketplace = job.get("marketplace")
    metric_name = job.get("metric_name")

    print(
        f"Running metric job id={job_id} "
        f"{marketplace}/{metric_name} "
        f"user_id={user_id} shop_id={shop_id}"
    )

    running_job = metric_job_manager.increment_attempt_and_mark_running(job_id)
    started_at = (running_job or job).get("started_at") or datetime.now(timezone.utc).isoformat()

    try:
        registry_entry = metric_registry.get_by_metric_name(
            marketplace=marketplace,
            metric_name=metric_name,
        )

        if not registry_entry:
            raise ValueError(f"Metric registry entry not found: {marketplace}/{metric_name}")

        state = metric_state_manager.ensure_state(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            metric_name=metric_name,
        )

        metric_state_manager.mark_attempt(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            metric_name=metric_name,
        )

        runner_file_key = registry_entry.get("runner_file_key")

        if not runner_file_key:
            raise ValueError(f"runner_file_key is empty for {marketplace}/{metric_name}")

        run_metric_job = import_metric_runner(runner_file_key)
        result = run_metric_job(job=job, state=state, registry_entry=registry_entry) or {}

        rows_read = result.get("rows_read") or 0
        rows_upserted = result.get("rows_upserted") or 0
        last_processed_date = result.get("last_processed_date")

        metric_state_manager.mark_success(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            metric_name=metric_name,
            rows_read=rows_read,
            rows_upserted=rows_upserted,
            last_processed_date=last_processed_date,
        )

        finished_job = metric_job_manager.mark_success(job_id)
        finished_at = (finished_job or {}).get("finished_at") or datetime.now(timezone.utc).isoformat()

        metric_log_manager.write_log(
            job_id=job_id,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            metric_name=metric_name,
            status="success",
            rows_read=rows_read,
            rows_upserted=rows_upserted,
            last_processed_date=last_processed_date,
            started_at=started_at,
            finished_at=finished_at,
        )

        print(
            f"Metric job success id={job_id} "
            f"rows_read={rows_read} rows_upserted={rows_upserted} "
            f"last_processed_date={last_processed_date}"
        )

        return True

    except Exception as exc:
        error_message = str(exc)
        error_code = exc.__class__.__name__

        metric_state_manager.mark_failed(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            metric_name=metric_name,
            error_code=error_code,
            error_message=error_message,
        )

        failed_job = metric_job_manager.mark_failed(
            job_id=job_id,
            error_code=error_code,
            error_message=error_message,
        )
        finished_at = (failed_job or {}).get("finished_at") or datetime.now(timezone.utc).isoformat()

        metric_log_manager.write_log(
            job_id=job_id,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            metric_name=metric_name,
            status="failed",
            rows_read=0,
            rows_upserted=0,
            error_code=error_code,
            error_message=error_message,
            started_at=started_at,
            finished_at=finished_at,
        )

        print(f"Metric job failed id={job_id} error={error_message}")

        return True


if __name__ == "__main__":
    run_metric_worker()