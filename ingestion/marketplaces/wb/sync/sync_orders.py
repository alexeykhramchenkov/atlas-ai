"""Thin Wildberries orders job-loader for Sync Orchestrator."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from core.logger import logger
from db.client import supabase
from ingestion.marketplaces.wb.api.endpoints.orders import get_orders


MARKETPLACE = "wb"
SOURCE_NAME = "orders"
RAW_TABLE = "raw_wb_orders"

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


def iter_days(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def extract_order_date(order: dict[str, Any]) -> str | None:
    value = order.get("date") or order.get("lastChangeDate")
    if not value:
        return None
    return str(value)[:10]


def upsert_raw_orders(
    user_id: int,
    shop_id: int,
    marketplace: str,
    orders: list[dict[str, Any]],
) -> int:
    rows: list[dict[str, Any]] = []

    for order in orders:
        srid = order.get("srid")
        wb_id = str(order.get("gNumber") or srid or "")

        if not srid:
            continue

        rows.append(
            {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "source": "wb_statistics_api",
                "endpoint": "supplier/orders",
                "wb_id": wb_id,
                "nm_id": order.get("nmId") or order.get("nmID") or order.get("nm_id"),
                "srid": srid,
                "event_date": extract_order_date(order),
                "payload": order,
            }
        )

    if not rows:
        return 0

    logger.info(f"Upserting RAW orders rows: {len(rows)}")

    supabase.table(RAW_TABLE).upsert(
        rows,
        on_conflict="user_id,shop_id,marketplace,srid",
    ).execute()

    return len(rows)


def insert_empty_orders_day_marker(
    user_id: int,
    shop_id: int,
    marketplace: str,
    day: str,
    reason: str = "empty_api_payload",
) -> int:
    row = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source": "wb_statistics_api",
        "endpoint": "supplier/orders",
        "wb_id": f"empty:{day}",
        "nm_id": None,
        "srid": f"empty:{day}",
        "event_date": day,
        "payload": {
            "empty_marker": True,
            "empty_reason": reason,
            "date": day,
        },
    }

    supabase.table(RAW_TABLE).upsert(
        row,
        on_conflict="user_id,shop_id,marketplace,srid",
    ).execute()

    return 1


# === Additional functions for per-day sync ===
def is_raw_orders_day_loaded(user_id: int, shop_id: int, marketplace: str, day: str) -> bool:
    response = (
        supabase
        .table(RAW_TABLE)
        .select("id", count="exact")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("event_date", day)
        .limit(1)
        .execute()
    )

    return bool(response.count and response.count > 0)


def filter_orders_by_day(orders: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    return [order for order in orders if not order.get("empty_marker") and extract_order_date(order) == day]


def group_orders_by_day(orders: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for order in orders:
        if order.get("empty_marker"):
            continue

        order_day = extract_order_date(order)
        if not order_day:
            continue

        grouped.setdefault(order_day, []).append(order)

    return grouped


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

    job_date_from = parse_job_date(job["date_from"])
    date_to = parse_job_date(job["date_to"])

    if job.get("job_type") == "coverage_repair":
        date_from = job_date_from
    else:
        lookback_days = get_lookback_days(rule)
        date_from = min(job_date_from, date_to - timedelta(days=lookback_days - 1))

    date_from_str = date_from.isoformat()
    date_to_str = date_to.isoformat()

    logger.info(
        f"WB orders job window | job_from={job_date_from.isoformat()} | "
        f"effective_from={date_from_str} | to={date_to_str}"
    )

    rows_fetched = 0
    rows_upserted = 0
    days_checked = 0
    days_loaded = 0
    days_skipped = 0

    days = list(iter_days(date_from, date_to))
    missing_days: list[date] = []

    for day in days:
        day_str = day.isoformat()
        days_checked += 1

        if is_raw_orders_day_loaded(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            day=day_str,
        ):
            days_skipped += 1
            continue

        missing_days.append(day)

    if not missing_days:
        logger.info(
            f"WB orders job | from={date_from_str} | to={date_to_str} | "
            f"all_days_loaded=true | checked_days={days_checked} | skipped_days={days_skipped}"
        )
    else:
        latest_day = date_to
        has_historical_gaps = any(day < latest_day for day in missing_days)

        if has_historical_gaps:
            load_from = date_from
            days_to_process = days
            load_mode = "full_repair_window"
        else:
            load_from = min(missing_days)
            days_to_process = missing_days
            load_mode = "latest_missing_only"

        load_from_str = load_from.isoformat()

        logger.info(
            f"WB orders load mode | mode={load_mode} | "
            f"missing_days={len(missing_days)} | api_date_from={load_from_str} | date_to={date_to_str}"
        )

        orders = get_orders(
            date_from=load_from_str,
            flag=0,
            api_token=api_token,
        )
        grouped_orders = group_orders_by_day(orders or [])

        for day in days_to_process:
            day_str = day.isoformat()
            day_orders = grouped_orders.get(day_str, [])
            day_rows_fetched = len(day_orders)
            day_rows_upserted = upsert_raw_orders(
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                orders=day_orders,
            )

            if day_rows_fetched == 0 and day_rows_upserted == 0:
                day_rows_upserted = insert_empty_orders_day_marker(
                    user_id=user_id,
                    shop_id=shop_id,
                    marketplace=marketplace,
                    day=day_str,
                )

            rows_fetched += day_rows_fetched
            rows_upserted += day_rows_upserted
            days_loaded += 1

            logger.info(
                f"WB orders job | day={day_str} | mode={load_mode} | "
                f"fetched={day_rows_fetched} | upserted={day_rows_upserted}"
            )

            if progress_callback:
                progress_callback(
                    {
                        "day": day,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "day_completed",
                        "date_from": date_from_str,
                        "date_to": date_to_str,
                        "load_mode": load_mode,
                    }
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

    logger.info(
        f"WB orders job finished | from={date_from_str} | to={date_to_str} | "
        f"checked_days={days_checked} | loaded_days={days_loaded} | skipped_days={days_skipped} | "
        f"fetched={rows_fetched} | upserted={rows_upserted}"
    )

    return {
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "days_checked": days_checked,
        "days_loaded": days_loaded,
        "days_skipped": days_skipped,
    }


def sync_wb_orders_job(
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