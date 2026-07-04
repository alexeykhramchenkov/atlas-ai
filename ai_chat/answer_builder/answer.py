import json
from typing import Any

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

    return _raw_json_answer(
        question=question,
        request=request,
        result=payload,
    )


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
