from __future__ import annotations

from typing import Any

from ai_chat.routing.analysis import resolve_analysis
from ai_chat.routing.entity import resolve_entity
from ai_chat.routing.lookup_chain import resolve_lookup_chain
from ai_chat.routing.metrics import MetricMatch, resolve_metrics
from ai_chat.routing.period import resolve_period_days
from ai_chat.routing.product import resolve_product
from ai_chat.routing.validation import is_valid_analytics_question
from db.client import supabase


DEFAULT_LIMIT = 1
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


def route(
    question: str,
    memory: dict[str, Any] | None = None,
    request_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_context = request_context or {}

    if not is_valid_analytics_question(question):
        return invalid_route()

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
            return invalid_route("unsupported_metric")

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

    if analysis == "explain_change":
        request["scope"] = entity
        if product:
            request["entity"] = "product"
            request["scope"] = "product"
            request["product_key"] = product["product_key"]
            request["product"] = product

    if len(metric_matches) > 1:
        request["metrics"] = [match.metric for match in metric_matches]

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

    return answer_scope, limit


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


def resolve_product_size_sales_follow_up(
    *,
    question: str,
    memory: dict[str, Any] | None,
    request_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    memory = memory or {}
    request_context = request_context or {}
    product_key = memory.get("last_product_key")

    if not product_key:
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
