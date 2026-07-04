

"""
Normalization state manager.

Stores per:
- user
- shop
- marketplace
- source

watermarks and execution state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from db.client import supabase


STATE_TABLE = "system_normalization_state"


class NormalizationStateError(RuntimeError):
    pass


def get_state(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
) -> Optional[Dict[str, Any]]:
    response = (
        supabase.table(STATE_TABLE)
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


def get_or_create_state(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
) -> Dict[str, Any]:
    state = get_state(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=source_name,
    )

    if state:
        return state

    payload = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "status": "idle",
    }

    response = (
        supabase.table(STATE_TABLE)
        .insert(payload)
        .execute()
    )

    rows = response.data or []

    if not rows:
        raise NormalizationStateError("Failed to create normalization state")

    return rows[0]


def mark_attempt(state_id: int) -> None:
    (
        supabase.table(STATE_TABLE)
        .update(
            {
                "last_attempt_at": datetime.utcnow().isoformat(),
                "status": "running",
            }
        )
        .eq("id", state_id)
        .execute()
    )


def mark_success(
    state_id: int,
    rows_read: int,
    rows_upserted: int,
    last_raw_updated_at: Any = None,
    last_raw_id: Any = None,
) -> None:
    payload = {
        "status": "success",
        "last_success_at": datetime.utcnow().isoformat(),
        "last_rows_read": rows_read,
        "last_rows_upserted": rows_upserted,
        "error_code": None,
        "error_message": None,
    }

    if last_raw_updated_at is not None:
        payload["last_raw_updated_at"] = last_raw_updated_at

    if last_raw_id is not None:
        payload["last_raw_id"] = last_raw_id

    (
        supabase.table(STATE_TABLE)
        .update(payload)
        .eq("id", state_id)
        .execute()
    )


def mark_failed(
    state_id: int,
    error_code: str,
    error_message: str,
) -> None:
    (
        supabase.table(STATE_TABLE)
        .update(
            {
                "status": "failed",
                "error_code": error_code,
                "error_message": error_message[:5000],
            }
        )
        .eq("id", state_id)
        .execute()
    )


if __name__ == "__main__":
    print("Normalization state manager loaded")