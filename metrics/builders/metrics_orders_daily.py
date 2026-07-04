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


SOURCE_TABLE = "snapshots_orders_daily"
TARGET_TABLE = "metrics_orders_daily"
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


def fetch_snapshots_for_metric_dates(dates_to_build: List[date]) -> List[Dict[str, Any]]:
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
            .eq("marketplace", MARKETPLACE)
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


def build_shop_totals_by_date(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any, str, date], Dict[str, float]]:
    totals: Dict[Tuple[Any, Any, str, date], Dict[str, float]] = defaultdict(lambda: {"orders": 0, "revenue": 0})

    for row in rows:
        snapshot_date = parse_date(row.get("snapshot_date"))
        user_id = row.get("user_id")
        shop_id = row.get("shop_id")
        marketplace = row.get("marketplace") or MARKETPLACE

        if snapshot_date is None or user_id is None or shop_id is None:
            continue

        key = (user_id, shop_id, marketplace, snapshot_date)
        totals[key]["orders"] += to_float(row.get("orders"))
        totals[key]["revenue"] += to_float(row.get("net_order_value"))

    return totals


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
    shop_totals: Dict[Tuple[Any, Any, str, date], Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    metric_date = parse_date(row.get("snapshot_date"))
    product_key = row.get("product_key")
    user_id = row.get("user_id")
    shop_id = row.get("shop_id")
    marketplace = row.get("marketplace") or MARKETPLACE

    if metric_date is None or not product_key or user_id is None or shop_id is None:
        return None

    orders_count = to_float(row.get("orders"))
    cancelled_orders_count = to_float(row.get("canceled_orders"))
    gross_order_value = to_float(row.get("gross_order_value"))
    net_order_value = to_float(row.get("net_order_value"))

    previous_day = metric_date - timedelta(days=1)
    previous_row = lookup.get((user_id, shop_id, marketplace, product_key, previous_day))
    previous_orders = to_float(previous_row.get("orders")) if previous_row else 0
    previous_revenue = to_float(previous_row.get("net_order_value")) if previous_row else 0

    current_7d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "orders")
    previous_7d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "orders")
    current_30d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "orders")
    previous_30d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "orders")

    current_7d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "net_order_value")
    previous_7d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "net_order_value")
    current_30d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "net_order_value")
    previous_30d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "net_order_value")

    shop_total = shop_totals.get((user_id, shop_id, marketplace, metric_date), {"orders": 0, "revenue": 0})

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": metric_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "seller_sku": row.get("seller_sku"),

        "orders_count": round(orders_count, 2),
        "cancelled_orders_count": round(cancelled_orders_count, 2),
        "gross_order_value": round(gross_order_value, 2),
        "net_order_value": round(net_order_value, 2),

        "cancel_rate": round(safe_divide(cancelled_orders_count, orders_count) * 100, 2),
        "avg_order_value": round(safe_divide(net_order_value, orders_count), 2),

        "orders_share_pct": round(safe_divide(orders_count, shop_total["orders"]) * 100, 2),
        "revenue_share_pct": round(safe_divide(net_order_value, shop_total["revenue"]) * 100, 2),

        "orders_growth_1d_pct": growth_pct(orders_count, previous_orders),
        "orders_growth_7d_pct": growth_pct(current_7d_orders, previous_7d_orders),
        "orders_growth_30d_pct": growth_pct(current_30d_orders, previous_30d_orders),

        "revenue_growth_1d_pct": growth_pct(net_order_value, previous_revenue),
        "revenue_growth_7d_pct": growth_pct(current_7d_revenue, previous_7d_revenue),
        "revenue_growth_30d_pct": growth_pct(current_30d_revenue, previous_30d_revenue),
    }


def build_metrics(rows: List[Dict[str, Any]], dates_to_build: List[date]) -> List[Dict[str, Any]]:
    lookup = build_lookup(rows)
    shop_totals = build_shop_totals_by_date(rows)
    target_dates: Set[date] = set(dates_to_build)
    metrics: List[Dict[str, Any]] = []

    for row in rows:
        row_date = parse_date(row.get("snapshot_date"))
        if row_date not in target_dates:
            continue

        metric_row = build_metric_row(row, lookup, shop_totals)
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
    user_id = job.get("user_id")
    shop_id = job.get("shop_id")
    marketplace = job.get("marketplace") or MARKETPLACE

    source_table = registry_entry.get("source_table_name") or SOURCE_TABLE
    target_table = registry_entry.get("target_table_name") or TARGET_TABLE

    print(
        f"Resolving orders metrics coverage "
        f"for user_id={user_id} shop_id={shop_id} marketplace={marketplace}..."
    )

    dates_to_build = get_dates_to_build(
        normalized_table=source_table,
        normalized_date_column="snapshot_date",
        snapshot_table=target_table,
        snapshot_date_column="snapshot_date",
        marketplace=marketplace,
        repair_days=REPAIR_DAYS,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No order metrics to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching order snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)

    if user_id is not None:
        snapshots = [row for row in snapshots if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshots = [row for row in snapshots if row.get("shop_id") == shop_id]

    if marketplace:
        snapshots = [row for row in snapshots if (row.get("marketplace") or MARKETPLACE) == marketplace]

    print(f"Order snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Order metrics prepared: {len(metrics)}")

    rows_upserted = upsert_metrics(metrics)
    last_processed_date = max(dates_to_build).isoformat() if dates_to_build else None

    return {
        "rows_read": len(snapshots),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def main() -> None:
    print("Resolving orders metrics coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="snapshot_date",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No order metrics to build")
        return

    print("Fetching order snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)
    print(f"Order snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Order metrics prepared: {len(metrics)}")

    sent = upsert_metrics(metrics)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")


if __name__ == "__main__":
    main()
