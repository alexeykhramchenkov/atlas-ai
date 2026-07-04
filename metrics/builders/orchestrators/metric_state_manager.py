from datetime import datetime, timezone

from db.client import supabase


TABLE_NAME = "system_metric_state"


class MetricStateManager:
    @staticmethod
    def get_state(user_id: int, shop_id: int, marketplace: str, metric_name: str):
        result = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("metric_name", metric_name)
            .limit(1)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None

    @staticmethod
    def ensure_state(user_id: int, shop_id: int, marketplace: str, metric_name: str):
        existing_state = MetricStateManager.get_state(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            metric_name=metric_name,
        )

        if existing_state:
            return existing_state

        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "user_id": user_id,
            "shop_id": shop_id,
            "marketplace": marketplace,
            "metric_name": metric_name,
            "status": "idle",
            "last_rows_read": 0,
            "last_rows_upserted": 0,
            "created_at": now,
            "updated_at": now,
        }

        result = supabase.table(TABLE_NAME).insert(payload).execute()
        rows = result.data or []

        return rows[0] if rows else payload

    @staticmethod
    def mark_attempt(user_id: int, shop_id: int, marketplace: str, metric_name: str):
        now = datetime.now(timezone.utc).isoformat()

        result = (
            supabase.table(TABLE_NAME)
            .update(
                {
                    "status": "running",
                    "last_attempt_at": now,
                    "error_code": None,
                    "error_message": None,
                    "updated_at": now,
                }
            )
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("metric_name", metric_name)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None

    @staticmethod
    def mark_success(
        user_id: int,
        shop_id: int,
        marketplace: str,
        metric_name: str,
        rows_read: int = 0,
        rows_upserted: int = 0,
        last_processed_date: str | None = None,
    ):
        now = datetime.now(timezone.utc).isoformat()

        payload = {
            "status": "success",
            "last_success_at": now,
            "last_attempt_at": now,
            "last_rows_read": rows_read or 0,
            "last_rows_upserted": rows_upserted or 0,
            "error_code": None,
            "error_message": None,
            "updated_at": now,
        }

        if last_processed_date:
            payload["last_processed_date"] = last_processed_date

        result = (
            supabase.table(TABLE_NAME)
            .update(payload)
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("metric_name", metric_name)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None

    @staticmethod
    def mark_failed(
        user_id: int,
        shop_id: int,
        marketplace: str,
        metric_name: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ):
        now = datetime.now(timezone.utc).isoformat()

        result = (
            supabase.table(TABLE_NAME)
            .update(
                {
                    "status": "failed",
                    "last_attempt_at": now,
                    "error_code": error_code,
                    "error_message": error_message,
                    "updated_at": now,
                }
            )
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("metric_name", metric_name)
            .execute()
        )

        rows = result.data or []
        return rows[0] if rows else None


metric_state_manager = MetricStateManager()