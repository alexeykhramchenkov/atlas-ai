

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from db.client import supabase


STATE_TABLE = "system_snapshot_state"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_snapshot_state(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
) -> dict[str, Any] | None:
    response = (
        supabase.table(STATE_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("snapshot_name", snapshot_name)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def ensure_snapshot_state(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
) -> dict[str, Any]:
    existing = get_snapshot_state(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        snapshot_name=snapshot_name,
    )

    if existing:
        return existing

    payload = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_name": snapshot_name,
        "status": "idle",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }

    response = (
        supabase.table(STATE_TABLE)
        .upsert(
            payload,
            on_conflict="user_id,shop_id,marketplace,snapshot_name",
        )
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else payload


def mark_snapshot_attempt(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
) -> dict[str, Any] | None:
    payload = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_name": snapshot_name,
        "status": "running",
        "last_attempt_at": utc_now_iso(),
        "error_code": None,
        "error_message": None,
        "updated_at": utc_now_iso(),
    }

    response = (
        supabase.table(STATE_TABLE)
        .upsert(
            payload,
            on_conflict="user_id,shop_id,marketplace,snapshot_name",
        )
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def mark_snapshot_success(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
    rows_read: int = 0,
    rows_upserted: int = 0,
    last_processed_date: date | str | None = None,
) -> dict[str, Any] | None:
    payload: dict[str, Any] = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_name": snapshot_name,
        "status": "success",
        "last_success_at": utc_now_iso(),
        "last_attempt_at": utc_now_iso(),
        "last_rows_read": rows_read or 0,
        "last_rows_upserted": rows_upserted or 0,
        "error_code": None,
        "error_message": None,
        "updated_at": utc_now_iso(),
    }

    if last_processed_date is not None:
        payload["last_processed_date"] = str(last_processed_date)

    response = (
        supabase.table(STATE_TABLE)
        .upsert(
            payload,
            on_conflict="user_id,shop_id,marketplace,snapshot_name",
        )
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


def mark_snapshot_failed(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_name: str,
    error_code: str = "SNAPSHOT_FAILED",
    error_message: str | None = None,
) -> dict[str, Any] | None:
    payload = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_name": snapshot_name,
        "status": "failed",
        "last_attempt_at": utc_now_iso(),
        "error_code": error_code,
        "error_message": error_message,
        "updated_at": utc_now_iso(),
    }

    response = (
        supabase.table(STATE_TABLE)
        .upsert(
            payload,
            on_conflict="user_id,shop_id,marketplace,snapshot_name",
        )
        .execute()
    )

    rows = response.data or []
    return rows[0] if rows else None


if __name__ == "__main__":
    state = ensure_snapshot_state(
        user_id=1,
        shop_id=1,
        marketplace="wb",
        snapshot_name="orders_daily",
    )
    print(state)