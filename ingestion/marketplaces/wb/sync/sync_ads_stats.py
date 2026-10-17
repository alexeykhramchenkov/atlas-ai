"""Thin Wildberries ads stats job-loader for Sync Orchestrator."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import time
from typing import Any, Callable, Iterable

from db.client import supabase
from ingestion.marketplaces.wb.api.endpoints.ads_stats import get_ads_fullstats


MARKETPLACE = "wb"
SOURCE_NAME = "ads_stats"
RAW_ADS_TABLE = "raw_wb_ads"
RAW_ADS_STATS_TABLE = "raw_wb_ads_stats"
BATCH_SIZE = 50

ProgressCallback = Callable[[dict[str, Any]], None]


def parse_job_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value[:10])

    raise ValueError(f"Unsupported job date value: {value!r}")


def get_lookback_days(rule: dict[str, Any] | None, default_days: int = 70) -> int:
    if not rule:
        return default_days

    value = (
        rule.get("daily_window_days")
        or rule.get("repair_window_days")
        or rule.get("coverage_days_required")
        or default_days
    )

    try:
        return max(int(value), 1)
    except (TypeError, ValueError):
        return default_days


def chunked(items: list[int], size: int) -> Iterable[list[int]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def iter_days(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def extract_advert_ids(payload: Any) -> set[int]:
    advert_ids: set[int] = set()

    if isinstance(payload, dict):
        advert_id = payload.get("advertId") or payload.get("advert_id") or payload.get("id")
        if advert_id:
            try:
                advert_ids.add(int(advert_id))
            except (TypeError, ValueError):
                pass

        for key in ("adverts", "advert_list", "data", "campaigns", "items", "list"):
            value = payload.get(key)
            if isinstance(value, (dict, list)):
                advert_ids.update(extract_advert_ids(value))

    elif isinstance(payload, list):
        for item in payload:
            advert_ids.update(extract_advert_ids(item))

    return advert_ids


def load_advert_ids(user_id: int, shop_id: int, limit: int = 10000) -> list[int]:
    response = (
        supabase
        .table(RAW_ADS_TABLE)
        .select("advert_id,payload")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", MARKETPLACE)
        .order("id", desc=True)
        .limit(limit)
        .execute()
    )

    advert_ids: set[int] = set()

    for row in response.data or []:
        advert_id = row.get("advert_id")
        if advert_id:
            try:
                advert_ids.add(int(advert_id))
            except (TypeError, ValueError):
                pass

        advert_ids.update(extract_advert_ids(row.get("payload")))

    return sorted(advert_ids)



def is_raw_ads_stats_day_loaded(user_id: int, shop_id: int, marketplace: str, day: str) -> bool:
    response = (
        supabase
        .table(RAW_ADS_STATS_TABLE)
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("date_from", day)
        .eq("date_to", day)
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


def delete_raw_ads_stats_day(user_id: int, shop_id: int, marketplace: str, day: str) -> None:
    (
        supabase
        .table(RAW_ADS_STATS_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("date_from", day)
        .eq("date_to", day)
        .execute()
    )


def insert_raw_ads_stats(
    user_id: int,
    shop_id: int,
    marketplace: str,
    day: str,
    advert_ids: list[int],
    payload: Any,
) -> int:
    row = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "date_from": day,
        "date_to": day,
        "advert_ids": advert_ids,
        "payload": payload,
        "source_table": RAW_ADS_TABLE,
        "source": "adv/v3/fullstats",
    }

    supabase.table(RAW_ADS_STATS_TABLE).insert(row).execute()
    return 1


def run_sync_job(
    job: dict[str, Any],
    connection: dict[str, Any],
    rule: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict[str, int]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    api_token = connection.get("api_token")

    job_date_from = parse_job_date(job["date_from"])
    date_to = parse_job_date(job["date_to"])
    if job.get("job_type") == "auto_sync":
        date_to -= timedelta(days=1)

    if job.get("job_type") == "coverage_repair":
        date_from = job_date_from
    else:
        lookback_days = get_lookback_days(rule)
        date_from = min(job_date_from, date_to - timedelta(days=lookback_days - 1))

    print(
        "WB ads_stats job window | "
        f"job_from={job_date_from.isoformat()} | "
        f"effective_from={date_from.isoformat()} | "
        f"to={date_to.isoformat()}"
    )

    request_sleep_sec = int((rule or {}).get("request_sleep_sec") or 0)

    rows_fetched = 0
    rows_upserted = 0
    days_checked = 0
    days_loaded = 0
    days_skipped = 0

    advert_ids = load_advert_ids(user_id=user_id, shop_id=shop_id)
    print(f"WB ads_stats job | found advert_ids={len(advert_ids)}")

    if not advert_ids:
        for day in iter_days(date_from, date_to):
            day_str = day.isoformat()
            days_checked += 1

            if is_raw_ads_stats_day_loaded(
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                day=day_str,
            ) and not (job.get("job_type") == "auto_sync" and day == date_to):
                days_skipped += 1
                continue

            delete_raw_ads_stats_day(
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                day=day_str,
            )
            rows_upserted += insert_raw_ads_stats(
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                day=day_str,
                advert_ids=[],
                payload={"data": [], "empty_reason": "no_advert_ids"},
            )
            days_loaded += 1

            if progress_callback:
                progress_callback(
                    {
                        "day": day,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "empty_day_completed",
                    }
                )
            if request_sleep_sec > 0 and day < date_to:
                time.sleep(request_sleep_sec)

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

    for day in iter_days(date_from, date_to):
        day_str = day.isoformat()
        days_checked += 1

        if is_raw_ads_stats_day_loaded(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            day=day_str,
        ) and not (job.get("job_type") == "auto_sync" and day == date_to):
            days_skipped += 1
            print(f"WB ads_stats job | day={day_str} | already_loaded=true")
            continue

        delete_raw_ads_stats_day(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            day=day_str,
        )

        batches = list(chunked(advert_ids, batch_size))
        for batch_index, ids_batch in enumerate(batches):
            payload = get_ads_fullstats(
                advert_ids=ids_batch,
                date_from=day_str,
                date_to=day_str,
                api_token=api_token,
            )

            rows_fetched += 1
            rows_upserted += insert_raw_ads_stats(
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                day=day_str,
                advert_ids=ids_batch,
                payload=payload if payload else {"data": [], "empty_reason": "empty_api_payload"},
            )

            print(
                f"WB ads_stats job | day={day_str} | advert_ids={len(ids_batch)}"
            )

            if progress_callback:
                progress_callback(
                    {
                        "day": day,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "batch_completed",
                        "batch_size": len(ids_batch),
                    }
                )

            is_last_batch = batch_index == len(batches) - 1
            if request_sleep_sec > 0 and not is_last_batch:
                if progress_callback:
                    progress_callback(
                        {
                            "day": day,
                            "rows_fetched": rows_fetched,
                            "rows_upserted": rows_upserted,
                            "phase": "before_batch_sleep",
                            "batch_size": len(ids_batch),
                        }
                    )
                time.sleep(request_sleep_sec)

        if progress_callback:
            progress_callback(
                {
                    "day": day,
                    "rows_fetched": rows_fetched,
                    "rows_upserted": rows_upserted,
                    "phase": "day_completed",
                }
            )
        days_loaded += 1

        if request_sleep_sec > 0 and day < date_to:
            if progress_callback:
                progress_callback(
                    {
                        "day": day,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "before_day_sleep",
                    }
                )
            time.sleep(request_sleep_sec)

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

    print(
        "WB ads_stats job finished | "
        f"from={date_from.isoformat()} | "
        f"to={date_to.isoformat()} | "
        f"checked_days={days_checked} | "
        f"loaded_days={days_loaded} | "
        f"skipped_days={days_skipped} | "
        f"rows_fetched={rows_fetched} | "
        f"rows_upserted={rows_upserted}"
    )

    return {
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "days_checked": days_checked,
        "days_loaded": days_loaded,
        "days_skipped": days_skipped,
    }


def sync_wb_ads_stats_job(
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
