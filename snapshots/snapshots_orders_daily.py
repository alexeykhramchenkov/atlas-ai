import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "normalized_orders"
CATALOG_TABLE = "normalized_products"
TARGET_TABLE = "snapshots_orders_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7


def require_tenant_context(job: Dict[str, Any]) -> Tuple[int, int, str]:
    missing = [field for field in ("user_id", "shop_id") if job.get(field) is None]
    if missing:
        raise ValueError(f"Orders snapshot job missing tenant context: {', '.join(missing)}")

    return (
        int(job["user_id"]),
        int(job["shop_id"]),
        str(job.get("marketplace") or MARKETPLACE),
    )


def to_float(value: Any, default: float = 0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


from core.dates import moscow_date as parse_date, moscow_midnight


def fetch_orders_for_dates(
    dates_to_build: List[date],
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
) -> List[Dict[str, Any]]:
    if not dates_to_build:
        return []

    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    start_date = min(dates_to_build)
    end_date_exclusive = max(dates_to_build) + timedelta(days=1)
    allowed_dates = set(dates_to_build)

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .gte("order_date", moscow_midnight(start_date))
            .lt("order_date", moscow_midnight(end_date_exclusive))
            .order("order_date")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []

        for row in batch:
            order_day = parse_date(row.get("order_date"))
            if order_day in allowed_dates:
                rows.append(row)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_group_key(row: Dict[str, Any]) -> Optional[Tuple[Any, Any, str, str, date]]:
    order_day = parse_date(row.get("order_date"))
    product_key = row.get("product_key")

    if not order_day or not product_key:
        return None

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        product_key,
        order_day,
    )



def fetch_active_products(
    *,
    user_id: int,
    shop_id: int,
    marketplace: str,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    while True:
        response = (
            supabase
            .table(CATALOG_TABLE)
            .select(
                "user_id,shop_id,marketplace,product_key,marketplace_product_id,"
                "brand,title,subject_id,subject_name,category_name,seller_sku"
            )
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .order("product_key")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def resolve_date_range(rows: List[Dict[str, Any]]) -> Tuple[Optional[date], Optional[date]]:
    dates: List[date] = []

    for row in rows:
        order_day = parse_date(row.get("order_date"))
        if order_day:
            dates.append(order_day)

    if not dates:
        return None, None

    return min(dates), max(dates)


def date_range(start_date: date, end_date: date) -> List[date]:
    days: List[date] = []
    current_date = start_date

    while current_date <= end_date:
        days.append(current_date)
        current_date = date.fromordinal(current_date.toordinal() + 1)

    return days


def build_empty_snapshot(product: Dict[str, Any], snapshot_date: date) -> Dict[str, Any]:
    return {
        "user_id": product.get("user_id"),
        "shop_id": product.get("shop_id"),
        "marketplace": product.get("marketplace") or MARKETPLACE,
        "product_key": product.get("product_key"),
        "marketplace_product_id": product.get("marketplace_product_id"),
        "snapshot_date": snapshot_date.isoformat(),
        "brand": product.get("brand"),
        "title": product.get("title"),
        "subject_id": product.get("subject_id"),
        "subject_name": product.get("subject_name"),
        "category_name": product.get("category_name"),
        "seller_sku": product.get("seller_sku"),
        "orders": 0,
        "canceled_orders": 0,
        "gross_order_value": 0,
        "net_order_value": 0,
        "avg_price": 0,
        "avg_discount_percent": 0,
        "regions_count": 0,
        "warehouses_count": 0,
    }


def build_snapshots(
    rows: List[Dict[str, Any]],
    active_products: List[Dict[str, Any]],
    dates_to_build: List[date],
) -> List[Dict[str, Any]]:
    if not dates_to_build:
        return []

    groups: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]] = {}
    regions: Dict[Tuple[Any, Any, str, str, date], Set[str]] = defaultdict(set)
    warehouses: Dict[Tuple[Any, Any, str, str, date], Set[str]] = defaultdict(set)
    prices: Dict[Tuple[Any, Any, str, str, date], List[float]] = defaultdict(list)
    discounts: Dict[Tuple[Any, Any, str, str, date], List[float]] = defaultdict(list)

    for product in active_products:
        product_key = product.get("product_key")
        user_id = product.get("user_id")
        marketplace = product.get("marketplace") or MARKETPLACE

        if not product_key or user_id is None:
            continue

        for snapshot_date in dates_to_build:
            key = (
                user_id,
                product.get("shop_id"),
                marketplace,
                product_key,
                snapshot_date,
            )
            groups[key] = build_empty_snapshot(product, snapshot_date)

    for row in rows:
        key = build_group_key(row)
        if key is None:
            continue

        user_id, shop_id, marketplace, product_key, snapshot_date = key

        if key not in groups:
            groups[key] = {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "product_key": product_key,
                "marketplace_product_id": row.get("marketplace_product_id"),
                "snapshot_date": snapshot_date.isoformat(),
                "brand": row.get("brand"),
                "title": row.get("title"),
                "subject_id": row.get("subject_id"),
                "subject_name": row.get("subject"),
                "category_name": row.get("category"),
                "seller_sku": row.get("seller_sku"),
                "orders": 0,
                "canceled_orders": 0,
                "gross_order_value": 0,
                "net_order_value": 0,
                "avg_price": 0,
                "avg_discount_percent": 0,
                "regions_count": 0,
                "warehouses_count": 0,
            }

        item = groups[key]

        item["orders"] += 1

        if row.get("is_cancel") is True:
            item["canceled_orders"] += 1

        gross_value = to_float(row.get("price_with_disc")) or to_float(row.get("total_price"))
        net_value = 0 if row.get("is_cancel") is True else gross_value

        item["gross_order_value"] += gross_value
        item["net_order_value"] += net_value

        price = to_float(row.get("price_with_disc")) or to_float(row.get("total_price"))
        discount = to_float(row.get("discount_percent"))

        if price > 0:
            prices[key].append(price)

        discounts[key].append(discount)

        region_name = row.get("region_name")
        warehouse_name = row.get("warehouse_name")

        if region_name:
            regions[key].add(str(region_name))

        if warehouse_name:
            warehouses[key].add(str(warehouse_name))

    result: List[Dict[str, Any]] = []

    for key, item in groups.items():
        item["gross_order_value"] = round(item["gross_order_value"], 2)
        item["net_order_value"] = round(item["net_order_value"], 2)
        item["avg_price"] = round(sum(prices[key]) / len(prices[key]), 2) if prices[key] else 0
        item["avg_discount_percent"] = round(sum(discounts[key]) / len(discounts[key]), 2) if discounts[key] else 0
        item["regions_count"] = len(regions[key])
        item["warehouses_count"] = len(warehouses[key])
        result.append(item)

    return result


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def upsert_snapshots(rows: List[Dict[str, Any]]) -> int:
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


def run_snapshot_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    registry_entry: Dict[str, Any],
) -> Dict[str, Any]:
    user_id, shop_id, marketplace = require_tenant_context(job)

    print("Resolving order snapshot coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="order_date",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        repair_days=REPAIR_DAYS,
    )
    print_dates_to_build(dates_to_build)

    # A bounded repair job rebuilds its whole period, including old corrected orders.
    if job.get("date_from") and job.get("date_to"):
        first = date.fromisoformat(str(job["date_from"])[:10])
        last = date.fromisoformat(str(job["date_to"])[:10])
        dates_to_build = [first + timedelta(days=i) for i in range((last-first).days+1)]

    if not dates_to_build:
        print("No order snapshots to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching normalized orders for selected dates...")
    orders = fetch_orders_for_dates(
        dates_to_build,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
    )
    print(f"Normalized orders fetched: {len(orders)}")

    print("Fetching active products...")
    active_products = fetch_active_products(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
    )
    print(f"Active products fetched: {len(active_products)}")

    snapshots = build_snapshots(orders, active_products, dates_to_build)
    print(f"Snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No snapshots to upsert")
        return {
            "rows_read": len(orders),
            "rows_upserted": 0,
            "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
        }

    print("Upserting order snapshots...")
    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(orders),
        "rows_upserted": sent,
        "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build tenant-scoped order snapshots")
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--shop-id", type=int, required=True)
    parser.add_argument("--marketplace", default=MARKETPLACE)
    args = parser.parse_args()

    result = run_snapshot_job(
        job={
            "user_id": args.user_id,
            "shop_id": args.shop_id,
            "marketplace": args.marketplace,
        },
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    main()
