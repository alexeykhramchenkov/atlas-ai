"""Thin Wildberries realization report job-loader for Sync Orchestrator.

Realization is report-based, not day-coverage based.
The sync checks a wide report window every run, discovers report IDs,
loads only new reports, and stores all report rows in RAW.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable

from db.client import supabase
from ingestion.marketplaces.wb.api.endpoints.finance import get_realization_report_all_pages


MARKETPLACE = "wb"
SOURCE_NAME = "realization"
RAW_TABLE = "raw_wb_realization"
REPORTS_TABLE = "system_sync_reports"
DEFAULT_LOOKBACK_DAYS = 70
WINDOW_SIZE_DAYS = 7

ProgressCallback = Callable[[dict[str, Any]], None]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_job_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value[:10])

    raise ValueError(f"Unsupported job date value: {value!r}")


# Helper for weekly windows
def build_weekly_windows(window_from: date, window_to: date) -> list[tuple[date, date]]:
    windows: list[tuple[date, date]] = []
    current_from = window_from

    while current_from <= window_to:
        current_to = min(current_from + timedelta(days=WINDOW_SIZE_DAYS - 1), window_to)
        windows.append((current_from, current_to))
        current_from = current_to + timedelta(days=1)

    return windows


def extract_realization_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload

    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return data

    return []


def extract_report_id(item: dict[str, Any]) -> str | None:
    value = item.get("realizationreport_id") or item.get("realizationReportId")
    if value is None:
        return None
    return str(value)


def extract_rrd_id(item: dict[str, Any]) -> str | None:
    value = item.get("rrd_id") or item.get("rrdId")
    if value is None:
        return None
    return str(value)


# --- Added helpers for extracting report period ---
def parse_optional_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])

    return None


def extract_report_period(
    report_rows: list[dict[str, Any]],
    fallback_from: date,
    fallback_to: date,
) -> tuple[date, date]:
    report_from_values: list[date] = []
    report_to_values: list[date] = []

    for item in report_rows:
        report_from = parse_optional_date(
            item.get("date_from")
            or item.get("dateFrom")
            or item.get("report_from")
            or item.get("reportFrom")
        )
        report_to = parse_optional_date(
            item.get("date_to")
            or item.get("dateTo")
            or item.get("report_to")
            or item.get("reportTo")
        )

        if report_from:
            report_from_values.append(report_from)
        if report_to:
            report_to_values.append(report_to)

    return (
        min(report_from_values) if report_from_values else fallback_from,
        max(report_to_values) if report_to_values else fallback_to,
    )


def parse_report_id_for_raw(report_id: str | None) -> int | None:
    if not report_id:
        return None

    try:
        return int(report_id)
    except ValueError:
        return None


def parse_rrd_id_for_raw(rrd_id: str | None) -> int | None:
    if not rrd_id:
        return None

    try:
        return int(rrd_id)
    except ValueError:
        return None


def group_rows_by_report_id(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}

    for item in rows:
        report_id = extract_report_id(item)
        if not report_id:
            continue

        grouped.setdefault(report_id, []).append(item)

    return grouped


def deduplicate_report_rows(report_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove duplicate rows inside one WB realization report by rrd_id."""
    seen_rrd_ids: set[str] = set()
    deduplicated_rows: list[dict[str, Any]] = []

    for item in report_rows:
        rrd_id = extract_rrd_id(item)
        if not rrd_id:
            continue

        if rrd_id in seen_rrd_ids:
            continue

        seen_rrd_ids.add(rrd_id)
        deduplicated_rows.append(item)

    return deduplicated_rows


def fetch_loaded_report_ids(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
) -> set[str]:
    response = (
        supabase
        .table(REPORTS_TABLE)
        .select("report_id")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .eq("status", "loaded")
        .execute()
    )

    return {str(row["report_id"]) for row in response.data or [] if row.get("report_id") is not None}


def upsert_report_registry(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    report_id: str,
    report_from: date,
    report_to: date,
    status: str,
    rows_fetched: int = 0,
    rows_upserted: int = 0,
    payload: dict[str, Any] | None = None,
) -> None:
    now = utc_now_iso()

    row = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "report_id": report_id,
        "report_from": report_from.isoformat(),
        "report_to": report_to.isoformat(),
        "status": status,
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "payload": payload or {},
        "updated_at": now,
    }

    if status == "loaded":
        row["loaded_at"] = now

    supabase.table(REPORTS_TABLE).upsert(
        row,
        on_conflict="user_id,shop_id,marketplace,source_name,report_id",
    ).execute()


def upsert_raw_realization_report(
    user_id: int,
    shop_id: int,
    marketplace: str,
    report_id: str,
    report_rows: list[dict[str, Any]],
    report_from: date,
    report_to: date,
) -> int:
    rows: list[dict[str, Any]] = []

    for item in report_rows:
        rrd_id = extract_rrd_id(item)
        if not rrd_id:
            continue

        nm_id = item.get("nm_id") or item.get("nmId")
        srid = item.get("srid")

        rows.append(
            {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "report_id": parse_report_id_for_raw(report_id),
                "rrd_id": parse_rrd_id_for_raw(rrd_id),
                "nm_id": nm_id,
                "srid": srid,
                "report_date": report_to.isoformat(),
                "report_from": report_from.isoformat(),
                "report_to": report_to.isoformat(),
                "payload": item,
            }
        )

    if not rows:
        return 0

    supabase.table(RAW_TABLE).upsert(
        rows,
        on_conflict="user_id,shop_id,marketplace,report_id,rrd_id",
    ).execute()

    return len(rows)


def upsert_sync_state(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    date_from: date,
    date_to: date,
    rows_fetched: int,
    rows_upserted: int,
    reports_discovered: int,
    reports_loaded: int,
    reports_skipped: int,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    now_iso = utc_now_iso()
    reports_processed = reports_loaded + reports_skipped
    missing_reports_count = max(reports_discovered - reports_processed, 0)
    coverage_percent = (
        round((reports_processed / reports_discovered) * 100, 2)
        if reports_discovered > 0
        else 100
    )

    row = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "last_attempt_at": now_iso,
        "updated_at": now_iso,
        "last_rows_fetched": rows_fetched,
        "last_rows_upserted": rows_upserted,
        "coverage_days_required": reports_discovered,
        "coverage_days_actual": reports_processed,
        "coverage_percent": coverage_percent,
        "coverage_from": date_from.isoformat(),
        "coverage_to": date_to.isoformat(),
        "last_loaded_date_from": date_from.isoformat(),
        "last_loaded_date_to": date_to.isoformat(),
        "missing_days_count": missing_reports_count,
        "repair_required": missing_reports_count > 0,
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

    window_to = parse_job_date(job.get("date_to") or job.get("date_from"))
    lookback_days = int((rule or {}).get("repair_window_days") or DEFAULT_LOOKBACK_DAYS)
    window_from = parse_job_date(job["date_from"]) if job.get("job_type") == "coverage_repair" else window_to - timedelta(days=lookback_days - 1)
    # The current endpoint accepts the bounded period and returns actual report IDs.
    # Keep grouping/deduplication below, without redundant overlapping weekly fetches.
    weekly_windows = [(window_from, window_to)]

    loaded_report_ids = fetch_loaded_report_ids(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=SOURCE_NAME,
    )

    rows_fetched = 0
    rows_upserted = 0
    discovered_reports = 0
    skipped_reports = 0
    loaded_reports = 0

    all_rows: list[dict[str, Any]] = []

    for api_window_from, api_window_to in weekly_windows:
        window_rows = get_realization_report_all_pages(
            date_from=api_window_from.isoformat(),
            date_to=api_window_to.isoformat(),
            api_token=api_token,
        )
        rows_fetched += len(window_rows)
        all_rows.extend(window_rows)

        if progress_callback:
            progress_callback(
                {
                    "day": api_window_to,
                    "rows_fetched": rows_fetched,
                    "rows_upserted": rows_upserted,
                    "phase": "window_fetched",
                    "window_from": api_window_from.isoformat(),
                    "window_to": api_window_to.isoformat(),
                    "window_rows": len(window_rows),
                }
            )

    grouped_reports = group_rows_by_report_id(all_rows)
    discovered_reports = len(grouped_reports)

    for report_id, report_rows in grouped_reports.items():
        if report_id in loaded_report_ids:
            skipped_reports += 1
            continue

        deduplicated_report_rows = deduplicate_report_rows(report_rows)
        report_from, report_to = extract_report_period(
            report_rows=deduplicated_report_rows,
            fallback_from=window_from,
            fallback_to=window_to,
        )

        upsert_report_registry(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            source_name=SOURCE_NAME,
            report_id=report_id,
            report_from=report_from,
            report_to=report_to,
            status="discovered",
            rows_fetched=len(deduplicated_report_rows),
            rows_upserted=0,
            payload={
                "window_from": window_from.isoformat(),
                "window_to": window_to.isoformat(),
                "raw_report_rows": len(report_rows),
                "deduplicated_report_rows": len(deduplicated_report_rows),
                "report_from": report_from.isoformat(),
                "report_to": report_to.isoformat(),
            },
        )

        upserted_for_report = upsert_raw_realization_report(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            report_id=report_id,
            report_rows=deduplicated_report_rows,
            report_from=report_from,
            report_to=report_to,
        )

        rows_upserted += upserted_for_report
        loaded_reports += 1
        loaded_report_ids.add(report_id)

        upsert_report_registry(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            source_name=SOURCE_NAME,
            report_id=report_id,
            report_from=report_from,
            report_to=report_to,
            status="loaded",
            rows_fetched=len(deduplicated_report_rows),
            rows_upserted=upserted_for_report,
            payload={
                "window_from": window_from.isoformat(),
                "window_to": window_to.isoformat(),
                "raw_report_rows": len(report_rows),
                "deduplicated_report_rows": len(deduplicated_report_rows),
                "report_from": report_from.isoformat(),
                "report_to": report_to.isoformat(),
            },
        )

        if progress_callback:
            progress_callback(
                {
                    "day": report_to,
                    "rows_fetched": rows_fetched,
                    "rows_upserted": rows_upserted,
                    "phase": "report_loaded",
                    "report_id": report_id,
                    "report_from": report_from.isoformat(),
                    "report_to": report_to.isoformat(),
                    "report_rows": len(deduplicated_report_rows),
                    "raw_report_rows": len(report_rows),
                    "loaded_reports": loaded_reports,
                    "skipped_reports": skipped_reports,
                }
            )

    upsert_sync_state(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=SOURCE_NAME,
        date_from=window_from,
        date_to=window_to,
        rows_fetched=rows_fetched,
        rows_upserted=rows_upserted,
        reports_discovered=discovered_reports,
        reports_loaded=loaded_reports,
        reports_skipped=skipped_reports,
        status="success",
    )

    print(
        f"WB realization job | window={window_from} → {window_to} | weekly_windows={len(weekly_windows)} | "
        f"rows_fetched={rows_fetched} | rows_upserted={rows_upserted} | "
        f"reports={discovered_reports} | loaded={loaded_reports} | skipped={skipped_reports}"
    )

    return {
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "reports_discovered": discovered_reports,
        "reports_loaded": loaded_reports,
        "reports_skipped": skipped_reports,
    }


def sync_wb_realization_job(
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
