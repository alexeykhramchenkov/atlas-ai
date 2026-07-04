from db.client import supabase


def get_sync_state(user_id: int, shop_id: int, marketplace: str, source_name: str):
    response = (
        supabase
        .table("system_sync_state")
        .select("*")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def upsert_sync_state(payload: dict):
    response = (
        supabase
        .table("system_sync_state")
        .upsert(
            payload,
            on_conflict="user_id,shop_id,marketplace,source_name"
        )
        .execute()
    )

    return response.data or []