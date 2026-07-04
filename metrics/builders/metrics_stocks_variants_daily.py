import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "snapshots_stocks_variants_daily"
TARGET_TABLE = "metrics_stocks_variants_daily"
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


def build_lookup(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]]:
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]] = {}

    for row in rows:
        snapshot_date = parse_date(row.get("snapshot_date"))
        product_key = row.get("product_key")
        variant_key = row.get("variant_key")
        warehouse_key = row.get("warehouse_key") or ""
        user_id = row.get("user_id")
        shop_id = row.get("shop_id")
        marketplace = row.get("marketplace") or MARKETPLACE

        if snapshot_date is None or not product_key or not variant_key or user_id is None or shop_id is None:
            continue

        lookup[(user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, snapshot_date)] = row

    return lookup


def sum_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    product_key: str,
    variant_key: str,
    warehouse_key: str,
    end_date: date,
    days: int,
    field: str,
) -> float:
    total = 0.0

    for index in range(days):
        item_date = end_date - timedelta(days=index)
        row = lookup.get((user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, item_date))
        if row:
            total += to_float(row.get(field))

    return total


def previous_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    product_key: str,
    variant_key: str,
    warehouse_key: str,
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
        variant_key=variant_key,
        warehouse_key=warehouse_key,
        end_date=period_end,
        days=days,
        field=field,
    )


def build_metric_row(
    row: Dict[str, Any],
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    metric_date = parse_date(row.get("snapshot_date"))
    product_key = row.get("product_key")
    variant_key = row.get("variant_key")
    warehouse_key = row.get("warehouse_key") or ""
    user_id = row.get("user_id")
    shop_id = row.get("shop_id")
    marketplace = row.get("marketplace") or MARKETPLACE

    if metric_date is None or not product_key or not variant_key or user_id is None or shop_id is None:
        return None

    quantity = to_float(row.get("quantity"))
    quantity_full = to_float(row.get("quantity_full"))
    in_way_to_client = to_float(row.get("in_way_to_client"))
    in_way_from_client = to_float(row.get("in_way_from_client"))
    stock_value = to_float(row.get("stock_value"))

    previous_day = metric_date - timedelta(days=1)
    previous_row = lookup.get((user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, previous_day))

    previous_quantity = to_float(previous_row.get("quantity")) if previous_row else 0
    previous_quantity_full = to_float(previous_row.get("quantity_full")) if previous_row else 0
    previous_stock_value = to_float(previous_row.get("stock_value")) if previous_row else 0

    current_7d_stock = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 7, 1, "quantity_full")
    previous_7d_stock = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 7, 8, "quantity_full")
    current_30d_stock = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 30, 1, "quantity_full")
    previous_30d_stock = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 30, 31, "quantity_full")

    current_7d_stock_value = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 7, 1, "stock_value")
    previous_7d_stock_value = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 7, 8, "stock_value")
    current_30d_stock_value = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 30, 1, "stock_value")
    previous_30d_stock_value = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, variant_key, warehouse_key, metric_date, 30, 31, "stock_value")

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": metric_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "variant_key": variant_key,
        "marketplace_variant_id": row.get("marketplace_variant_id"),
        "size_name": row.get("size_name"),
        "seller_sku": row.get("seller_sku"),
        "warehouse_key": row.get("warehouse_key"),
        "warehouse_name": row.get("warehouse_name"),

        "quantity": round(quantity, 2),
        "quantity_full": round(quantity_full, 2),
        "in_way_to_client": round(in_way_to_client, 2),
        "in_way_from_client": round(in_way_from_client, 2),
        "stock_value": round(stock_value, 2),

        "avg_stock_value_per_unit": round(safe_divide(stock_value, quantity_full), 2),
        "stock_available_share_pct": round(safe_divide(quantity, quantity_full) * 100, 2),
        "stock_in_way_to_client_share_pct": round(safe_divide(in_way_to_client, quantity_full) * 100, 2),
        "stock_in_way_from_client_share_pct": round(safe_divide(in_way_from_client, quantity_full) * 100, 2),

        "stock_growth_1d_pct": growth_pct(quantity_full, previous_quantity_full),
        "available_stock_growth_1d_pct": growth_pct(quantity, previous_quantity),
        "stock_value_growth_1d_pct": growth_pct(stock_value, previous_stock_value),

        "stock_growth_7d_pct": growth_pct(current_7d_stock, previous_7d_stock),
        "stock_value_growth_7d_pct": growth_pct(current_7d_stock_value, previous_7d_stock_value),

        "stock_growth_30d_pct": growth_pct(current_30d_stock, previous_30d_stock),
        "stock_value_growth_30d_pct": growth_pct(current_30d_stock_value, previous_30d_stock_value),
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
                on_conflict="user_id,shop_id,marketplace,product_key,variant_key,warehouse_key,snapshot_date",
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
        f"Resolving stock variant metrics coverage "
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
        print("No stock variant metrics to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching stock variant snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)

    if user_id is not None:
        snapshots = [row for row in snapshots if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshots = [row for row in snapshots if row.get("shop_id") == shop_id]

    if marketplace:
        snapshots = [row for row in snapshots if (row.get("marketplace") or MARKETPLACE) == marketplace]

    print(f"Stock variant snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Stock variant metrics prepared: {len(metrics)}")

    rows_upserted = upsert_metrics(metrics)
    last_processed_date = max(dates_to_build).isoformat() if dates_to_build else None

    return {
        "rows_read": len(snapshots),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def main() -> None:
    print("Resolving stock variant metrics coverage...")
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
        print("No stock variant metrics to build")
        return

    print("Fetching stock variant snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)
    print(f"Stock variant snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Stock variant metrics prepared: {len(metrics)}")

    sent = upsert_metrics(metrics)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")


if __name__ == "__main__":
    main()
