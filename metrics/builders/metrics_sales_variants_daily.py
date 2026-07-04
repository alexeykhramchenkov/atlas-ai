

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build

SOURCE_TABLE = "snapshots_sales_variants_daily"
TARGET_TABLE = "metrics_sales_variants_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7
HISTORY_DAYS = 61


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    value_str = str(value)
    if not value_str:
        return None

    return datetime.fromisoformat(value_str.replace("Z", "+00:00")).date()


def to_float(value: Any, default: float = 0.0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def growth_pct(current: float, previous: float) -> float:
    if previous == 0:
        if current == 0:
            return 0.0
        return 100.0
    return round(((current - previous) / previous) * 100, 2)


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


def build_index(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any, str, str, str, date], Dict[str, Any]]:
    index: Dict[Tuple[Any, Any, str, str, str, date], Dict[str, Any]] = {}

    for row in rows:
        snapshot_date = parse_date(row.get("snapshot_date"))
        product_key = row.get("product_key")
        variant_key = row.get("variant_key")

        if not snapshot_date or not product_key or not variant_key:
            continue

        key = (
            row.get("user_id"),
            row.get("shop_id"),
            row.get("marketplace") or MARKETPLACE,
            product_key,
            variant_key,
            snapshot_date,
        )
        index[key] = row

    return index


def sum_window(
    index: Dict[Tuple[Any, Any, str, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    product_key: str,
    variant_key: str,
    end_date: date,
    days: int,
    field: str,
) -> float:
    total = 0.0
    for i in range(days):
        day = end_date - timedelta(days=i)
        row = index.get((user_id, shop_id, marketplace, product_key, variant_key, day))
        if row:
            total += to_float(row.get(field))
    return total


def build_metric_row(
    row: Dict[str, Any],
    index: Dict[Tuple[Any, Any, str, str, str, date], Dict[str, Any]],
    day_totals: Dict[Tuple[Any, Any, str, date], Dict[str, float]],
) -> Optional[Dict[str, Any]]:
    metric_date = parse_date(row.get("snapshot_date"))
    product_key = row.get("product_key")
    variant_key = row.get("variant_key")

    if not metric_date or not product_key or not variant_key:
        return None

    user_id = row.get("user_id")
    shop_id = row.get("shop_id")
    marketplace = row.get("marketplace") or MARKETPLACE

    sales_count = to_float(row.get("sales_count"))
    return_count = to_float(row.get("return_count"))
    quantity = to_float(row.get("quantity"))
    gross_sales_value = to_float(row.get("gross_sales_value"))
    net_sales_value = to_float(row.get("net_sales_value"))
    for_pay_sum = to_float(row.get("for_pay_sum"))
    payment_sale_amount_sum = to_float(row.get("payment_sale_amount_sum"))

    return_rate = safe_pct(return_count, sales_count) if sales_count else 0.0
    avg_sale_value = round(net_sales_value / sales_count, 2) if sales_count else 0.0

    day_key = (user_id, shop_id, marketplace, metric_date)
    total_sales = day_totals.get(day_key, {}).get("sales_count", 0.0)
    total_positive_revenue = day_totals.get(day_key, {}).get("positive_net_sales_value", 0.0)

    sales_share_pct = safe_pct(sales_count, total_sales)
    positive_net_sales_value = max(net_sales_value, 0.0)
    revenue_share_pct = safe_pct(positive_net_sales_value, total_positive_revenue)

    sales_1d_prev = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date - timedelta(days=1), 1, "sales_count")
    sales_7d_current = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date, 7, "sales_count")
    sales_7d_prev = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date - timedelta(days=7), 7, "sales_count")
    sales_30d_current = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date, 30, "sales_count")
    sales_30d_prev = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date - timedelta(days=30), 30, "sales_count")

    revenue_1d_prev = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date - timedelta(days=1), 1, "net_sales_value")
    revenue_7d_current = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date, 7, "net_sales_value")
    revenue_7d_prev = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date - timedelta(days=7), 7, "net_sales_value")
    revenue_30d_current = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date, 30, "net_sales_value")
    revenue_30d_prev = sum_window(index, user_id, shop_id, marketplace, product_key, variant_key, metric_date - timedelta(days=30), 30, "net_sales_value")

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": metric_date.isoformat(),
        "product_key": product_key,
        "variant_key": variant_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "marketplace_variant_id": row.get("marketplace_variant_id"),
        "seller_sku": row.get("seller_sku"),
        "size_name": row.get("size_name"),

        "sales_count": round(sales_count, 2),
        "return_count": round(return_count, 2),
        "quantity": round(quantity, 2),
        "gross_sales_value": round(gross_sales_value, 2),
        "net_sales_value": round(net_sales_value, 2),
        "for_pay_sum": round(for_pay_sum, 2),
        "payment_sale_amount_sum": round(payment_sale_amount_sum, 2),

        "return_rate": return_rate,
        "avg_sale_value": avg_sale_value,
        "sales_share_pct": sales_share_pct,
        "revenue_share_pct": revenue_share_pct,

        "sales_growth_1d_pct": growth_pct(sales_count, sales_1d_prev),
        "sales_growth_7d_pct": growth_pct(sales_7d_current, sales_7d_prev),
        "sales_growth_30d_pct": growth_pct(sales_30d_current, sales_30d_prev),

        "revenue_growth_1d_pct": growth_pct(net_sales_value, revenue_1d_prev),
        "revenue_growth_7d_pct": growth_pct(revenue_7d_current, revenue_7d_prev),
        "revenue_growth_30d_pct": growth_pct(revenue_30d_current, revenue_30d_prev),
    }


def build_day_totals(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any, str, date], Dict[str, float]]:
    totals: Dict[Tuple[Any, Any, str, date], Dict[str, float]] = defaultdict(lambda: {
        "sales_count": 0.0,
        "positive_net_sales_value": 0.0,
    })

    for row in rows:
        snapshot_date = parse_date(row.get("snapshot_date"))
        if not snapshot_date:
            continue

        key = (
            row.get("user_id"),
            row.get("shop_id"),
            row.get("marketplace") or MARKETPLACE,
            snapshot_date,
        )

        sales_count = to_float(row.get("sales_count"))
        net_sales_value = to_float(row.get("net_sales_value"))

        totals[key]["sales_count"] += sales_count
        totals[key]["positive_net_sales_value"] += max(net_sales_value, 0.0)

    return totals


def build_metrics(rows: List[Dict[str, Any]], dates_to_build: List[date]) -> List[Dict[str, Any]]:
    index = build_index(rows)
    day_totals = build_day_totals(rows)
    target_dates = set(dates_to_build)

    result: List[Dict[str, Any]] = []
    for row in rows:
        row_date = parse_date(row.get("snapshot_date"))
        if row_date not in target_dates:
            continue

        metric_row = build_metric_row(row, index, day_totals)
        if metric_row:
            result.append(metric_row)

    return result


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
                on_conflict="user_id,shop_id,marketplace,product_key,variant_key,snapshot_date",
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
        f"Resolving sales variant metrics coverage "
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
        print("No sales variant metrics to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching sales variant snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)

    if user_id is not None:
        snapshots = [row for row in snapshots if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshots = [row for row in snapshots if row.get("shop_id") == shop_id]

    if marketplace:
        snapshots = [row for row in snapshots if (row.get("marketplace") or MARKETPLACE) == marketplace]

    print(f"Sales variant snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Sales variant metrics prepared: {len(metrics)}")

    rows_upserted = upsert_metrics(metrics)
    last_processed_date = max(dates_to_build).isoformat() if dates_to_build else None

    return {
        "rows_read": len(snapshots),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def build_metrics_sales_variants_daily() -> None:
    print("Resolving sales variant metrics coverage...")
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
        print("No sales variant metrics to build")
        return

    print("Fetching sales variant snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)
    print(f"Sales variant snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Sales variant metrics prepared: {len(metrics)}")

    sent = upsert_metrics(metrics)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")


if __name__ == "__main__":
    build_metrics_sales_variants_daily()