import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


SOURCE_TABLE = "snapshots_stocks_variants_daily"
PRODUCTS_TABLE = "normalized_products"
TARGET_TABLE = "snapshots_stocks_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_int(value: Any, default: int = 0) -> int:
    if value in [None, ""]:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
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


def fetch_variant_snapshots(snapshot_date: Optional[str] = None, batch_size: int = 1000, *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        query = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
            .order("snapshot_date")
            .range(offset, offset + batch_size - 1)
        )

        if snapshot_date:
            query = query.eq("snapshot_date", snapshot_date)

        response = query.execute()
        batch = response.data or []
        rows.extend(batch)

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


def build_group_key(row: Dict[str, Any]) -> Optional[Tuple[Any, Any, str, str, str]]:
    snapshot_date = parse_date(row.get("snapshot_date"))
    product_key = row.get("product_key")

    if not snapshot_date or not product_key:
        return None

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        product_key,
        snapshot_date.isoformat(),
    )


def build_empty_group(row: Dict[str, Any], snapshot_date: str, products_by_key: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    product = products_by_key.get(row.get("product_key"), {})
    return {
        "user_id": row.get("user_id"),
        "shop_id": row.get("shop_id"),
        "marketplace": row.get("marketplace") or MARKETPLACE,
        "snapshot_date": snapshot_date,
        "product_key": row.get("product_key"),
        "marketplace_product_id": row.get("marketplace_product_id") or product.get("marketplace_product_id"),
        "brand": row.get("brand") or product.get("brand"),
        "title": product.get("title"),
        "subject_id": product.get("subject_id"),
        "subject_name": product.get("subject_name") or row.get("subject"),
        "category_name": product.get("category_name") or row.get("category"),
        "seller_sku": product.get("seller_sku"),
        "total_quantity": 0,
        "total_quantity_full": 0,
        "total_in_way_to_client": 0,
        "total_in_way_from_client": 0,
        "total_stock_value": 0,
        "variants_count": 0,
        "warehouses_count": 0,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }


def build_snapshots(rows: List[Dict[str, Any]], products_by_key: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, Any, str, str, str], Dict[str, Any]] = {}
    variants: Dict[Tuple[Any, Any, str, str, str], Set[str]] = defaultdict(set)
    warehouses: Dict[Tuple[Any, Any, str, str, str], Set[str]] = defaultdict(set)

    for row in rows:
        key = build_group_key(row)
        if key is None:
            continue

        snapshot_date = key[-1]

        if key not in groups:
            groups[key] = build_empty_group(row, snapshot_date, products_by_key)

        item = groups[key]
        item["total_quantity"] += to_int(row.get("quantity"))
        item["total_quantity_full"] += to_int(row.get("quantity_full"))
        item["total_in_way_to_client"] += to_int(row.get("in_way_to_client"))
        item["total_in_way_from_client"] += to_int(row.get("in_way_from_client"))
        item["total_stock_value"] += to_float(row.get("stock_value"))

        variant_key = row.get("variant_key")
        warehouse_key = row.get("warehouse_key")

        if variant_key:
            variants[key].add(str(variant_key))
        if warehouse_key:
            warehouses[key].add(str(warehouse_key))

    result: List[Dict[str, Any]] = []

    for key, item in groups.items():
        item["total_stock_value"] = round(item["total_stock_value"], 2)
        item["variants_count"] = len(variants[key])
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
    snapshot_date = job.get("date_to") or job.get("date_from") or date.today().isoformat()

    print("Fetching stock variant snapshots...")
    variant_snapshots = fetch_variant_snapshots(snapshot_date=snapshot_date, user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Stock variant snapshots fetched: {len(variant_snapshots)}")

    print("Fetching products...")
    products_by_key = fetch_products(user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Products fetched: {len(products_by_key)}")

    snapshots = build_snapshots(variant_snapshots, products_by_key)
    print(f"Stock product snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No stock product snapshots to upsert")
        return {
            "rows_read": len(variant_snapshots),
            "rows_upserted": 0,
            "last_processed_date": snapshot_date,
        }

    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(variant_snapshots),
        "rows_upserted": sent,
        "last_processed_date": snapshot_date,
    }


def build_snapshots_stocks_daily(snapshot_date: Optional[str] = None) -> None:
    job = {}
    if snapshot_date:
        job["date_to"] = snapshot_date

    result = run_snapshot_job(
        job=job,
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_snapshots_stocks_daily()