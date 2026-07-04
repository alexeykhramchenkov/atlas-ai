

"""
Normalization registry manager.

Responsible for:
- reading enabled normalizers from system_normalization_registry
- finding one registry entry by marketplace + source_name
- dynamically importing a normalizer module
- validating that the module has run_normalization_job()
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from db.client import supabase  # noqa: E402


REGISTRY_TABLE = "system_normalization_registry"


class NormalizationRegistryError(RuntimeError):
    """Raised when registry lookup or module loading fails."""


def get_enabled_registry_entries(marketplace: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Return enabled normalization registry entries ordered by priority.

    If marketplace is provided, return entries only for that marketplace.
    """
    query = (
        supabase.table(REGISTRY_TABLE)
        .select("*")
        .eq("is_enabled", True)
        .order("priority", desc=False)
    )

    if marketplace:
        query = query.eq("marketplace", marketplace)

    response = query.execute()
    return response.data or []


def get_registry_entry(marketplace: str, source_name: str) -> Optional[Dict[str, Any]]:
    """
    Return one enabled registry entry by marketplace + source_name.
    """
    response = (
        supabase.table(REGISTRY_TABLE)
        .select("*")
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .eq("is_enabled", True)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def require_registry_entry(marketplace: str, source_name: str) -> Dict[str, Any]:
    """
    Return registry entry or raise a clear error.
    """
    entry = get_registry_entry(marketplace=marketplace, source_name=source_name)

    if not entry:
        raise NormalizationRegistryError(
            f"No enabled normalization registry entry found for "
            f"marketplace={marketplace!r}, source_name={source_name!r}"
        )

    return entry


def load_normalizer_function(registry_entry: Dict[str, Any]) -> Callable[..., Dict[str, Any]]:
    """
    Import normalizer module from registry_entry['normalizer_path'].

    Every normalizer must expose:
        run_normalization_job(job, state, registry_entry) -> dict
    """
    module_path = registry_entry.get("normalizer_path")

    if not module_path:
        raise NormalizationRegistryError(
            f"Registry entry id={registry_entry.get('id')} has empty normalizer_path"
        )

    try:
        module = importlib.import_module(module_path)
    except Exception as exc:
        raise NormalizationRegistryError(
            f"Failed to import normalizer module {module_path!r}: {exc}"
        ) from exc

    normalizer_func = getattr(module, "run_normalization_job", None)

    if not callable(normalizer_func):
        raise NormalizationRegistryError(
            f"Normalizer module {module_path!r} must define callable "
            f"run_normalization_job(job, state, registry_entry)"
        )

    return normalizer_func


def load_normalizer_by_source(
    marketplace: str,
    source_name: str,
) -> tuple[Dict[str, Any], Callable[..., Dict[str, Any]]]:
    """
    Convenience helper for worker:
    marketplace + source_name -> registry entry + run_normalization_job function.
    """
    entry = require_registry_entry(marketplace=marketplace, source_name=source_name)
    normalizer_func = load_normalizer_function(entry)
    return entry, normalizer_func


if __name__ == "__main__":
    entries = get_enabled_registry_entries()
    print(f"Enabled normalization registry entries: {len(entries)}")

    for item in entries:
        print(
            f"- {item['marketplace']} / {item['source_name']} -> "
            f"{item['normalizer_path']}"
        )