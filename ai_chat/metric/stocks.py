from datetime import date, timedelta
from typing import Any


DATASET = "stocks"
ANALYSIS = "metric_value"
DEFAULT_ENTITY = "store"
DEFAULT_METRIC = "stock_qty"
DEFAULT_PERIOD_DAYS = 30
PRODUCT_TABLE = "metrics_stocks_daily"
VARIANT_TABLE = "metrics_stocks_variants_daily"
ORDERS_TABLE = "metrics_orders_daily"
MAX_ROWS = 10000
PAGE_SIZE = 1000

METRIC_ALIASES = {
    "total_stock_qty": "stock_qty",
    "stock_qty": "stock_qty",
    "stock_qty_full": "stock_qty_full",
    "stock_in_way": "stock_in_way_to_client",
    "stock_in_way_to_client": "stock_in_way_to_client",
    "stock_in_way_from_client": "stock_in_way_from_client",
    "stock_value": "stock_value",
}

PRODUCT_FIELDS = """
snapshot_date,
product_key,
marketplace_product_id,
seller_sku,
total_quantity,
total_quantity_full,
total_in_way_to_client,
total_in_way_from_client,
total_stock_value,
variants_count,
warehouses_count
"""

VARIANT_FIELDS = """
snapshot_date,
product_key,
marketplace_product_id,
variant_key,
marketplace_variant_id,
size_name,
seller_sku,
warehouse_key,
warehouse_name,
quantity,
quantity_full,
in_way_to_client,
in_way_from_client,
stock_value
"""


def metric_value(request: dict, supabase, config: dict) -> dict:
    entity = request.get("entity") or DEFAULT_ENTITY
    metric = _normalize_metric(request.get("metric"))

    if entity not in {
        "store",
        "product",
        "variant",
        "warehouse",
        "product_warehouse",
        "variant_warehouse",
    }:
        raise ValueError(f"Unsupported entity for stocks.metric_value: {entity}")

    table = PRODUCT_TABLE if entity in {"store", "product"} else VARIANT_TABLE
    select_fields = PRODUCT_FIELDS if table == PRODUCT_TABLE else VARIANT_FIELDS

    snapshot_date = _latest_snapshot_date(
        request=request,
        supabase=supabase,
        table=table,
    )

    if not snapshot_date:
        return _empty_result(entity=entity, metric=metric)

    rows = _fetch_rows(
        request=request,
        supabase=supabase,
        table=table,
        select_fields=select_fields,
        snapshot_date=snapshot_date,
    )

    if entity == "store":
        totals = _aggregate_product_rows(rows)
        return {
            "entity": "store",
            "dataset": DATASET,
            "analysis": ANALYSIS,
            "metric": metric,
            "snapshot_date": snapshot_date,
            **totals,
        }

    grouped_rows = _group_rows(rows=rows, entity=entity)

    if entity == "product" and request.get("product_key"):
        _add_product_days_left(
            rows=grouped_rows,
            request=request,
            supabase=supabase,
        )

    return {
        "entity": entity,
        "dataset": DATASET,
        "analysis": ANALYSIS,
        "metric": metric,
        "snapshot_date": snapshot_date,
        "rows": grouped_rows,
        "meta": {
            "rows_count": len(grouped_rows),
        },
    }


def _latest_snapshot_date(request: dict, supabase, table: str) -> str | None:
    query = (
        supabase
        .table(table)
        .select("snapshot_date")
        .eq("user_id", request["user_id"])
        .eq("shop_id", request["shop_id"])
        .eq("marketplace", request.get("marketplace", "wb"))
        .order("snapshot_date", desc=True)
        .limit(1)
    )

    query = _apply_optional_filters(query=query, request=request, table=table)
    response = query.execute()
    rows = response.data or []

    if not rows:
        return None

    return rows[0].get("snapshot_date")


def _fetch_rows(
    request: dict,
    supabase,
    table: str,
    select_fields: str,
    snapshot_date: str,
) -> list[dict]:
    rows: list[dict] = []
    start = 0

    while start < MAX_ROWS:
        end = min(start + PAGE_SIZE - 1, MAX_ROWS - 1)

        query = (
            supabase
            .table(table)
            .select(select_fields)
            .eq("user_id", request["user_id"])
            .eq("shop_id", request["shop_id"])
            .eq("marketplace", request.get("marketplace", "wb"))
            .eq("snapshot_date", snapshot_date)
            .range(start, end)
        )

        query = _apply_optional_filters(query=query, request=request, table=table)
        response = query.execute()
        page_rows = response.data or []
        rows.extend(page_rows)

        if len(page_rows) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return rows


def _apply_optional_filters(query, request: dict, table: str):
    product_key = request.get("product_key")
    variant_key = request.get("variant_key")
    warehouse_key = request.get("warehouse_key")

    if product_key:
        query = query.eq("product_key", product_key)

    if table == VARIANT_TABLE and variant_key:
        query = query.eq("variant_key", variant_key)

    if table == VARIANT_TABLE and warehouse_key:
        query = query.eq("warehouse_key", warehouse_key)

    return query


def _group_rows(rows: list[dict], entity: str) -> list[dict]:
    groups: dict[tuple, dict] = {}

    for row in rows:
        key = _group_key(row=row, entity=entity)

        if key is None:
            continue

        if key not in groups:
            groups[key] = _new_group(row=row, entity=entity)

        _add_row_to_group(groups[key], row=row)

    result = []

    for group in groups.values():
        _finalize_group(group)
        result.append(group)

    return result


def _group_key(row: dict, entity: str) -> tuple | None:
    if entity == "product":
        product_key = row.get("product_key")
        return (product_key,) if product_key else None

    if entity == "variant":
        product_key = row.get("product_key")
        variant_key = row.get("variant_key")
        size_name = row.get("size_name")
        return (product_key, variant_key, size_name) if product_key and variant_key else None

    if entity == "warehouse":
        warehouse_key = row.get("warehouse_key")
        warehouse_name = row.get("warehouse_name")
        return (warehouse_key, warehouse_name) if warehouse_key else None

    if entity == "product_warehouse":
        product_key = row.get("product_key")
        warehouse_key = row.get("warehouse_key")
        warehouse_name = row.get("warehouse_name")
        return (product_key, warehouse_key, warehouse_name) if product_key and warehouse_key else None

    if entity == "variant_warehouse":
        product_key = row.get("product_key")
        variant_key = row.get("variant_key")
        size_name = row.get("size_name")
        warehouse_key = row.get("warehouse_key")
        warehouse_name = row.get("warehouse_name")
        return (product_key, variant_key, size_name, warehouse_key, warehouse_name) if product_key and variant_key and warehouse_key else None

    return None


def _new_group(row: dict, entity: str) -> dict:
    group = {
        "entity": entity,
        "product_key": row.get("product_key"),
        "marketplace_product_id": row.get("marketplace_product_id"),
        "seller_sku": row.get("seller_sku"),
        "variant_key": row.get("variant_key"),
        "marketplace_variant_id": row.get("marketplace_variant_id"),
        "size_name": row.get("size_name"),
        "warehouse_key": row.get("warehouse_key"),
        "warehouse_name": row.get("warehouse_name"),
        "stock_qty": 0.0,
        "stock_qty_full": 0.0,
        "stock_in_way_to_client": 0.0,
        "stock_in_way_from_client": 0.0,
        "stock_value": 0.0,
        "variants_count": 0,
        "warehouses_count": 0,
        "_variant_keys": set(),
        "_warehouse_keys": set(),
    }

    return {key: value for key, value in group.items() if value is not None}


def _add_row_to_group(group: dict, row: dict) -> None:
    if "total_quantity" in row:
        group["stock_qty"] += _safe_float(row.get("total_quantity"))
        group["stock_qty_full"] += _safe_float(row.get("total_quantity_full"))
        group["stock_in_way_to_client"] += _safe_float(row.get("total_in_way_to_client"))
        group["stock_in_way_from_client"] += _safe_float(row.get("total_in_way_from_client"))
        group["stock_value"] += _safe_float(row.get("total_stock_value"))
        group["variants_count"] += _safe_float(row.get("variants_count"))
        group["warehouses_count"] += _safe_float(row.get("warehouses_count"))
        return

    group["stock_qty"] += _safe_float(row.get("quantity"))
    group["stock_qty_full"] += _safe_float(row.get("quantity_full"))
    group["stock_in_way_to_client"] += _safe_float(row.get("in_way_to_client"))
    group["stock_in_way_from_client"] += _safe_float(row.get("in_way_from_client"))
    group["stock_value"] += _safe_float(row.get("stock_value"))

    variant_key = row.get("variant_key")
    warehouse_key = row.get("warehouse_key")

    if variant_key:
        group.setdefault("_variant_keys", set()).add(variant_key)

    if warehouse_key:
        group.setdefault("_warehouse_keys", set()).add(warehouse_key)


def _finalize_group(group: dict) -> None:
    variant_keys = group.pop("_variant_keys", set())
    warehouse_keys = group.pop("_warehouse_keys", set())

    if variant_keys:
        group["variants_count"] = len(variant_keys)

    if warehouse_keys:
        group["warehouses_count"] = len(warehouse_keys)

    group["avg_stock_value_per_unit"] = _safe_divide(
        group["stock_value"],
        group["stock_qty_full"],
    )


def _aggregate_product_rows(rows: list[dict]) -> dict:
    totals = {
        "stock_qty": 0.0,
        "stock_qty_full": 0.0,
        "stock_in_way_to_client": 0.0,
        "stock_in_way_from_client": 0.0,
        "stock_value": 0.0,
        "variants_count": 0.0,
        "warehouses_count": 0.0,
    }

    for row in rows:
        totals["stock_qty"] += _safe_float(row.get("total_quantity"))
        totals["stock_qty_full"] += _safe_float(row.get("total_quantity_full"))
        totals["stock_in_way_to_client"] += _safe_float(row.get("total_in_way_to_client"))
        totals["stock_in_way_from_client"] += _safe_float(row.get("total_in_way_from_client"))
        totals["stock_value"] += _safe_float(row.get("total_stock_value"))
        totals["variants_count"] += _safe_float(row.get("variants_count"))
        totals["warehouses_count"] += _safe_float(row.get("warehouses_count"))

    totals["avg_stock_value_per_unit"] = _safe_divide(
        totals["stock_value"],
        totals["stock_qty_full"],
    )

    return totals


def _add_product_days_left(
    rows: list[dict],
    request: dict,
    supabase,
) -> None:
    product_key = request.get("product_key")

    if not product_key:
        return

    try:
        period_days = _safe_period_days(request.get("period_days", DEFAULT_PERIOD_DAYS))
        orders_count_period = _fetch_orders_count_period(
            request=request,
            supabase=supabase,
            product_key=product_key,
            period_days=period_days,
        )
        avg_daily_orders = _safe_divide(orders_count_period, period_days)
    except Exception:
        orders_count_period = 0.0
        avg_daily_orders = 0.0

    for row in rows:
        if row.get("product_key") != product_key:
            continue

        row["orders_count_period"] = orders_count_period
        row["avg_daily_orders"] = avg_daily_orders
        row["stock_available_total"] = _calculate_stock_available_total(row)
        row["days_left"] = _calculate_days_left(
            stock_qty=row.get("stock_qty"),
            avg_daily_orders=avg_daily_orders,
        )
        row["days_left_total"] = _calculate_days_left(
            stock_qty=row.get("stock_available_total"),
            avg_daily_orders=avg_daily_orders,
        )


def _fetch_orders_count_period(
    request: dict,
    supabase,
    product_key: str,
    period_days: int,
) -> float:
    rows: list[dict] = []
    start = 0
    date_from = _date_from_period(period_days)

    while start < MAX_ROWS:
        end = min(start + PAGE_SIZE - 1, MAX_ROWS - 1)

        response = (
            supabase
            .table(ORDERS_TABLE)
            .select("orders_count")
            .eq("user_id", request["user_id"])
            .eq("shop_id", request["shop_id"])
            .eq("marketplace", request.get("marketplace", "wb"))
            .eq("product_key", product_key)
            .gte("snapshot_date", date_from)
            .range(start, end)
            .execute()
        )
        page_rows = response.data or []
        rows.extend(page_rows)

        if len(page_rows) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return sum(_safe_float(row.get("orders_count")) for row in rows)


def _calculate_days_left(stock_qty: Any, avg_daily_orders: float) -> float | None:
    if stock_qty in [None, ""]:
        return None

    stock_qty_value = _safe_float(stock_qty)

    if avg_daily_orders <= 0:
        return None

    return round(stock_qty_value / avg_daily_orders, 2)


def _calculate_stock_available_total(row: dict) -> float | None:
    if row.get("stock_qty") in [None, ""]:
        return None

    return (
        _safe_float(row.get("stock_qty"))
        + _safe_float(row.get("stock_in_way_to_client"))
        + _safe_float(row.get("stock_in_way_from_client"))
    )


def _date_from_period(period_days: int) -> str:
    return (date.today() - timedelta(days=period_days)).isoformat()


def _safe_period_days(value: Any) -> int:
    try:
        period_days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PERIOD_DAYS

    if period_days <= 0:
        return DEFAULT_PERIOD_DAYS

    return period_days


def _empty_result(entity: str, metric: str) -> dict:
    if entity == "store":
        return {
            "entity": "store",
            "dataset": DATASET,
            "analysis": ANALYSIS,
            "metric": metric,
            "snapshot_date": None,
            "stock_qty": 0.0,
            "stock_qty_full": 0.0,
            "stock_in_way_to_client": 0.0,
            "stock_in_way_from_client": 0.0,
            "stock_value": 0.0,
            "avg_stock_value_per_unit": 0.0,
            "variants_count": 0.0,
            "warehouses_count": 0.0,
        }

    return {
        "entity": entity,
        "dataset": DATASET,
        "analysis": ANALYSIS,
        "metric": metric,
        "snapshot_date": None,
        "rows": [],
        "meta": {
            "rows_count": 0,
        },
    }


def _normalize_metric(metric: Any) -> str:
    if not metric:
        return DEFAULT_METRIC

    metric_name = str(metric).strip().lower()
    return METRIC_ALIASES.get(metric_name, metric_name)


def _safe_float(value: Any) -> float:
    if value in [None, ""]:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0

    return round(numerator / denominator, 2)
