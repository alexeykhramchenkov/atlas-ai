import json
from typing import Any

from ai_chat.llm_client import generate_text


def build_explain_change_answer(
    *,
    question: str | None,
    request: dict[str, Any] | None,
    result: dict[str, Any],
    language: str,
) -> str:
    data_block = _build_data_block(result=result, language=language)
    factual_summary = _build_factual_summary(
        result=result,
        request=request,
        language=language,
    )
    prompt = _build_prompt(
        question=question,
        result=result,
        factual_summary=factual_summary,
        language=language,
    )
    summary = generate_text(
        prompt=prompt,
        temperature=0.1,
        num_predict=180,
        timeout=120,
    )

    if not summary:
        raise ValueError("Empty LLM answer")

    if not _is_valid_summary(
        summary=summary,
        result=result,
        request=request,
        language=language,
    ):
        summary = _build_deterministic_summary(
            result=result,
            request=request,
            language=language,
        )

    return _compose_answer(data_block=data_block, summary=summary)


def _build_prompt(
    *,
    question: str | None,
    result: dict[str, Any],
    factual_summary: str,
    language: str,
) -> str:
    compact_result = _compact_result(result)

    if _is_product_orders_explain(result):
        return _build_product_prompt(
            question=question,
            result=result,
            factual_summary=factual_summary,
            language=language,
        )

    if language == "en":
        return f"""
You write only the AI Summary block text for a store owner.

Rules:
- use only factual_summary and JSON;
- do not invent causes;
- do not change main_cause;
- do not list metrics;
- do not repeat the deterministic Data block;
- do not use bullets, numbering, tables, or headings;
- write 1-3 short sentences;
- do not show product_key, seller_sku, marketplace_product_id, or other technical ids;
- do not write recommendations;
- do not write what to do next;
- do not mention recommended_action;
- do not mention contributors;
- LLM does not calculate metrics or perform analysis, it only explains the ready result;
- if conversion.change_pct > 0, you may say the issue is probably not at the purchase step.

User question:
{question}

Answer language:
English

Factual summary:
{factual_summary}

Structured result:
{json.dumps(compact_result, ensure_ascii=False, indent=2, default=str)}

Write only the AI Summary text. Do not include "AI Summary" heading.
""".strip()

    return f"""
Ты формируешь только текст блока AI Summary для владельца магазина.

Правила:
- используй только данные из factual_summary и JSON;
- не придумывай причины;
- не меняй main_cause;
- не перечисляй метрики списком;
- не повторяй deterministic-блок "Данные";
- не используй bullets, нумерацию, таблицы или заголовки;
- напиши 1-3 коротких предложения;
- не показывай product_key, seller_sku, marketplace_product_id или другие технические id;
- не пиши рекомендации;
- не пиши, что делать дальше;
- не упоминай recommended_action;
- не упоминай contributors;
- LLM не считает метрики и не делает анализ, только объясняет готовый result;
- если conversion.change_pct > 0, можно сказать, что проблема, скорее всего, не на этапе покупки.

Вопрос пользователя:
{question}

Язык ответа:
{language}

Factual summary:
{factual_summary}

Structured result:
{json.dumps(compact_result, ensure_ascii=False, indent=2, default=str)}

Сформируй только текст AI Summary. Не добавляй заголовок "AI Summary".
""".strip()


def _build_product_prompt(
    *,
    question: str | None,
    result: dict[str, Any],
    factual_summary: str,
    language: str,
) -> str:
    compact_result = _compact_result(result)

    if language == "en":
        return f"""
You write only the AI Summary block text for a store owner about one product.

Rules:
- use only factual_summary;
- do not invent causes for the views drop;
- do not mention content, ads, SEO, price, or competitors unless factual_summary contains them;
- do not list metrics;
- do not repeat the deterministic Data block;
- do not use bullets, numbering, tables, or headings;
- write 1-3 short sentences;
- do not show technical ids;
- do not show contributors;
- do not write recommendations;
- do not write what to do next;
- do not mention recommended_action;
- do not change main_cause;
- if conversion decreased, do NOT say the problem is not at the purchase step;
- LLM does not calculate metrics or perform analysis, it only explains the ready result.

User question:
{question}

Answer language:
English

Factual summary:
{factual_summary}

Structured result:
{json.dumps(compact_result, ensure_ascii=False, indent=2, default=str)}

Write only the AI Summary text. Do not include "AI Summary" heading.
""".strip()

    return f"""
Ты формируешь только текст блока AI Summary для владельца магазина по одному товару.

Правила:
- используй только данные из factual_summary;
- не придумывай причины падения просмотров;
- не пиши про контент, рекламу, SEO, цену или конкурентов, если этого нет в factual_summary;
- не перечисляй метрики списком;
- не повторяй deterministic-блок "Данные";
- не используй bullets, нумерацию, таблицы или заголовки;
- напиши 1-3 коротких предложения;
- не показывай technical ids;
- не показывай contributors;
- не пиши рекомендации;
- не пиши, что делать дальше;
- не упоминай recommended_action;
- не меняй main_cause;
- если conversion снизилась, НЕ пиши, что проблема не на этапе покупки;
- LLM не считает метрики и не делает анализ, только объясняет готовый result.

Вопрос пользователя:
{question}

Язык ответа:
{language}

Factual summary:
{factual_summary}

Structured result:
{json.dumps(compact_result, ensure_ascii=False, indent=2, default=str)}

Сформируй только текст AI Summary. Не добавляй заголовок "AI Summary".
""".strip()


def _build_factual_summary(
    *,
    result: dict[str, Any],
    request: dict[str, Any] | None,
    language: str,
) -> str:
    if _is_product_orders_explain(result):
        return _build_product_factual_summary(
            result=result,
            request=request,
            language=language,
        )

    if language == "en":
        return _build_store_factual_summary_en(result=result)

    return _build_store_factual_summary_ru(result=result)


def _build_store_factual_summary_ru(*, result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    cart_rate = factors.get("cart_rate") or {}
    conversion = factors.get("conversion") or {}
    stock = factors.get("stock") or {}

    lines = [
        f"Заказы снизились на {_abs_number(target.get('change_pct'))}%.",
        f"Просмотры снизились на {_abs_number(views.get('change_pct'))}%.",
        f"Cart rate изменился на {_format_change(cart_rate.get('change_pct'))}.",
        _conversion_sentence(conversion.get("change_pct")),
        f"Остатки: {_format_metric_change(stock)}.",
        f"Основная причина: {result.get('main_cause')}.",
    ]

    return "\n".join(lines)


def _build_store_factual_summary_en(*, result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    cart_rate = factors.get("cart_rate") or {}
    conversion = factors.get("conversion") or {}
    stock = factors.get("stock") or {}

    lines = [
        f"Orders decreased by {_abs_number(target.get('change_pct'))}%.",
        f"Views decreased by {_abs_number(views.get('change_pct'))}%.",
        f"Cart rate changed by {_format_change(cart_rate.get('change_pct'))}.",
        _conversion_sentence(conversion.get("change_pct"), language="en"),
        f"Stock: {_format_metric_change(stock)}.",
        f"Main cause: {result.get('main_cause')}.",
    ]

    return "\n".join(lines)


def _build_product_factual_summary(
    *,
    result: dict[str, Any],
    request: dict[str, Any] | None,
    language: str,
) -> str:
    product = _product_from_result_or_request(result=result, request=request)
    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    cart_rate = factors.get("cart_rate") or {}
    conversion = factors.get("conversion") or {}

    title = product.get("title") or "товару"

    if language == "en":
        lines = [
            f"Orders for product \"{title}\" decreased by {_abs_number(target.get('change_pct'))}%.",
            "Main cause:",
            f"views decreased by {_abs_number(views.get('change_pct'))}%.",
            "Additionally:",
            (
                f"cart rate decreased by {_abs_number(cart_rate.get('change_pct'))}%, "
                f"{_conversion_sentence(conversion.get('change_pct'), language='en').lower()}."
            ),
            "Conclusion:",
            "the main drop is tied to traffic loss.",
        ]

        if _safe_float(conversion.get("change_pct")) < 0:
            lines.append("Funnel quality also worsened, but less than views.")

        return "\n".join(lines)

    lines = [
        f"Заказы по товару \"{title}\" снизились на {_abs_number(target.get('change_pct'))}%.",
        "Главная причина:",
        f"просмотры снизились на {_abs_number(views.get('change_pct'))}%.",
        "Дополнительно:",
        (
            f"cart rate снизился на {_abs_number(cart_rate.get('change_pct'))}%, "
            f"{_conversion_sentence(conversion.get('change_pct')).lower()}."
        ),
        "Вывод:",
        "основное падение связано с потерей трафика.",
    ]

    if _safe_float(conversion.get("change_pct")) < 0:
        lines.append("Качество воронки тоже ухудшилось, но слабее, чем просмотры.")

    return "\n".join(lines)


def _build_deterministic_answer(
    *,
    result: dict[str, Any],
    request: dict[str, Any] | None,
    language: str,
) -> str:
    if _is_product_orders_explain(result):
        return _build_product_deterministic_answer(
            result=result,
            request=request,
            language=language,
        )

    if language == "en":
        return _build_store_deterministic_answer_en(result=result)

    return _build_store_deterministic_answer_ru(result=result)


def _build_store_deterministic_answer_ru(*, result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    conversion = factors.get("conversion") or {}
    contributors = ((result.get("contributors") or {}).get("rows") or [])[:3]
    conversion_text = _conversion_sentence(conversion.get("change_pct"))

    lines = [
        f"Заказы снизились на {_abs_number(target.get('change_pct'))}%.",
        "",
        "Основная причина — снижение трафика.",
        "",
    ]

    if _safe_float(conversion.get("change_pct")) > 0:
        lines.append(
            f"Просмотры снизились на {_abs_number(views.get('change_pct'))}%, "
            f"при этом {conversion_text.lower()}. "
            "Это говорит о том, что проблема находится не на этапе покупки, "
            "а на этапе привлечения посетителей в карточки товаров."
        )
    else:
        lines.append(
            f"Просмотры снизились на {_abs_number(views.get('change_pct'))}%. "
            f"{conversion_text}."
        )

    if contributors:
        lines.extend(
            [
                "",
                "Наибольший вклад в падение заказов внесли:",
                "",
            ]
        )

        for index, contributor in enumerate(contributors, start=1):
            title = contributor.get("title") or "Товар"
            change_abs = _format_signed_number(contributor.get("change_abs"))
            lines.append(f"{index}. {title} ({change_abs} заказов)")

    return "\n".join(lines)


def _build_store_deterministic_answer_en(*, result: dict[str, Any]) -> str:
    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    conversion = factors.get("conversion") or {}
    contributors = ((result.get("contributors") or {}).get("rows") or [])[:3]
    conversion_text = _conversion_sentence(conversion.get("change_pct"), language="en")

    lines = [
        f"Orders decreased by {_abs_number(target.get('change_pct'))}%.",
        "",
        "The main cause is a traffic drop.",
        "",
    ]

    if _safe_float(conversion.get("change_pct")) > 0:
        lines.append(
            f"Views decreased by {_abs_number(views.get('change_pct'))}%, "
            f"while {conversion_text.lower()}. "
            "This means the main problem is not at the purchase step, but at traffic acquisition."
        )
    else:
        lines.append(
            f"Views decreased by {_abs_number(views.get('change_pct'))}. "
            f"{conversion_text}."
        )

    if contributors:
        lines.extend(
            [
                "",
                "The largest contributors to the order drop were:",
                "",
            ]
        )

        for index, contributor in enumerate(contributors, start=1):
            title = contributor.get("title") or "Product"
            change_abs = _format_signed_number(contributor.get("change_abs"))
            lines.append(f"{index}. {title} ({change_abs} orders)")

    return "\n".join(lines)


def _build_product_deterministic_answer(
    *,
    result: dict[str, Any],
    request: dict[str, Any] | None,
    language: str,
) -> str:
    product = _product_from_result_or_request(result=result, request=request)
    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    cart_rate = factors.get("cart_rate") or {}
    conversion = factors.get("conversion") or {}

    title = product.get("title") or "товару"
    conversion_change = _safe_float(conversion.get("change_pct"))

    if language == "en":
        lines = [
            f"Orders for product \"{title}\" decreased by {_abs_number(target.get('change_pct'))}%.",
            "",
            "Main cause:",
            f"views decreased by {_abs_number(views.get('change_pct'))}%.",
            "",
            "Additionally:",
            (
                f"cart rate decreased by {_abs_number(cart_rate.get('change_pct'))}%, "
                f"{_conversion_sentence(conversion.get('change_pct'), language='en').lower()}."
            ),
            "",
            "Conclusion:",
        ]

        if conversion_change < 0:
            lines.append(
                "the main drop is tied to traffic loss. "
                "Funnel quality also worsened, but less than views."
            )
        elif conversion_change > 0:
            lines.append(
                "the main drop is tied to traffic loss. "
                "Funnel quality does not look like the main cause because conversion increased."
            )
        else:
            lines.append(
                "the main drop is tied to traffic loss. "
                "Conversion did not change."
            )

        return "\n".join(lines)

    lines = [
        f"Заказы по товару \"{title}\" снизились на {_abs_number(target.get('change_pct'))}%.",
        "",
        "Главная причина:",
        f"просмотры снизились на {_abs_number(views.get('change_pct'))}%.",
        "",
        "Дополнительно:",
        (
            f"cart rate снизился на {_abs_number(cart_rate.get('change_pct'))}%, "
            f"{_conversion_sentence(conversion.get('change_pct')).lower()}."
        ),
        "",
        "Вывод:",
    ]

    if conversion_change < 0:
        lines.append(
            "основное падение связано с потерей трафика. "
            "Качество воронки тоже ухудшилось, но слабее, чем просмотры."
        )
    elif conversion_change > 0:
        lines.append(
            "основное падение связано с потерей трафика. "
            "Качество воронки не выглядит основной причиной, потому что конверсия выросла."
        )
    else:
        lines.append(
            "основное падение связано с потерей трафика. "
            "Конверсия не изменилась."
        )

    return "\n".join(lines)


def _compose_answer(*, data_block: str, summary: str) -> str:
    return f"{data_block.strip()}\n\nAI Summary\n{summary.strip()}"


def _build_data_block(*, result: dict[str, Any], language: str) -> str:
    labels = _metric_labels(language=language)
    target = result.get("target") or {}
    factors = result.get("factors") or {}
    metrics = [
        target,
        factors.get("views") or {},
        factors.get("cart_rate") or {},
        factors.get("conversion") or {},
        factors.get("stock") or {},
    ]

    lines = ["Data" if language == "en" else "Данные"]
    for metric in metrics:
        metric_name = metric.get("metric")
        if not metric_name:
            continue

        label = labels.get(metric_name, str(metric_name))
        lines.append(f"- {label}: {_format_metric_change(metric)}")

    return "\n".join(lines)


def _metric_labels(*, language: str) -> dict[str, str]:
    if language == "en":
        return {
            "orders": "Orders",
            "orders_count": "Orders",
            "views": "Views",
            "cart_rate": "Cart rate",
            "conversion": "Conversion",
            "stock": "Stock",
        }

    return {
        "orders": "Заказы",
        "orders_count": "Заказы",
        "views": "Просмотры",
        "cart_rate": "Cart rate",
        "conversion": "Конверсия",
        "stock": "Остатки",
    }


def _format_metric_change(metric: dict[str, Any]) -> str:
    if metric.get("metric") == "stock" and metric.get("view") == "state":
        return f"{_format_number(_safe_float(metric.get('value')))} шт."

    if metric.get("view") == "compare" or metric.get("change_pct") is not None:
        return _format_change(metric.get("change_pct"))

    if metric.get("value") is not None:
        return _format_change(metric.get("value"))

    return "n/a"


def _build_deterministic_summary(
    *,
    result: dict[str, Any],
    request: dict[str, Any] | None,
    language: str,
) -> str:
    if _is_product_orders_explain(result):
        return _build_product_deterministic_summary(
            result=result,
            request=request,
            language=language,
        )

    return _build_store_deterministic_summary(result=result, language=language)


def _build_store_deterministic_summary(*, result: dict[str, Any], language: str) -> str:
    factors = result.get("factors") or {}
    views_change = _safe_float((factors.get("views") or {}).get("change_pct"))
    conversion_change = _safe_float((factors.get("conversion") or {}).get("change_pct"))
    cart_rate_change = _safe_float((factors.get("cart_rate") or {}).get("change_pct"))
    main_cause = result.get("main_cause")

    if language == "en":
        if main_cause == "views":
            if conversion_change >= 0:
                return "Orders changed mainly because traffic fell. Conversion is not the main weak point, so the issue is likely higher in the funnel."
            return "Orders changed mainly because traffic fell. Conversion also worsened, so the decline is visible both in traffic and lower in the funnel."
        if main_cause == "conversion":
            return "Orders changed mainly because conversion fell. Traffic is not the main driver, so the issue is lower in the funnel."
        if main_cause == "cart_rate":
            return "Orders changed mainly because cart rate weakened. The main issue is between product views and adding items to cart."
        return "Orders changed without one clear dominant factor. The closest signal is the combined movement of traffic and funnel quality."

    if main_cause == "views":
        if conversion_change >= 0:
            return "Заказы изменились в основном из-за падения трафика. Конверсия не выглядит главным слабым местом, поэтому проблема выше по воронке."
        return "Заказы изменились в основном из-за падения трафика. Конверсия тоже ухудшилась, поэтому снижение видно и в трафике, и ниже по воронке."
    if main_cause == "conversion":
        return "Заказы изменились в основном из-за падения конверсии. Трафик не выглядит главным фактором, поэтому проблема ниже по воронке."
    if main_cause == "cart_rate":
        return "Заказы изменились в основном из-за ухудшения cart rate. Главное проседание находится между просмотром карточки и добавлением в корзину."
    if views_change < 0 or conversion_change < 0 or cart_rate_change < 0:
        return "Заказы снизились без одного явно доминирующего фактора. Главный сигнал находится в совместном ухудшении трафика и качества воронки."
    return "Заказы изменились без явного негативного фактора. По готовым данным нет одной сильной причины просадки."


def _build_product_deterministic_summary(
    *,
    result: dict[str, Any],
    request: dict[str, Any] | None,
    language: str,
) -> str:
    factors = result.get("factors") or {}
    conversion_change = _safe_float((factors.get("conversion") or {}).get("change_pct"))
    main_cause = result.get("main_cause")

    if language == "en":
        if main_cause == "views":
            if conversion_change < 0:
                return "The product's orders changed mainly because traffic fell. Funnel quality also worsened, but traffic is the main signal."
            return "The product's orders changed mainly because traffic fell. Conversion does not look like the main cause."
        if main_cause == "conversion":
            return "The product's orders changed mainly because conversion fell. The issue is lower in the funnel, after users open the product card."
        return "The product's orders changed without one clear dominant factor in the available data."

    if main_cause == "views":
        if conversion_change < 0:
            return "Заказы по товару изменились в основном из-за падения трафика. Качество воронки тоже ухудшилось, но главный сигнал находится в просмотрах."
        return "Заказы по товару изменились в основном из-за падения трафика. Конверсия не выглядит главной причиной."
    if main_cause == "conversion":
        return "Заказы по товару изменились в основном из-за падения конверсии. Проблема находится ниже по воронке, после открытия карточки."
    return "Заказы по товару изменились без одной явно доминирующей причины в доступных данных."


def _append_current_product_state(
    *,
    answer: str,
    result: dict[str, Any],
    language: str,
) -> str:
    block = _build_current_product_state_block(
        result=result,
        language=language,
    )
    if not block:
        return answer

    return f"{answer}\n\n{block}"


def _build_current_product_state_block(
    *,
    result: dict[str, Any],
    language: str,
) -> str | None:
    if not _is_product_orders_explain(result):
        return None

    context = result.get("enriched_context") or {}
    if not context:
        return None

    price = context.get("price") or {}
    stock = context.get("stock") or {}
    reviews = context.get("reviews") or {}

    lines = [
        "Current product state:" if language == "en" else "Текущее состояние товара:"
    ]

    if price.get("price_with_discount") not in [None, ""]:
        label = "Discounted price" if language == "en" else "Цена со скидкой"
        lines.append(f"• {label}: {_format_money_rub(price.get('price_with_discount'), language=language)}")

    if price.get("discount_percent") not in [None, ""]:
        label = "Discount" if language == "en" else "Скидка"
        lines.append(f"• {label}: {_format_percent(price.get('discount_percent'))}")

    if stock.get("stock_qty") not in [None, ""]:
        label = "Stock" if language == "en" else "Остаток"
        unit = "pcs" if language == "en" else "шт."
        lines.append(f"• {label}: {_format_int_like(stock.get('stock_qty'))} {unit}")

    if (
        stock.get("sizes_in_stock_count") not in [None, ""]
        and stock.get("total_sizes_count") not in [None, ""]
    ):
        label = "Sizes in stock" if language == "en" else "Размеры в наличии"
        lines.append(
            f"• {label}: "
            f"{_format_int_like(stock.get('sizes_in_stock_count'))} "
            f"{'of' if language == 'en' else 'из'} "
            f"{_format_int_like(stock.get('total_sizes_count'))}"
        )

    sizes_in_stock = _natural_sort_sizes(stock.get("sizes_in_stock") or [])
    if sizes_in_stock:
        label = "In stock" if language == "en" else "В наличии"
        lines.append(f"• {label}: {', '.join(sizes_in_stock)}")

    sizes_out_of_stock = _natural_sort_sizes(stock.get("sizes_out_of_stock") or [])
    if sizes_out_of_stock:
        label = "Out of stock" if language == "en" else "Нет в наличии"
        lines.append(f"• {label}: {', '.join(sizes_out_of_stock)}")

    if reviews.get("rating") not in [None, ""]:
        label = "Rating" if language == "en" else "Рейтинг"
        lines.append(f"• {label}: {_format_number(_safe_float(reviews.get('rating')))}")

    if reviews.get("total_reviews_count") not in [None, ""]:
        label = "Reviews" if language == "en" else "Отзывов"
        lines.append(f"• {label}: {_format_int_like(reviews.get('total_reviews_count'))}")

    if reviews.get("positive_reviews_count") not in [None, ""]:
        label = "Positive" if language == "en" else "Положительных"
        lines.append(f"• {label}: {_format_int_like(reviews.get('positive_reviews_count'))}")

    if reviews.get("negative_reviews_count") not in [None, ""]:
        label = "Negative" if language == "en" else "Негативных"
        lines.append(f"• {label}: {_format_int_like(reviews.get('negative_reviews_count'))}")

    return "\n".join(lines) if len(lines) > 1 else None


def _is_valid_summary(
    *,
    summary: str,
    result: dict[str, Any],
    request: dict[str, Any] | None,
    language: str,
) -> bool:
    forbidden_tokens = [
        "данные",
        "data",
        "ai summary",
        "product_key",
        "seller_sku",
        "marketplace_product_id",
        "wb_",
        "contributors",
        "вкладчик",
        "вкладчиков",
        "recommended_action",
        "recommended action",
        "рекоменд",
        "что делать",
        "следующий шаг",
        "next step",
        "you should",
        "нужно ",
        "надо ",
        "следует ",
    ]

    normalized = summary.strip()
    summary_lower = normalized.lower()
    if not normalized:
        return False

    if any(token in summary_lower for token in forbidden_tokens):
        return False

    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped.startswith(("-", "•", "*")):
            return False
        if stripped[:2] in {"1.", "2.", "3.", "4.", "5."}:
            return False

    if _sentence_count(normalized) > 3:
        return False

    return True


def _sentence_count(value: str) -> int:
    count = sum(value.count(char) for char in ".!?")
    return max(count, 1)


def _is_valid_store_english_answer(*, answer: str, result: dict[str, Any]) -> bool:
    answer_lower = answer.lower()

    forbidden_tokens = [
        "product_key",
        "seller_sku",
        "marketplace_product_id",
        "wb_",
        "due to the main cause being",
    ]
    if any(token in answer_lower for token in forbidden_tokens):
        return False

    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    conversion = factors.get("conversion") or {}
    contributors = ((result.get("contributors") or {}).get("rows") or [])[:3]

    required_numbers = [
        _abs_number(target.get("change_pct")),
        _abs_number(views.get("change_pct")),
        _abs_number(conversion.get("change_pct")),
    ]
    if any(number not in answer for number in required_numbers):
        return False

    for contributor in contributors:
        change_abs = _format_signed_number(contributor.get("change_abs"))
        if change_abs not in answer:
            return False

    return True


def _is_valid_store_russian_answer(*, answer: str, result: dict[str, Any]) -> bool:
    answer_lower = answer.lower()

    forbidden_tokens = [
        "product_key",
        "seller_sku",
        "marketplace_product_id",
        "wb_",
    ]
    if any(token in answer_lower for token in forbidden_tokens):
        return False

    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    conversion = factors.get("conversion") or {}
    contributors = ((result.get("contributors") or {}).get("rows") or [])[:3]

    required_numbers = [
        _abs_number(target.get("change_pct")),
        _abs_number(views.get("change_pct")),
        _abs_number(conversion.get("change_pct")),
    ]
    if any(number not in answer for number in required_numbers):
        return False

    for contributor in contributors:
        change_abs = _format_signed_number(contributor.get("change_abs"))
        if change_abs not in answer:
            return False

    if _safe_float(conversion.get("change_pct")) > 0:
        contradiction_phrases = [
            "упала конверсия",
            "конверсия упала",
            "конверсия снизилась",
            "снизилась конверсия",
            "падение конверсии",
            "снижение конверсии",
            "ухудшилась конверсия",
        ]
        if any(phrase in answer_lower for phrase in contradiction_phrases):
            return False

    return True


def _is_valid_product_answer(*, answer: str, result: dict[str, Any]) -> bool:
    forbidden_tokens = [
        "product_key",
        "seller_sku",
        "marketplace_product_id",
        "wb_",
        "контент",
        "реклам",
        "seo",
        "конкурент",
        "рекоменд",
    ]

    answer_lower = answer.lower()
    if any(token in answer_lower for token in forbidden_tokens):
        return False

    if "contributors" in answer_lower or "вкладчик" in answer_lower:
        return False

    target = result.get("target") or {}
    factors = result.get("factors") or {}
    views = factors.get("views") or {}
    cart_rate = factors.get("cart_rate") or {}
    conversion = factors.get("conversion") or {}

    required_numbers = [
        _abs_number(target.get("change_pct")),
        _abs_number(views.get("change_pct")),
        _abs_number(cart_rate.get("change_pct")),
        _abs_number(conversion.get("change_pct")),
    ]

    if any(number not in answer for number in required_numbers):
        return False

    if _safe_float(conversion.get("change_pct")) < 0 and "не на этапе покупки" in answer_lower:
        return False

    return True


def _is_product_orders_explain(result: dict[str, Any]) -> bool:
    return (
        result.get("analysis") == "explain_change"
        and result.get("metric") == "orders"
        and result.get("scope") == "product"
    )


def _is_store_orders_explain(result: dict[str, Any]) -> bool:
    return (
        result.get("analysis") == "explain_change"
        and result.get("metric") == "orders"
        and result.get("scope") == "store"
    )


def _product_from_result_or_request(
    *,
    result: dict[str, Any],
    request: dict[str, Any] | None,
) -> dict[str, Any]:
    return result.get("product") or (request or {}).get("product") or {}


def _conversion_sentence(value: Any, language: str = "ru") -> str:
    number = _safe_float(value)

    if language == "en":
        if number > 0:
            return f"Conversion increased by {_format_number(number)}%"
        if number < 0:
            return f"Conversion decreased by {_format_number(abs(number))}%"
        return "Conversion did not change"

    if number > 0:
        return f"Конверсия выросла на {_format_number(number)}%"
    if number < 0:
        return f"Конверсия снизилась на {_format_number(abs(number))}%"
    return "Конверсия не изменилась"


def _abs_number(value: Any) -> str:
    number = _safe_float(value)
    return _format_number(abs(number))


def _format_signed_number(value: Any) -> str:
    number = _safe_float(value)
    if number == int(number):
        return str(int(number))
    return _format_number(number)


def _format_change(value: Any) -> str:
    if value is None:
        return "n/a"

    number = _safe_float(value)
    sign = "+" if number > 0 else ""
    return f"{sign}{_format_number(number)}%"


def _format_number(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_money_rub(value: Any, language: str) -> str:
    number = _safe_float(value)
    formatted = f"{int(round(number)):,}".replace(",", " ")
    if language == "en":
        formatted = f"{int(round(number)):,}"
    return f"{formatted} ₽"


def _format_percent(value: Any) -> str:
    return f"{_format_number(_safe_float(value))}%"


def _format_int_like(value: Any) -> str:
    number = _safe_float(value)
    if number == int(number):
        return str(int(number))
    return _format_number(number)


def _natural_sort_sizes(values: list[Any]) -> list[str]:
    return sorted(
        [str(value) for value in values if value not in [None, ""]],
        key=_size_sort_key,
    )


def _size_sort_key(value: str) -> tuple[int, Any]:
    try:
        return (0, int(value))
    except ValueError:
        return (1, value)


def _safe_float(value: Any) -> float:
    if value in [None, ""]:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _compact_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "analysis": result.get("analysis"),
        "metric": result.get("metric"),
        "scope": result.get("scope"),
        "status": result.get("status"),
        "target": result.get("target"),
        "main_cause": result.get("main_cause"),
        "factors": result.get("factors"),
    }
