

from datetime import datetime, timezone

from db.client import supabase


JOBS_TABLE = "system_metric_jobs"


class MetricJobManager:
    @staticmethod
    def create_job_if_not_exists(
        user_id: int,
        shop_id: int,
        marketplace: str,
        metric_name: str,
        priority: int = 100,
        job_type: str = "daily",
    ):
        existing = (
            supabase.table(JOBS_TABLE)
            .select("id,status")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("metric_name", metric_name)
            .in_("status", ["pending", "running"])
            .limit(1)
            .execute()
        )

        existing_rows = existing.data or []
        if existing_rows:
            return None

        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "user_id": user_id,
            "shop_id": shop_id,
            "marketplace": marketplace,
            "metric_name": metric_name,
            "job_type": job_type,
            "status": "pending",
            "priority": priority,
            "attempts": 0,
            "max_attempts": 3,
            "created_at": now,
            "updated_at": now,
        }

        result = supabase.table(JOBS_TABLE).insert(payload).execute()
        rows = result.data or []

        return rows[0] if rows else payload

    @staticmethod
    def get_next_pending_job():
        result = (
            supabase.table(JOBS_TABLE)
            .select("*")
            .eq("status", "pending")
            .order("priority")
            .order("created_at")
            .limit(1)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None

    @staticmethod
    def increment_attempt_and_mark_running(job_id: int, locked_by: str = "metric_worker"):
        job = (
            supabase.table(JOBS_TABLE)
            .select("attempts")
            .eq("id", job_id)
            .limit(1)
            .execute()
        )

        rows = job.data or []
        current_attempts = rows[0].get("attempts", 0) if rows else 0

        now = datetime.now(timezone.utc).isoformat()

        result = (
            supabase.table(JOBS_TABLE)
            .update(
                {
                    "status": "running",
                    "attempts": current_attempts + 1,
                    "locked_at": now,
                    "locked_by": locked_by,
                    "started_at": now,
                    "error_code": None,
                    "error_message": None,
                    "updated_at": now,
                }
            )
            .eq("id", job_id)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None

    @staticmethod
    def mark_success(job_id: int):
        now = datetime.now(timezone.utc).isoformat()

        result = (
            supabase.table(JOBS_TABLE)
            .update(
                {
                    "status": "success",
                    "finished_at": now,
                    "locked_at": None,
                    "locked_by": None,
                    "error_code": None,
                    "error_message": None,
                    "updated_at": now,
                }
            )
            .eq("id", job_id)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None

    @staticmethod
    def mark_failed(job_id: int, error_code: str | None = None, error_message: str | None = None):
        now = datetime.now(timezone.utc).isoformat()

        result = (
            supabase.table(JOBS_TABLE)
            .update(
                {
                    "status": "failed",
                    "finished_at": now,
                    "locked_at": None,
                    "locked_by": None,
                    "error_code": error_code,
                    "error_message": error_message,
                    "updated_at": now,
                }
            )
            .eq("id", job_id)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None


metric_job_manager = MetricJobManager()