

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "snapshots_funnel_daily"
TARGET_TABLE = "metrics_funnel_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7
HISTORY_DAYS = 61


def parse_date(value: Any) -> Optional[date]:
    if value in [None, ""]:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def to_float(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0
    return numerator / denominator


def growth_pct(current_value: float, previous_value: float) -> float:
    if previous_value == 0:
        return 0
    return round((current_value - previous_value) / previous_value * 100, 2)


def fetch_snapshots_for_metric_dates(dates_to_build: List[date], *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> List[Dict[str, Any]]:
    if not dates_to_build:
        return []

    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    start_date = min(dates_to_build) - timedelta(days=HISTORY_DAYS)
    end_date_exclusive = max(dates_to_build) + timedelta(days=1)

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
            .gte("snapshot_date", start_date.isoformat())
            .lt("snapshot_date", end_date_exclusive.isoformat())
            .order("snapshot_date")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_lookup(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]]:
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]] = {}

    for row in rows:
        snapshot_date = parse_date(row.get("snapshot_date"))
        product_key = row.get("product_key")
        user_id = row.get("user_id")
        shop_id = row.get("shop_id")
        marketplace = row.get("marketplace") or MARKETPLACE

        if snapshot_date is None or not product_key or user_id is None or shop_id is None:
            continue

        lookup[(user_id, shop_id, marketplace, product_key, snapshot_date)] = row

    return lookup


def sum_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    product_key: str,
    end_date: date,
    days: int,
    field: str,
) -> float:
    total = 0.0

    for index in range(days):
        item_date = end_date - timedelta(days=index)
        row = lookup.get((user_id, shop_id, marketplace, product_key, item_date))
        if row:
            total += to_float(row.get(field))

    return total


def previous_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    product_key: str,
    metric_date: date,
    days: int,
    offset_days: int,
    field: str,
) -> float:
    period_end = metric_date - timedelta(days=offset_days)
    return sum_period_value(
        lookup=lookup,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        product_key=product_key,
        end_date=period_end,
        days=days,
        field=field,
    )


def build_metric_row(
    row: Dict[str, Any],
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    metric_date = parse_date(row.get("snapshot_date"))
    product_key = row.get("product_key")
    user_id = row.get("user_id")
    shop_id = row.get("shop_id")
    marketplace = row.get("marketplace") or MARKETPLACE

    if metric_date is None or not product_key or user_id is None or shop_id is None:
        return None

    open_count = to_float(row.get("open_count"))
    cart_count = to_float(row.get("cart_count"))
    order_count = to_float(row.get("order_count"))
    buyout_count = to_float(row.get("buyout_count"))
    cancel_count = to_float(row.get("cancel_count"))

    order_sum = to_float(row.get("order_sum"))
    buyout_sum = to_float(row.get("buyout_sum"))
    cancel_sum = to_float(row.get("cancel_sum"))
    wishlist_adds = to_float(row.get("wishlist_adds"))
    avg_price = to_float(row.get("avg_price"))

    stocks_wb = to_float(row.get("stocks_wb"))
    stocks_mp = to_float(row.get("stocks_mp"))
    stock_balance_sum = to_float(row.get("stock_balance_sum"))
    product_rating = to_float(row.get("product_rating"))
    feedback_rating = to_float(row.get("feedback_rating"))
    localization_pct = to_float(row.get("localization_pct"))

    previous_day = metric_date - timedelta(days=1)
    previous_row = lookup.get((user_id, shop_id, marketplace, product_key, previous_day))

    previous_open_count = to_float(previous_row.get("open_count")) if previous_row else 0
    previous_cart_count = to_float(previous_row.get("cart_count")) if previous_row else 0
    previous_order_count = to_float(previous_row.get("order_count")) if previous_row else 0
    previous_buyout_count = to_float(previous_row.get("buyout_count")) if previous_row else 0
    previous_order_sum = to_float(previous_row.get("order_sum")) if previous_row else 0
    previous_buyout_sum = to_float(previous_row.get("buyout_sum")) if previous_row else 0

    current_7d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "order_count")
    previous_7d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "order_count")
    current_30d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "order_count")
    previous_30d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "order_count")

    current_7d_open = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "open_count")
    previous_7d_open = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "open_count")
    current_30d_open = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "open_count")
    previous_30d_open = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "open_count")

    current_7d_buyout_sum = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "buyout_sum")
    previous_7d_buyout_sum = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "buyout_sum")
    current_30d_buyout_sum = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "buyout_sum")
    previous_30d_buyout_sum = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "buyout_sum")

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": metric_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "seller_sku": row.get("seller_sku"),

        "open_count": round(open_count, 2),
        "cart_count": round(cart_count, 2),
        "order_count": round(order_count, 2),
        "buyout_count": round(buyout_count, 2),
        "cancel_count": round(cancel_count, 2),

        "order_sum": round(order_sum, 2),
        "buyout_sum": round(buyout_sum, 2),
        "cancel_sum": round(cancel_sum, 2),
        "wishlist_adds": round(wishlist_adds, 2),
        "avg_price": round(avg_price, 2),

        "stocks_wb": round(stocks_wb, 2),
        "stocks_mp": round(stocks_mp, 2),
        "stock_balance_sum": round(stock_balance_sum, 2),
        "product_rating": round(product_rating, 2),
        "feedback_rating": round(feedback_rating, 2),
        "localization_pct": round(localization_pct, 2),

        "open_to_cart_pct": round(safe_divide(cart_count, open_count) * 100, 2),
        "cart_to_order_pct": round(safe_divide(order_count, cart_count) * 100, 2),
        "order_to_buyout_pct": round(safe_divide(buyout_count, order_count) * 100, 2),
        "cancel_rate_pct": round(safe_divide(cancel_count, order_count) * 100, 2),
        "buyout_rate_pct": round(safe_divide(buyout_count, buyout_count + cancel_count) * 100, 2),
        "wishlist_rate_pct": round(safe_divide(wishlist_adds, open_count) * 100, 2),

        "open_growth_1d_pct": growth_pct(open_count, previous_open_count),
        "cart_growth_1d_pct": growth_pct(cart_count, previous_cart_count),
        "order_growth_1d_pct": growth_pct(order_count, previous_order_count),
        "buyout_growth_1d_pct": growth_pct(buyout_count, previous_buyout_count),
        "order_sum_growth_1d_pct": growth_pct(order_sum, previous_order_sum),
        "buyout_sum_growth_1d_pct": growth_pct(buyout_sum, previous_buyout_sum),

        "open_growth_7d_pct": growth_pct(current_7d_open, previous_7d_open),
        "order_growth_7d_pct": growth_pct(current_7d_orders, previous_7d_orders),
        "buyout_sum_growth_7d_pct": growth_pct(current_7d_buyout_sum, previous_7d_buyout_sum),

        "open_growth_30d_pct": growth_pct(current_30d_open, previous_30d_open),
        "order_growth_30d_pct": growth_pct(current_30d_orders, previous_30d_orders),
        "buyout_sum_growth_30d_pct": growth_pct(current_30d_buyout_sum, previous_30d_buyout_sum),
    }


def build_metrics(rows: List[Dict[str, Any]], dates_to_build: List[date]) -> List[Dict[str, Any]]:
    lookup = build_lookup(rows)
    target_dates: Set[date] = set(dates_to_build)
    metrics: List[Dict[str, Any]] = []

    for row in rows:
        row_date = parse_date(row.get("snapshot_date"))
        if row_date not in target_dates:
            continue

        metric_row = build_metric_row(row, lookup)
        if metric_row is not None:
            metrics.append(metric_row)

    return metrics


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_metrics(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        print("Nothing to upsert")
        return 0

    sent = 0

    for batch in chunked(rows, BATCH_SIZE):
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(
                batch,
                on_conflict="user_id,shop_id,marketplace,product_key,snapshot_date",
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(rows)}")

    return sent


def run_metric_job(job, state, registry_entry) -> Dict[str, Any]:
    user_id, shop_id = int(job["user_id"]), int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    user_id = job.get("user_id")
    shop_id = job.get("shop_id")
    marketplace = job.get("marketplace") or MARKETPLACE

    source_table = registry_entry.get("source_table_name") or SOURCE_TABLE
    target_table = registry_entry.get("target_table_name") or TARGET_TABLE

    print(
        f"Resolving funnel metrics coverage "
        f"for user_id={user_id} shop_id={shop_id} marketplace={marketplace}..."
    )

    dates_to_build = get_dates_to_build(
        normalized_table=source_table,
        normalized_date_column="snapshot_date",
        snapshot_table=target_table,
        snapshot_date_column="snapshot_date",
        marketplace=marketplace,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No funnel metrics to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching funnel snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)

    if user_id is not None:
        snapshots = [row for row in snapshots if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshots = [row for row in snapshots if row.get("shop_id") == shop_id]

    if marketplace:
        snapshots = [row for row in snapshots if (row.get("marketplace") or MARKETPLACE) == marketplace]

    print(f"Funnel snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Funnel metrics prepared: {len(metrics)}")

    rows_upserted = upsert_metrics(metrics)
    last_processed_date = max(dates_to_build).isoformat() if dates_to_build else None

    return {
        "rows_read": len(snapshots),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def main( *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> None:
    print("Resolving funnel metrics coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="snapshot_date",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No funnel metrics to build")
        return

    print("Fetching funnel snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Funnel snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Funnel metrics prepared: {len(metrics)}")

    sent = upsert_metrics(metrics)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")


if __name__ == "__main__":
    main()
