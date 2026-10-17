import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


SOURCE_TABLE = "raw_wb_stocks"
TARGET_TABLE = "normalized_stocks"
MARKETPLACE = "wb"
DEFAULT_SHOP_ID = 1
BATCH_SIZE = 100


def get_watermark(state: Optional[Dict[str, Any]]) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return None

    return payload


def payload_value(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in [None, ""]:
            return value

    return default


def to_int(value: Any, default: int = 0) -> int:
    if value in [None, ""]:
        return default

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_float(value: Any) -> Optional[float]:
    if value in [None, ""]:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value in [1, "1", "true", "True", "TRUE", "yes", "YES"]:
        return True

    return False


def build_product_key(marketplace_product_id: Any) -> Optional[str]:
    if marketplace_product_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_product_id}"


def build_variant_key(marketplace_variant_id: Any) -> Optional[str]:
    if marketplace_variant_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_variant_id}"


def build_warehouse_key(warehouse_name: Any) -> Optional[str]:
    if warehouse_name in [None, ""]:
        return None

    value = str(warehouse_name).lower()
    cleaned = "".join(char if char.isalnum() else "_" for char in value).strip("_")
    while "__" in cleaned:
        cleaned = cleaned.replace("__", "_")

    return f"{MARKETPLACE}_{cleaned}"


def normalize_raw_stocks_payload(payload: Any) -> List[Dict[str, Any]]:
    payload = parse_payload(payload)

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        data = payload.get("data")

        if isinstance(data, dict):
            stocks = data.get("stocks")
            if isinstance(stocks, list):
                return [item for item in stocks if isinstance(item, dict)]

        for key in ("stocks", "items", "rows", "list", "payload"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        return [payload]

    return []


def build_stock_row(raw_row: Dict[str, Any], item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    user_id = raw_row.get("user_id")
    shop_id = raw_row.get("shop_id") or DEFAULT_SHOP_ID

    nm_id = payload_value(item, "nmId", "nmID", "nm_id", default=raw_row.get("nm_id"))
    barcode = payload_value(item, "barcode", default=raw_row.get("barcode"))
    warehouse_name = payload_value(
        item,
        "warehouseName",
        "warehouse_name",
        default=raw_row.get("warehouse_name"),
    )
    tech_size = payload_value(item, "techSize", "tech_size", "size", default=raw_row.get("tech_size"))

    if not user_id or not nm_id or not warehouse_name:
        return None

    marketplace_product_id = str(nm_id)
    product_key = build_product_key(marketplace_product_id)

    variant_id = item.get("chrtId") or barcode
    marketplace_variant_id = str(variant_id) if variant_id not in [None, ""] else None
    variant_key = build_variant_key(marketplace_variant_id)

    size_name = str(tech_size) if tech_size not in [None, ""] else None
    seller_sku = payload_value(
        item,
        "supplierArticle",
        "supplier_article",
        default=raw_row.get("supplier_article"),
    )
    warehouse_key = build_warehouse_key(warehouse_name)

    quantity = to_int(payload_value(item, "quantity", default=0), default=0)
    quantity_full = to_int(payload_value(item, "quantityFull", "quantity_full", default=quantity), default=quantity)

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": MARKETPLACE,
        "product_key": product_key,
        "marketplace_product_id": marketplace_product_id,
        "variant_key": variant_key,
        "marketplace_variant_id": marketplace_variant_id,
        "size_name": size_name,
        "seller_sku": seller_sku,
        "warehouse_key": warehouse_key,
        "brand": payload_value(item, "brand", default=raw_row.get("brand")),
        "subject": payload_value(item, "subject", default=raw_row.get("subject")),
        "category": payload_value(item, "category", default=raw_row.get("category")),
        "warehouse_name": warehouse_name,
        "quantity": quantity,
        "quantity_full": quantity_full,
        "in_way_to_client": to_int(payload_value(item, "inWayToClient", "in_way_to_client", default=0), default=0),
        "in_way_from_client": to_int(payload_value(item, "inWayFromClient", "in_way_from_client", default=0), default=0),
        "price": to_float(payload_value(item, "Price", "price")),
        "discount": to_float(payload_value(item, "Discount", "discount")),
        "is_supply": to_bool(payload_value(item, "isSupply", "is_supply")),
        "is_realization": to_bool(payload_value(item, "isRealization", "is_realization")),
        "last_change_date": payload_value(item, "lastChangeDate", "last_change_date"),
    }


def fetch_raw_stocks(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    batch_size: int = 1000,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        query = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
        )

        if last_raw_updated_at is not None:
            query = query.or_(
                f"updated_at.gt.{last_raw_updated_at},and(updated_at.eq.{last_raw_updated_at},id.gt.{last_raw_id})"
            )

        response = (
            query
            .order("updated_at")
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


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_rows(rows: List[Dict[str, Any]]) -> int:
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
                on_conflict="user_id,shop_id,marketplace,product_key,variant_key,warehouse_key",
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(rows)}")

    return sent


def run_normalization_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    registry_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_rows = fetch_raw_stocks(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
        batch_size=1000,
    )

    if not raw_rows:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    stocks_by_key: Dict[tuple, Dict[str, Any]] = {}

    for raw_row in raw_rows:
        items = normalize_raw_stocks_payload(raw_row.get("payload"))

        for item in items:
            stock_row = build_stock_row(raw_row, item)

            if stock_row is None:
                continue

            dedupe_key = (
                stock_row["user_id"],
                stock_row["shop_id"],
                stock_row["marketplace"],
                stock_row["product_key"],
                stock_row.get("variant_key"),
                stock_row.get("warehouse_key"),
            )

            stocks_by_key[dedupe_key] = stock_row

    rows = list(stocks_by_key.values())

    rows_upserted = 0
    if rows:
        rows_upserted = upsert_rows(rows)

    newest_row = raw_rows[-1]

    return {
        "rows_read": len(raw_rows),
        "rows_upserted": rows_upserted,
        "last_raw_updated_at": newest_row.get("updated_at"),
        "last_raw_id": newest_row.get("id"),
    }


if __name__ == "__main__":
    result = run_normalization_job(
        job={
            "user_id": 1,
            "shop_id": 1,
        },
        state=None,
        registry_entry=None,
    )

    print(result)