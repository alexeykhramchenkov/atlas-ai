import hashlib
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


SOURCE_TABLE = "raw_wb_sales"
TARGET_TABLE = "normalized_sales"
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


def normalize_wb_date(value: Any) -> Any:
    if value in (None, "", "0001-01-01T00:00:00", "0001-01-01 00:00:00"):
        return None

    if isinstance(value, str) and value.startswith("0001-01-01"):
        return None

    return value


def to_number(value: Any, default: float = 0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def build_product_key(marketplace_product_id: Any) -> Optional[str]:
    if marketplace_product_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_product_id}"


def build_variant_key(marketplace_variant_id: Any) -> Optional[str]:
    if marketplace_variant_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_variant_id}"


def build_event_hash(raw_row: Dict[str, Any], payload: Dict[str, Any]) -> str:
    sale_id = payload_value(payload, "saleID", "saleId", "sale_id", default="")
    srid = payload_value(payload, "srid", default=raw_row.get("srid") or "")
    last_change_date = payload_value(
        payload,
        "lastChangeDate",
        "last_change_date",
        default=raw_row.get("event_date") or "",
    )

    raw_key = f"{MARKETPLACE}|sale|{sale_id}|{srid}|{last_change_date}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def build_financial_event(raw_row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload = raw_row.get("payload") or {}

    if not isinstance(payload, dict):
        return None

    sale_id = payload_value(payload, "saleID", "saleId", "sale_id")
    srid = payload_value(payload, "srid", default=raw_row.get("srid"))
    nm_id = payload_value(payload, "nmId", "nm_id", default=raw_row.get("nm_id"))
    marketplace_product_id = str(nm_id) if nm_id else None
    product_key = build_product_key(marketplace_product_id)

    barcode = payload_value(payload, "barcode")
    marketplace_variant_id = str(barcode) if barcode else None
    variant_key = build_variant_key(marketplace_variant_id)

    tech_size = payload_value(payload, "techSize", "tech_size")
    size_name = str(tech_size) if tech_size else None
    supplier_article = payload_value(payload, "supplierArticle", "supplier_article")
    seller_sku = str(supplier_article) if supplier_article else None

    brand = payload_value(payload, "brand")
    subject = payload_value(payload, "subject")
    category = payload_value(payload, "category")

    warehouse_name = payload_value(payload, "warehouseName", "warehouse_name")
    warehouse_type = payload_value(payload, "warehouseType", "warehouse_type")
    region_name = payload_value(payload, "regionName", "oblast", "region_name")
    country_name = payload_value(payload, "countryName", "country_name")
    oblast_okrug_name = payload_value(payload, "oblastOkrugName", "oblast_okrug_name")

    total_price = payload_value(payload, "totalPrice", "total_price", default=0)
    finished_price = payload_value(payload, "finishedPrice", "finished_price", default=0)
    price_with_disc = payload_value(payload, "priceWithDisc", "price_with_disc", default=0)
    discount_percent = payload_value(payload, "discountPercent", "discount_percent", default=0)
    spp = payload_value(payload, "spp", default=0)

    for_pay = payload_value(payload, "forPay", "for_pay", default=0)
    payment_sale_amount = payload_value(payload, "paymentSaleAmount", "payment_sale_amount", default=0)

    g_number = payload_value(payload, "gNumber", "g_number")

    is_supply = payload_value(payload, "isSupply", "is_supply", default=False)
    is_realization = payload_value(payload, "isRealization", "is_realization", default=False)

    sale_created_at = normalize_wb_date(payload_value(payload, "date", "saleDate", "sale_date"))

    event_time = normalize_wb_date(payload_value(
        payload,
        "lastChangeDate",
        "last_change_date",
        "date",
        "saleDate",
        "sale_date",
        default=raw_row.get("event_date"),
    ))

    if not event_time:
        return None

    amount = payload_value(
        payload,
        "finishedPrice",
        "finished_price",
        "forPay",
        "for_pay",
        "priceWithDisc",
        "price_with_disc",
        default=0,
    )

    sale_type = "return" if to_number(amount) < 0 or to_number(for_pay) < 0 or to_number(finished_price) < 0 else "sale"

    quantity = payload_value(payload, "quantity", default=1)

    event_hash = build_event_hash(raw_row, payload)

    return {
        "user_id": raw_row.get("user_id"),
        "shop_id": raw_row.get("shop_id"),
        "marketplace": MARKETPLACE,
        "product_key": product_key,
        "marketplace_product_id": marketplace_product_id,
        "variant_key": variant_key,
        "marketplace_variant_id": marketplace_variant_id,
        "seller_sku": seller_sku,
        "size_name": size_name,
        "brand": brand,
        "subject": subject,
        "category": category,
        "marketplace_order_id": str(g_number) if g_number else None,
        "sale_id": str(sale_id) if sale_id else None,
        "srid": str(srid) if srid else None,
        "event_type": sale_type,
        "sale_type": sale_type,
        "quantity": quantity,
        "amount": amount,
        "for_pay": for_pay,
        "payment_sale_amount": payment_sale_amount,
        "total_price": total_price,
        "finished_price": finished_price,
        "price_with_disc": price_with_disc,
        "discount_percent": discount_percent,
        "spp": spp,
        "currency": "RUB",
        "warehouse_name": warehouse_name,
        "warehouse_type": warehouse_type,
        "region_name": region_name,
        "country_name": country_name,
        "oblast_okrug_name": oblast_okrug_name,
        "is_supply": bool(is_supply),
        "is_realization": bool(is_realization),
        "sale_created_at": sale_created_at,
        "event_time": event_time,
        "event_hash": event_hash,
    }


def fetch_raw_sales(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    limit: int = 10000,
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

    raw_sales = fetch_raw_sales(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
        limit=50000,
    )

    if not raw_sales:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    events = []
    seen_hashes = set()

    for raw_row in raw_sales:
        event = build_financial_event(raw_row)

        if event is None:
            continue

        event_hash = event.get("event_hash")
        if event_hash in seen_hashes:
            continue

        seen_hashes.add(event_hash)
        events.append(event)

    rows_upserted = 0
    if events:
        rows_upserted = insert_events_batch(events, batch_size=100)

    newest_row = raw_sales[-1]

    return {
        "rows_read": len(raw_sales),
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