import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


PRODUCTS_TABLE = "normalized_products"
VARIANTS_TABLE = "normalized_product_variants"
CHARACTERISTICS_TABLE = "normalized_product_characteristics"
DIMENSIONS_TABLE = "normalized_product_dimensions"
TARGET_TABLE = "snapshots_products_daily"
BATCH_SIZE = 100


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def make_hash(value: Any) -> str:
    return hashlib.sha256(stable_json(value).encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    return " ".join(str(value).strip().lower().split())


# Utility: convert to int or None if empty/invalid
def to_int_or_none(value: Any) -> Optional[int]:
    if value in [None, ""]:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_products(batch_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(PRODUCTS_TABLE)
            .select("*")
            .order("product_key")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def fetch_variants(batch_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(VARIANTS_TABLE)
            .select("product_key,variant_key,marketplace_variant_id,size_name,barcode,seller_sku")
            .order("product_key")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def fetch_characteristics(batch_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(CHARACTERISTICS_TABLE)
            .select("product_key,id,name,value")
            .order("product_key")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def fetch_dimensions(batch_size: int = 1000) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(DIMENSIONS_TABLE)
            .select("product_key,width,height,length,weight_brutto")
            .order("product_key")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def group_by_product_key(rows: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    for row in rows:
        product_key = row.get("product_key")
        if not product_key:
            continue

        grouped.setdefault(product_key, []).append(row)

    return grouped


def index_by_product_key(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        product_key = row.get("product_key")
        if not product_key:
            continue

        indexed[str(product_key)] = row

    return indexed


def get_photos(product: Dict[str, Any]) -> List[Dict[str, Any]]:
    photos = product.get("photos_json") or product.get("photos") or []
    if not isinstance(photos, list):
        return []

    return [photo for photo in photos if isinstance(photo, dict)]


def get_photo_fields(product: Dict[str, Any]) -> tuple[Optional[str], Optional[str], List[Dict[str, Any]]]:
    photos = get_photos(product)

    if photos:
        first_photo = photos[0]
        return first_photo.get("hq"), first_photo.get("big"), photos

    return product.get("photo_hq"), product.get("photo_big"), photos


def build_title_hash(product: Dict[str, Any]) -> str:
    return make_hash({"title": normalize_text(product.get("title"))})


def build_description_hash(product: Dict[str, Any]) -> str:
    return make_hash({"description": normalize_text(product.get("description"))})


def build_photos_hash(photo_hq: Optional[str], photo_big: Optional[str]) -> str:
    return make_hash({"photo_hq": photo_hq, "photo_big": photo_big})


def build_video_hash(video_url: Optional[str]) -> str:
    return make_hash({"video_url": video_url})


def build_variants_hash(variants: List[Dict[str, Any]]) -> str:
    normalized = []

    for variant in variants:
        normalized.append(
            {
                "variant_key": variant.get("variant_key"),
                "marketplace_variant_id": variant.get("marketplace_variant_id"),
                "size_name": normalize_text(variant.get("size_name")),
                "barcode": normalize_text(variant.get("barcode")),
                "seller_sku": normalize_text(variant.get("seller_sku")),
            }
        )

    return make_hash(sorted(normalized, key=lambda x: (str(x.get("variant_key")), str(x.get("barcode")))))


def build_dimensions_hash(dimensions: Optional[Dict[str, Any]]) -> str:
    dimensions = dimensions or {}

    return make_hash(
        {
            "width": dimensions.get("width"),
            "height": dimensions.get("height"),
            "length": dimensions.get("length"),
            "weight_brutto": dimensions.get("weight_brutto"),
            "dimensions_is_valid": dimensions.get("dimensions_is_valid"),
        }
    )


def build_characteristics_json(characteristics: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []

    for item in characteristics:
        result.append(
            {
                "characteristic_id": item.get("id"),
                "name": item.get("name"),
                "value": item.get("value"),
            }
        )

    return sorted(result, key=lambda x: (str(x.get("characteristic_id")), str(x.get("name"))))


def is_empty_characteristic_value(value: Any) -> bool:
    if value in [None, ""]:
        return True

    if isinstance(value, list):
        return len(value) == 0

    return False


def build_content_hash(title_hash: str, description_hash: str, characteristics_hash: str) -> str:
    return make_hash(
        {
            "title_hash": title_hash,
            "description_hash": description_hash,
            "characteristics_hash": characteristics_hash,
        }
    )


def build_media_hash(photos_hash: str, video_hash: str) -> str:
    return make_hash({"photos_hash": photos_hash, "video_hash": video_hash})


def build_characteristics_hash(characteristics: List[Dict[str, Any]]) -> str:
    normalized = []

    for item in characteristics:
        normalized.append(
            {
                "characteristic_id": item.get("id"),
                "name": normalize_text(item.get("name")),
                "value": normalize_text(item.get("value")),
            }
        )

    return make_hash(sorted(normalized, key=lambda x: (str(x.get("characteristic_id")), x.get("name") or "")))


def build_seo_hash(
    product: Dict[str, Any],
    characteristics: List[Dict[str, Any]],
) -> str:
    seo_payload = {
        "title": normalize_text(product.get("title")),
        "description": normalize_text(product.get("description")),
        "brand": normalize_text(product.get("brand")),
        "subject_id": product.get("subject_id"),
        "subject_name": normalize_text(product.get("subject_name")),
        "characteristics_hash": build_characteristics_hash(characteristics),
    }

    return make_hash(seo_payload)


def build_snapshot_row(
    product: Dict[str, Any],
    variants: List[Dict[str, Any]],
    characteristics: List[Dict[str, Any]],
    dimensions: Optional[Dict[str, Any]],
    snapshot_date: str,
) -> Dict[str, Any]:
    photo_hq, photo_big, photos = get_photo_fields(product)
    video_url = product.get("video_url") or product.get("video")
    has_video = bool(video_url)
    photos_count = len(photos) if photos else int(bool(photo_hq or photo_big))
    main_photo_url = photo_hq or photo_big
    characteristics_json = build_characteristics_json(characteristics)
    filled_characteristics_count = sum(1 for item in characteristics if not is_empty_characteristic_value(item.get("value")))
    empty_characteristics_count = sum(1 for item in characteristics if is_empty_characteristic_value(item.get("value")))
    title_hash = build_title_hash(product)
    description_hash = build_description_hash(product)
    photos_hash = build_photos_hash(photo_hq, photo_big)
    video_hash = build_video_hash(video_url)
    variants_hash = build_variants_hash(variants)
    characteristics_hash = build_characteristics_hash(characteristics)
    dimensions_hash = build_dimensions_hash(dimensions)
    content_hash = build_content_hash(title_hash, description_hash, characteristics_hash)
    media_hash = build_media_hash(photos_hash, video_hash)
    nm_id = to_int_or_none(product.get("nm_id")) or to_int_or_none(product.get("marketplace_product_id"))

    return {
        "user_id": product.get("user_id"),
        "shop_id": product.get("shop_id"),
        "marketplace": product.get("marketplace"),
        "snapshot_date": snapshot_date,
        "product_key": product.get("product_key"),
        "marketplace_product_id": product.get("marketplace_product_id"),
        "marketplace_parent_product_id": product.get("marketplace_parent_product_id"),
        "seller_sku": product.get("seller_sku"),
        "category_name": product.get("category_name"),
        "nm_id": nm_id,
        "imt_id": product.get("imt_id"),
        "nm_uuid": product.get("nm_uuid"),
        "brand": product.get("brand"),
        "title": product.get("title"),
        "vendor_code": product.get("vendor_code") or product.get("seller_sku"),
        "subject_id": product.get("subject_id"),
        "subject_name": product.get("subject_name"),
        "description": product.get("description"),
        "photo_hq": photo_hq,
        "photo_big": photo_big,
        "photos_json": photos,
        "photos_count": photos_count,
        "main_photo_url": main_photo_url,
        "video_url": video_url,
        "has_video": has_video,
        "need_kiz": product.get("need_kiz") or False,
        "kiz_marked": product.get("kiz_marked") or False,
        "is_swatch_try_on": product.get("is_swatch_try_on") or False,
        "variants_count": len(variants),
        "sizes_count": len(variants),
        "barcodes_count": len({variant.get("barcode") for variant in variants if variant.get("barcode")}),
        "characteristics_count": len(characteristics),
        "characteristics_json": characteristics_json,
        "filled_characteristics_count": filled_characteristics_count,
        "empty_characteristics_count": empty_characteristics_count,
        "width": dimensions.get("width") if dimensions else None,
        "height": dimensions.get("height") if dimensions else None,
        "length": dimensions.get("length") if dimensions else None,
        "weight_brutto": dimensions.get("weight_brutto") if dimensions else None,
        "dimensions_is_valid": None,
        "title_hash": title_hash,
        "description_hash": description_hash,
        "photos_hash": photos_hash,
        "video_hash": video_hash,
        "variants_hash": variants_hash,
        "characteristics_hash": characteristics_hash,
        "dimensions_hash": dimensions_hash,
        "content_hash": content_hash,
        "media_hash": media_hash,
        "seo_hash": build_seo_hash(product, characteristics),
        "updated_at_wb": product.get("updated_at_wb") or product.get("updated_at_marketplace"),
        "created_at_marketplace": product.get("created_at_marketplace"),
        "updated_at_marketplace": product.get("updated_at_marketplace"),
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
            .upsert(batch, on_conflict="user_id,shop_id,marketplace,product_key,snapshot_date")
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

    print("Fetching normalized products...")
    products = fetch_products()
    print(f"Products fetched: {len(products)}")

    print("Fetching normalized variants...")
    variants = fetch_variants()
    variants_by_product = group_by_product_key(variants)
    print(f"Variants fetched: {len(variants)}")

    print("Fetching normalized product characteristics...")
    characteristics = fetch_characteristics()
    characteristics_by_product = group_by_product_key(characteristics)
    print(f"Characteristics fetched: {len(characteristics)}")

    print("Fetching normalized product dimensions...")
    dimensions = fetch_dimensions()
    dimensions_by_product = index_by_product_key(dimensions)
    print(f"Dimensions fetched: {len(dimensions)}")

    snapshots: List[Dict[str, Any]] = []

    for product in products:
        product_key = product.get("product_key")
        if not product_key:
            continue

        snapshots.append(
            build_snapshot_row(
                product=product,
                variants=variants_by_product.get(product_key, []),
                characteristics=characteristics_by_product.get(product_key, []),
                dimensions=dimensions_by_product.get(product_key),
                snapshot_date=snapshot_date,
            )
        )

    print(f"Snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No product snapshots to upsert")
        return {
            "rows_read": len(products),
            "rows_upserted": 0,
            "last_processed_date": snapshot_date,
        }

    sent = upsert_snapshots(snapshots)
    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(products),
        "rows_upserted": sent,
        "last_processed_date": snapshot_date,
    }


def build_snapshots_products_daily(snapshot_date: Optional[str] = None) -> None:
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
    build_snapshots_products_daily()