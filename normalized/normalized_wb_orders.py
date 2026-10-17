import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


SOURCE_TABLE = "raw_wb_orders"
TARGET_TABLE = "normalized_orders"
MARKETPLACE = "wb"

BATCH_SIZE = 100


def get_watermark(state: Optional[Dict[str, Any]]) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def payload_value(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in payload and payload.get(key) is not None:
            return payload.get(key)
    return default


def normalize_wb_date(value: Any) -> Any:
    if value in (None, "", "0001-01-01T00:00:00", "0001-01-01 00:00:00"):
        return None

    if isinstance(value, str) and value.startswith("0001-01-01"):
        return None

    return value


def to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value: Any, default: float = 0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "TRUE", "yes", "Да", "да"):
        return True
    return False


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def build_product_key(marketplace_product_id: Any) -> Optional[str]:
    if marketplace_product_id in [None, ""]:
        return None

    return f"{MARKETPLACE}_{marketplace_product_id}"


def build_variant_key(marketplace_variant_id: Any) -> Optional[str]:
    if marketplace_variant_id in [None, ""]:
        return None

    return f"{MARKETPLACE}_{marketplace_variant_id}"


def build_normalized_order(raw_row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload = raw_row.get("payload") or {}

    if not isinstance(payload, dict):
        return None

    user_id = to_int(raw_row.get("user_id"))
    shop_id = to_int(raw_row.get("shop_id"))

    if user_id is None or shop_id is None:
        return None

    srid = clean_text(payload_value(payload, "srid", default=raw_row.get("srid")))
    g_number = clean_text(payload_value(payload, "gNumber", "g_number"))

    nm_id = to_int(payload_value(payload, "nmId", "nm_id", default=raw_row.get("nm_id")))
    marketplace_product_id = str(nm_id) if nm_id else None
    product_key = build_product_key(marketplace_product_id)

    barcode = clean_text(payload_value(payload, "barcode"))
    marketplace_variant_id = barcode
    variant_key = build_variant_key(marketplace_variant_id)

    size_name = clean_text(payload_value(payload, "techSize", "tech_size"))
    seller_sku = clean_text(payload_value(payload, "supplierArticle", "supplier_article"))

    order_date = normalize_wb_date(
        payload_value(payload, "date", "orderDate", "order_date", default=raw_row.get("event_date"))
    )
    last_change_date = normalize_wb_date(
        payload_value(payload, "lastChangeDate", "last_change_date", default=raw_row.get("event_date"))
    )
    cancel_date = normalize_wb_date(payload_value(payload, "cancelDate", "cancel_date"))

    if not srid and not g_number:
        return None

    if not order_date and not last_change_date:
        return None

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
        "order_id": srid,

        "srid": srid,
        "g_number": g_number,

        "order_date": order_date,
        "last_change_date": last_change_date,

        "brand": clean_text(payload_value(payload, "brand")),
        "subject": clean_text(payload_value(payload, "subject")),
        "category": clean_text(payload_value(payload, "category")),

        "warehouse_name": clean_text(payload_value(payload, "warehouseName", "warehouse_name")),
        "warehouse_type": clean_text(payload_value(payload, "warehouseType", "warehouse_type")),

        "region_name": clean_text(payload_value(payload, "regionName", "oblast", "region_name")),
        "country_name": clean_text(payload_value(payload, "countryName", "country_name")),
        "oblast_okrug_name": clean_text(payload_value(payload, "oblastOkrugName", "oblast_okrug_name")),

        "total_price": to_float(payload_value(payload, "totalPrice", "total_price")),
        "discount_percent": to_float(payload_value(payload, "discountPercent", "discount_percent")),
        "price_with_disc": to_float(payload_value(payload, "priceWithDisc", "price_with_disc")),
        "finished_price": to_float(payload_value(payload, "finishedPrice", "finished_price")),
        "spp": to_float(payload_value(payload, "spp")),

        "is_cancel": to_bool(payload_value(payload, "isCancel", "is_cancel", default=False)),
        "cancel_date": cancel_date,

        "is_supply": to_bool(payload_value(payload, "isSupply", "is_supply", default=False)),
        "is_realization": to_bool(payload_value(payload, "isRealization", "is_realization", default=False)),
    }


def fetch_raw_orders(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
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
        .limit(limit)
        .execute()
    )

    return response.data or []


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def deduplicate_orders(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        srid = row.get("srid")
        g_number = row.get("g_number")

        dedupe_key = row.get("order_id") or srid or g_number
        if not dedupe_key:
            continue

        existing = result.get(dedupe_key)
        if existing is None:
            result[dedupe_key] = row
            continue

        existing_date = existing.get("last_change_date") or existing.get("order_date") or ""
        row_date = row.get("last_change_date") or row.get("order_date") or ""

        if str(row_date) >= str(existing_date):
            result[dedupe_key] = row

    return list(result.values())


def upsert_orders(rows: List[Dict[str, Any]]) -> int:
    sent = 0

    for batch in chunked(rows, BATCH_SIZE):
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(
                batch,
                on_conflict="user_id,shop_id,marketplace,srid",
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

    raw_orders = fetch_raw_orders(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
        limit=50000,
    )

    if not raw_orders:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    rows: List[Dict[str, Any]] = []

    for raw_row in raw_orders:
        normalized_order = build_normalized_order(raw_row)

        if normalized_order is None:
            continue

        rows.append(normalized_order)

    rows = deduplicate_orders(rows)

    rows_upserted = 0
    if rows:
        rows_upserted = upsert_orders(rows)

    newest_row = raw_orders[-1]

    return {
        "rows_read": len(raw_orders),
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
