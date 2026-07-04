from __future__ import annotations

from typing import Any


def resolve_last_product_context(
    *,
    telegram_user_id: int,
    user_id: int,
    shop_id: int,
    marketplace: str,
    supabase,
) -> dict[str, Any]:
    response = (
        supabase
        .table("system_ai_questions")
        .select("router_request,result,created_at")
        .eq("status", "success")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    for row in response.data or []:
        request = row.get("router_request") or {}

        if not _same_context(
            request=request,
            telegram_user_id=telegram_user_id,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
        ):
            continue

        product_key = request.get("product_key")
        product = request.get("product") or {}

        if product_key:
            return {
                "last_product_key": product_key,
                "last_product": product,
                "last_analysis": request.get("analysis"),
                "last_metric": request.get("metric"),
                "last_scope": request.get("scope") or request.get("entity"),
            }

    return {}


def _same_context(
    *,
    request: dict[str, Any],
    telegram_user_id: int,
    user_id: int,
    shop_id: int,
    marketplace: str,
) -> bool:
    return (
        request.get("telegram_user_id") == telegram_user_id
        and request.get("user_id") == user_id
        and request.get("shop_id") == shop_id
        and request.get("marketplace") == marketplace
    )
