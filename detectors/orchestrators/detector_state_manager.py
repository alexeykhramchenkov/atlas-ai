

from db.client import supabase


TABLE_NAME = "system_detector_state"


class DetectorStateManager:
    @staticmethod
    def get_state(user_id, shop_id, marketplace, detector_name):
        result = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("detector_name", detector_name)
            .limit(1)
            .execute()
        )

        rows = result.data or []

        return rows[0] if rows else None

    @staticmethod
    def upsert_state(payload: dict):
        return (
            supabase.table(TABLE_NAME)
            .upsert(
                payload,
                on_conflict="user_id,shop_id,marketplace,detector_name",
            )
            .execute()
        )


detector_state_manager = DetectorStateManager()