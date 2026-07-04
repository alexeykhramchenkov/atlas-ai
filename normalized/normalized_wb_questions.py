from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.client import supabase


SOURCE_TABLE = "raw_wb_questions"
TARGET_TABLE = "normalized_questions"
MARKETPLACE = "wb"
BATCH_SIZE = 1000


def get_watermark(state: dict[str, Any] | None) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_datetime(value: Any) -> str | None:
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized_value = value.replace("Z", "+00:00")

        if "." in normalized_value:
            date_part, fraction_and_tz = normalized_value.split(".", 1)

            if "+" in fraction_and_tz:
                fraction_part, timezone_part = fraction_and_tz.split("+", 1)
                normalized_value = f"{date_part}.{fraction_part[:6]}+{timezone_part}"
            elif "-" in fraction_and_tz:
                fraction_part, timezone_part = fraction_and_tz.split("-", 1)
                normalized_value = f"{date_part}.{fraction_part[:6]}-{timezone_part}"
            else:
                normalized_value = f"{date_part}.{fraction_and_tz[:6]}"

        parsed = datetime.fromisoformat(normalized_value)
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.isoformat()


def payload_get(payload: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = payload

    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)

    return current if current is not None else default


def extract_question_payload(raw_payload: Any) -> dict[str, Any]:
    if not isinstance(raw_payload, dict):
        return {}

    data = raw_payload.get("data")
    if isinstance(data, dict):
        return data

    return raw_payload


def extract_is_answered(raw_payload: Any, question_payload: dict[str, Any]) -> bool:
    if isinstance(raw_payload, dict) and "is_answered" in raw_payload:
        return bool(raw_payload.get("is_answered"))

    answer = question_payload.get("answer")
    return bool(isinstance(answer, dict) and answer.get("text"))


def fetch_raw_questions(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    batch_size: int = BATCH_SIZE,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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


def normalize_question(row: dict[str, Any]) -> dict[str, Any] | None:
    raw_payload = row.get("payload") or {}
    question_payload = extract_question_payload(raw_payload)

    question_id = question_payload.get("id")
    if not question_id:
        return None

    product_details = question_payload.get("productDetails") or {}
    answer = question_payload.get("answer") or {}

    marketplace_product_id = product_details.get("nmId") or product_details.get("nmID") or product_details.get("nm_id")
    product_key = f"wb_{marketplace_product_id}" if marketplace_product_id else None

    is_answered = extract_is_answered(raw_payload, question_payload)

    return {
        "user_id": row.get("user_id"),
        "shop_id": row.get("shop_id"),
        "marketplace": row.get("marketplace") or MARKETPLACE,

        "question_id": str(question_id),

        "product_key": product_key,
        "marketplace_product_id": int(marketplace_product_id) if marketplace_product_id else None,
        "marketplace_variant_id": product_details.get("imtId"),

        "brand": product_details.get("brandName"),
        "product_name": product_details.get("productName"),
        "supplier_article": product_details.get("supplierArticle"),

        "question_text": question_payload.get("text"),

        "is_answered": is_answered,
        "answer_text": answer.get("text") if isinstance(answer, dict) else None,

        "question_created_at": parse_datetime(question_payload.get("createdDate")),
        "answer_created_at": parse_datetime(answer.get("createDate")) if isinstance(answer, dict) else None,

        "question_state": question_payload.get("state"),

        "is_warned": bool(question_payload.get("isWarned", False)),
        "was_viewed": bool(question_payload.get("wasViewed", False)),

        "raw_payload": raw_payload,
        "created_at": utc_now_iso(),
    }


def deduplicate_questions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduplicated: dict[tuple[Any, Any, str, str], dict[str, Any]] = {}

    for row in rows:
        key = (
            row.get("user_id"),
            row.get("shop_id"),
            row.get("marketplace") or MARKETPLACE,
            str(row.get("question_id")),
        )
        deduplicated[key] = row

    return list(deduplicated.values())


def upsert_normalized_questions(rows: list[dict[str, Any]], batch_size: int = BATCH_SIZE) -> int:
    if not rows:
        return 0

    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        supabase.table(TARGET_TABLE).upsert(
            batch,
            on_conflict="user_id,shop_id,marketplace,question_id",
        ).execute()
        total += len(batch)
        print(f"Rows sent to normalized_questions: {total}")

    return total


def run_normalization_job(
    job: dict[str, Any],
    state: dict[str, Any] | None = None,
    registry_entry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_rows = fetch_raw_questions(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
        batch_size=BATCH_SIZE,
    )

    if not raw_rows:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    normalized_rows = []

    for row in raw_rows:
        normalized_row = normalize_question(row)
        if not normalized_row:
            continue
        normalized_rows.append(normalized_row)

    normalized_rows = deduplicate_questions(normalized_rows)

    rows_upserted = 0
    if normalized_rows:
        rows_upserted = upsert_normalized_questions(normalized_rows)

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
