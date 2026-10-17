from zoneinfo import ZoneInfo
from datetime import date, datetime, timedelta
from typing import Any

from ai_chat.enrichers.product import enrich_products
from ai_chat.internal_tools.get_funnel import get_funnel
from ai_chat.internal_tools.get_orders import get_orders
from ai_chat.internal_tools.get_stocks import get_stocks
from ai_chat.timing import timing


SUPPORTED_FUNNEL_COMPARE_METRICS = {
    "views",
    "cart_rate",
    "conversion",
}
DEFAULT_PERIOD_DAYS = 30
PRODUCT_CONTEXT_REVIEWS_LIMIT = 30


def compare_metric(
    *,
    metric: str,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = DEFAULT_PERIOD_DAYS,
    product_key: str | None = None,
) -> dict:
    with timing(
        "metric_adapter",
        operation=f"{metric}.compare",
        product_key=product_key,
    ):
        return _compare_metric(
            metric=metric,
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            period_days=period_days,
            product_key=product_key,
        )


def _compare_metric(
    *,
    metric: str,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = DEFAULT_PERIOD_DAYS,
    product_key: str | None = None,
) -> dict:
    if metric == "orders":
        return _compare_orders(
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            period_days=period_days,
            product_key=product_key,
        )

    if metric not in SUPPORTED_FUNNEL_COMPARE_METRICS:
        raise ValueError(f"Unsupported compare metric: {metric}")

    return _compare_funnel_metrics(
        metrics=[metric],
        supabase=supabase,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        period_days=period_days,
        product_key=product_key,
    )[metric]


def compare_funnel_metrics(
    *,
    metrics: list[str],
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = DEFAULT_PERIOD_DAYS,
    product_key: str | None = None,
) -> dict:
    with timing(
        "metric_adapter",
        operation="funnel.compare",
        metrics=",".join(metrics),
        product_key=product_key,
    ):
        return _compare_funnel_metrics(
            metrics=metrics,
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            period_days=period_days,
            product_key=product_key,
        )


def _compare_funnel_metrics(
    *,
    metrics: list[str],
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = DEFAULT_PERIOD_DAYS,
    product_key: str | None = None,
) -> dict:
    unsupported_metrics = [
        metric for metric in metrics if metric not in SUPPORTED_FUNNEL_COMPARE_METRICS
    ]
    if unsupported_metrics:
        raise ValueError(f"Unsupported funnel compare metrics: {unsupported_metrics}")

    period_days = _safe_period_days(period_days)
    latest_date = datetime.now(ZoneInfo("Europe/Moscow")).date() - timedelta(days=1)
    current_from = latest_date - timedelta(days=period_days - 1)
    previous_to = current_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=period_days - 1)
    common=dict(supabase=supabase,user_id=user_id,shop_id=shop_id,
                marketplace=marketplace,product_key=product_key)
    current_rows=get_funnel(**common,start_date=current_from.isoformat(),end_date=latest_date.isoformat())["products"]
    previous_rows=get_funnel(**common,start_date=previous_from.isoformat(),end_date=previous_to.isoformat())["products"]

    return {
        metric: _build_compare_result(
            metric=metric,
            current=_calculate_metric(metric=metric, rows=current_rows),
            previous=_calculate_metric(metric=metric, rows=previous_rows),
            period_days=period_days,
            current_from=current_from,
            current_to=latest_date,
            previous_from=previous_from,
            previous_to=previous_to,
            source_tool="get_funnel",
            current_rows_count=len(current_rows),
            previous_rows_count=len(previous_rows),
        )
        for metric in metrics
    }


def _build_compare_result(
    *,
    metric: str,
    current: float,
    previous: float,
    period_days: int,
    current_from: date,
    current_to: date,
    previous_from: date,
    previous_to: date,
    source_tool: str,
    current_rows_count: int,
    previous_rows_count: int,
) -> dict:
    return {
        "metric": metric,
        "view": "compare",
        "current": round(current, 2),
        "previous": round(previous, 2),
        "change_abs": round(current - previous, 2),
        "change_pct": _change_pct(current=current, previous=previous),
        "period_days": period_days,
        "current_period": {
            "date_from": current_from.isoformat(),
            "date_to": current_to.isoformat(),
        },
        "previous_period": {
            "date_from": previous_from.isoformat(),
            "date_to": previous_to.isoformat(),
        },
        "meta": {
            "source_tool": source_tool,
            "current_rows_count": current_rows_count,
            "previous_rows_count": previous_rows_count,
        },
    }


def _compare_orders(
    *,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str,
    period_days: int,
    product_key: str | None,
) -> dict:
    period_days = _safe_period_days(period_days)
    current_data = get_orders(user_id=user_id,shop_id=shop_id,marketplace=marketplace,
                              product_key=product_key,period_days=period_days,supabase=supabase)
    latest_date = date.fromisoformat(current_data["end_date"])
    current_from = latest_date - timedelta(days=period_days - 1)
    previous_to = current_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=period_days - 1)

    current_rows = current_data["products"]
    previous_data = get_orders(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        product_key=product_key,
        supabase=supabase,
        start_date=previous_from.isoformat(),
        end_date=previous_to.isoformat(),
    )
    previous_rows = previous_data["products"]

    current = current_data["orders_count"]
    previous = previous_data["orders_count"]

    return {
        "metric": "orders",
        "view": "compare",
        "current": round(current, 2),
        "previous": round(previous, 2),
        "change_abs": round(current - previous, 2),
        "change_pct": _change_pct(current=current, previous=previous),
        "period_days": period_days,
        "current_period": {
            "date_from": current_from.isoformat(),
            "date_to": latest_date.isoformat(),
        },
        "previous_period": {
            "date_from": previous_from.isoformat(),
            "date_to": previous_to.isoformat(),
        },
        "meta": {
            "source_tool": "get_orders",
            "current_rows_count": len(current_rows),
            "previous_rows_count": len(previous_rows),
        },
    }


def get_metric_state(
    *,
    metric: str,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    product_key: str | None = None,
) -> dict:
    with timing(
        "metric_adapter",
        operation=f"{metric}.state",
        product_key=product_key,
    ):
        return _get_metric_state(
            metric=metric,
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            product_key=product_key,
        )


def _get_metric_state(
    *,
    metric: str,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    product_key: str | None = None,
) -> dict:
    if metric != "stock":
        raise ValueError(f"Unsupported state metric: {metric}")

    facts = get_stocks(
        supabase=supabase,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        product_key=product_key,
        level="product",
    )
    rows=facts["products"]
    value=facts["total_quantity"]

    return {
        "metric": metric,
        "view": "state",
        "value": round(value, 2),
        "status": _stock_status(value=value, rows=rows),
        "meta": {
            "source_tool": "get_stocks",
            "snapshot_date": facts["as_of"],
            "rows_count": len(rows),
        },
    }


def find_contributors(
    *,
    metric: str,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = DEFAULT_PERIOD_DAYS,
    scope: str = "product",
    direction: str = "negative",
    limit: int = 3,
) -> dict:
    with timing(
        "metric_adapter",
        operation="find_contributors",
        metric=metric,
        scope=scope,
        direction=direction,
        limit=limit,
    ):
        return _find_contributors(
            metric=metric,
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            period_days=period_days,
            scope=scope,
            direction=direction,
            limit=limit,
        )


def _find_contributors(
    *,
    metric: str,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = DEFAULT_PERIOD_DAYS,
    scope: str = "product",
    direction: str = "negative",
    limit: int = 3,
) -> dict:
    if metric != "orders":
        raise ValueError(f"Unsupported contributors metric: {metric}")

    if scope != "product":
        raise ValueError(f"Unsupported contributors scope: {scope}")

    period_days = _safe_period_days(period_days)
    current_data = get_orders(user_id=user_id,shop_id=shop_id,marketplace=marketplace,
                              product_key=product_key,period_days=period_days,supabase=supabase)
    latest_date = date.fromisoformat(current_data["end_date"])
    current_from = latest_date - timedelta(days=period_days - 1)
    previous_to = current_from - timedelta(days=1)
    previous_from = previous_to - timedelta(days=period_days - 1)

    current_rows = current_data["products"]
    previous_data = get_orders(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        supabase=supabase,
        start_date=previous_from.isoformat(),
        end_date=previous_to.isoformat(),
    )
    previous_rows = previous_data["products"]


    current_by_key = {row["product_key"]: row for row in current_rows if row.get("product_key")}
    previous_by_key = {row["product_key"]: row for row in previous_rows if row.get("product_key")}
    rows = []

    for product_key in sorted(set(current_by_key) | set(previous_by_key)):
        current = _safe_float((current_by_key.get(product_key) or {}).get("orders_count"))
        previous = _safe_float((previous_by_key.get(product_key) or {}).get("orders_count"))
        change_abs = current - previous

        rows.append(
            {
                "product_key": product_key,
                "current": round(current, 2),
                "previous": round(previous, 2),
                "change_abs": round(change_abs, 2),
                "change_pct": _change_pct(current=current, previous=previous),
            }
        )

    reverse = direction != "negative"
    rows = sorted(rows, key=lambda row: row["change_abs"], reverse=reverse)
    rows = enrich_products(rows=rows[:limit],supabase=supabase,user_id=user_id,shop_id=shop_id,marketplace=marketplace)

    return {
        "metric": metric,
        "view": "contributors",
        "scope": scope,
        "direction": direction,
        "rows": rows,
        "period_days": period_days,
        "current_period": {
            "date_from": current_from.isoformat(),
            "date_to": latest_date.isoformat(),
        },
        "previous_period": {
            "date_from": previous_from.isoformat(),
            "date_to": previous_to.isoformat(),
        },
        "meta": {
            "source_tool": "get_orders",
            "current_rows_count": len(current_rows),
            "previous_rows_count": len(previous_rows),
            "rows_count": len(rows),
        },
    }


def get_product_context(
    *,
    supabase,
    product_key: str,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
) -> dict:
    with timing(
        "metric_adapter",
        operation="product.context",
        product_key=product_key,
    ):
        return {
            "price": _get_product_price_context(
                supabase=supabase,
                product_key=product_key,
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
            ),
            "stock": _get_product_stock_context(
                supabase=supabase,
                product_key=product_key,
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
            ),
            "reviews": _get_product_reviews_context(
                supabase=supabase,
                product_key=product_key,
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
            ),
        }


def _get_product_price_context(
    *,
    supabase,
    product_key: str,
    user_id: int,
    shop_id: int,
    marketplace: str,
) -> dict:
    from ai_chat.internal_tools.get_prices import get_prices
    from ai_chat.internal_tools._common import DataUnavailableError
    try:
        rows=get_prices(user_id,shop_id,marketplace,product_key=product_key,supabase=supabase)['prices']
    except DataUnavailableError:
        rows=[]
    def one(field):
        values={r.get(field) for r in rows}
        return next(iter(values)) if len(values)==1 else None
    return {'price_with_discount':one('final_price'),'base_price':one('base_price'),'discount_percent':one('discount_percent')}


def _get_product_stock_context(
    *,
    supabase,
    product_key: str,
    user_id: int,
    shop_id: int,
    marketplace: str,
) -> dict:
    product_rows = get_stocks(
        supabase=supabase,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        product_key=product_key,
        level="product",
    )
    variant_rows = get_stocks(
        supabase=supabase,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        product_key=product_key,
        level="variant",
    )
    product_row=next(iter(product_rows["products"]),{})
    size_state=_build_size_stock_state(variant_rows["products"])

    return {
        "stock_qty": _nullable_float(product_row.get("total_quantity")),
        "stock_qty_full": _nullable_float(product_row.get("total_quantity")),
        "sizes_in_stock_count": len(size_state["sizes_in_stock"]),
        "total_sizes_count": len(size_state["all_sizes"]),
        "sizes_in_stock": size_state["sizes_in_stock"],
        "sizes_out_of_stock": size_state["sizes_out_of_stock"],
    }


def _get_product_reviews_context(
    *,
    supabase,
    product_key: str,
    user_id: int,
    shop_id: int,
    marketplace: str,
) -> dict:
    from ai_chat.internal_tools.get_reviews import get_reviews
    from ai_chat.internal_tools._common import DataUnavailableError
    try:
        feedback_rows=get_reviews(user_id,shop_id,marketplace,product_key=product_key,period_days=30,supabase=supabase)['reviews']
    except DataUnavailableError:
        return {'rating':None,'total_reviews_count':None,'positive_reviews_count':None,
                'negative_reviews_count':None,'negative_review_snippets':[],'positive_review_snippets':[]}

    return {
        "rating": _average_rating(feedback_rows),
        "total_reviews_count": len(feedback_rows),
        "positive_reviews_count": _count_reviews_by_rating(
            feedback_rows,
            min_rating=4,
            max_rating=5,
        ),
        "negative_reviews_count": _count_reviews_by_rating(
            feedback_rows,
            min_rating=1,
            max_rating=3,
        ),
        "negative_review_snippets": _extract_review_snippets(
            feedback_rows,
            sentiment="negative",
        ),
        "positive_review_snippets": _extract_review_snippets(
            feedback_rows,
            sentiment="positive",
        ),
    }


def _average_rating(rows: list[dict]) -> float | None:
    ratings = [
        _safe_float(row.get("rating"))
        for row in rows
        if row.get("rating") not in [None, ""]
    ]

    if not ratings:
        return None

    return round(sum(ratings) / len(ratings), 2)


def _count_reviews_by_rating(
    rows: list[dict],
    *,
    min_rating: int,
    max_rating: int,
) -> int:
    count = 0

    for row in rows:
        if row.get("rating") in [None, ""]:
            continue

        rating = _safe_float(row.get("rating"))
        if min_rating <= rating <= max_rating:
            count += 1

    return count


def _build_size_stock_state(rows: list[dict]) -> dict:
    by_size: dict[str, dict] = {}

    for row in rows:
        size_name = row.get("size_name")
        if not size_name:
            continue

        size = by_size.setdefault(
            str(size_name),
            {
                "size_name": str(size_name),
                "stock_qty": 0.0,
                "stock_qty_full": 0.0,
            },
        )
        size["stock_qty"] += _safe_float(row.get("total_quantity"))
        size["stock_qty_full"] += _safe_float(row.get("total_quantity"))

    all_sizes = sorted(by_size)
    sizes_in_stock = sorted(
        size_name
        for size_name, size in by_size.items()
        if size["stock_qty"] > 0
    )
    sizes_out_of_stock = sorted(set(all_sizes) - set(sizes_in_stock))

    return {
        "all_sizes": all_sizes,
        "sizes_in_stock": sizes_in_stock,
        "sizes_out_of_stock": sizes_out_of_stock,
    }


def _extract_review_snippets(rows: list[dict], sentiment: str) -> list[str]:
    snippets: list[str] = []

    for row in rows:
        rating = _safe_float(row.get("rating"))
        if sentiment == "positive" and rating < 4:
            continue
        if sentiment == "negative" and rating > 3:
            continue

        if sentiment == "positive":
            snippets.extend(_split_review_text(row.get("pros")))
            snippets.extend(_review_tags(row))
        else:
            snippets.extend(_split_review_text(row.get("cons")))
            snippets.extend(_split_review_text(row.get("text")))

    return _unique_non_empty(snippets)[:5]


def _review_tags(row: dict) -> list[str]:
    tags = row.get("tags") or []
    if not isinstance(tags, list):
        return []

    return [str(tag) for tag in tags if tag]


def _split_review_text(value: Any) -> list[str]:
    if not value:
        return []

    return [
        item.strip()
        for item in str(value).replace("\n", ".").split(".")
        if item.strip()
    ]


def _unique_non_empty(values: list[str]) -> list[str]:
    result = []
    seen = set()

    for value in values:
        normalized = " ".join(str(value).split())
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        result.append(normalized)

    return result


def _calculate_metric(metric: str, rows: list[dict]) -> float:
    if metric == "views":
        return sum(_safe_float(row.get("open_count")) for row in rows)

    if metric == "cart_rate":
        views = sum(_safe_float(row.get("open_count")) for row in rows)
        carts = sum(_safe_float(row.get("cart_count")) for row in rows)
        return (carts / views) * 100 if views else 0.0

    if metric == "conversion":
        carts = sum(_safe_float(row.get("cart_count")) for row in rows)
        orders = sum(_safe_float(row.get("order_count")) for row in rows)
        return (orders / carts) * 100 if carts else 0.0

    raise ValueError(f"Unsupported funnel metric: {metric}")


def _filter_period(rows: list[dict], date_from: date, date_to: date) -> list[dict]:
    result = []

    for row in rows:
        snapshot_date = _parse_date(row.get("snapshot_date"))
        if snapshot_date is None:
            continue
        if date_from <= snapshot_date <= date_to:
            result.append(row)

    return result


def _latest_date(rows: list[dict]) -> date | None:
    dates = [
        parsed_date
        for parsed_date in (_parse_date(row.get("snapshot_date")) for row in rows)
        if parsed_date is not None
    ]

    return max(dates) if dates else None


def _empty_compare(metric: str, period_days: int) -> dict:
    return {
        "metric": metric,
        "view": "compare",
        "current": 0.0,
        "previous": 0.0,
        "change_abs": 0.0,
        "change_pct": None,
        "period_days": period_days,
        "meta": {
            "source_tool": "get_funnel",
            "current_rows_count": 0,
            "previous_rows_count": 0,
        },
    }


def _stock_status(value: float, rows: list[dict]) -> str:
    if not rows:
        return "unknown"

    if value <= 0:
        return "low"

    return "ok"


def _latest_snapshot_value(rows: list[dict]) -> Any:
    dates = [row.get("snapshot_date") for row in rows if row.get("snapshot_date")]
    return max(dates) if dates else None


def _change_pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return None

    return round(((current - previous) / previous) * 100, 2)


def _safe_period_days(value: Any) -> int:
    try:
        period_days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PERIOD_DAYS

    if period_days <= 0:
        return DEFAULT_PERIOD_DAYS

    return period_days


def _safe_float(value: Any) -> float:
    if value in [None, ""]:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _nullable_float(value: Any) -> float | None:
    if value in [None, ""]:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if value in [None, ""]:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    return datetime.fromisoformat(str(value)).date()
