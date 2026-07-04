import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


REGISTRY_TABLE = "system_sync_registry"

_registry_cache: Optional[Dict[tuple[str, str], dict[str, Any]]] = None


def _split_sync_path(sync_path: str) -> dict[str, str]:
    if not sync_path or "." not in sync_path:
        raise ValueError(f"Invalid sync_path: {sync_path}")

    module_path, function_name = sync_path.rsplit(".", 1)
    return {
        "module": module_path,
        "function": function_name,
    }


def _normalize_registry_row(row: dict[str, Any]) -> dict[str, Any]:
    row = dict(row or {})

    sync_path = row.get("sync_path")
    handler = _split_sync_path(sync_path)

    return {
        "marketplace": row.get("marketplace"),
        "source_name": row.get("source_name"),
        "sync_path": sync_path,
        "module": handler["module"],
        "function": handler["function"],
        "source_group": row.get("source_group"),
        "is_enabled": row.get("is_enabled", True),
        "version": row.get("version") or 1,
    }


def load_sync_registry(force_reload: bool = False) -> Dict[tuple[str, str], dict[str, Any]]:
    global _registry_cache

    if _registry_cache is not None and not force_reload:
        return _registry_cache

    response = (
        supabase
        .table(REGISTRY_TABLE)
        .select("*")
        .eq("is_enabled", True)
        .order("marketplace")
        .order("source_name")
        .execute()
    )

    rows = response.data or []
    registry: Dict[tuple[str, str], dict[str, Any]] = {}

    for row in rows:
        normalized = _normalize_registry_row(row)
        marketplace = normalized.get("marketplace")
        source_name = normalized.get("source_name")

        if marketplace and source_name:
            registry[(marketplace, source_name)] = normalized

    _registry_cache = registry
    return registry


def get_sync_handler(
    marketplace: str,
    source_name: str,
    force_reload: bool = False,
) -> Optional[dict[str, Any]]:
    registry = load_sync_registry(force_reload=force_reload)
    return registry.get((marketplace, source_name))


def is_registered(marketplace: str, source_name: str) -> bool:
    return get_sync_handler(marketplace, source_name) is not None


def get_registered_syncs(force_reload: bool = False) -> list[dict[str, Any]]:
    registry = load_sync_registry(force_reload=force_reload)
    return [registry[key] for key in sorted(registry.keys())]


def clear_sync_registry_cache() -> None:
    global _registry_cache
    _registry_cache = None


if __name__ == "__main__":
    syncs = get_registered_syncs(force_reload=True)
    print(f"Registered sync handlers: {len(syncs)}")

    for sync in syncs:
        print(
            f"- {sync['marketplace']}:{sync['source_name']} "
            f"→ {sync['module']}.{sync['function']}"
        )