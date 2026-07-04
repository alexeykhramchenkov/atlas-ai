from db.client import supabase


TABLE_NAME = "system_metric_registry"


class MetricRegistry:
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
    def get_by_metric_name(marketplace: str, metric_name: str):
        result = (
            supabase.table(TABLE_NAME)
            .select("*")
            .eq("marketplace", marketplace)
            .eq("metric_name", metric_name)
            .limit(1)
            .execute()
        )

        rows = result.data or []

        return rows[0] if rows else None


metric_registry = MetricRegistry()