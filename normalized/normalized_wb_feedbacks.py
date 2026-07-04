import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase



SOURCE_TABLE = "raw_wb_feedbacks"
TARGET_TABLE = "normalized_feedbacks"
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
        value = payload.get(key)
        if value not in [None, ""]:
            return value
    return default


def parse_payload(payload: Any) -> Any:
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}
    return payload


def extract_feedbacks(payload: Any) -> list[dict]:
    """
    WB feedbacks usually come as:
    {"data": {"data": {"feedbacks": [...]}}}
    """
    payload = parse_payload(payload)

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    if payload.get("id") and isinstance(payload.get("productDetails"), dict):
        return [payload]

    data = payload.get("data")
    if isinstance(data, dict) and data.get("id") and isinstance(data.get("productDetails"), dict):
        return [data]

    if isinstance(data, dict):
        nested_data = data.get("data")
        if isinstance(nested_data, dict):
            feedbacks = nested_data.get("feedbacks")
            if isinstance(feedbacks, list):
                return [item for item in feedbacks if isinstance(item, dict)]

        feedbacks = data.get("feedbacks")
        if isinstance(feedbacks, list):
            return [item for item in feedbacks if isinstance(item, dict)]

    for key in ("feedbacks", "items", "rows", "list", "payload"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    return []


def safe_int(value: Any) -> Optional[int]:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_bool(value: Any) -> bool:
    return bool(value)


def count_photos(photo_links: Any) -> int:
    if isinstance(photo_links, list):
        return len(photo_links)
    return 0


def has_video(video: Any) -> bool:
    if video is None:
        return False
    if isinstance(video, list):
        return len(video) > 0
    if isinstance(video, dict):
        return len(video) > 0
    return bool(video)


def has_answer(answer: Any) -> bool:
    if answer is None:
        return False
    if isinstance(answer, str):
        return answer.strip() != ""
    if isinstance(answer, dict):
        return len(answer) > 0
    return bool(answer)


def answer_to_text(answer: Any) -> Optional[str]:
    if answer is None:
        return None
    if isinstance(answer, str):
        return answer
    if isinstance(answer, dict):
        for key in ("text", "answer", "message"):
            value = answer.get(key)
            if value:
                return str(value)
        return json.dumps(answer, ensure_ascii=False)
    return str(answer)


def list_to_json(value: Any) -> Any:
    if isinstance(value, list):
        return value
    return None


def build_event_hash(raw_row: Dict[str, Any], feedback: Dict[str, Any]) -> str:
    feedback_id = payload_value(feedback, "id", default="")
    created_at = payload_value(feedback, "createdDate", "created_at", default="")

    product_details = feedback.get("productDetails") or {}
    if not isinstance(product_details, dict):
        product_details = {}

    nm_id = payload_value(product_details, "nmId", "nmID", "nm_id", default="")
    size = payload_value(product_details, "size", default="")

    raw_key = f"{MARKETPLACE}|feedback|{feedback_id}|{nm_id}|{size}|{created_at}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def build_product_key(marketplace_product_id: Any) -> Optional[str]:
    if marketplace_product_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_product_id}"


def build_variant_key(marketplace_variant_id: Any) -> Optional[str]:
    if marketplace_variant_id in [None, "", 0, "0"]:
        return None

    return f"{MARKETPLACE}_{marketplace_variant_id}"


def build_feedback_event(raw_row: Dict[str, Any], feedback: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    feedback_id = payload_value(feedback, "id")
    if not feedback_id:
        return None

    product_details = feedback.get("productDetails") or {}
    if not isinstance(product_details, dict):
        product_details = {}

    nm_id = safe_int(payload_value(product_details, "nmId", "nmID", "nm_id"))
    size = payload_value(product_details, "size")

    marketplace_product_id = str(nm_id) if nm_id else None

    product_key = build_product_key(marketplace_product_id)

    # WB feedback API does not return a real variant identifier
    # (barcode/chrtID/sizeID), only the size value.
    # Therefore feedbacks are linked by product_key + size_name.
    marketplace_variant_id = None
    variant_key = None

    size_name = str(size) if size is not None else None
    seller_sku = payload_value(product_details, "supplierArticle", "supplier_article")

    photo_links = feedback.get("photoLinks")
    photo_count = count_photos(photo_links)
    video = feedback.get("video")
    answer = feedback.get("answer")

    created_at = payload_value(feedback, "createdDate", "created_at")
    last_order_created_at = payload_value(feedback, "lastOrderCreatedAt", "last_order_created_at")
    rating = safe_int(payload_value(feedback, "productValuation", "rating"))
    event_hash = build_event_hash(raw_row, feedback)

    return {
        "user_id": raw_row.get("user_id"),
        "shop_id": raw_row.get("shop_id"),
        "marketplace": MARKETPLACE,

        "feedback_id": str(feedback_id),

        "product_key": product_key,
        "marketplace_product_id": marketplace_product_id,
        "variant_key": variant_key,
        "marketplace_variant_id": marketplace_variant_id,
        "size_name": size_name,
        "seller_sku": seller_sku,

        "product_name": payload_value(product_details, "productName", "product_name"),
        "brand": payload_value(product_details, "brandName", "brand"),
        "subject_id": safe_int(payload_value(feedback, "subjectId", "subject_id")),
        "subject_name": payload_value(feedback, "subjectName", "subject_name"),
        "color": payload_value(feedback, "color"),

        "rating": rating,
        "pros": payload_value(feedback, "pros"),
        "cons": payload_value(feedback, "cons"),
        "text": payload_value(feedback, "text"),
        "tags": list_to_json(feedback.get("bables")),

        "order_status": payload_value(feedback, "orderStatus", "order_status"),
        "matching_size": payload_value(feedback, "matchingSize", "matching_size"),

        "has_photo": photo_count > 0,
        "photo_count": photo_count,
        "has_video": has_video(video),

        "has_answer": has_answer(answer),
        "answer_text": answer_to_text(answer),
        "was_viewed": safe_bool(payload_value(feedback, "wasViewed", "was_viewed", default=False)),

        "user_name": payload_value(feedback, "userName", "user_name"),

        "created_at": created_at,
        "last_order_created_at": last_order_created_at,
        "last_order_shk_id": str(payload_value(feedback, "lastOrderShkId", "last_order_shk_id")) if payload_value(feedback, "lastOrderShkId", "last_order_shk_id") else None,

        "event_hash": event_hash,
    }



def fetch_raw_feedbacks(
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


def upsert_feedbacks(events: list[Dict[str, Any]], batch_size: int = BATCH_SIZE) -> int:
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

    raw_rows = fetch_raw_feedbacks(
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

    events = []
    seen_hashes = set()

    for raw_row in raw_rows:
        payload = parse_payload(raw_row.get("payload") or raw_row.get("raw_payload"))
        feedbacks = extract_feedbacks(payload)

        for feedback in feedbacks:
            event = build_feedback_event(raw_row, feedback)

            if event is None:
                continue

            event_hash = event.get("event_hash")
            if event_hash in seen_hashes:
                continue

            seen_hashes.add(event_hash)
            events.append(event)

    rows_upserted = 0
    if events:
        rows_upserted = upsert_feedbacks(events)

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