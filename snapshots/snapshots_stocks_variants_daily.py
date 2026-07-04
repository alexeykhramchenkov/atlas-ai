import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


SOURCE_TABLE = "normalized_stocks"
TARGET_TABLE = "snapshots_stocks_variants_daily"
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


def fetch_normalized_stocks(batch_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", MARKETPLACE)
            .order("id")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_snapshot_row(row: Dict[str, Any], snapshot_date: str) -> Dict[str, Any]:
    quantity = to_int(row.get("quantity"))
    quantity_full = to_int(row.get("quantity_full"))
    in_way_to_client = to_int(row.get("in_way_to_client"))
    in_way_from_client = to_int(row.get("in_way_from_client"))

    price = to_float(row.get("price"))
    discount = to_float(row.get("discount"))

    effective_price = price * (1 - discount / 100) if discount > 0 else price
    stock_value = round(quantity_full * effective_price, 2)

    return {
        "user_id": row.get("user_id"),
        "shop_id": row.get("shop_id"),
        "marketplace": row.get("marketplace") or MARKETPLACE,
        "snapshot_date": snapshot_date,

        "product_key": row.get("product_key"),
        "marketplace_product_id": row.get("marketplace_product_id"),
        "variant_key": row.get("variant_key"),
        "marketplace_variant_id": row.get("marketplace_variant_id"),
        "size_name": row.get("size_name"),
        "seller_sku": row.get("seller_sku"),

        "warehouse_key": row.get("warehouse_key"),
        "warehouse_name": row.get("warehouse_name"),

        "brand": row.get("brand"),
        "subject": row.get("subject"),
        "category": row.get("category"),

        "quantity": quantity,
        "quantity_full": quantity_full,
        "in_way_to_client": in_way_to_client,
        "in_way_from_client": in_way_from_client,
        "stock_value": stock_value,

        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
    }


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
                on_conflict="user_id,shop_id,marketplace,product_key,variant_key,warehouse_key,snapshot_date",
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
    snapshot_date = job.get("date_to") or job.get("date_from") or date.today().isoformat()

    print("Fetching normalized stocks...")
    normalized_stocks = fetch_normalized_stocks()
    print(f"Normalized stocks fetched: {len(normalized_stocks)}")

    snapshots = [build_snapshot_row(row, snapshot_date) for row in normalized_stocks]
    print(f"Stock variant snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No stock variant snapshots to upsert")
        return {
            "rows_read": len(normalized_stocks),
            "rows_upserted": 0,
            "last_processed_date": snapshot_date,
        }

    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(normalized_stocks),
        "rows_upserted": sent,
        "last_processed_date": snapshot_date,
    }


def build_snapshots_stocks_variants_daily(snapshot_date: Optional[str] = None) -> None:
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
    build_snapshots_stocks_variants_daily()