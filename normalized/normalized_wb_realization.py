import hashlib
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from db.client import supabase


SOURCE_TABLE = "raw_wb_realization"
TARGET_TABLE = "normalized_realization"
MARKETPLACE = "wb"


def get_watermark(state: dict[str, Any] | None) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def safe_decimal(value: Any) -> Optional[float]:
    if value in [None, ""]:
        return None

    try:
        return float(Decimal(str(value).replace(",", ".")))
    except (InvalidOperation, ValueError, TypeError):
        return None


def safe_str(value: Any) -> Optional[str]:
    if value in [None, ""]:
        return None

    return str(value)


def parse_dt(value: Any) -> Optional[str]:
    if value in [None, ""]:
        return None

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).isoformat()
        except ValueError:
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").isoformat()
            except ValueError:
                return None

    return None


def payload_value(payload: dict, *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in [None, ""]:
            return value

    return None


def build_product_key(marketplace_product_id: Any) -> Optional[str]:
    if marketplace_product_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_product_id}"


def build_variant_key(marketplace_variant_id: Any) -> Optional[str]:
    if marketplace_variant_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_variant_id}"


def build_event_hash(
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    report_id: Any,
    rrd_id: Any,
    srid: Any,
    event_type: Any,
    operation_type: Any,
) -> str:
    raw = f"{user_id}|{shop_id}|{marketplace}|{report_id}|{rrd_id}|{srid}|{event_type}|{operation_type}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_raw_realization(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    batch_size: int = 1000,
) -> list[dict]:
    rows: list[dict] = []
    offset = 0

    while True:
        query = (
            supabase
            .table(SOURCE_TABLE)
            .select("id,user_id,shop_id,marketplace,report_id,rrd_id,payload,updated_at")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", MARKETPLACE)
        )

        if last_raw_updated_at is not None:
            query = query.or_(
                f"updated_at.gt.{last_raw_updated_at},and(updated_at.eq.{last_raw_updated_at},id.gt.{last_raw_id})"
            )

        response = (
            query
            .order("updated_at", desc=False)
            .order("id", desc=False)
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        if not batch:
            break

        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_realization_event(raw_row: dict) -> Optional[dict]:
    payload = raw_row.get("payload") or {}
    if not isinstance(payload, dict):
        return None

    user_id = raw_row.get("user_id")
    shop_id = raw_row.get("shop_id")
    marketplace = raw_row.get("marketplace") or MARKETPLACE

    report_id = raw_row.get("report_id") or payload_value(
        payload,
        "realizationreport_id",
        "realization_report_id",
        "report_id",
    )
    rrd_id = raw_row.get("rrd_id") or payload_value(payload, "rrd_id", "rrdId")

    nm_id = payload_value(payload, "nm_id", "nmId")
    barcode = payload_value(payload, "barcode")
    srid = payload_value(payload, "srid")

    marketplace_product_id = safe_str(nm_id)
    marketplace_variant_id = safe_str(barcode)

    product_key = build_product_key(marketplace_product_id)
    variant_key = build_variant_key(marketplace_variant_id)

    seller_sku = safe_str(payload_value(
        payload,
        "sa_name",
        "supplierArticle",
        "supplier_article",
        "vendorCode",
    ))
    size_name = safe_str(payload_value(
        payload,
        "ts_name",
        "techSize",
        "tech_size",
        "size",
    ))

    event_type = payload_value(
        payload,
        "doc_type_name",
        "docTypeName",
        "supplier_oper_name",
        "supplierOperName",
        "event_type",
    ) or "realization"

    operation_type = payload_value(
        payload,
        "supplier_oper_name",
        "supplierOperName",
        "bonus_type_name",
        "bonusTypeName",
    ) or event_type
    supplier_oper_name_norm = str(operation_type or "").strip().lower()

    quantity = payload_value(payload, "quantity", "count", "delivery_amount", "return_amount")

    amount = payload_value(
        payload,
        "retail_amount",
        "retail_amount_withdisc_rub",
        "ppvz_for_pay",
        "ppvz_sales_commission",
        "delivery_rub",
        "storage_fee",
        "penalty",
        "deduction",
        "acceptance",
        "amount",
    )

    if supplier_oper_name_norm == "хранение":
        event_time = payload_value(
            payload,
            "rr_dt",
            "rrDt",
            "event_time",
        )
    else:
        event_time = payload_value(
            payload,
            "sale_dt",
            "saleDt",
            "order_dt",
            "orderDt",
            "rr_dt",
            "rrDt",
            "event_time",
        )

    event_hash = build_event_hash(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        report_id=report_id,
        rrd_id=rrd_id,
        srid=srid,
        event_type=event_type,
        operation_type=operation_type,
    )

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,

        "product_key": product_key,
        "variant_key": variant_key,
        "marketplace_product_id": marketplace_product_id,
        "marketplace_variant_id": marketplace_variant_id,
        "seller_sku": seller_sku,
        "size_name": size_name,

        "srid": safe_str(srid),

        "event_type": safe_str(event_type),
        "operation_type": safe_str(operation_type),

        "quantity": safe_decimal(quantity),
        "amount": safe_decimal(amount),
        "currency": safe_str(payload_value(payload, "currency_name", "currency", "currencyIsoCode4217")) or "RUB",

        "event_time": parse_dt(event_time),

        "raw_payload": payload,
        "event_hash": event_hash,
    }


def dedupe_rows(rows: list[dict]) -> list[dict]:
    seen = set()
    result = []

    for row in rows:
        event_hash = row.get("event_hash")
        if not event_hash or event_hash in seen:
            continue

        seen.add(event_hash)
        result.append(row)

    return result


def upsert_rows(rows: list[dict], batch_size: int = 100) -> int:
    sent = 0

    for index in range(0, len(rows), batch_size):
        batch = rows[index:index + batch_size]
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(batch, on_conflict="event_hash")
            .execute()
        )
        sent += len(batch)
        print(f"Sent batch: {min(index + batch_size, len(rows))}/{len(rows)}")

    return sent


def run_normalization_job(
    job: dict[str, Any],
    state: dict[str, Any] | None = None,
    registry_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_rows = fetch_raw_realization(
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

    events = []

    for raw_row in raw_rows:
        event = build_realization_event(raw_row)
        if not event:
            continue

        events.append(event)

    events = dedupe_rows(events)

    rows_upserted = 0
    if events:
        rows_upserted = upsert_rows(events)

    newest_row = raw_rows[-1]

    return {
        "rows_read": len(raw_rows),
        "rows_upserted": rows_upserted,
        "last_raw_updated_at": newest_row.get("updated_at"),
        "last_raw_id": newest_row.get("id"),
    }


if __name__ == "__main__":
    result = run_normalization_job(
        job={"user_id": 1, "shop_id": 1},
        state=None,
        registry_entry=None,
    )

    print(result)