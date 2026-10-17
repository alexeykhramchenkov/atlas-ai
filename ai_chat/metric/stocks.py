from datetime import date, timedelta
from typing import Any


DATASET = "stocks"
ANALYSIS = "metric_value"
DEFAULT_ENTITY = "store"
DEFAULT_METRIC = "stock_qty"
DEFAULT_PERIOD_DAYS = 30
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

def metric_value(request: dict, supabase, config: dict) -> dict:
    from ai_chat.internal_tools.get_stocks import get_stocks, StockDataUnavailableError
    entity=request.get("entity") or DEFAULT_ENTITY
    metric=_normalize_metric(request.get("metric"))
    if entity not in {"store","product","variant","warehouse","product_warehouse","variant_warehouse"}:
        raise ValueError(f"Unsupported stock entity: {entity}")
    if metric=="stock_value":
        raise ValueError("Inventory valuation is not part of the approved quantity contract")
    try:
        facts=get_stocks(user_id=request["user_id"],shop_id=request["shop_id"],
            marketplace=request.get("marketplace","wb"),product_key=request.get("product_key"),
            variant_key=request.get("variant_key"),warehouse_key=request.get("warehouse_key"),
            as_of=request.get("snapshot_date"),level="product" if entity in {"store","product"} else "variant",supabase=supabase)
    except StockDataUnavailableError:
        return _empty_result(entity,metric)
    # Compatibility names for existing consumers, sourced only from get_stocks.
    rows=[{**row,"stock_qty":row["total_quantity"],"stock_qty_full":row["total_quantity"],
           "stock_in_way_to_client":row["to_customer_quantity"],"stock_in_way_from_client":row["from_customer_quantity"]}
          for row in facts["products"]]
    result={"entity":entity,"dataset":DATASET,"analysis":ANALYSIS,"metric":metric,"snapshot_date":facts["as_of"],**facts}
    if entity=="store":
        return {**result,"stock_qty":facts["total_quantity"],"stock_qty_full":facts["total_quantity"],
                "stock_in_way_to_client":facts["to_customer_quantity"],"stock_in_way_from_client":facts["from_customer_quantity"]}
    if entity in {"warehouse","product_warehouse","variant_warehouse"}:
        groups={}
        for row in rows:
            key=(row.get("product_key") if entity!="warehouse" else None,
                 row.get("variant_key") if entity=="variant_warehouse" else None,row.get("warehouse_key"))
            if key not in groups:groups[key]={**row,**{f:0 for f in ("stock_qty","stock_qty_full","stock_in_way_to_client","stock_in_way_from_client")}}
            for field in ("stock_qty","stock_qty_full","stock_in_way_to_client","stock_in_way_from_client"):groups[key][field]+=row[field]
        rows=list(groups.values())
    if entity=="product" and request.get("product_key"):
        _add_product_days_left(rows=rows,request=request,supabase=supabase)
    return {**result,"rows":rows,"meta":{"rows_count":len(rows)}}


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
        row["stock_available_total"] = row["total_quantity"]
        row["days_left"] = _calculate_days_left(
            stock_qty=row.get("stock_qty"),
            avg_daily_orders=avg_daily_orders,
        )
        row["days_left_total"] = _calculate_days_left(
            stock_qty=row.get("stock_available_total"),
            avg_daily_orders=avg_daily_orders,
        )


def _fetch_orders_count_period(request, supabase, product_key, period_days):
    from ai_chat.internal_tools.get_orders import get_orders
    dates={"start_date":request.get("date_from"),"end_date":request.get("date_to")}
    if not any(dates.values()):dates={"period_days":period_days}
    return get_orders(user_id=request["user_id"],shop_id=request["shop_id"],marketplace=request.get("marketplace","wb"),
                      product_key=product_key,supabase=supabase,**dates)["orders_count"]


def _calculate_days_left(stock_qty: Any, avg_daily_orders: float) -> float | None:
    if stock_qty in [None, ""]:
        return None

    stock_qty_value = _safe_float(stock_qty)

    if avg_daily_orders <= 0:
        return None

    return round(stock_qty_value / avg_daily_orders, 2)


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
            "stock_qty": None,
            "stock_qty_full": None,
            "stock_in_way_to_client": None,
            "stock_in_way_from_client": None,
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
