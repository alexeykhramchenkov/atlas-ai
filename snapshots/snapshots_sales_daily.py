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


SOURCE_TABLE = "normalized_sales"
PRODUCTS_TABLE = "normalized_products"
TARGET_TABLE = "snapshots_sales_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7


def to_float(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def fetch_sales_for_dates(dates_to_build: List[date], *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> List[Dict[str, Any]]:
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
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
            .gte("event_time", start_date.isoformat())
            .lt("event_time", end_date_exclusive.isoformat())
            .order("event_time")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []

        for row in batch:
            sale_day = parse_date(row.get("event_time") or row.get("sale_created_at"))
            if sale_day in allowed_dates:
                rows.append(row)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def fetch_products( *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> Dict[str, Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    while True:
        response = (
            supabase
            .table(PRODUCTS_TABLE)
            .select(
                "product_key,marketplace_product_id,title,brand,subject_id,subject_name,category_name,seller_sku"
            )
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
            .order("product_key")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return {row.get("product_key"): row for row in rows if row.get("product_key")}


def build_group_key(
    row: Dict[str, Any]
) -> Optional[Tuple[Any, Any, str, str, date]]:
    sale_day = parse_date(row.get("event_time") or row.get("sale_created_at"))
    product_key = row.get("product_key")

    if not sale_day or not product_key:
        return None

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        product_key,
        sale_day,
    )


def build_empty_group(
    row: Dict[str, Any],
    key: Tuple[Any, Any, str, str, date],
    products_by_key: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    user_id, shop_id, marketplace, product_key, snapshot_date = key
    product = products_by_key.get(product_key, {})

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id") or product.get("marketplace_product_id"),
        "snapshot_date": snapshot_date.isoformat(),
        "brand": row.get("brand") or product.get("brand"),
        "title": product.get("title"),
        "subject_id": product.get("subject_id"),
        "subject_name": product.get("subject_name") or row.get("subject"),
        "category_name": product.get("category_name") or row.get("category"),
        "seller_sku": row.get("seller_sku") or product.get("seller_sku"),
        "sales_count": 0,
        "return_count": 0,
        "quantity": 0,
        "gross_sales_value": 0,
        "net_sales_value": 0,
        "for_pay_sum": 0,
        "payment_sale_amount_sum": 0,
        "avg_price": 0,
        "avg_discount_percent": 0,
        "regions_count": 0,
        "warehouses_count": 0,
    }


def is_return(row: Dict[str, Any]) -> bool:
    event_type = str(row.get("event_type") or "").lower()
    sale_type = str(row.get("sale_type") or "").lower()
    sale_id = str(row.get("sale_id") or "").upper()

    return "return" in event_type or "return" in sale_type or sale_id.startswith("R")


def build_snapshots(
    rows: List[Dict[str, Any]], products_by_key: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]] = {}
    prices: Dict[Tuple[Any, Any, str, str, date], List[float]] = defaultdict(list)
    discounts: Dict[Tuple[Any, Any, str, str, date], List[float]] = defaultdict(list)
    regions: Dict[Tuple[Any, Any, str, str, date], Set[str]] = defaultdict(set)
    warehouses: Dict[Tuple[Any, Any, str, str, date], Set[str]] = defaultdict(set)

    for row in rows:
        key = build_group_key(row)
        if key is None:
            continue

        if key not in groups:
            groups[key] = build_empty_group(row, key, products_by_key)

        item = groups[key]
        quantity = to_float(row.get("quantity"), default=1)
        amount = (
            to_float(row.get("amount"))
            or to_float(row.get("finished_price"))
            or to_float(row.get("price_with_disc"))
            or to_float(row.get("total_price"))
        )
        for_pay = to_float(row.get("for_pay"))
        payment_sale_amount = to_float(row.get("payment_sale_amount"))
        discount = to_float(row.get("discount_percent"))

        if is_return(row):
            item["return_count"] += 1
            item["net_sales_value"] -= abs(amount)
            item["quantity"] -= abs(quantity)
        else:
            item["sales_count"] += 1
            item["net_sales_value"] += amount
            item["quantity"] += quantity

        item["gross_sales_value"] += amount
        item["for_pay_sum"] += for_pay
        item["payment_sale_amount_sum"] += payment_sale_amount

        if amount > 0:
            prices[key].append(amount)
        discounts[key].append(discount)

        region_name = row.get("region_name")
        warehouse_name = row.get("warehouse_name")

        if region_name:
            regions[key].add(str(region_name))
        if warehouse_name:
            warehouses[key].add(str(warehouse_name))

    result: List[Dict[str, Any]] = []

    for key, item in groups.items():
        item["quantity"] = round(item["quantity"], 2)
        item["gross_sales_value"] = round(item["gross_sales_value"], 2)
        item["net_sales_value"] = round(item["net_sales_value"], 2)
        item["for_pay_sum"] = round(item["for_pay_sum"], 2)
        item["payment_sale_amount_sum"] = round(item["payment_sale_amount_sum"], 2)
        item["avg_price"] = round(sum(prices[key]) / len(prices[key]), 2) if prices[key] else 0
        item["avg_discount_percent"] = round(sum(discounts[key]) / len(discounts[key]), 2) if discounts[key] else 0
        item["regions_count"] = len(regions[key])
        item["warehouses_count"] = len(warehouses[key])
        result.append(item)

    return result


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_snapshots(rows: List[Dict[str, Any]]) -> int:
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


def run_snapshot_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    registry_entry: Dict[str, Any],
) -> Dict[str, Any]:
    user_id, shop_id = int(job["user_id"]), int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    print("Resolving sales daily snapshot coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="event_time",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No sales snapshots to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching normalized sales for selected dates...")
    sales = fetch_sales_for_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Normalized sales fetched: {len(sales)}")

    print("Fetching products...")
    products_by_key = fetch_products(user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Products fetched: {len(products_by_key)}")

    snapshots = build_snapshots(sales, products_by_key)
    print(f"Sales snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No sales snapshots to upsert")
        return {
            "rows_read": len(sales),
            "rows_upserted": 0,
            "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
        }

    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(sales),
        "rows_upserted": sent,
        "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
    }


def build_snapshots_sales_daily() -> None:
    result = run_snapshot_job(
        job={},
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_snapshots_sales_daily()