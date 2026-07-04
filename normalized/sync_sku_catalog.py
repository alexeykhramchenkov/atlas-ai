import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from supabase import create_client


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))


load_dotenv(ROOT_DIR / ".env")


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


SOURCE_TABLE = "normalized_products"
TARGET_TABLE = "sku_catalog"
MARKETPLACE = "wb"
DEFAULT_USER_ID = 1
DEFAULT_SHOP_ID = 1
BATCH_SIZE = 100


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_normalized_products() -> List[Dict[str, Any]]:
    response = (
        supabase
        .table(SOURCE_TABLE)
        .select("*")
        .execute()
    )
    return response.data or []


def fetch_existing_statuses() -> Dict[str, str]:
    response = (
        supabase
        .table(TARGET_TABLE)
        .select("product_key, product_status")
        .execute()
    )

    result: Dict[str, str] = {}
    for row in response.data or []:
        product_key = row.get("product_key")
        product_status = row.get("product_status")
        if product_key and product_status:
            result[product_key] = product_status

    return result


def build_catalog_row(
    row: Dict[str, Any],
    existing_statuses: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    nm_id = to_int(row.get("nm_id") or row.get("nmid") or row.get("nmID"))
    if not nm_id:
        return None

    product_key = f"{MARKETPLACE}_{nm_id}"
    product_status = existing_statuses.get(product_key, "active")
    now = utc_now_iso()

    return {
        "user_id": to_int(row.get("user_id")) or DEFAULT_USER_ID,
        "shop_id": to_int(row.get("shop_id")) or DEFAULT_SHOP_ID,
        "marketplace": clean_text(row.get("marketplace")) or MARKETPLACE,
        "product_key": product_key,
        "nm_id": nm_id,
        "imt_id": to_int(row.get("imt_id") or row.get("imtID")),
        "sku": None,
        "barcode": None,
        "brand": clean_text(row.get("brand")),
        "title": clean_text(row.get("title") or row.get("name")),
        "category": clean_text(row.get("category") or row.get("parent_name") or row.get("parentName")),
        "subject": clean_text(row.get("subject") or row.get("subject_name") or row.get("subjectName") or row.get("object")),
        "vendor_code": clean_text(row.get("vendor_code") or row.get("vendorCode") or row.get("vendor_code_wb")),
        "product_status": product_status,
        "updated_at": now,
        "last_sync_at": now,
    }


def deduplicate_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        product_key = row.get("product_key")
        if not product_key:
            continue

        existing = result.get(product_key)
        if existing is None:
            result[product_key] = row
            continue

        for key, value in row.items():
            if existing.get(key) in (None, "") and value not in (None, ""):
                existing[key] = value

    return list(result.values())


def upsert_rows(rows: List[Dict[str, Any]]) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(batch, on_conflict="product_key")
            .execute()
        )
        print(f"Sent batch: {start + len(batch)}/{len(rows)}")


def main() -> None:
    print(f"Fetching products from {SOURCE_TABLE}...")
    products = fetch_normalized_products()
    print(f"Normalized products fetched: {len(products)}")

    print("Fetching existing product statuses...")
    existing_statuses = fetch_existing_statuses()
    print(f"Existing statuses fetched: {len(existing_statuses)}")

    rows: List[Dict[str, Any]] = []
    skipped = 0

    for product in products:
        catalog_row = build_catalog_row(product, existing_statuses)
        if catalog_row is None:
            skipped += 1
            continue
        rows.append(catalog_row)

    print(f"Catalog rows prepared before dedupe: {len(rows)}")
    print(f"Skipped invalid: {skipped}")

    rows = deduplicate_rows(rows)
    print(f"Catalog rows prepared after dedupe: {len(rows)}")

    if not rows:
        print("No rows to upsert")
        return

    upsert_rows(rows)
    print("Done")
    print(f"Rows sent to sku_catalog: {len(rows)}")


if __name__ == "__main__":
    main()