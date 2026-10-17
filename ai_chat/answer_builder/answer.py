import json
from typing import Any

from core.config import settings
from ai_chat.llm_client import generate_openai_json
from ai_chat.answer_builder.explain_change import build_explain_change_answer
from ai_chat.answer_builder.fields import extract_fields
from ai_chat.answer_builder.resolver import resolve_answer_rule
from ai_chat.answer_builder.templates import apply_template


def build_answer(
    *,
    question: str | None = None,
    request: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    execution_result: dict[str, Any] | None = None,
    supabase: Any = None,
    language: str | None = None,
) -> str:
    payload = execution_result if execution_result is not None else result

    # Prefer the existing rule table for any explicitly supplied execution context.
    # No stock/order-specific formatting or calculations in this path.
    if supabase is not None and (payload is not None or (request or {}).get('is_valid_question') is False):
        rule=resolve_answer_rule(supabase=supabase,
            question_type=(request or {}).get("question_type") or "simple",
            language=language or (request or {}).get("language") or "ru",request=request or {},result=payload)
        if rule is not None:
            fields=extract_fields(data=payload or {},field_rules=rule.get("fields") or [],language=language or "ru")
            return apply_template(rule=rule,fields=fields,language=language or "ru",data=payload or {},request=request or {})

    from ai_chat.routing.seller_questions import BY_METRIC
    if request and request.get("is_valid_question") is False and request.get("error_code") == "unsupported_metric":
        rule = resolve_answer_rule(supabase=_resolve_rules_supabase(supabase), question_type="simple",
            language=language or "ru", request=request, result={})
        if rule:
            return apply_template(rule=rule,fields=[],language=language or "ru",data={},request=request)
        return "Этот расчёт пока не поддерживается."
    if request and request.get("metric") in BY_METRIC and request.get("date_from") and request.get("date_to"):
        rule = resolve_answer_rule(supabase=_resolve_rules_supabase(supabase), question_type="simple",
            language=language or request.get("language") or "ru", request=request, result=payload or {})
        if not rule:
            return "Не найдено правило оформления ответа."
        return apply_template(rule=rule, fields=[], language=language or "ru", data=payload or {}, request=request)

    if request and request.get("is_valid_question") is False and request.get("metric") == "orders_count":
        rule = resolve_answer_rule(supabase=_resolve_rules_supabase(supabase), question_type="simple",
            language=language or request.get("language") or "ru", request=request, result={})
        if not rule:
            return "Не найдено правило оформления ответа."
        return apply_template(rule=rule, fields=[], language=language or "ru", data={}, request=request)

    if (payload is not None and payload.get("metric") == "orders_count"
            and payload.get("date_from") and payload.get("date_to")):
        rule = resolve_answer_rule(supabase=_resolve_rules_supabase(supabase),
            question_type=(request or {}).get("question_type") or "simple",
            language=language or (request or {}).get("language") or "ru",
            request=request or {}, result=payload)
        if not rule:
            return "Не найдено правило оформления ответа."
        return apply_template(rule=rule, fields=[], language=language or "ru", data=payload, request=request or {})

    if payload is None:
        return _raw_json_answer(
            question=question,
            request=request,
            result=payload,
        )

    question_type = (
        (request or {}).get("question_type")
        or payload.get("question_type")
        or "simple"
    )
    answer_language = (
        language
        or (request or {}).get("language")
        or payload.get("language")
        or "ru"
    )

    if payload.get("analysis") == "explain_change":
        try:
            return build_explain_change_answer(
                question=question,
                request=request,
                result=payload,
                language=answer_language,
            )
        except Exception:
            return _raw_json_answer(
                question=question,
                request=request,
                result=payload,
            )

    if _is_product_metric_list(request=request, result=payload):
        return _build_product_metric_list(
            request=request or {},
            result=payload,
            language=answer_language,
        )

    if _is_product_warehouse_answer(request=request, result=payload):
        return _build_product_warehouse_answer(
            request=request or {},
            result=payload,
            language=answer_language,
        )

    if _is_region_ranking_answer(result=payload):
        return _build_region_ranking_answer(
            request=request or {},
            result=payload,
            language=answer_language,
        )

    rule_supabase = _resolve_rules_supabase(supabase)
    if rule_supabase is not None:
        try:
            rule = resolve_answer_rule(
                supabase=rule_supabase,
                question_type=question_type,
                language=answer_language,
                request=request or {},
                result=payload,
            )
            if rule:
                fields = extract_fields(
                    data=payload,
                    field_rules=rule.get("fields") or [],
                    language=answer_language,
                )
                return apply_template(
                    rule=rule,
                    fields=fields,
                    language=answer_language,
                    data=payload,
                    request=request or {},
                )
        except Exception:
            pass

    if _is_variant_ranking_answer(request=request, result=payload):
        try:
            return _build_variant_ranking_answer(
                request=request or {},
                result=payload,
                language=answer_language,
            )
        except Exception:
            return _raw_json_answer(
                question=question,
                request=request,
                result=payload,
            )

    if _is_overview_answer(result=payload):
        try:
            return _build_overview_answer(
                result=payload,
                language=answer_language,
            )
        except Exception:
            return _raw_json_answer(
                question=question,
                request=request,
                result=payload,
            )

    if settings.openai_api_key:
        try:
            return _build_openai_grounded_answer(
                question=question,
                request=request or {},
                result=payload,
                language=answer_language,
            )
        except Exception:
            pass

    return _raw_json_answer(question=question, request=request, result=payload)


def _build_openai_grounded_answer(
    *, question: str | None,
    request: dict[str, Any],
    result: dict[str, Any],
    language: str,
) -> str:
    facts = json.dumps(result, ensure_ascii=False, default=str)
    prompt = f"""Write a concise Telegram answer in language {language!r}.
Answer the user's analytics question using ONLY FACTS_JSON below.
Do not invent, estimate, recalculate, or add any number absent from FACTS_JSON.
If facts are insufficient, say exactly what data is missing. Do not mention JSON.
User question: {question!r}
FACTS_JSON: {facts}
"""
    response = generate_openai_json(
        prompt=prompt,
        schema_name="grounded_analytics_answer",
        schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
        },
    )
    answer = str(response.get("answer") or "").strip()
    if not answer:
        raise ValueError("OpenAI returned an empty analytics answer")
    return answer


def _raw_json_answer(
    *,
    question: str | None,
    request: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> str:
    return json.dumps(
        {
            "question": question,
            "request": request,
            "result": result,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )


def _is_product_metric_list(
    *, request: dict[str, Any] | None, result: dict[str, Any]
) -> bool:
    request = request or {}
    if (request.get("entity") or result.get("entity")) != "product":
        return False
    if not isinstance(result.get("rows"), list):
        return False
    if result.get("analysis") in {"best", "worst"}:
        return True
    return result.get("analysis") == "metric_value" and result.get("dataset") == "stocks"


def _build_product_metric_list(
    *, request: dict[str, Any], result: dict[str, Any], language: str
) -> str:
    rows = list(result.get("rows") or [])
    limit = max(1, int(request.get("limit") or 5))
    metric = result.get("metric") or request.get("metric")

    if result.get("dataset") == "stocks":
        rows.sort(key=lambda row: _safe_number(row.get("stock_qty")))

    lines = []
    for row in rows[:limit]:
        title = row.get("title") or row.get("product_name") or "Товар"
        product_key = row.get("product_key") or "—"
        value, unit = _product_metric_value(row=row, metric=metric, language=language)
        lines.append(f"{title}_{product_key} - {_format_number(value)} {unit}".rstrip())

    if lines:
        return "\n".join(lines)
    return "No data found." if language == "en" else "Данные не найдены."


def _product_metric_value(
    *, row: dict[str, Any], metric: str | None, language: str
) -> tuple[Any, str]:
    if metric in {"stock", "stock_qty", "total_stock_qty"}:
        return row.get("stock_qty", row.get("value")), "units" if language == "en" else "шт."
    if metric in {"revenue", "orders_revenue", "gross_order_value", "net_order_value"}:
        value = row.get("value")
        if value is None:
            value = row.get("orders_revenue", row.get("gross_order_value"))
        return value, "₽"
    if metric == "profit":
        return row.get("value", row.get("profit")), "₽"
    value = row.get("orders_count")
    if value is None:
        value = row.get("orders", row.get("value"))
    return value, "orders" if language == "en" else "заказов"


def _is_product_warehouse_answer(
    *, request: dict[str, Any] | None, result: dict[str, Any]
) -> bool:
    request = request or {}
    return (
        request.get("scope") == "product"
        and request.get("entity") == "warehouse"
        and result.get("entity") == "warehouse"
        and isinstance(result.get("rows"), list)
    )


def _build_product_warehouse_answer(
    *, request: dict[str, Any], result: dict[str, Any], language: str
) -> str:
    rows = result.get("rows") or []
    if not rows:
        return "No data found." if language == "en" else "Данные не найдены."

    product = request.get("product") or {}
    title = product.get("title") or "Product" if language == "en" else product.get("title") or "Товар"
    product_key = request.get("product_key") or product.get("product_key") or "—"
    top_row = rows[0]
    warehouse = str(
        top_row.get("warehouse_name")
        or top_row.get("warehouse_key")
        or "—"
    ).removeprefix("wb_").replace("_", " ").title()
    quantity = top_row.get("quantity", top_row.get("value"))
    total_stock = product.get("stock_qty")

    if language == "en":
        lines = [
            f"{title}_{product_key}",
            f"Most stock is at {warehouse} — {_format_number(quantity)} units.",
        ]
        if total_stock is not None:
            lines.append(f"Total product stock — {_format_number(total_stock)} units.")
        return "\n".join(lines)

    lines = [
        f"{title}_{product_key}",
        f"Больше всего на складе {warehouse} — {_format_number(quantity)} шт.",
    ]
    if total_stock is not None:
        lines.append(f"Всего остаток товара — {_format_number(total_stock)} шт.")
    return "\n".join(lines)


def _is_region_ranking_answer(*, result: dict[str, Any]) -> bool:
    return (
        result.get("dataset") == "orders"
        and result.get("analysis") in {"best", "worst"}
        and result.get("entity") == "region"
        and result.get("metric") in {"orders", "orders_count"}
        and isinstance(result.get("rows"), list)
    )


def _build_region_ranking_answer(
    *, request: dict[str, Any], result: dict[str, Any], language: str
) -> str:
    rows = [
        row
        for row in (result.get("rows") or [])
        if _safe_number(row.get("orders_count", row.get("value"))) > 0
    ]
    limit = max(1, int(request.get("limit") or 5))
    period_days = request.get("period_days") or result.get("period_days") or 30
    product = request.get("product") or {}
    product_key = request.get("product_key") or product.get("product_key")

    if language == "en":
        lines = []
        if product_key:
            lines.extend(
                [f"{product.get('title') or 'Product'}_{product_key}", ""]
            )
        lines.append(f"Top order regions over the last {period_days} days:")
    else:
        lines = []
        if product_key:
            lines.extend(
                [f"{product.get('title') or 'Товар'}_{product_key}", ""]
            )
        lines.append(
            f"За последние {period_days} дней больше всего заказывали в следующих регионах:"
        )

    for row in rows[:limit]:
        region = row.get("region_name") or "—"
        orders = row.get("orders_count", row.get("value"))
        unit = "orders" if language == "en" else _ru_orders_unit(orders)
        lines.append(f"{region} - {_format_number(orders)} {unit}")
    if rows:
        return "\n".join(lines)
    return "No data found." if language == "en" else "Данные не найдены."


def _ru_orders_unit(value: Any) -> str:
    number = int(abs(_safe_number(value)))
    if number % 10 == 1 and number % 100 != 11:
        return "заказ"
    if number % 10 in {2, 3, 4} and number % 100 not in {12, 13, 14}:
        return "заказа"
    return "заказов"


def _resolve_rules_supabase(supabase: Any) -> Any:
    if supabase is not None:
        return supabase

    try:
        from db.client import supabase as default_supabase
    except Exception:
        return None

    return default_supabase


def _is_overview_answer(result: dict[str, Any]) -> bool:
    return (
        result.get("dataset") == "store"
        and result.get("analysis") == "overview"
        and result.get("scope") == "store"
    )


def _build_overview_answer(*, result: dict[str, Any], language: str) -> str:
    metrics = result.get("metrics") or {}
    revenue = metrics.get("revenue") or {}
    orders = metrics.get("orders") or {}
    profit = metrics.get("profit") or {}

    latest_complete_day = result.get("latest_complete_day")
    revenue_value = _format_money(revenue.get("current"), language)
    revenue_change = _format_change(revenue.get("change_pct"))
    orders_value = _format_number(orders.get("current"))
    orders_change = _format_change(orders.get("change_pct"))
    profit_value = _format_profit(profit, language)
    summary = _build_overview_summary(
        revenue=revenue,
        orders=orders,
        profit=profit,
        language=language,
    )

    if language == "en":
        lines = [
            f"Latest sales update: {latest_complete_day}",
            "",
            "Sales:",
            "",
            f"• Revenue: {revenue_value} ({revenue_change} vs previous day)",
            f"• Orders: {orders_value} ({orders_change} vs previous day)",
            f"• Profit: {profit_value}",
            "",
            "AI Summary:",
            summary,
        ]
        return "\n".join(lines)

    lines = [
        f"Последнее обновление продаж: {latest_complete_day}",
        "",
        "Продажи:",
        "",
        f"• Выручка: {revenue_value} ({revenue_change} к предыдущему дню)",
        f"• Заказы: {orders_value} ({orders_change} к предыдущему дню)",
        f"• Прибыль: {profit_value}",
        "",
        "AI Summary:",
        summary,
    ]
    return "\n".join(lines)


def _build_overview_summary(*, revenue: dict[str, Any], orders: dict[str, Any], profit: dict[str, Any], language: str) -> str:
    revenue_direction = _change_direction(revenue.get("change_abs"), language)
    orders_direction = _change_direction(orders.get("change_abs"), language)
    latest_profit_date = profit.get("latest_profit_date")

    if language == "en":
        parts = [
            f"Revenue is {revenue_direction} versus the previous complete day.",
            f"Orders are {orders_direction}.",
        ]
        if profit.get("status") == "no_fresh_data":
            parts.append(f"Profit data is not available for this day; latest profit date is {latest_profit_date}.")
        return " ".join(parts)

    parts = [
        f"Выручка {revenue_direction} относительно предыдущего полного дня.",
        f"Заказы {orders_direction}.",
    ]
    if profit.get("status") == "no_fresh_data":
        parts.append(f"Данные по прибыли за этот день пока недоступны; последняя дата по прибыли — {latest_profit_date}.")
    return " ".join(parts)


def _format_money(value: Any, language: str) -> str:
    amount = _format_number(value)
    return f"{amount} ₽"


def _format_change(value: Any) -> str:
    if value is None:
        return "n/a"

    numeric = _safe_number(value)
    sign = "+" if numeric > 0 else ""
    return f"{sign}{_format_number(numeric)}%"


def _format_profit(profit: dict[str, Any], language: str) -> str:
    if profit.get("status") == "no_fresh_data":
        return "no fresh data" if language == "en" else "свежих данных нет"

    return _format_money(profit.get("current"), language)


def _change_direction(value: Any, language: str) -> str:
    numeric = _safe_number(value)

    if language == "en":
        if numeric > 0:
            return "higher"
        if numeric < 0:
            return "lower"
        return "flat"

    if numeric > 0:
        return "выше"
    if numeric < 0:
        return "ниже"
    return "без изменений"


def _is_variant_ranking_answer(
    *,
    request: dict[str, Any] | None,
    result: dict[str, Any],
) -> bool:
    request = request or {}

    return (
        result.get("dataset") == "orders"
        and result.get("analysis") == "best"
        and result.get("entity") == "variant"
        and request.get("scope") == "product"
        and result.get("metric") in {"orders", "orders_count"}
    )


def _build_variant_ranking_answer(
    *,
    request: dict[str, Any],
    result: dict[str, Any],
    language: str,
) -> str:
    product = request.get("product") or {}
    rows = result.get("rows") or []
    product_title = product.get("title") or "Товар"

    if language == "en":
        lines = [
            str(product_title),
            "Best-selling sizes:",
        ]
    else:
        lines = [
            str(product_title),
            "Лучшие размеры:",
        ]

    for index, row in enumerate(rows, start=1):
        size_name = row.get("size_name") or "UNKNOWN"
        orders = _format_number(row.get("orders") or row.get("orders_count") or row.get("value"))
        share_pct = _format_number(row.get("share_pct"))

        if language == "en":
            lines.append(f"{index}. {size_name} — {orders} orders ({share_pct}%)")
        else:
            lines.append(f"{index}. {size_name} — {orders} заказов ({share_pct}%)")

    out_of_stock_sizes = _sizes_out_of_stock(result)

    if out_of_stock_sizes:
        lines.append("")

        if language == "en":
            if len(out_of_stock_sizes) == 1:
                lines.append(f"Size {out_of_stock_sizes[0]} is currently out of stock.")
            else:
                lines.append(
                    "Sizes "
                    + ", ".join(out_of_stock_sizes)
                    + " are currently out of stock."
                )
        else:
            if len(out_of_stock_sizes) == 1:
                lines.append(f"Размер {out_of_stock_sizes[0]} сейчас отсутствует на складе.")
            else:
                lines.append(
                    "Размеры "
                    + ", ".join(out_of_stock_sizes)
                    + " сейчас отсутствуют на складе."
                )

    return "\n".join(lines)


def _sizes_out_of_stock(result: dict[str, Any]) -> list[str]:
    stock = (
        result.get("enriched_context", {})
        .get("stock", {})
    )
    sizes = stock.get("sizes_out_of_stock") or []

    return sorted(
        [str(size) for size in sizes if size],
        key=_natural_size_key,
    )


def _natural_size_key(value: str) -> tuple[int, str]:
    try:
        return (0, f"{int(value):08d}")
    except ValueError:
        return (1, value)


def _safe_number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _format_number(value: Any) -> str:
    numeric = _safe_number(value)

    if numeric.is_integer():
        return f"{int(numeric):,}".replace(",", " ")

    formatted = f"{numeric:,.2f}".rstrip("0").rstrip(".")
    return formatted.replace(",", " ")
