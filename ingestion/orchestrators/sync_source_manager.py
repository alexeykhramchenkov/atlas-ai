from __future__ import annotations
from db.client import supabase


def get_enabled_sync_sources(marketplace: str | None = None):
    query = (
        supabase
        .table("system_sync_sources")
        .select("*")
        .eq("is_enabled", True)
        .eq("is_deprecated", False)
    )

    if marketplace:
        query = query.eq("marketplace", marketplace)

    response = query.execute()
    return response.data or []


def get_sync_source(marketplace: str, source_name: str):
    response = (
        supabase
        .table("system_sync_sources")
        .select("*")
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .eq("is_enabled", True)
        .eq("is_deprecated", False)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None