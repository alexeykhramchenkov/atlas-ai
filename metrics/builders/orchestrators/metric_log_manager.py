from datetime import datetime, timezone

from db.client import supabase


LOG_TABLE = "system_metric_log"


def _duration_sec(started_at: str | None, finished_at: str | None):
    if not started_at or not finished_at:
        return None

    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        return (finished - started).total_seconds()
    except Exception:
        return None


class MetricLogManager:
    @staticmethod
    def write_log(
        job_id: int | None,
        user_id: int,
        shop_id: int,
        marketplace: str,
        metric_name: str,
        status: str,
        rows_read: int = 0,
        rows_upserted: int = 0,
        last_processed_date: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        started_at: str | None = None,
        finished_at: str | None = None,
    ):
        now = datetime.now(timezone.utc).isoformat()
        finished_at = finished_at or now

        payload = {
            "job_id": job_id,
            "user_id": user_id,
            "shop_id": shop_id,
            "marketplace": marketplace,
            "metric_name": metric_name,
            "status": status,
            "rows_read": rows_read or 0,
            "rows_upserted": rows_upserted or 0,
            "last_processed_date": last_processed_date,
            "error_code": error_code,
            "error_message": error_message,
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_sec": _duration_sec(started_at, finished_at),
            "created_at": now,
        }

        result = supabase.table(LOG_TABLE).insert(payload).execute()
        rows = result.data or []

        return rows[0] if rows else payload


metric_log_manager = MetricLogManager()
