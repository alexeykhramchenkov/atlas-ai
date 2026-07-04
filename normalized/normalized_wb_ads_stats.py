import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from db.client import supabase



SOURCE_TABLE = "raw_wb_ads_stats"
TARGET_TABLE = "normalized_ads_stats"
MARKETPLACE = "wb"
AD_PLATFORM = "wb_ads"
BATCH_SIZE = 100


def get_watermark(state: Optional[Dict[str, Any]]) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def payload_value(payload: Dict[str, Any], *keys: str, default=None):
    for key in keys:
        value = payload.get(key) if isinstance(payload, dict) else None
        if value not in [None, ""]:
            return value
    return default


def to_int(value: Any, default: int = 0) -> int:
    if value in [None, ""]:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def to_number(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_date(value: Any) -> Optional[str]:
    if not value:
        return None
    value = str(value)
    return value[:10]


def build_product_key(marketplace_product_id: Any) -> Optional[str]:
    if marketplace_product_id in [None, "", 0, "0"]:
        return None
    return f"{MARKETPLACE}_{marketplace_product_id}"


def build_event_hash(*parts: Any) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()



def fetch_raw_ads_stats(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
    query = (
        supabase
        .table(SOURCE_TABLE)
        .select("id,user_id,shop_id,marketplace,payload,loaded_at,updated_at")
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


def as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def extract_days(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, list):
        result: List[Dict[str, Any]] = []
        for item in payload:
            result.extend(extract_days(item))
        return result

    if not isinstance(payload, dict):
        return []

    advert_id = payload_value(payload, "advertId", "advert_id", "ad_id")

    days = payload.get("days")
    if isinstance(days, list):
        result = []
        for day in days:
            if isinstance(day, dict):
                day_copy = dict(day)
                if advert_id is not None and day_copy.get("advertId") is None:
                    day_copy["advertId"] = advert_id
                result.append(day_copy)
        return result

    if payload.get("date") or payload.get("day"):
        return [payload]

    data = payload.get("data")
    if isinstance(data, list):
        result = []
        for item in data:
            result.extend(extract_days(item))
        return result

    if isinstance(data, dict):
        if advert_id is not None and data.get("advertId") is None:
            data = dict(data)
            data["advertId"] = advert_id
        if isinstance(data.get("days"), list):
            return extract_days(data)
        if data.get("date") or data.get("day"):
            return [data]

    return []


def extract_apps(day: Dict[str, Any]) -> List[Dict[str, Any]]:
    apps = day.get("apps")
    if isinstance(apps, list):
        result = []
        for app in apps:
            if isinstance(app, dict):
                app_copy = dict(app)
                if day.get("advertId") is not None and app_copy.get("advertId") is None:
                    app_copy["advertId"] = day.get("advertId")
                result.append(app_copy)
        return result

    return [day]


def extract_products(app: Dict[str, Any]) -> List[Dict[str, Any]]:
    nms = app.get("nms")
    if isinstance(nms, list):
        return nms

    products = app.get("products")
    if isinstance(products, list):
        return products

    nm = app.get("nm")
    if isinstance(nm, list):
        return nm

    if app.get("nmId") or app.get("nmID") or app.get("nm_id"):
        return [app]

    return []


def build_stat_row(raw_row: Dict[str, Any], day: Dict[str, Any], app: Dict[str, Any], product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    user_id = raw_row.get("user_id")
    shop_id = raw_row.get("shop_id")
    marketplace = raw_row.get("marketplace") or MARKETPLACE

    date = normalize_date(payload_value(day, "date", "day"))
    ad_id = (
        payload_value(raw_row, "ad_id", default=None)
        or payload_value(day, "advertId", "advert_id", "ad_id")
        or payload_value(app, "advertId", "advert_id", "ad_id")
    )

    nm_id = payload_value(product, "nmId", "nmID", "nm_id")
    marketplace_product_id = str(nm_id) if nm_id not in [None, ""] else None
    product_key = build_product_key(marketplace_product_id)

    if not user_id or not shop_id or not date or not ad_id or not product_key:
        return None

    views = to_int(payload_value(product, "views", default=0))
    clicks = to_int(payload_value(product, "clicks", default=0))
    orders = to_int(payload_value(product, "orders", default=0))
    canceled = to_int(payload_value(product, "canceled", "cancelled", default=0))
    add_to_cart = to_int(payload_value(product, "atbs", "add_to_cart", "addToCart", default=0))
    shks = to_int(payload_value(product, "shks", default=0))

    spend = to_number(payload_value(product, "sum", "spend", default=0))
    revenue = to_number(payload_value(product, "sum_price", "sumPrice", "revenue", default=0))

    event_hash = build_event_hash(user_id, shop_id, marketplace, AD_PLATFORM, date, ad_id, product_key)

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "ad_platform": AD_PLATFORM,
        "date": date,
        "ad_id": to_int(ad_id),
        "campaign_id": str(ad_id),

        "product_key": product_key,
        "marketplace_product_id": marketplace_product_id,
        "brand": payload_value(product, "brand"),
        "title": payload_value(product, "name", "title"),
        "seller_sku": payload_value(product, "vendorCode", "vendor_code"),
        "subject_id": to_int(payload_value(product, "subjectID", "subjectId", "subject_id"), default=None) if payload_value(product, "subjectID", "subjectId", "subject_id") is not None else None,
        "subject_name": payload_value(product, "subjectName", "subject_name"),

        "views": views,
        "clicks": clicks,
        "orders": orders,
        "canceled": canceled,
        "add_to_cart": add_to_cart,
        "shks": shks,
        "spend": spend,
        "revenue": revenue,
        "currency": "RUB",

        "raw_payload": {"day": day, "app": app, "product": product},
        "event_hash": event_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_rows(raw_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = raw_row.get("payload") or {}
    if isinstance(payload, dict):
        raw_ad_id = payload_value(payload, "advertId", "advert_id", "ad_id")
        if raw_ad_id is not None:
            raw_row = dict(raw_row)
            raw_row["ad_id"] = raw_ad_id

    rows_by_hash: Dict[str, Dict[str, Any]] = {}

    for day in extract_days(payload):
        for app in extract_apps(day):
            products = extract_products(app)

            for product in products:
                row = build_stat_row(raw_row, day, app, product)
                if not row:
                    continue

                event_hash = row["event_hash"]
                existing = rows_by_hash.get(event_hash)

                if existing is None:
                    rows_by_hash[event_hash] = row
                    continue

                for field in [
                    "views",
                    "clicks",
                    "orders",
                    "canceled",
                    "add_to_cart",
                    "shks",
                ]:
                    existing[field] = to_int(existing.get(field)) + to_int(row.get(field))

                for field in ["spend", "revenue"]:
                    existing[field] = to_number(existing.get(field)) + to_number(row.get(field))

                existing["updated_at"] = datetime.now(timezone.utc).isoformat()

    return list(rows_by_hash.values())


def upsert_rows(rows: List[Dict[str, Any]]) -> int:
    sent = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        supabase.table(TARGET_TABLE).upsert(batch, on_conflict="event_hash").execute()
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

    raw_rows = fetch_raw_ads_stats(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
        limit=50000,
    )

    if not raw_rows:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    rows_by_hash: Dict[str, Dict[str, Any]] = {}

    for raw_row in raw_rows:
        rows = build_rows(raw_row)
        for row in rows:
            rows_by_hash[row["event_hash"]] = row

    rows = list(rows_by_hash.values())

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
        job={"user_id": 1, "shop_id": 1},
        state=None,
        registry_entry=None,
    )

    print(result)