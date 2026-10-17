from __future__ import annotations

from typing import Any


def resolve_last_product_context(
    *,
    telegram_user_id: int,
    user_id: int,
    shop_id: int,
    marketplace: str,
    supabase,
    telegram_chat_id: int | None = None,
    before_question_id: int | None = None,
) -> dict[str, Any]:
    row = latest_dialogue_row(
        telegram_user_id=telegram_user_id, telegram_chat_id=telegram_chat_id,
        user_id=user_id, shop_id=shop_id, marketplace=marketplace, supabase=supabase,
        before_question_id=before_question_id,
    )
    if not row or row.get("status") != "success" or row.get("delivery_status", "sent") != "sent":
        return {}
    request = row.get("router_request") or {}
    result = row.get("result") or {}
    if result.get("status", "ok") != "ok":
        return {}
    single = _single_product_from_result(request=request, result=result)
    product = single or result.get("product") or request.get("product") or {}
    product_key = product.get("product_key") or request.get("product_key")
    memory = {
        "shown_product_keys": list(dict.fromkeys(r["product_key"] for r in result.get("rows", []) if r.get("product_key"))) if request.get("entity") in {"product","variant","product_warehouse","variant_warehouse"} or (request.get("dataset") == "stocks" and request.get("metric") == "stock_qty") or request.get("view") == "contributors" else [],
        "product_keys": request.get("product_keys"),
        "last_product_key": product_key, "last_product": product,
        "last_analysis": request.get("analysis"), "last_metric": request.get("metric"),
        "last_scope": (request.get("scope") or request.get("entity")) if request.get("dataset") == "orders" and request.get("metric") == "orders_amount" else (request.get("entity") or request.get("scope")),
        "last_dataset": request.get("dataset"),
        "last_direction": request.get("direction"),
        "last_view": request.get("view"),
    }
    if result.get("date_from") and result.get("date_to"):
        memory.update(date_from=result.get("date_from"), date_to=result.get("date_to"))
    return memory


def latest_dialogue_row(*, telegram_user_id, telegram_chat_id, user_id, shop_id,
                        marketplace, supabase, before_question_id=None):
    """The immediately previous turn is the only context, including failed turns."""
    from datetime import datetime, timezone, timedelta
    query = (supabase.table("system_ai_questions")
             .select("id,user_question,router_request,result,status,delivery_status,created_at")
             .eq("router_request->>telegram_user_id", str(telegram_user_id)))
    if telegram_chat_id is not None:
        query = query.eq("router_request->>telegram_chat_id", str(telegram_chat_id))
    if before_question_id is not None:
        query = query.lt("id", before_question_id)
    rows = query.order("created_at", desc=True).order("id", desc=True).limit(1).execute().data or []
    if not rows:
        return None
    row = rows[0]
    request = row.get("router_request") or {}
    if not _same_context(request=request, telegram_user_id=telegram_user_id,
                         user_id=user_id, shop_id=shop_id, marketplace=marketplace):
        return None
    if telegram_chat_id is not None and request.get("telegram_chat_id") != telegram_chat_id:
        return None
    try:
        created = datetime.fromisoformat(str(row["created_at"]).replace("Z", "+00:00"))
        if created.tzinfo is None:
            return None
        age = datetime.now(timezone.utc) - created
        if not timedelta(0) <= age <= timedelta(minutes=10):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return row


def _single_product_from_result(
    *, request: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    if (request.get("entity") or request.get("scope")) != "product":
        return {}
    if request.get("answer_scope") != "single" and int(request.get("limit") or 0) != 1:
        return {}

    rows = result.get("rows") or []
    if len(rows) != 1 or not isinstance(rows[0], dict):
        return {}
    return rows[0] if rows[0].get("product_key") else {}


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
