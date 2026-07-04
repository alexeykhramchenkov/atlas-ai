from __future__ import annotations

from typing import Any

from db.client import supabase


REGISTRY_TABLE = "system_snapshot_registry"


def get_enabled_snapshot_registry(*, marketplace: str = "wb") -> list[dict[str, Any]]:
    response = (
        supabase.table(REGISTRY_TABLE)
        .select("*")
        .eq("marketplace", marketplace)
        .eq("is_enabled", True)
        .order("run_priority")
        .execute()
    )

    return response.data or []


def get_snapshot_registry_entry(*, marketplace: str, snapshot_name: str) -> dict[str, Any] | None:
    response = (
        supabase.table(REGISTRY_TABLE)
        .select("*")
        .eq("marketplace", marketplace)
        .eq("snapshot_name", snapshot_name)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


if __name__ == "__main__":
    entries = get_enabled_snapshot_registry(marketplace="wb")
    print(f"Enabled snapshot registry entries: {len(entries)}")

    for entry in entries:
        print(
            entry["marketplace"],
            entry["snapshot_name"],
            entry["source_table_name"],
            "->",
            entry["target_table_name"],
            entry["runner_file_key"],
        )