from datetime import date, timedelta
from typing import Any


DEFAULT_PERIOD_DAYS = 30


DEFAULT_METRICS = ["orders_count", "orders_revenue"]
METRIC_ALIASES = {
    "orders": "orders_count",
    "revenue": "orders_revenue",
    "order_revenue": "orders_revenue",
    "aov": "average_order_value",
}


def metric_value(request: dict, supabase, config: dict) -> dict:
    """
    Orders metric expert: metric_value.

    Supported entities:
    - store: total orders for the store
    - product: total orders for one product
    """
    entity = request.get("entity", "store")

    if entity == "store":
        return _store_orders_value(
            request=request,
            supabase=supabase,
            config=config,
        )

    if entity == "product":
        return _product_orders_value(
            request=request,
            supabase=supabase,
            config=config,
        )

    raise ValueError(f"Unsupported entity for orders.metric_value: {entity}")


def _store_orders_value(request: dict, supabase, config: dict) -> dict:
    rows = _fetch_rows(
        request=request,
        supabase=supabase,
        config=config,
    )

    totals = _calculate_totals(rows=rows, config=config)
    requested_metrics = _requested_metrics(request)

    result = {
        "dataset": "orders",
        "analysis": "metric_value",
        "entity": "store",
        "period_days": request.get("period_days", DEFAULT_PERIOD_DAYS),
    }

    result.update(_pick_metrics(totals, requested_metrics))

    return result


def _product_orders_value(request: dict, supabase, config: dict) -> dict:
    product_key = request.get("product_key")

    if not product_key:
        raise ValueError("product_key is required for product orders metric_value")

    rows = _fetch_rows(
        request=request,
        supabase=supabase,
        config=config,
        product_key=product_key,
    )

    totals = _calculate_totals(rows=rows, config=config)
    requested_metrics = _requested_metrics(request)

    result = {
        "dataset": "orders",
        "analysis": "metric_value",
        "entity": "product",
        "product_key": product_key,
        "period_days": request.get("period_days", DEFAULT_PERIOD_DAYS),
    }

    result.update(_pick_metrics(totals, requested_metrics))

    return result


def _fetch_rows(
    request: dict,
    supabase,
    config: dict,
    product_key: str | None = None,
) -> list[dict]:
    table = config["table"]
    date_field = config.get("date_field", "snapshot_date")
    select_fields = config.get("select", "*")
    period_days = int(request.get("period_days", DEFAULT_PERIOD_DAYS))
    date_from = _date_from(period_days)
    max_rows = int(config.get("limit", 10000))
    page_size = int(config.get("page_size", 1000))

    rows: list[dict] = []
    start = 0

    while start < max_rows:
        end = min(start + page_size - 1, max_rows - 1)

        query = (
            supabase
            .table(table)
            .select(select_fields)
            .eq("user_id", request["user_id"])
            .eq("shop_id", request["shop_id"])
            .eq("marketplace", request.get("marketplace", "wb"))
            .gte(date_field, date_from)
            .order(date_field, desc=True)
            .range(start, end)
        )

        if product_key:
            query = query.eq("product_key", product_key)

        response = query.execute()
        page_rows = response.data or []
        rows.extend(page_rows)

        if len(page_rows) < page_size:
            break

        start += page_size

    return rows


def _requested_metrics(request: dict) -> list[str]:
    metrics = request.get("metrics")

    if not metrics:
        metric = request.get("metric")
        metrics = [metric] if metric else DEFAULT_METRICS

    normalized = []

    for metric in metrics:
        if not metric:
            continue

        metric_name = str(metric).strip().lower()
        metric_name = METRIC_ALIASES.get(metric_name, metric_name)

        if metric_name not in normalized:
            normalized.append(metric_name)

    return normalized or DEFAULT_METRICS


def _calculate_totals(rows: list[dict], config: dict) -> dict:
    orders_field = config.get("orders_field") or config.get("value_field", "orders_count")
    cancelled_field = config.get("cancelled_field", "cancelled_orders_count")
    revenue_field = config.get("revenue_field", "net_order_value")
    cancelled_revenue_field = config.get("cancelled_revenue_field")

    orders_count = sum(_safe_float(row.get(orders_field)) for row in rows)
    cancelled_orders = sum(_safe_float(row.get(cancelled_field)) for row in rows)
    orders_revenue = sum(_safe_float(row.get(revenue_field)) for row in rows)
    cancelled_revenue = (
        sum(_safe_float(row.get(cancelled_revenue_field)) for row in rows)
        if cancelled_revenue_field
        else 0.0
    )

    net_orders = orders_count - cancelled_orders
    net_revenue = orders_revenue - cancelled_revenue
    cancel_rate = round((cancelled_orders / orders_count) * 100, 2) if orders_count else 0.0
    average_order_value = round(orders_revenue / orders_count, 2) if orders_count else 0.0

    return {
        "orders_count": orders_count,
        "orders_revenue": orders_revenue,
        "cancelled_orders": cancelled_orders,
        "cancelled_revenue": cancelled_revenue,
        "net_orders": net_orders,
        "net_revenue": net_revenue,
        "cancel_rate": cancel_rate,
        "average_order_value": average_order_value,
    }


def _pick_metrics(totals: dict, requested_metrics: list[str]) -> dict:
    result = {}

    for metric in requested_metrics:
        if metric in totals:
            result[metric] = totals[metric]

    return result


def _date_from(period_days: int) -> str:
    return (date.today() - timedelta(days=period_days)).isoformat()


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
