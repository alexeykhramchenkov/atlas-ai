import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase



SOURCE_TABLE = "raw_wb_prices"
TARGET_TABLE = "normalized_prices"
MARKETPLACE = "wb"


def get_watermark(state: Optional[Dict[str, Any]]) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def payload_value(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in [None, ""]:
            return value
    return default


def extract_items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        data = payload.get("data")

        if isinstance(data, dict):
            list_goods = data.get("listGoods")
            if isinstance(list_goods, list):
                return [item for item in list_goods if isinstance(item, dict)]

        for key in ("listGoods", "items", "rows", "list", "payload"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        return [payload]

    return []


def extract_size_items(item: Dict[str, Any]) -> list[dict]:
    sizes = item.get("sizes")

    if isinstance(sizes, list) and sizes:
        return [size for size in sizes if isinstance(size, dict)]

    return [{}]


def build_event_hash(raw_row: Dict[str, Any], item: Dict[str, Any], size: Dict[str, Any]) -> str:
    nm_id = payload_value(item, "nmID", "nmId", "nm_id", default=raw_row.get("nm_id") or "")
    size_id = payload_value(size, "sizeID", "sizeId", "size_id", default="")
    updated_at = raw_row.get("loaded_at") or ""
    discount = payload_value(item, "discount", "discountPercent", default="")
    price = payload_value(size, "price", default=payload_value(item, "price", default=""))
    discounted_price = payload_value(
        size,
        "discountedPrice",
        "discounted_price",
        default=payload_value(item, "discountedPrice", "discounted_price", default=""),
    )

    raw_key = f"{MARKETPLACE}|price_snapshot|{nm_id}|{size_id}|{price}|{discounted_price}|{discount}|{updated_at}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def build_price_event(raw_row: Dict[str, Any], item: Dict[str, Any], size: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    nm_id = payload_value(item, "nmID", "nmId", "nm_id", default=raw_row.get("nm_id"))
    size_id = payload_value(size, "sizeID", "sizeId", "size_id")
    vendor_code = payload_value(item, "vendorCode", "vendor_code")

    event_time = raw_row.get("loaded_at")
    if not event_time:
        return None

    base_price = payload_value(size, "price", default=payload_value(item, "price"))
    final_price = payload_value(
        size,
        "discountedPrice",
        "discounted_price",
        default=payload_value(item, "discountedPrice", "discounted_price"),
    )
    discount_percent = payload_value(item, "discount", "discountPercent")
    currency = payload_value(item, "currencyIsoCode4217", "currency", default="RUB")

    event_hash = build_event_hash(raw_row, item, size)

    return {
        "user_id": raw_row.get("user_id"),
        "shop_id": raw_row.get("shop_id"),
        "marketplace": MARKETPLACE,

        "snapshot_date": str(event_time)[:10],

        "product_key": f"{MARKETPLACE}_{nm_id}" if nm_id not in [None, "", 0, "0"] else None,
        "variant_key": f"{MARKETPLACE}_{size_id}" if size_id not in [None, "", 0, "0"] else None,

        "marketplace_product_id": str(nm_id) if nm_id not in [None, "", 0, "0"] else None,
        "marketplace_variant_id": str(size_id) if size_id not in [None, "", 0, "0"] else None,

        "seller_sku": str(vendor_code) if vendor_code not in [None, ""] else None,
        "size_name": payload_value(size, "techSizeName", "techSize", "tech_size", "sizeName", "size_name"),

        "event_type": "price_snapshot",
        "base_price": base_price,
        "discount_percent": discount_percent,
        "final_price": final_price,
        "currency": currency,
        "event_time": event_time,

        "raw_payload": {"item": item, "size": size},
        "event_hash": event_hash,
    }


def fetch_raw_prices(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    limit: int = 1000,
) -> list[Dict[str, Any]]:
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


def chunked(items: list[Dict[str, Any]], size: int) -> list[list[Dict[str, Any]]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def insert_events_batch(events: list[Dict[str, Any]], batch_size: int = 100) -> int:
    sent = 0

    for batch in chunked(events, batch_size):
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(
                batch,
                on_conflict="event_hash",
                ignore_duplicates=True,
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(events)}")

    return sent


def run_normalization_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    registry_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_prices = fetch_raw_prices(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
        limit=50000,
    )

    if not raw_prices:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    events = []

    for raw_row in raw_prices:
        payload = raw_row.get("payload")
        items = extract_items(payload)

        for item in items:
            sizes = extract_size_items(item)

            for size in sizes:
                event = build_price_event(raw_row, item, size)

                if event is None:
                    continue

                events.append(event)

    rows_upserted = 0
    if events:
        rows_upserted = insert_events_batch(events, batch_size=100)

    newest_row = raw_prices[-1]

    return {
        "rows_read": len(raw_prices),
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