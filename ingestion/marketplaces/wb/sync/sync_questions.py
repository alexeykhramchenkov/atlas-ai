"""Thin Wildberries questions snapshot job-loader for Sync Orchestrator."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from db.client import supabase
from ingestion.marketplaces.wb.api.endpoints.questions import get_questions


MARKETPLACE = "wb"
SOURCE_NAME = "questions"
RAW_TABLE = "raw_wb_questions"
TAKE = 5000

ProgressCallback = Callable[[dict[str, Any]], None]


def parse_job_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value[:10])

    raise ValueError(f"Unsupported job date value: {value!r}")


def extract_questions(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    data = payload.get("data") or {}

    if isinstance(data, dict):
        questions = data.get("questions") or data.get("items") or []
        if isinstance(questions, list):
            return questions

    if isinstance(data, list):
        return data

    questions = payload.get("questions") or payload.get("items") or []
    if isinstance(questions, list):
        return questions

    return []


def is_raw_questions_snapshot_loaded(
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_date: str,
) -> bool:
    response = (
        supabase
        .table(RAW_TABLE)
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("snapshot_date", snapshot_date)
        .limit(1)
        .execute()
    )

    return bool(response.count and response.count > 0)


def upsert_sync_state(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    date_from: date,
    date_to: date,
    rows_fetched: int,
    rows_upserted: int,
    days_checked: int,
    days_loaded: int,
    days_skipped: int,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    now_iso = datetime.utcnow().isoformat()
    coverage_days_required = max((date_to - date_from).days + 1, 0)
    coverage_days_actual = days_skipped + days_loaded
    coverage_percent = (
        round((coverage_days_actual / coverage_days_required) * 100, 2)
        if coverage_days_required > 0
        else 100
    )
    missing_days_count = max(coverage_days_required - coverage_days_actual, 0)

    row = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "last_attempt_at": now_iso,
        "updated_at": now_iso,
        "last_rows_fetched": rows_fetched,
        "last_rows_upserted": rows_upserted,
        "coverage_days_required": coverage_days_required,
        "coverage_days_actual": coverage_days_actual,
        "coverage_percent": coverage_percent,
        "coverage_from": date_from.isoformat(),
        "coverage_to": date_to.isoformat(),
        "last_loaded_date_from": date_from.isoformat(),
        "last_loaded_date_to": date_to.isoformat(),
        "missing_days_count": missing_days_count,
        "repair_required": missing_days_count > 0,
        "status": status,
        "error_message": error_message,
    }

    if status == "success":
        row["last_success_at"] = now_iso
        row["error_code"] = None

    supabase.table("system_sync_state").upsert(
        row,
        on_conflict="user_id,shop_id,marketplace,source_name",
    ).execute()


def delete_raw_questions_snapshot(
    user_id: int,
    shop_id: int,
    marketplace: str,
    snapshot_date: str,
) -> None:
    (
        supabase
        .table(RAW_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("snapshot_date", snapshot_date)
        .execute()
    )


def insert_raw_questions(
    user_id: int,
    shop_id: int,
    marketplace: str,
    questions: list[dict[str, Any]],
    is_answered: bool,
    snapshot_date: str,
) -> int:
    rows: list[dict[str, Any]] = []

    for question in questions:
        question_id = question.get("id") or question.get("questionId")
        nm_id = question.get("nmId") or question.get("nmID") or question.get("nm_id")
        created_date = question.get("createdDate") or question.get("created_date") or question.get("date")

        if question_id is None:
            continue

        rows.append(
            {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "question_id": str(question_id),
                "nm_id": nm_id,
                "created_date": created_date,
                "snapshot_date": snapshot_date,
                "payload": {
                    "is_answered": is_answered,
                    "data": question,
                },
            }
        )

    if not rows:
        return 0

    supabase.table(RAW_TABLE).upsert(
        rows,
        on_conflict="user_id,shop_id,marketplace,snapshot_date,question_id",
    ).execute()

    return len(rows)


def run_sync_job(
    job: dict[str, Any],
    connection: dict[str, Any],
    rule: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    api_token = connection.get("api_token")

    date_from = parse_job_date(job.get("date_from") or job.get("date_to"))
    date_to = parse_job_date(job.get("date_to") or job.get("date_from"))
    snapshot_date = date_to.isoformat()

    days_checked = 1
    days_loaded = 0
    days_skipped = 0

    if is_raw_questions_snapshot_loaded(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        snapshot_date=snapshot_date,
    ):
        days_skipped = 1
        upsert_sync_state(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            source_name=SOURCE_NAME,
            date_from=date_from,
            date_to=date_to,
            rows_fetched=0,
            rows_upserted=0,
            days_checked=days_checked,
            days_loaded=days_loaded,
            days_skipped=days_skipped,
            status="success",
        )

        print(f"WB questions job | snapshot_date={snapshot_date} | already_loaded=true")

        return {
            "rows_fetched": 0,
            "rows_upserted": 0,
            "days_checked": days_checked,
            "days_loaded": days_loaded,
            "days_skipped": days_skipped,
        }

    rows_fetched = 0
    rows_upserted = 0

    delete_raw_questions_snapshot(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        snapshot_date=snapshot_date,
    )

    for is_answered in (False, True):
        skip = 0

        while True:
            payload = get_questions(
                is_answered=is_answered,
                take=TAKE,
                skip=skip,
                api_token=api_token,
            )

            questions = extract_questions(payload)
            fetched_count = len(questions)
            rows_fetched += fetched_count
            rows_upserted += insert_raw_questions(
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                questions=questions,
                is_answered=is_answered,
                snapshot_date=snapshot_date,
            )

            if progress_callback:
                progress_callback(
                    {
                        "day": date_to,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "page_completed",
                        "is_answered": is_answered,
                        "skip": skip,
                        "take": TAKE,
                    }
                )

            if not questions or fetched_count < TAKE:
                break

            skip += TAKE

    days_loaded = 1

    print(
        f"WB questions job | snapshot_date={snapshot_date} | "
        f"fetched={rows_fetched} | inserted={rows_upserted}"
    )

    upsert_sync_state(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=SOURCE_NAME,
        date_from=date_from,
        date_to=date_to,
        rows_fetched=rows_fetched,
        rows_upserted=rows_upserted,
        days_checked=days_checked,
        days_loaded=days_loaded,
        days_skipped=days_skipped,
        status="success",
    )

    return {
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "days_checked": days_checked,
        "days_loaded": days_loaded,
        "days_skipped": days_skipped,
    }


def sync_wb_questions_job(
    job: dict[str, Any],
    connection: dict[str, Any],
    rule: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    return run_sync_job(
        job=job,
        connection=connection,
        rule=rule,
        progress_callback=progress_callback,
    )