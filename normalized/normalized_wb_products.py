import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


SOURCE_TABLE = "raw_wb_cards"
MARKETPLACE = "wb"
DEFAULT_SHOP_ID = 1
BATCH_SIZE = 100


PRODUCTS_TABLE = "normalized_products"
SIZES_TABLE = "normalized_product_variants"
DIMENSIONS_TABLE = "normalized_product_dimensions"
CHARACTERISTICS_TABLE = "normalized_product_characteristics"


def get_watermark(state: Optional[Dict[str, Any]]) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def parse_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            return {}

        return parsed if isinstance(parsed, dict) else {}

    return payload if isinstance(payload, dict) else {}


def payload_value(payload: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in [None, ""]:
            return value

    return default


def to_int(value: Any) -> Optional[int]:
    if value in [None, ""]:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value in [1, "1", "true", "True", "TRUE", "yes", "YES"]:
        return True

    return False


def build_product_key(marketplace_product_id: Any) -> str:
    return f"{MARKETPLACE}_{marketplace_product_id}"


def build_variant_key(marketplace_variant_id: Any) -> Optional[str]:
    if marketplace_variant_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_variant_id}"


def normalize_photos(card: Dict[str, Any]) -> List[Dict[str, Any]]:
    photos = card.get("photos") or []
    if not isinstance(photos, list):
        return []

    return [photo for photo in photos if isinstance(photo, dict)]


def get_video_url(card: Dict[str, Any]) -> Optional[str]:
    return payload_value(card, "video", "videoUrl", "video_url")


def normalize_raw_cards_payload(payload: Any) -> List[Dict[str, Any]]:
    payload = parse_payload(payload)

    if not payload:
        return []

    cards = payload.get("cards") or payload.get("data") or payload.get("products")

    if isinstance(cards, list):
        return [card for card in cards if isinstance(card, dict)]

    return [payload]


def build_product_row(raw_row: Dict[str, Any], card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    user_id = raw_row.get("user_id")
    shop_id = raw_row.get("shop_id") or DEFAULT_SHOP_ID

    nm_id = payload_value(card, "nmID", "nmId", "nm_id")
    if not user_id or not nm_id:
        return None

    marketplace_product_id = str(nm_id)
    marketplace_parent_product_id = payload_value(card, "imtID", "imtId", "imt_id")
    seller_sku = payload_value(card, "vendorCode", "vendor_code", "supplierArticle")
    subject_name = payload_value(card, "subjectName", "subject_name", "object")
    created_at_marketplace = payload_value(card, "createdAt", "created_at", "created_at_wb")
    updated_at_marketplace = payload_value(card, "updatedAt", "updated_at", "updated_at_wb")

    product_key = build_product_key(marketplace_product_id)
    photos_json = normalize_photos(card)
    video_url = get_video_url(card)

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": MARKETPLACE,
        "product_key": product_key,
        "marketplace_product_id": marketplace_product_id,
        "marketplace_parent_product_id": str(marketplace_parent_product_id) if marketplace_parent_product_id is not None else None,
        "seller_sku": seller_sku,
        "category_name": subject_name,
        "created_at_marketplace": created_at_marketplace,
        "updated_at_marketplace": updated_at_marketplace,
        "brand": payload_value(card, "brand", "brandName", "brand_name"),
        "title": payload_value(card, "title", "imtName", "name"),
        "description": payload_value(card, "description"),
        "photos_json": photos_json,
        "photos_count": len(photos_json),
        "main_photo_url": (photos_json[0].get("hq") or photos_json[0].get("big") or photos_json[0].get("square")) if photos_json else None,
        "video_url": video_url,
        "has_video": bool(video_url),
        "raw_payload": card,
        "subject_id": to_int(payload_value(card, "subjectID", "subjectId", "subject_id")),
        "subject_name": subject_name,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_size_rows(raw_row: Dict[str, Any], card: Dict[str, Any]) -> List[Dict[str, Any]]:
    product = build_product_row(raw_row, card)
    if not product:
        return []

    sizes = card.get("sizes") or []
    if not isinstance(sizes, list):
        return []

    rows: List[Dict[str, Any]] = []

    for size in sizes:
        if not isinstance(size, dict):
            continue

        chrt_id = payload_value(size, "chrtID", "chrtId", "chrt_id")
        if not chrt_id:
            continue

        marketplace_variant_id = str(chrt_id)
        size_name = payload_value(size, "techSize", "tech_size")
        variant_key = build_variant_key(marketplace_variant_id)

        skus = size.get("skus") or []
        if isinstance(skus, list) and skus:
            barcodes = [str(sku) for sku in skus if sku not in [None, ""]]
        else:
            barcodes = [None]

        for barcode in barcodes:
            rows.append(
                {
                    "user_id": product["user_id"],
                    "shop_id": product["shop_id"],
                    "marketplace": MARKETPLACE,
                    "product_key": product["product_key"],
                    "variant_key": variant_key,
                    "marketplace_product_id": product["marketplace_product_id"],
                    "marketplace_variant_id": marketplace_variant_id,
                    "size_name": size_name,
                    "barcode": barcode,
                    "seller_sku": product["seller_sku"],
                }
            )

    return rows


def build_dimension_row(raw_row: Dict[str, Any], card: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    product = build_product_row(raw_row, card)
    if not product:
        return None

    dimensions = card.get("dimensions") or {}
    if not isinstance(dimensions, dict):
        dimensions = {}

    return {
        "user_id": product["user_id"],
        "shop_id": product["shop_id"],
        "marketplace": MARKETPLACE,
        "product_key": product["product_key"],
        "marketplace_product_id": product["marketplace_product_id"],
        "width": dimensions.get("width"),
        "height": dimensions.get("height"),
        "length": dimensions.get("length"),
        "weight_brutto": dimensions.get("weightBrutto") or dimensions.get("weight_brutto"),
    }


def normalize_characteristic_value(value: Any) -> Optional[str]:
    if value in [None, ""]:
        return None

    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)

    return str(value)


def build_characteristic_rows(raw_row: Dict[str, Any], card: Dict[str, Any]) -> List[Dict[str, Any]]:
    product = build_product_row(raw_row, card)
    if not product:
        return []

    characteristics = card.get("characteristics") or []
    if not isinstance(characteristics, list):
        return []

    rows: List[Dict[str, Any]] = []

    for characteristic in characteristics:
        if not isinstance(characteristic, dict):
            continue

        name = payload_value(characteristic, "name")
        value = payload_value(characteristic, "value", "values")

        if not name:
            continue

        rows.append(
            {
                "user_id": product["user_id"],
                "shop_id": product["shop_id"],
                "marketplace": MARKETPLACE,
                "product_key": product["product_key"],
                "marketplace_product_id": product["marketplace_product_id"],
                "name": name,
                "value": normalize_characteristic_value(value),
            }
        )

    return rows


def fetch_raw_cards(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    limit: int = 1000,
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
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_rows(table_name: str, rows: List[Dict[str, Any]], on_conflict: str) -> int:
    if not rows:
        print(f"Nothing to upsert into {table_name}")
        return 0

    sent = 0

    for batch in chunked(rows, BATCH_SIZE):
        (
            supabase
            .table(table_name)
            .upsert(batch, on_conflict=on_conflict)
            .execute()
        )

        sent += len(batch)
        print(f"{table_name}: sent batch {sent}/{len(rows)}")

    return sent


def run_normalization_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    registry_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_rows = fetch_raw_cards(
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

    products_by_key: Dict[tuple, Dict[str, Any]] = {}
    sizes_by_key: Dict[tuple, Dict[str, Any]] = {}
    dimensions_by_key: Dict[tuple, Dict[str, Any]] = {}
    characteristics_by_key: Dict[tuple, Dict[str, Any]] = {}

    skipped_invalid = 0

    for raw_row in raw_rows:
        cards = normalize_raw_cards_payload(raw_row.get("payload"))

        for card in cards:
            product = build_product_row(raw_row, card)

            if not product:
                skipped_invalid += 1
                continue

            product_key = product["product_key"]
            products_by_key[(product["user_id"], product["shop_id"], product["marketplace"], product_key)] = product

            for size_row in build_size_rows(raw_row, card):
                sizes_by_key[
                    (
                        size_row["user_id"],
                        size_row["marketplace"],
                        size_row["product_key"],
                        size_row["variant_key"],
                        size_row["barcode"],
                    )
                ] = size_row

            dimension_row = build_dimension_row(raw_row, card)
            if dimension_row:
                dimensions_by_key[(dimension_row["user_id"], dimension_row["shop_id"], dimension_row["marketplace"], product_key)] = dimension_row

            for characteristic_row in build_characteristic_rows(raw_row, card):
                characteristics_by_key[
                    (
                        characteristic_row["user_id"],
                        characteristic_row["shop_id"],
                        characteristic_row["marketplace"],
                        characteristic_row["product_key"],
                        characteristic_row["name"],
                    )
                ] = characteristic_row

    products = list(products_by_key.values())
    sizes = list(sizes_by_key.values())
    dimensions = list(dimensions_by_key.values())
    characteristics = list(characteristics_by_key.values())

    print(f"Products prepared: {len(products)}")
    print(f"Sizes prepared: {len(sizes)}")
    print(f"Dimensions prepared: {len(dimensions)}")
    print(f"Characteristics prepared: {len(characteristics)}")
    print(f"Skipped invalid: {skipped_invalid}")

    products_upserted = upsert_rows(PRODUCTS_TABLE, products, "product_key")
    sizes_upserted = upsert_rows(SIZES_TABLE, sizes, "product_key,variant_key,barcode")
    dimensions_upserted = upsert_rows(DIMENSIONS_TABLE, dimensions, "product_key")
    characteristics_upserted = upsert_rows(CHARACTERISTICS_TABLE, characteristics, "product_key,name")

    newest_row = raw_rows[-1]

    return {
        "rows_read": len(raw_rows),
        "rows_upserted": (
            products_upserted
            + sizes_upserted
            + dimensions_upserted
            + characteristics_upserted
        ),
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