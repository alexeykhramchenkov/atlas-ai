from db.client import supabase


def get_sync_rule(marketplace: str, source_name: str):
    response = (
        supabase
        .table("system_sync_rules")
        .select("*")
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .eq("is_enabled", True)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None