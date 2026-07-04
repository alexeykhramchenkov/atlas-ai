"""Thin Wildberries product cards job-loader for Sync Orchestrator."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

from core.logger import logger
from db.client import supabase
from ingestion.marketplaces.wb.api.client import get_content_cards


MARKETPLACE = "wb"
SOURCE_NAME = "cards"
RAW_TABLE = "raw_wb_cards"

ProgressCallback = Callable[[dict[str, Any]], None]


def parse_job_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value[:10])

    raise ValueError(f"Unsupported job date value: {value!r}")


def extract_cards(response: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not response:
        return []

    cards = response.get("cards") or []
    if cards:
        return cards

    data = response.get("data") or {}
    if isinstance(data, dict):
        cards = data.get("cards") or []
        if cards:
            return cards

    return []


# --- Inserted functions ---
def is_raw_cards_snapshot_loaded(
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
        .eq("event_date", snapshot_date)
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


def delete_raw_cards_snapshot(
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
        .eq("event_date", snapshot_date)
        .execute()
    )


def insert_raw_cards(
    user_id: int,
    shop_id: int,
    marketplace: str,
    cards: list[dict[str, Any]],
    snapshot_date: str,
    raw_payload: Any,
) -> int:
    rows: list[dict[str, Any]] = []

    if cards:
        for card in cards:
            nm_id = card.get("nmID") or card.get("nmId") or card.get("nm_id")

            rows.append(
                {
                    "user_id": user_id,
                    "shop_id": shop_id,
                    "marketplace": marketplace,
                    "source": "wb_content_api",
                    "endpoint": "content/v2/get/cards/list",
                    "wb_id": str(nm_id or ""),
                    "nm_id": nm_id,
                    "event_date": snapshot_date,
                    "payload": card,
                }
            )
    else:
        rows.append(
            {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "source": "wb_content_api",
                "endpoint": "content/v2/get/cards/list",
                "wb_id": "",
                "nm_id": None,
                "event_date": snapshot_date,
                "payload": raw_payload if raw_payload else {"data": [], "empty_reason": "empty_api_payload"},
            }
        )

    logger.info(f"Inserting RAW cards rows: {len(rows)}")
    supabase.table(RAW_TABLE).insert(rows).execute()

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

    # cards is a snapshot/current-state source. Use job date_to as snapshot date.
    date_from = parse_job_date(job.get("date_from") or job.get("date_to"))
    date_to = parse_job_date(job.get("date_to") or job.get("date_from"))
    snapshot_date = date_to.isoformat()

    days_checked = 1
    days_loaded = 0
    days_skipped = 0

    if is_raw_cards_snapshot_loaded(
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

        logger.info(f"WB cards job | snapshot_date={snapshot_date} | already_loaded=true")

        return {
            "rows_fetched": 0,
            "rows_upserted": 0,
            "days_checked": days_checked,
            "days_loaded": days_loaded,
            "days_skipped": days_skipped,
        }

    response = get_content_cards(limit=100, api_token=api_token)
    cards = extract_cards(response)
    rows_fetched = len(cards)

    logger.info(f"Cards received from WB API: {rows_fetched}")

    delete_raw_cards_snapshot(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        snapshot_date=snapshot_date,
    )

    rows_upserted = insert_raw_cards(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        cards=cards,
        snapshot_date=snapshot_date,
        raw_payload=response,
    )
    days_loaded = 1

    if progress_callback:
        progress_callback(
            {
                "day": date_to,
                "rows_fetched": rows_fetched,
                "rows_upserted": rows_upserted,
                "phase": "snapshot_completed",
            }
        )

    logger.info(
        f"WB cards job | snapshot_date={snapshot_date} | "
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


def sync_wb_cards_job(
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
