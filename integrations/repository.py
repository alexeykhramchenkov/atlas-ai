from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from db.client import supabase_admin
from integrations.security import encrypt_token, token_fingerprint


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_oauth_state(
    *,
    provider: str,
    tg_user_id: int,
    tg_chat_id: int | None,
    external_account_id: str,
    expires_at: datetime,
) -> str:
    state = secrets.token_urlsafe(32)
    supabase_admin.table("system_oauth_states").insert(
        {
            "provider": provider,
            "state": state,
            "tg_user_id": tg_user_id,
            "tg_chat_id": tg_chat_id,
            "external_account_id": external_account_id,
            "expires_at": expires_at.isoformat(),
        }
    ).execute()
    return state


def consume_oauth_state(
    *,
    provider: str,
    state: str,
    external_account_id: str,
) -> dict[str, Any] | None:
    now = utc_now_iso()
    response = (
        supabase_admin.table("system_oauth_states")
        .select("*")
        .eq("provider", provider)
        .eq("state", state)
        .eq("external_account_id", external_account_id)
        .eq("status", "pending")
        .gte("expires_at", now)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None

    row = rows[0]
    supabase_admin.table("system_oauth_states").update(
        {
            "status": "consumed",
            "consumed_at": now,
        }
    ).eq("id", row["id"]).execute()
    return row


def save_connected_shopify_account(
    *,
    tg_user_id: int,
    tg_chat_id: int | None,
    shop_domain: str,
    access_token: str,
    scopes: list[str],
    token_payload: dict[str, Any],
) -> dict[str, Any]:
    user = upsert_system_user(tg_user_id=tg_user_id)
    shop = upsert_system_shop(user_id=user["id"], shop_name=shop_domain)
    connection = upsert_marketplace_connection(
        user_id=user["id"],
        shop_id=shop["id"],
        marketplace="shopify",
        external_account_id=shop_domain,
        external_account_name=shop_domain,
        access_token=access_token,
        scopes=scopes,
        provider_meta={
            key: value
            for key, value in token_payload.items()
            if key != "access_token"
        },
    )
    upsert_user_context(
        tg_user_id=tg_user_id,
        active_user_id=user["id"],
        active_shop_id=shop["id"],
        active_marketplace="shopify",
        active_connection_id=connection["id"],
    )
    return connection


def upsert_system_user(*, tg_user_id: int) -> dict[str, Any]:
    response = (
        supabase_admin.table("system_users")
        .upsert(
            {
                "tg_user_id": tg_user_id,
                "is_active": True,
                "updated_at": utc_now_iso(),
            },
            on_conflict="tg_user_id",
        )
        .execute()
    )
    return response.data[0]


def upsert_system_shop(*, user_id: int, shop_name: str) -> dict[str, Any]:
    response = (
        supabase_admin.table("system_shops")
        .upsert(
            {
                "user_id": user_id,
                "shop_name": shop_name,
                "status": "active",
                "updated_at": utc_now_iso(),
            },
            on_conflict="user_id,shop_name",
        )
        .execute()
    )
    return response.data[0]


def upsert_marketplace_connection(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
    external_account_id: str,
    external_account_name: str,
    access_token: str,
    scopes: list[str],
    provider_meta: dict[str, Any],
) -> dict[str, Any]:
    now = utc_now_iso()
    encrypted_token = encrypt_token(access_token)
    payload = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "api_token": encrypted_token,
        "external_account_id": external_account_id,
        "external_account_name": external_account_name,
        "status": "connected",
        "scopes": scopes,
        "token_type": "offline",
        "encrypted_api_token": encrypted_token,
        "token_fingerprint": token_fingerprint(access_token),
        "provider_meta": provider_meta,
        "connected_at": now,
        "updated_at": now,
    }
    response = (
        supabase_admin.table("system_marketplace_connections")
        .upsert(
            payload,
            on_conflict="user_id,marketplace,external_account_id",
        )
        .execute()
    )
    return response.data[0]


def upsert_user_context(
    *,
    tg_user_id: int,
    active_user_id: int,
    active_shop_id: int,
    active_marketplace: str,
    active_connection_id: int,
) -> None:
    supabase_admin.table("system_user_context").upsert(
        {
            "tg_user_id": tg_user_id,
            "owner_user_id": active_user_id,
            "active_user_id": active_user_id,
            "active_shop_id": active_shop_id,
            "active_marketplace": active_marketplace,
            "active_connection_id": active_connection_id,
            "updated_at": utc_now_iso(),
        },
        on_conflict="tg_user_id",
    ).execute()
