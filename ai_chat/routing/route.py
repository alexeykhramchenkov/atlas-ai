from __future__ import annotations

import re
from typing import Any

from ai_chat.routing.analysis import resolve_analysis
from ai_chat.routing.entity import resolve_entity
from ai_chat.routing.lookup_chain import resolve_lookup_chain
from ai_chat.routing.metrics import MetricMatch, resolve_metrics
from ai_chat.routing.period import resolve_period_days
from ai_chat.routing.product import resolve_product
from ai_chat.routing.validation import is_valid_analytics_question
from ai_chat.routing.llm_fallback import route_with_openai
from db.client import supabase


DEFAULT_LIMIT = 1
DEFAULT_LIST_LIMIT = 5
DEFAULT_ANSWER_SCOPE = "single"
PRODUCT_EXPLAIN_CHANGE_DEFAULT_DATASET = "orders"
PRODUCT_EXPLAIN_CHANGE_DEFAULT_METRIC = "orders_count"
PRODUCT_EXPLAIN_CHANGE_DEFAULT_ENTITY = "product"
NON_DEFAULT_METRIC_MARKERS = {
    "прибыль",
    "прибыли",
    "выручка",
    "выручки",
    "выручку",
    "просмотры",
    "просмотров",
    "просмотр",
    "profit",
    "revenue",
    "views",
}
FOLLOW_UP_SIZE_MARKERS = {
    "размер",
    "размеры",
    "размера",
    "размеров",
    "size",
    "sizes",
}
FOLLOW_UP_SALES_MARKERS = {
    "продаются",
    "продается",
    "продажи",
    "продажам",
    "selling",
    "sales",
}
PRODUCT_REFERENCE_MARKERS = {
    "он",
    "она",
    "него",
    "неё",
    "нее",
    "ему",
    "ей",
    "его",
    "её",
    "этот товар",
    "этого товара",
    "этому товару",
    "по нему",
    "по ней",
    "у него",
    "к него",
    "у неё",
    "у нее",
}
PRODUCT_DIMENSION_MARKERS = {
    "склад",
    "складе",
    "склада",
    "складах",
    "складу",
    "warehouse",
    "размер",
    "размере",
    "размера",
    "размерах",
    "size",
    "sizes",
    "регион",
    "регионе",
    "региона",
    "регионах",
    "region",
    "regions",
}
STORE_SCOPE_MARKERS = {
    "по всему магазину",
    "по всем товарам",
    "всего на складах",
    "весь магазин",
    "all products",
    "whole store",
}
OVERVIEW_SALES_MARKERS = {
    "how are my sales doing",
    "how are sales doing",
    "sales doing",
    "sales update",
    "what's happening with my sales",
    "what is happening with my sales",
    "whats happening with my sales",
    "what's up with my sales",
    "what is up with my sales",
    "whats up with my sales",
    "как продажи",
    "как продажи сегодня",
    "что с продажами",
    "что по продажам",
    "что происходит с продажами",
}
EN_TOP_SCOPE_MARKERS = {
    "top 5",
    "top products",
    "show my top 5 products",
}
DECLINING_PRODUCTS_MARKERS = {
    "which products are declining",
    "products are declining",
    "declining products",
}
EXPLAIN_CHANGE_SALES_METRIC_MARKERS = {
    "продажи",
    "продаж",
    "продажам",
}
OVERVIEW_PERIOD = "latest_complete_day"
OVERVIEW_COMPARE_TO = "previous_day"


def _route_request(
    question: str,
    memory: dict[str, Any] | None = None,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_context = request_context or {}

    text = question.lower().replace("ё", "е")
    memory = memory or {}
    from ai_chat.routing.llm_fallback import resolve_buyer_questions
    buyer_questions = resolve_buyer_questions(question, memory=memory, request_context=request_context,
        resolve_explicit=lambda q: resolve_product(question=q, supabase=supabase,
            user_id=request_context['user_id'], shop_id=request_context['shop_id'],
            marketplace=request_context.get('marketplace','wb')),
        resolve_reference=lambda q,m: resolve_product_from_memory(question=q,memory=m))
    if buyer_questions is not None:
        return buyer_questions
    from ai_chat.routing.llm_fallback import resolve_funnel_change
    funnel_change = resolve_funnel_change(question, memory=memory, request_context=request_context)
    if funnel_change is not None:
        return funnel_change
    from ai_chat.routing.llm_fallback import resolve_shown_orders
    shown_orders = resolve_shown_orders(question, memory=memory, request_context=request_context)
    if shown_orders is not None:
        return shown_orders
    chain_text = " ".join(text.strip().rstrip("?!.").split())
    period_pattern = r"(?:за (?:последни[ех] )?(?:неделю|месяц|квартал|год|\d{1,3} д(?:ня|ней)?))"
    explicit_period = bool(re.search(period_pattern, chain_text))
    chain_base = re.sub(r"\s+" + period_pattern + r"$", "", chain_text)
    weekly = chain_base in {"сколько продаж", "сколько заказов", "сколько было продаж"} and explicit_period
    best = chain_base in {"какой товар лучший", "какой товар самый лучший"}
    regions = resolve_entity(question=question, default_entity="store") == "region"
    period_followup = bool(re.fullmatch(r"а?\s*" + period_pattern, chain_text)) and memory.get("last_metric") in {"orders_count", "orders_today"}
    if weekly or best or regions or period_followup:
        entity = memory.get("last_scope") if period_followup else "store" if weekly else "region" if regions else "product"
        analysis = memory.get("last_analysis") if period_followup else "metric_value" if weekly else "best"
        days = resolve_period_days(question) if explicit_period else 7
        req = {**request_context, "is_valid_question": True, "question_type": "simple", "dataset": "orders",
               "analysis": analysis, "metric": "orders_count", "entity": entity,
               "scope": "store" if entity == "store" else "product", "period_days": days,
               "answer_scope": "top" if entity == "region" else "single", "limit": 5 if entity == "region" else 1}
        explicit_product = None
        explicit_product_requested = regions and chain_base not in {"куда чаще всего заказывают товар", "куда чаще всего заказывают этот товар", "куда чаще всего заказывают"}
        if regions and chain_base not in {"куда чаще всего заказывают товар", "куда чаще всего заказывают этот товар", "куда чаще всего заказывают"}:
            explicit_product = resolve_product(question=question, supabase=supabase,
                user_id=request_context["user_id"], shop_id=request_context["shop_id"], marketplace=request_context.get("marketplace", "wb"))
        from ai_chat.metric.seller_questions import ORDER_METRICS
        inherit_period = not best or memory.get("last_metric") in {"orders_count", *ORDER_METRICS}
        if not weekly and not explicit_period and not explicit_product and inherit_period:
            for key in ("date_from", "date_to"):
                if memory.get(key): req[key] = memory[key]
            if req.get("date_from") and req.get("date_to"):
                from datetime import date
                req["period_days"] = (date.fromisoformat(req["date_to"]) - date.fromisoformat(req["date_from"])).days + 1
        if entity == "region":
            req["product_key"] = (explicit_product or {}).get("product_key") or (None if explicit_product_requested else memory.get("last_product_key"))
            if explicit_product:
                req["product"] = explicit_product
            if not req.get("product_key"):
                return {**req, "is_valid_question": False, "error_code": "unclear_question",
                        "message": "По какому товару? Напиши название или артикул WB."}
        return req

    from ai_chat.routing.seller_questions import resolve_seller_question, BY_METRIC
    seller_request = resolve_seller_question(question, memory, request_context,
        resolve_registered=lambda q: next((m.metric for m in resolve_metrics(question=q, supabase=supabase)
            if m.metric in BY_METRIC), None),
        resolve_explicit=lambda q: resolve_product(question=q, supabase=supabase,
            user_id=request_context["user_id"], shop_id=request_context["shop_id"], marketplace=request_context.get("marketplace", "wb")),
        resolve_reference=lambda q, m: resolve_product_from_memory(question=q, memory=m))
    if seller_request is not None:
        return seller_request

    if any(marker in text for marker in ("законч", "заканч", "пополн")):
        product = resolve_product(question=question,supabase=supabase,
            user_id=request_context['user_id'],shop_id=request_context['shop_id'],
            marketplace=request_context.get('marketplace','wb'))
        if not product:
            product = resolve_product_from_memory(question=question,memory=memory)
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        end = datetime.now(ZoneInfo("Europe/Moscow")).date() - timedelta(days=1)
        days=resolve_period_days(question,default_period_days=30)
        if product:
            return {**request_context,'is_valid_question':True,'question_type':'simple',
                'dataset':'stocks','analysis':'metric_value','metric':'days_left','entity':'product',
                'scope':'product','product_key':product['product_key'],'product':product,
                'period_days':days,'date_from':(end-timedelta(days=days-1)).isoformat(),'date_to':end.isoformat()}
        return {**request_context, "is_valid_question": True, "question_type": "simple",
                "dataset": "stocks", "analysis": "rank", "metric": "days_left",
                "entity": "product", "period_days": days, "limit": 5,
                "date_from": (end-timedelta(days=days-1)).isoformat(), "date_to": end.isoformat()}

    if not is_valid_analytics_question(question):
        return route_with_openai(
            question,
            request_context=request_context,
        ) or invalid_route()

    lookup_chain = resolve_lookup_chain(
        question=question,
        supabase=supabase,
    )

    if lookup_chain:
        period_days = resolve_period_days(question)
        return {
            "is_valid_question": True,
            "question_type": "lookup_chain",
            "period_days": period_days,
            "answer_scope": DEFAULT_ANSWER_SCOPE,
            "limit": DEFAULT_LIMIT,
            "plan": lookup_chain["plan"],
            **request_context,
        }

    product = resolve_product(
        question=question,
        supabase=supabase,
        user_id=int(request_context.get("user_id") or 1),
        shop_id=int(request_context.get("shop_id") or 1),
        marketplace=request_context.get("marketplace") or "wb",
    )
    if product is None:
        product = resolve_product_from_memory(question=question, memory=memory)
    metric_matches = resolve_metrics(
        question=question,
        supabase=supabase,
    )
    analysis = resolve_analysis(question)

    if not metric_matches:
        declining_products = resolve_declining_products_request(
            question=question,
            request_context=request_context,
        )
        if declining_products:
            return declining_products

        overview = resolve_store_sales_overview(
            question=question,
            request_context=request_context,
        )
        if overview:
            return overview

        follow_up = resolve_product_size_sales_follow_up(
            question=question,
            memory=memory,
            request_context=request_context,
        )
        if follow_up:
            if product:
                follow_up.update(product_key=product["product_key"], product=product)
            return follow_up

        if analysis == "explain_change" and has_sales_metric_marker(question):
            metric_matches = [
                MetricMatch(
                    dataset="orders",
                    metric="orders_count",
                    default_entity="store",
                    matched_alias="продажи",
                    score=0,
                )
            ]
        elif (
            analysis == "explain_change"
            and product
            and not has_non_default_metric_marker(question)
        ):
            metric_matches = [
                MetricMatch(
                    dataset=PRODUCT_EXPLAIN_CHANGE_DEFAULT_DATASET,
                    metric=PRODUCT_EXPLAIN_CHANGE_DEFAULT_METRIC,
                    default_entity=PRODUCT_EXPLAIN_CHANGE_DEFAULT_ENTITY,
                    matched_alias=None,
                    score=0,
                )
            ]
        else:
            return route_with_openai(
                question,
                request_context=request_context,
            ) or invalid_route("unsupported_metric")

    primary_metric = metric_matches[0]
    entity = resolve_entity(
        question=question,
        default_entity=primary_metric.default_entity,
    )
    period_days = resolve_period_days(question)
    answer_scope, limit = resolve_answer_scope(
        question=question,
        supabase=supabase,
    )

    request = {
        "is_valid_question": True,
        "question_type": "simple",
        "dataset": primary_metric.dataset,
        "analysis": analysis,
        "metric": "orders" if analysis == "explain_change" and primary_metric.metric == "orders_count" else primary_metric.metric,
        "entity": entity,
        "period_days": period_days,
        "answer_scope": answer_scope,
        "limit": limit,
        **request_context,
    }

    if product:
        request["entity"] = entity if entity in {"variant", "warehouse", "region"} else "product"
        request["scope"] = "product"
        request["product_key"] = product["product_key"]
        request["product"] = product

    if request["dataset"] == "funnel" and request["metric"] == "funnel":
        request["analysis"] = "compare"
        request["period_days"] = resolve_period_days(question, default_period_days=7)

    if request["entity"] == "region" and request.get("answer_scope") == "single":
        request["answer_scope"] = "top"
        request["limit"] = DEFAULT_LIST_LIMIT

    if analysis == "explain_change":
        request["scope"] = entity
        if product:
            request["entity"] = "product"
            request["scope"] = "product"
            request["product_key"] = product["product_key"]
            request["product"] = product

    if len(metric_matches) > 1:
        request["metrics"] = [match.metric for match in metric_matches]

    if request.get("dataset") == "orders" and request.get("metric") == "orders_revenue":
        request["metric"] = "orders_amount"
    return request


def has_sales_metric_marker(question: str) -> bool:
    normalized_question = normalize_text(question)
    return any(
        marker in normalized_question
        for marker in EXPLAIN_CHANGE_SALES_METRIC_MARKERS
    )


def resolve_answer_scope(question: str, supabase) -> tuple[str, int]:
    normalized_question = normalize_text(question)

    if any(marker in normalized_question for marker in EN_TOP_SCOPE_MARKERS):
        return "top", 5

    rules = load_scope_rules(supabase)
    best_match = None

    for rule in rules:
        aliases = rule.get("aliases_ru") or []
        priority = int(rule.get("priority") or 100)

        for alias in aliases:
            normalized_alias = normalize_text(alias)

            if not normalized_alias:
                continue

            if normalized_alias in normalized_question:
                score = len(normalized_alias)
                candidate = {
                    "answer_scope": rule.get("answer_scope"),
                    "default_limit": rule.get("default_limit"),
                    "priority": priority,
                    "score": score,
                }

                if is_better_scope_match(candidate, best_match):
                    best_match = candidate

    if not best_match:
        return DEFAULT_ANSWER_SCOPE, DEFAULT_LIMIT

    answer_scope = best_match.get("answer_scope") or DEFAULT_ANSWER_SCOPE
    limit = int(best_match.get("default_limit") or DEFAULT_LIMIT)
    if answer_scope in {"top", "all"}:
        explicit_limit = resolve_explicit_limit(normalized_question)
        limit = explicit_limit or DEFAULT_LIST_LIMIT

    return answer_scope, limit


def resolve_explicit_limit(question: str) -> int | None:
    match = re.search(r"\b(?:топ\s*)?(\d{1,2})\b", question)
    if not match:
        return None
    return max(1, min(int(match.group(1)), 50))


def load_scope_rules(supabase) -> list[dict[str, Any]]:
    response = (
        supabase
        .table("system_ai_scope_rules")
        .select("answer_scope,default_limit,aliases_ru,priority")
        .eq("is_active", True)
        .order("priority", desc=False)
        .execute()
    )

    return response.data or []


def is_better_scope_match(candidate: dict[str, Any], current: dict[str, Any] | None) -> bool:
    if current is None:
        return True

    if candidate["score"] != current["score"]:
        return candidate["score"] > current["score"]

    return candidate["priority"] < current["priority"]


def normalize_text(value: str) -> str:
    return " ".join(str(value).lower().replace("_", " ").split())


def has_non_default_metric_marker(question: str) -> bool:
    normalized_question = normalize_text(question)
    return any(
        marker in normalized_question
        for marker in NON_DEFAULT_METRIC_MARKERS
    )


def resolve_product_from_memory(
    *, question: str, memory: dict[str, Any] | None
) -> dict[str, Any] | None:
    memory = memory or {}
    product_key = memory.get("last_product_key")
    if not product_key:
        return None

    normalized_question = normalize_text(question)
    if any(marker in normalized_question for marker in STORE_SCOPE_MARKERS):
        return None
    tokens = set(normalized_question.split())
    has_reference = any(
        marker in normalized_question if " " in marker else marker in tokens
        for marker in PRODUCT_REFERENCE_MARKERS
    )
    if not has_reference:
        return None

    return {
        **(memory.get("last_product") or {}),
        "product_key": product_key,
        "match_type": "memory",
        "matched_text": "previous_product",
    }


def resolve_product_size_sales_follow_up(
    *,
    question: str,
    memory: dict[str, Any] | None,
    request_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    memory = memory or {}
    request_context = request_context or {}
    product_key = memory.get("last_product_key")

    if not product_key or resolve_product_from_memory(question=question, memory=memory) is None:
        return None

    normalized_question = normalize_text(question)
    has_size_marker = any(
        marker in normalized_question
        for marker in FOLLOW_UP_SIZE_MARKERS
    )
    has_sales_marker = any(
        marker in normalized_question
        for marker in FOLLOW_UP_SALES_MARKERS
    )

    if not has_size_marker or not has_sales_marker:
        return None

    return {
        "is_valid_question": True,
        "question_type": "follow_up",
        "dataset": "orders",
        "analysis": "best",
        "metric": "orders",
        "entity": "variant",
        "scope": "product",
        "product_key": product_key,
        "product": memory.get("last_product") or {},
        "period_days": resolve_period_days(question),
        "answer_scope": "top",
        "limit": 5,
        **request_context,
    }


def resolve_store_sales_overview(
    *,
    question: str,
    request_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized_question = normalize_text(question)

    if not any(marker in normalized_question for marker in OVERVIEW_SALES_MARKERS):
        return None

    return {
        "is_valid_question": True,
        "question_type": "simple",
        "dataset": "store",
        "analysis": "overview",
        "scope": "store",
        "entity": "store",
        "period": OVERVIEW_PERIOD,
        "compare_to": OVERVIEW_COMPARE_TO,
        "metrics": [
            "revenue",
            "orders",
            "profit",
        ],
        "answer_scope": DEFAULT_ANSWER_SCOPE,
        "limit": DEFAULT_LIMIT,
        **(request_context or {}),
    }


def resolve_declining_products_request(
    *,
    question: str,
    request_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    normalized_question = normalize_text(question)

    if not any(marker in normalized_question for marker in DECLINING_PRODUCTS_MARKERS):
        return None

    return {
        "is_valid_question": True,
        "question_type": "simple",
        "dataset": "orders",
        "analysis": "explain_change",
        "metric": "orders",
        "entity": "product",
        "scope": "store",
        "period_days": resolve_period_days(question),
        "answer_scope": "top",
        "limit": 5,
        **(request_context or {}),
    }


def invalid_route(error_code: str = "unclear_question") -> dict[str, Any]:
    return {
        "is_valid_question": False,
        "error_code": error_code,
        "message": "Question is unclear or unsupported.",
    }


def resolve_clarification_reply(*, question, request_context, supabase, before_question_id=None):
    """Resolve one product-only reply from the existing journal; no pending store."""
    from ai_chat.memory import latest_dialogue_row
    previous = latest_dialogue_row(telegram_user_id=request_context["telegram_user_id"],
        telegram_chat_id=request_context["telegram_chat_id"], user_id=request_context["user_id"],
        shop_id=request_context["shop_id"], marketplace=request_context["marketplace"], supabase=supabase,
        before_question_id=before_question_id)
    if not previous or previous.get("status") != "invalid_question":
        return None
    pending = previous.get("router_request") or {}
    if pending.get("action") == "clarify" and previous.get("delivery_status") == "sent":
        from ai_chat.routing.llm_fallback import resume_clarification
        try:
            return resume_clarification(question, pending=pending, request_context=request_context,
                resolve_product=lambda q: resolve_product(question=q,supabase=supabase,
                    user_id=request_context['user_id'],shop_id=request_context['shop_id'],
                    marketplace=request_context['marketplace']))
        except Exception:
            return pending
    from ai_chat.routing.seller_questions import PRODUCT_REQUIRED
    if not (pending.get("error_code") == "unclear_question" and
            ((pending.get("metric") == "orders_count" and pending.get("entity") == "region")
             or pending.get("metric") in PRODUCT_REQUIRED)):
        return None
    text = normalize_text(question).strip()
    # A new question always cancels the pending clarification.
    if any(word in text.split() for word in ("сколько", "куда", "какой", "какие", "почему", "как", "что", "за", "месяц", "неделю")) or "?" in text:
        return None
    product = resolve_product(question=question, supabase=supabase, user_id=request_context["user_id"],
                              shop_id=request_context["shop_id"], marketplace=request_context["marketplace"])
    if not product:
        return None
    from ai_chat.routing.product import collect_product_aliases
    cleaned = re.sub(r"^артикул(?: wb)?\s*:?\s*", "", text)
    if cleaned not in {normalize_text(str(alias)) for alias in collect_product_aliases(product) if alias}:
        return None
    req = {**pending, **request_context, "is_valid_question": True, "product_key": product["product_key"], "product": product}
    req.pop("error_code", None)
    req.pop("message", None)
    return req


# Existing Router remains the execution planner; this is its generic intent check.

def route(question, memory=None, request_context=None):
    from ai_chat.routing.llm_fallback import clarify_request
    draft = _route_request(question, memory=memory, request_context=request_context)
    return clarify_request(question, draft=draft, memory=memory or {})
