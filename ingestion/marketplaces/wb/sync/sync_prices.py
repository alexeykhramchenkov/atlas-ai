"""Thin Wildberries prices snapshot job-loader for Sync Orchestrator."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Optional

from db.client import supabase
from ingestion.marketplaces.wb.api.endpoints.prices import get_prices, get_quarantine_goods


MARKETPLACE = "wb"
SOURCE_NAME = "prices"
RAW_TABLE = "raw_wb_prices"
PRICE_LIMIT = 1000
QUARANTINE_LIMIT = 1000

ProgressCallback = Callable[[dict[str, Any]], None]


def parse_job_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value[:10])

    raise ValueError(f"Unsupported job date value: {value!r}")


def extract_price_goods(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    data = payload.get("data") or {}

    if isinstance(data, dict):
        goods = data.get("listGoods") or data.get("goods") or []
        if isinstance(goods, list):
            return goods

    goods = payload.get("listGoods") or payload.get("goods") or []
    if isinstance(goods, list):
        return goods

    return []


def extract_quarantine_goods(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("goods") or payload.get("listGoods") or []
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            goods = data.get("listGoods") or data.get("goods") or []
            if isinstance(goods, list):
                return goods

    return []


def is_raw_prices_snapshot_loaded(
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


def delete_raw_prices_snapshot(
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


def insert_raw_price_goods(
    user_id: int,
    shop_id: int,
    marketplace: str,
    goods: list[dict[str, Any]],
    snapshot_date: str,
    payload_type: str,
) -> int:
    rows: list[dict[str, Any]] = []

    for item in goods:
        nm_id = item.get("nmID") or item.get("nmId") or item.get("nm_id")

        rows.append(
            {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "nm_id": nm_id,
                "snapshot_date": snapshot_date,
                "payload_type": payload_type,
                "payload": item,
            }
        )

    if not rows:
        return 0

    supabase.table(RAW_TABLE).insert(rows).execute()
    return len(rows)


def run_sync_job(
    job: dict[str, Any],
    connection: dict[str, Any],
    rule: Optional[dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
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

    if is_raw_prices_snapshot_loaded(
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

        print(f"WB prices job | snapshot_date={snapshot_date} | already_loaded=true")

        return {
            "rows_fetched": 0,
            "rows_upserted": 0,
            "days_checked": days_checked,
            "days_loaded": days_loaded,
            "days_skipped": days_skipped,
        }

    rows_fetched = 0
    rows_upserted = 0

    delete_raw_prices_snapshot(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        snapshot_date=snapshot_date,
    )

    offset = 0
    while True:
        prices_payload = get_prices(
            limit=PRICE_LIMIT,
            offset=offset,
            api_token=api_token,
        )

        goods = extract_price_goods(prices_payload)
        rows_fetched += len(goods)
        rows_upserted += insert_raw_price_goods(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            goods=goods,
            snapshot_date=snapshot_date,
            payload_type="prices",
        )

        if progress_callback:
            progress_callback(
                {
                    "day": date_to,
                    "rows_fetched": rows_fetched,
                    "rows_upserted": rows_upserted,
                    "phase": "prices_page_completed",
                    "offset": offset,
                    "limit": PRICE_LIMIT,
                }
            )

        if not goods or len(goods) < PRICE_LIMIT:
            break

        offset += PRICE_LIMIT

    quarantine_offset = 0
    while True:
        quarantine_payload = get_quarantine_goods(
            limit=QUARANTINE_LIMIT,
            offset=quarantine_offset,
            api_token=api_token,
        )

        quarantine_goods = extract_quarantine_goods(quarantine_payload)
        rows_fetched += len(quarantine_goods)
        rows_upserted += insert_raw_price_goods(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            goods=quarantine_goods,
            snapshot_date=snapshot_date,
            payload_type="quarantine_goods",
        )

        if progress_callback:
            progress_callback(
                {
                    "day": date_to,
                    "rows_fetched": rows_fetched,
                    "rows_upserted": rows_upserted,
                    "phase": "quarantine_page_completed",
                    "offset": quarantine_offset,
                    "limit": QUARANTINE_LIMIT,
                }
            )

        if not quarantine_goods or len(quarantine_goods) < QUARANTINE_LIMIT:
            break

        quarantine_offset += QUARANTINE_LIMIT

    days_loaded = 1

    print(
        f"WB prices job | snapshot_date={snapshot_date} | "
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


def sync_wb_prices_job(
    job: dict[str, Any],
    connection: dict[str, Any],
    rule: Optional[dict[str, Any]] = None,
    progress_callback: Optional[ProgressCallback] = None,
) -> dict[str, int]:
    return run_sync_job(
        job=job,
        connection=connection,
        rule=rule,
        progress_callback=progress_callback,
    )
