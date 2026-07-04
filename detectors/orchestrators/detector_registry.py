

from db.client import supabase


TABLE_NAME = "system_detector_registry"


class DetectorRegistry:
    @staticmethod
    def get_enabled_entries(marketplace: str | None = None):
        query = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("is_enabled", True)
            .order("run_priority")
        )

        if marketplace:
            query = query.eq("marketplace", marketplace)

        result = query.execute()

        return result.data or []

    @staticmethod
    def get_by_detector_name(marketplace: str, detector_name: str):
        result = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("marketplace", marketplace)
            .eq("detector_name", detector_name)
            .limit(1)
            .execute()
        )

        rows = result.data or []

        return rows[0] if rows else None


detector_registry = DetectorRegistry()