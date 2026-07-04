from db.client import supabase


TABLE_NAME = "system_detector_log"


class DetectorLogManager:
    @staticmethod
    def log_start(job: dict):
        payload = {
            "job_id": job.get("id"),
            "user_id": job.get("user_id"),
            "shop_id": job.get("shop_id"),
            "marketplace": job.get("marketplace"),
            "detector_name": job.get("detector_name"),
            "status": "running",
        }

        result = supabase.table(TABLE_NAME).insert(payload).execute()
        rows = result.data or []
        return rows[0] if rows else None

    @staticmethod
    def log_success(log_id, rows_read=0, signals_created=0, last_processed_date=None):
        payload = {
            "status": "success",
            "rows_read": rows_read,
            "signals_created": signals_created,
            "last_processed_date": last_processed_date,
            "error_message": None,
        }

        return supabase.table(TABLE_NAME).update(payload).eq("id", log_id).execute()

    @staticmethod
    def log_failed(log_id, error_message: str):
        payload = {
            "status": "failed",
            "error_message": error_message,
        }

        return supabase.table(TABLE_NAME).update(payload).eq("id", log_id).execute()


detector_log_manager = DetectorLogManager()
