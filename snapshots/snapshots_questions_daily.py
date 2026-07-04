from __future__ import annotations
import re

from datetime import date, datetime, timezone
from typing import Any

from db.client import supabase


SOURCE_TABLE = "normalized_questions"
TARGET_TABLE = "snapshots_questions_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 1000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        normalized_value = value.replace("Z", "+00:00")
        normalized_value = re.sub(
            r"\.(\d{1,})([+-]\d{2}:\d{2})$",
            lambda match: f".{match.group(1)[:6].ljust(6, '0')}{match.group(2)}",
            normalized_value,
        )
        normalized_value = re.sub(
            r"\.(\d{1,})$",
            lambda match: f".{match.group(1)[:6].ljust(6, '0')}",
            normalized_value,
        )
        parsed = datetime.fromisoformat(normalized_value)
    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def safe_pct(part: float, total: float) -> float:
    if not total:
        return 0.0
    return round((part / total) * 100, 2)


def fetch_normalized_questions(batch_size: int = BATCH_SIZE) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", MARKETPLACE)
            .order("question_created_at", desc=False)
            .order("id", desc=False)
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        if not batch:
            break

        rows.extend(batch)
        print(f"Fetched normalized questions batch: {len(rows)}")

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_group_key(row: dict[str, Any]) -> tuple[Any, Any, str, str, int | None, date] | None:
    question_created_at = parse_datetime(row.get("question_created_at"))
    if not question_created_at:
        return None

    product_key = row.get("product_key") or "__unknown__"
    marketplace_product_id = row.get("marketplace_product_id")

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        product_key,
        marketplace_product_id,
        question_created_at.date(),
    )


def build_empty_group(row: dict[str, Any], snapshot_date: date) -> dict[str, Any]:
    return {
        "user_id": row.get("user_id"),
        "shop_id": row.get("shop_id"),
        "marketplace": row.get("marketplace") or MARKETPLACE,
        "snapshot_date": snapshot_date.isoformat(),
        "product_key": row.get("product_key") or "__unknown__",
        "marketplace_product_id": row.get("marketplace_product_id"),
        "questions_count": 0,
        "answered_count": 0,
        "unanswered_count": 0,
        "answer_rate_pct": 0,
        "avg_answer_time_hours": 0,
        "_answer_time_hours_sum": 0.0,
        "_answer_time_count": 0,
        "created_at": utc_now_iso(),
    }


def apply_question_row(item: dict[str, Any], row: dict[str, Any]) -> None:
    item["questions_count"] += 1

    is_answered = bool(row.get("is_answered"))
    if is_answered:
        item["answered_count"] += 1
    else:
        item["unanswered_count"] += 1

    question_created_at = parse_datetime(row.get("question_created_at"))
    answer_created_at = parse_datetime(row.get("answer_created_at"))

    if is_answered and question_created_at and answer_created_at:
        delta_hours = (answer_created_at - question_created_at).total_seconds() / 3600
        if delta_hours >= 0:
            item["_answer_time_hours_sum"] += delta_hours
            item["_answer_time_count"] += 1


def finalize_snapshot_row(item: dict[str, Any]) -> dict[str, Any]:
    questions_count = float(item.get("questions_count") or 0)
    answered_count = float(item.get("answered_count") or 0)
    answer_time_count = int(item.pop("_answer_time_count", 0) or 0)
    answer_time_sum = float(item.pop("_answer_time_hours_sum", 0.0) or 0.0)

    item["answer_rate_pct"] = safe_pct(answered_count, questions_count)
    item["avg_answer_time_hours"] = round(answer_time_sum / answer_time_count, 2) if answer_time_count else 0

    return item


def build_snapshots(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, Any, str, str, int | None, date], dict[str, Any]] = {}
    skipped_rows = 0

    for row in rows:
        key = build_group_key(row)
        if not key:
            skipped_rows += 1
            continue

        snapshot_date = key[-1]
        if key not in grouped:
            grouped[key] = build_empty_group(row, snapshot_date=snapshot_date)

        apply_question_row(grouped[key], row)

    print(f"Question rows skipped in snapshots: {skipped_rows}")
    return [finalize_snapshot_row(item) for item in grouped.values()]


def upsert_snapshots(rows: list[dict[str, Any]], batch_size: int = BATCH_SIZE) -> int:
    if not rows:
        return 0

    total = 0
    for start in range(0, len(rows), batch_size):
        batch = rows[start:start + batch_size]
        supabase.table(TARGET_TABLE).upsert(
            batch,
            on_conflict="user_id,shop_id,marketplace,product_key,snapshot_date",
        ).execute()
        total += len(batch)
        print(f"Rows sent to snapshots_questions_daily: {total}")

    return total



def run_snapshot_job(
    job: dict[str, Any],
    state: dict[str, Any] | None,
    registry_entry: dict[str, Any],
) -> dict[str, Any]:
    print("Fetching normalized questions...")
    source_rows = fetch_normalized_questions()
    print(f"Normalized questions fetched: {len(source_rows)}")

    snapshot_rows = build_snapshots(source_rows)
    print(f"Question snapshots prepared: {len(snapshot_rows)}")

    if not snapshot_rows:
        print("No question snapshots to upsert")
        return {
            "rows_read": len(source_rows),
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    upserted = upsert_snapshots(snapshot_rows)
    print(f"Question snapshots upserted: {upserted}")

    last_processed_date = max(row.get("snapshot_date") for row in snapshot_rows if row.get("snapshot_date"))

    return {
        "rows_read": len(source_rows),
        "rows_upserted": upserted,
        "last_processed_date": last_processed_date,
    }


def build_questions_snapshots() -> None:
    result = run_snapshot_job(
        job={},
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_questions_snapshots()