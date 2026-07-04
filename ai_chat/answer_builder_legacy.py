import json
from typing import Any, Dict

import requests


DEFAULT_MODEL = "qwen2.5:3b"
OLLAMA_URL = "http://localhost:11434/api/generate"
# Internal product language is always English.
# Final user answer language is auto-detected from the user question.
PRODUCT_LANGUAGE = "en"
USER_LANGUAGE_MODE = "auto"  # auto / en / ru


SYSTEM_RULES = """You are an ecommerce analytics expert for Shopify-style dashboards.

Answer:
- answer in the requested answer language
- internal facts, tool outputs and business terminology are in English
- translate naturally for the user when the requested answer language is Russian
- short and practical
- based only on the provided facts
- do not invent missing data
- do not show raw JSON to the user
- do not mention internal field names such as key_sizes_missing, root_cause, current_stock_qty, stock_qty
- never output Russian text when the requested answer language is English
- do not say that you are a model or artificial intelligence

Critical interpretation rules:
- if there is no cause in the facts, do not invent one
- if this is a product ranking, list products and values only
- if this is a product card, list product metrics only
- if this is an actions list and it is empty, say that there are no real actions yet
- if the facts say "Key size problem: no", then sizes are NOT the cause
- if the facts say "Missing key sizes count: 0", then key sizes are available
- available stock by size must not be called a problem
- if the data is not enough, say so clearly
- if ads, search rankings, and impressions are not provided, say exactly: "Next: check ads performance, search ranking, and impressions data."
- do not mention social media, email, organic search, or other traffic sources unless they are provided in the facts
"""


TOOL_RESPONSE_RULES = {
    "rank_products": """Response mode: product ranking.
Strictly list products and values from the facts.
Do not add causes, recommendations, or checks about ads, traffic, stock, product cards, or search rankings.
""",
    "get_product_card": """Response mode: product card.
Strictly list only the product metrics from the facts.
Do not analyze causes, drops, recommendations, ads, traffic, stock, sizes, or search rankings.
If the user asks for one specific metric, such as profit, answer that metric and optionally add 1-2 directly related metrics.
""",
    "find_root_cause": """Response mode: root cause analysis.
Give a short conclusion with the main cause, what is not the cause, and what to check next.
Do not use technical field names.
""",
    "get_actions": """Response mode: actions for today.
If the actions list is empty or the tool is not connected, say directly that there are no real actions yet.
Do not invent actions.
""",
}


def _compact_json(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _detect_language(text: str) -> str:
    has_cyrillic = any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in text)
    return "ru" if has_cyrillic else "en"


def _resolve_language(question: str) -> str:
    if USER_LANGUAGE_MODE in {"en", "ru"}:
        return USER_LANGUAGE_MODE
    return _detect_language(question)



def _language_name(language: str) -> str:
    return "Russian" if language == "ru" else "English"


# Helper to map metric key to localized label
def _metric_label(metric: str, language: str) -> str:
    labels = {
        "ru": {
            "views": "просмотры",
            "orders": "заказы",
            "profit": "прибыль",
            "revenue": "выручка",
            "buyout_rate": "выкуп",
            "metric": "метрика",
        },
        "en": {
            "views": "views",
            "orders": "orders",
            "profit": "profit",
            "revenue": "revenue",
            "buyout_rate": "buyout rate",
            "metric": "metric",
        },
    }

    return labels.get(language, {}).get(metric, metric)


def _product_label(product: Dict[str, Any]) -> str:
    title = (
        product.get("product_name")
        or product.get("title")
        or product.get("name")
        or product.get("subject")
    )
    product_key = product.get("product_key")

    if title and product_key:
        return f"{title} ({product_key})"

    return title or product_key or "unnamed product"


# --- Helper functions for tool results and formatting ---

def _get_tool_name(execution_result: Dict[str, Any]) -> str | None:
    if execution_result.get("tool"):
        return execution_result.get("tool")

    tool_call = execution_result.get("tool_call") or {}
    return tool_call.get("tool")


def _get_tool_args(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(execution_result.get("args"), dict):
        return execution_result.get("args") or {}

    tool_call = execution_result.get("tool_call") or {}
    if isinstance(tool_call.get("args"), dict):
        return tool_call.get("args") or {}

    return {}


def _get_tool_result(execution_result: Dict[str, Any]) -> Dict[str, Any]:
    result = execution_result.get("result")
    return result if isinstance(result, dict) else {}


def _format_money(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "n/a"


def _format_number(value: Any, decimals: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "n/a"

    if decimals == 0:
        return f"{number:,.0f}"
    return f"{number:,.{decimals}f}"



def _format_metric_value(metric: str | None, value: Any) -> str:
    if value is None:
        return "n/a"

    if metric in {"revenue", "profit", "impact_money"}:
        return _format_money(value)

    if metric in {"turnover"}:
        return _format_number(value, 4)

    if metric in {"conversion", "buyout_rate"}:
        return f"{_format_number(value, 2)}%"

    return _format_number(value)


# --- Actions formatting and translation helpers ---

def _format_priority(priority: Any, language: str) -> str:
    priority_str = str(priority or "info").lower()

    if language == "ru":
        mapping = {
            "critical": "критично",
            "warning": "важно",
            "info": "инфо",
        }
        return mapping.get(priority_str, priority_str)

    return priority_str


def _translate_action_title(title: str, language: str) -> str:
    if language != "ru":
        return title

    mapping = {
        "Unlock cash from inventory": "Разморозить деньги в остатках",
        "Reduce frozen inventory": "Сократить зависшие остатки",
        "Check conversion decline": "Проверить падение конверсии",
        "Check add-to-cart decline": "Проверить падение добавлений в корзину",
        "Check buyout rate decline": "Проверить падение выкупа",
        "Check traffic decline": "Проверить падение трафика",
        "Check order decline": "Проверить падение заказов",
        "Check revenue decline": "Проверить падение выручки",
        "Check profit decline": "Проверить падение прибыли",
        "Check low stock risk": "Проверить риск низких остатков",
        "Check out-of-stock risk": "Проверить риск отсутствия товара",
        "Check ads with no orders": "Проверить рекламу без заказов",
        "Check ad efficiency": "Проверить эффективность рекламы",
        "Investigate product event": "Разобрать событие по товару",
    }
    return mapping.get(title, title)


def _translate_action_reason(reason: str, language: str) -> str:
    if language != "ru":
        return reason

    mapping = {
        "The product is selling slowly relative to inventory. Review turnover, inventory value, demand and pricing.": "Товар продается медленно относительно остатка. Проверь оборачиваемость, стоимость остатков, спрос и цену.",
        "Cash may be frozen in slow-moving inventory. Review stock levels, sales, profitability and liquidation options.": "Деньги могут быть заморожены в медленно продающихся остатках. Проверь остатки, продажи, прибыльность и варианты распродажи.",
        "The detector found a decline in conversion. Check pricing, images, reviews, size availability and competitiveness.": "Детектор нашел падение конверсии. Проверь цену, фото, отзывы, наличие размеров и конкурентность карточки.",
        "The detector found a decline in add-to-cart rate. Check offer quality, pricing, images, ratings and competitors.": "Детектор нашел падение добавлений в корзину. Проверь оффер, цену, фото, рейтинг и конкурентов.",
        "The detector found a decline in buyout rate. Check product quality, customer expectations, sizes and return reasons.": "Детектор нашел падение выкупа. Проверь качество товара, ожидания покупателей, размеры и причины возвратов.",
        "The detector found a decline in views. Check ads, search ranking, impressions and external visibility.": "Детектор нашел падение просмотров. Проверь рекламу, позиции в поиске, показы и внешнюю видимость.",
        "The detector found a decline in orders. Check traffic, conversion, stock levels and pricing.": "Детектор нашел падение заказов. Проверь трафик, конверсию, остатки и цену.",
        "The detector found a decline in revenue. Check orders, average order value, pricing and stock availability.": "Детектор нашел падение выручки. Проверь заказы, средний чек, цену и наличие товара.",
        "The detector found a decline in profit. Check fees, logistics, pricing, discounts and ad spend.": "Детектор нашел падение прибыли. Проверь комиссии, логистику, цену, скидки и рекламные расходы.",
        "There is a risk of lost sales due to low stock. Check inventory, sizes and incoming shipments.": "Есть риск потери продаж из-за низких остатков. Проверь остатки, размеры и поставки.",
        "The product may run out of stock. Check inventory and prepare replenishment.": "Товар может закончиться. Проверь остатки и подготовь пополнение.",
        "Ads may be spending budget without generating orders. Check CTR, CPC, orders and revenue.": "Реклама может тратить бюджет без заказов. Проверь CTR, CPC, заказы и выручку.",
        "There is a risk of inefficient ad spend. Review campaigns, bids and products with poor ROI.": "Есть риск неэффективных рекламных расходов. Проверь кампании, ставки и товары с низкой окупаемостью.",
        "An analytics event was triggered. Review metrics, business impact and the root cause.": "Сработало аналитическое событие. Проверь метрики, влияние на бизнес и причину.",
    }
    return mapping.get(reason, reason)


def _build_actions_direct_answer(actions: list[Dict[str, Any]], language: str) -> str:
    lines = ["Главные действия сегодня:"] if language == "ru" else ["Today's top actions:"]

    for action in actions[:5]:
        title = _translate_action_title(str(action.get("title") or "Investigate product event"), language)
        reason = _translate_action_reason(str(action.get("reason") or ""), language)
        product_key = action.get("product_key") or "store"
        priority = _format_priority(action.get("priority"), language)
        priority_score = action.get("priority_score")
        impact_money = action.get("impact_money")
        evidence = action.get("evidence") or {}
        lost_orders = evidence.get("lost_orders")

        details = [f"priority: {priority}"] if language != "ru" else [f"приоритет: {priority}"]

        if priority_score is not None:
            details.append(f"score: {priority_score}" if language != "ru" else f"оценка: {priority_score}")

        if impact_money:
            details.append(f"impact: {_format_money(impact_money)}" if language != "ru" else f"влияние: {_format_money(impact_money)}")

        if lost_orders is not None:
            details.append(f"lost orders: {lost_orders}" if language != "ru" else f"потерянные заказы: {lost_orders}")

        lines.append(
            f"{action.get('rank')}. {title} — {product_key} "
            f"({', '.join(details)}). {reason}"
        )

    return "\n".join(lines)


def _build_fact_summary(tool_name: str, tool_result: Dict[str, Any]) -> str:
    facts = []

    status = tool_result.get("status")
    if status and status != "ok":
        facts.append(f"Tool status: {status}.")
        if tool_result.get("note"):
            facts.append(f"Note: {tool_result.get('note')}")
        return "\n".join(f"- {fact}" for fact in facts)

    if tool_name == "rank_products":
        params = tool_result.get("params") or {}
        products = tool_result.get("products") or []
        metric = params.get("metric")
        metric_label = params.get("metric_label") or metric or "metric"
        secondary_metric = params.get("secondary_metric")
        secondary_metric_label = params.get("secondary_metric_label") or secondary_metric
        period_days = params.get("period_days")
        direction = params.get("direction")
        title = "top products" if direction == "desc" else "weakest products"

        secondary_text = f" and {secondary_metric_label}" if secondary_metric else ""
        facts.append(f"Requested ranking: {title} by {metric_label}{secondary_text} over the last {period_days} days.")

        if not products:
            facts.append("No products found for this request.")
        else:
            for product in products[:10]:
                primary_value = product.get("value")
                secondary_value = product.get("secondary_value")
                secondary_part = ""

                if secondary_metric:
                    secondary_part = f", {secondary_metric_label}: {_format_metric_value(secondary_metric, secondary_value)}"

                facts.append(
                    f"#{product.get('rank')}: {_product_label(product)} — "
                    f"{metric_label}: {_format_metric_value(metric, primary_value)}"
                    f"{secondary_part}, orders: {_format_metric_value('orders', product.get('orders'))}, "
                    f"stock: {_format_metric_value('stock', product.get('stock'))}."
                )

        return "\n".join(f"- {fact}" for fact in facts)

    if tool_name == "get_product_card":
        params = tool_result.get("params") or {}
        product = tool_result.get("product") or {}
        product_key = product.get("product_key") or params.get("product_key")
        product_label = _product_label({**product, "product_key": product_key})
        period_days = params.get("period_days")

        facts.append(f"Product card for {product_label} over the last {period_days} days.")
        facts.append(f"Orders: {product.get('orders')}.")
        facts.append(f"Revenue: {product.get('revenue')}.")
        facts.append(f"Profit: {product.get('profit')}.")
        facts.append(f"Views: {product.get('views')}.")
        facts.append(f"Cart rate: {product.get('cart_rate')}%.")
        facts.append(f"Buyout rate: {product.get('buyout_rate')}%.")
        facts.append(f"Stock: {product.get('stock_qty')} units.")

        return "\n".join(f"- {fact}" for fact in facts)

    if tool_name == "get_actions":
        actions = tool_result.get("actions") or []
        note = tool_result.get("note")

        if not actions:
            facts.append("The action list is empty.")
            if note:
                facts.append(f"Reason: {note}")
        else:
            facts.append(f"Actions found: {len(actions)}.")
            for action in actions[:10]:
                evidence = action.get("evidence") or {}
                impact_money = action.get("impact_money")
                impact_text = f", impact {_format_money(impact_money)}" if impact_money else ""
                lost_orders = evidence.get("lost_orders")
                lost_orders_text = f", lost orders {lost_orders}" if lost_orders is not None else ""
                facts.append(
                    f"#{action.get('rank')}: {action.get('title')} for {action.get('product_key')} "
                    f"({action.get('priority')}, score {action.get('priority_score')}{impact_text}{lost_orders_text}) — "
                    f"{action.get('reason')}"
                )

        return "\n".join(f"- {fact}" for fact in facts)

    if tool_name == "find_root_cause":
        target_metric = tool_result.get("target_metric") or {}
        root_cause = tool_result.get("root_cause") or {}
        product_card = tool_result.get("product_card") or {}
        product_label = _product_label(product_card) if product_card else None
        size_availability = tool_result.get("size_availability") or {}

        if target_metric:
            facts.append(
                f"Target metric {target_metric.get('metric')}: "
                f"{target_metric.get('previous')} → {target_metric.get('current')} "
                f"({target_metric.get('change_pct')}%)."
            )

        if root_cause:
            main_cause = root_cause.get("main_cause")
            title = root_cause.get("title") or main_cause
            confidence = root_cause.get("confidence")
            facts.append(f"Main detected cause: {title} (confidence {confidence}).")

            if main_cause == "views_drop":
                facts.append(
                    "What current analysis shows: traffic, reach, or impressions declined. "
                    "Next: check ads performance, search ranking, and impressions data."
                )
            elif root_cause.get("description"):
                facts.append(f"Cause description: {root_cause.get('description')}")

        if product_card:
            facts.append(
                f"Product card {product_label}: orders {product_card.get('orders')}, "
                f"revenue {product_card.get('revenue')}, "
                f"profit {product_card.get('profit')}, "
                f"views {product_card.get('views')}, "
                f"cart rate {product_card.get('cart_rate')}%, "
                f"stock {product_card.get('stock_qty')} units."
            )

        if size_availability:
            key_sizes_missing = size_availability.get("key_sizes_missing")
            missing_key_sizes = size_availability.get("missing_key_sizes") or []
            facts.append(f"Key size problem: {'yes' if key_sizes_missing else 'no'}.")
            facts.append(f"Missing key sizes count: {len(missing_key_sizes)}.")

            key_sizes = size_availability.get("key_sizes") or []
            if key_sizes:
                sizes_text = ", ".join(
                    f"{item.get('size_name')} — {item.get('current_stock_qty')} units"
                    for item in key_sizes
                )
                facts.append(f"Available key sizes: {sizes_text}.")

        if not facts:
            facts.append("No compact fact summary is available. Use only the tool result.")

        return "\n".join(f"- {fact}" for fact in facts)

    return "\n".join(f"- {line}" for line in _compact_json(tool_result).splitlines()[:40])


def _build_prompt(question: str, execution_result: Dict[str, Any]) -> str:
    tool_name = _get_tool_name(execution_result)
    tool_args = _get_tool_args(execution_result)
    tool_result = _get_tool_result(execution_result)
    fact_summary = _build_fact_summary(tool_name=tool_name, tool_result=tool_result)
    tool_rules = TOOL_RESPONSE_RULES.get(tool_name, "Response mode: general. Use only compact facts.")
    language = _resolve_language(question)

    return f"""{SYSTEM_RULES}

User question:
{question}

Internal product language:
English

Answer language:
{_language_name(language)}

Called tool:
{tool_name}

Rules for this tool:
{tool_rules}

Tool arguments:
{_compact_json(tool_args)}

Compact facts for the answer:
{fact_summary}

Write the final answer to the user using only the compact facts above.
The final answer must be written in {_language_name(language)}.
All internal facts are in English; translate them naturally if the final answer language is Russian.

Answer format:
Follow only the rules for the called tool above.
Do not repeat instructions, rules, or formatting notes.
Do not add generic sections if they are not needed for this tool.

Before answering, check:
1. Are you calling something a cause even though the facts say "no"?
2. If the facts say "Key size problem: no", do not mention sizes as the cause.
3. Do not use technical field names.
4. Do not write "views dropped because views dropped".
4a. Do not say "because of traffic decline". Say "current analysis shows traffic / reach / impressions declined" instead.
5. For rank_products, get_product_card, and get_actions, do not add cause analysis or recommendations.
6. Do not mention social media, email, organic search, or any traffic source unless it is explicitly present in the compact facts.
7. Internal system language is English. User-facing answer language is auto-detected from the question.
"""


def _fallback_answer(execution_result: Dict[str, Any]) -> str:
    tool_result = execution_result.get("result", {})
    return _compact_json(tool_result)


# Direct safe answer for specific root cause cases
def _safe_direct_answer(question: str, execution_result: Dict[str, Any]) -> str | None:
    language = _resolve_language(question)
    tool_name = _get_tool_name(execution_result)
    tool_result = _get_tool_result(execution_result)

    if tool_name == "get_actions":
        status = tool_result.get("status")
        actions = tool_result.get("actions") or []
        if status != "ok" or not actions:
            if language == "ru":
                return "Реальных действий пока нет: события не найдены или список действий пуст."
            return "No real actions yet: no detector events were found or the action list is empty."

        return _build_actions_direct_answer(actions=actions, language=language)

    root_cause = tool_result.get("root_cause") or {}
    target_metric = tool_result.get("target_metric") or {}
    size_availability = tool_result.get("size_availability") or {}

    metric_key = target_metric.get("metric") or "metric"
    metric = _metric_label(metric_key, language)
    previous = target_metric.get("previous")
    current = target_metric.get("current")
    change_pct = target_metric.get("change_pct")

    question_lower = question.lower()
    asks_no_orders = any(phrase in question_lower for phrase in ["no orders", "нет заказ", "заказов нет"])
    asks_drop = any(phrase in question_lower for phrase in ["drop", "dropped", "decrease", "decreased", "down", "упал", "упали", "сниз", "просел"])

    if metric_key == "profit" and change_pct is not None and float(change_pct) > 0 and asks_drop:
        if language == "ru":
            return f"Прибыль не упала. Она выросла с {previous} до {current} ({change_pct}%)."
        return f"Profit did not drop. It increased from {previous} to {current} ({change_pct}%)."

    if metric_key == "orders" and asks_no_orders and current not in {None, 0, 0.0}:
        if language == "ru":
            return f"Заказы не отсутствуют. Они снизились с {previous} до {current} ({change_pct}%)."
        return f"There are still orders. Orders decreased from {previous} to {current} ({change_pct}%)."

    if root_cause.get("main_cause") != "views_drop":
        return None

    if language == "ru":
        lines = [
            f"Что произошло: {metric} изменились с {previous} до {current} ({change_pct}%).",
            "Текущий анализ показывает снижение трафика, охвата или показов.",
        ]

        if size_availability and size_availability.get("key_sizes_missing") is False:
            lines.append("Что не является причиной: ключевые размеры доступны.")

        lines.append("Дальше: проверь эффективность рекламы, позиции в поиске и данные по показам.")
        return "\n".join(lines)

    lines = [
        f"What happened: {metric} changed from {previous} to {current} ({change_pct}%).",
        "Current analysis shows a decline in traffic, reach, or impressions.",
    ]

    if size_availability and size_availability.get("key_sizes_missing") is False:
        lines.append("What is not the cause: key sizes are available.")

    lines.append("Next: check ads performance, search ranking, and impressions data.")
    return "\n".join(lines)


def build_answer(
    question: str,
    execution_result: Dict[str, Any],
    model: str = DEFAULT_MODEL,
) -> str:
    prompt = _build_prompt(question=question, execution_result=execution_result)

    safe_answer = _safe_direct_answer(question=question, execution_result=execution_result)
    if safe_answer:
        return safe_answer

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,
                "num_predict": 350,
                },
            },
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        answer = (data.get("response") or "").strip()

        if not answer:
            return _fallback_answer(execution_result)

        return answer

    except Exception as exc:
        fallback = _fallback_answer(execution_result)
        language = _resolve_language(question)
        if language == "ru":
            return f"Не удалось получить ответ от Ollama: {exc}\n\nДанные инструмента:\n{fallback}"
        return f"Could not get an answer from Ollama: {exc}\n\nTool data:\n{fallback}"


if __name__ == "__main__":
    sample_execution_result = {
        "tool_call": {
            "tool": "find_root_cause",
            "args": {
                "metric": "views",
                "product_key": "wb_236370462",
                "period_days": 14,
            },
        },
        "result": {
            "status": "ok",
            "target_metric": {
                "metric": "views",
                "previous": 1212,
                "current": 464,
                "change_pct": -61.72,
            },
            "root_cause": {
                "main_cause": "views_drop",
                "title": "Views drop",
                "confidence": 0.87,
                "description": "At the current analysis level, traffic / reach / impressions declined.",
            },
            "size_availability": {
                "key_sizes_missing": False,
                "missing_key_sizes": [],
                "missing_orders_share_pct": 0.0,
                "key_sizes": [
                    {"size_name": "90", "current_stock_qty": 16},
                    {"size_name": "100", "current_stock_qty": 51},
                    {"size_name": "110", "current_stock_qty": 21},
                    {"size_name": "120", "current_stock_qty": 21},
                ],
            },
        },
    }

    print(
        build_answer(
            question="Why did views drop for product wb_236370462?",
            execution_result=sample_execution_result,
        )
    )
