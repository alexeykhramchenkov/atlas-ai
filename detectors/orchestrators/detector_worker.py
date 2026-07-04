

import importlib
from datetime import datetime, timezone

from detectors.orchestrators.detector_registry import detector_registry
from detectors.orchestrators.detector_state_manager import detector_state_manager
from detectors.orchestrators.detector_job_manager import detector_job_manager
from detectors.orchestrators.detector_log_manager import detector_log_manager


class DetectorWorker:
    def __init__(self, limit: int = 20):
        self.limit = limit

    def run_once(self):
        jobs = detector_job_manager.get_pending_jobs(limit=self.limit)

        if not jobs:
            print("No pending detector jobs")
            return 0

        processed = 0

        for job in jobs:
            self.process_job(job)
            processed += 1

        return processed

    def process_job(self, job: dict):
        job_id = job["id"]
        detector_name = job["detector_name"]
        marketplace = job["marketplace"]

        print(
            f"Running detector job id={job_id} "
            f"{marketplace}/{detector_name} "
            f"user_id={job['user_id']} shop_id={job['shop_id']}"
        )

        log_row = None

        try:
            detector_job_manager.mark_running(job_id)
            log_row = detector_log_manager.log_start(job)

            registry_entry = detector_registry.get_by_detector_name(
                marketplace=marketplace,
                detector_name=detector_name,
            )

            if not registry_entry:
                raise RuntimeError(
                    f"Detector registry entry not found: {marketplace}/{detector_name}"
                )

            detector_path = registry_entry.get("detector_path")

            if not detector_path:
                raise RuntimeError(
                    f"detector_path is empty for: {marketplace}/{detector_name}"
                )

            state = detector_state_manager.get_state(
                job["user_id"],
                job["shop_id"],
                marketplace,
                detector_name,
            )

            module = importlib.import_module(detector_path)

            if not hasattr(module, "run_detector_job"):
                raise RuntimeError(
                    f"Detector module has no run_detector_job(): {detector_path}"
                )

            result = module.run_detector_job(
                job=job,
                state=state,
                registry_entry=registry_entry,
            )

            rows_read = result.get("rows_read", 0)
            signals_created = result.get("signals_created", 0)
            last_processed_date = result.get("last_processed_date")

            detector_job_manager.mark_success(
                job_id=job_id,
                rows_read=rows_read,
                signals_created=signals_created,
            )

            detector_state_manager.upsert_state(
                {
                    "user_id": job["user_id"],
                    "shop_id": job["shop_id"],
                    "marketplace": marketplace,
                    "detector_name": detector_name,
                    "status": "success",
                    "last_success_at": datetime.now(timezone.utc).isoformat(),
                    "last_processed_date": last_processed_date,
                    "last_rows_read": rows_read,
                    "last_signals_created": signals_created,
                    "error_message": None,
                }
            )

            if log_row:
                detector_log_manager.log_success(
                    log_id=log_row["id"],
                    rows_read=rows_read,
                    signals_created=signals_created,
                    last_processed_date=last_processed_date,
                )

            print(
                f"Detector job success id={job_id} "
                f"rows_read={rows_read} signals_created={signals_created}"
            )

        except Exception as error:
            error_message = str(error)

            detector_job_manager.mark_failed(job_id, error_message)

            detector_state_manager.upsert_state(
                {
                    "user_id": job["user_id"],
                    "shop_id": job["shop_id"],
                    "marketplace": marketplace,
                    "detector_name": detector_name,
                    "status": "failed",
                    "last_attempt_at": datetime.now(timezone.utc).isoformat(),
                    "error_message": error_message,
                }
            )

            if log_row:
                detector_log_manager.log_failed(
                    log_id=log_row["id"],
                    error_message=error_message,
                )

            print(f"Detector job failed id={job_id}: {error_message}")

    def run_loop(self):
        total_processed = 0

        while True:
            processed = self.run_once()

            if processed == 0:
                break

            total_processed += processed

        return total_processed


if __name__ == "__main__":
    DetectorWorker().run_loop()