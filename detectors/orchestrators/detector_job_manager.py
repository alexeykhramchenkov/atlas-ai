from db.client import supabase


TABLE_NAME = "system_detector_jobs"


class DetectorJobManager:
    @staticmethod
    def create_job(payload: dict):
        return supabase.table(TABLE_NAME).insert(payload).execute()

    @staticmethod
    def get_pending_jobs(limit: int = 20):
        result = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("status", "pending")
            .order("run_priority")
            .order("created_at")
            .limit(limit)
            .execute()
        )

        return result.data or []

    @staticmethod
    def has_pending_or_running_job(user_id, shop_id, marketplace, detector_name):
        result = (
            supabase.table(TABLE_NAME)
            .select("id")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("detector_name", detector_name)
            .in_("status", ["pending", "running"])
            .limit(1)
            .execute()
        )

        return bool(result.data)

    @staticmethod
    def mark_running(job_id):
        return (
            supabase.table(TABLE_NAME)
            .update({"status": "running"})
            .eq("id", job_id)
            .execute()
        )

    @staticmethod
    def mark_success(job_id, rows_read=0, signals_created=0):
        return (
            supabase.table(TABLE_NAME)
            .update(
                {
                    "status": "success",
                    "rows_read": rows_read,
                    "signals_created": signals_created,
                    "error_message": None,
                }
            )
            .eq("id", job_id)
            .execute()
        )

    @staticmethod
    def mark_failed(job_id, error_message: str):
        return (
            supabase.table(TABLE_NAME)
            .update(
                {
                    "status": "failed",
                    "error_message": error_message,
                }
            )
            .eq("id", job_id)
            .execute()
        )


detector_job_manager = DetectorJobManager()
