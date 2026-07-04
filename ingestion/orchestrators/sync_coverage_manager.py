from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any

from db.client import supabase
from ingestion.orchestrators.sync_rule_manager import get_sync_rule
from ingestion.orchestrators.sync_source_manager import get_sync_source


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value[:10])
    raise ValueError(f"Unsupported date value: {value!r}")


def iter_days(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def get_required_coverage_days(rule: dict[str, Any] | None) -> int:
    if not rule:
        return 70

    for key in ("daily_window_days", "repair_window_days"):
        value = rule.get(key)
        if value is not None:
            value_int = int(value)
            if value_int > 0:
                return value_int

    return 70


def get_date_column(source: dict[str, Any]) -> str:
    return source.get("date_column") or "period_start"


def fetch_loaded_day_counts(
    raw_table_name: str,
    date_column: str,
    user_id: int,
    shop_id: int,
    marketplace: str,
    date_from: date,
    date_to: date,
    page_size: int = 1000,
) -> dict[date, int]:
    day_counts: dict[date, int] = {}
    offset = 0

    while True:
        response = (
            supabase
            .table(raw_table_name)
            .select(date_column)
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .gte(date_column, date_from.isoformat())
            .lte(date_column, date_to.isoformat())
            .order(date_column, desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = response.data or []

        for row in rows:
            value = row.get(date_column)
            if value:
                day = parse_date(value)
                day_counts[day] = day_counts.get(day, 0) + 1

        if len(rows) < page_size:
            break

        offset += page_size

    return day_counts


def fetch_coverage_day_counts(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    date_from: date,
    date_to: date,
    page_size: int = 1000,
) -> dict[date, int]:
    day_counts: dict[date, int] = {}
    offset = 0

    while True:
        response = (
            supabase
            .table("system_sync_coverage_days")
            .select("coverage_date")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("source_name", source_name)
            .eq("status", "loaded")
            .gte("coverage_date", date_from.isoformat())
            .lte("coverage_date", date_to.isoformat())
            .order("coverage_date", desc=False)
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = response.data or []

        for row in rows:
            value = row.get("coverage_date")
            if value:
                day = parse_date(value)
                day_counts[day] = day_counts.get(day, 0) + 1

        if len(rows) < page_size:
            break

        offset += page_size

    return day_counts


def detect_damaged_days(
    day_counts: dict[date, int],
    min_rows_ratio: float = 0.9,
) -> list[date]:
    if len(day_counts) < 7:
        return []

    positive_counts = [count for count in day_counts.values() if count > 0]
    if not positive_counts:
        return []

    baseline = median(positive_counts)
    min_expected_rows = max(1, int(baseline * min_rows_ratio))

    damaged_days = []
    for day, count in day_counts.items():
        if count < min_expected_rows:
            damaged_days.append(day)

    return sorted(damaged_days)


def update_coverage_state(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    coverage_from: date,
    coverage_to: date,
    required_days: int,
    loaded_days: set[date],
    missing_days: list[date],
) -> dict[str, Any]:
    coverage_days_actual = len(loaded_days)
    missing_days_count = len(missing_days)
    coverage_percent = round((coverage_days_actual / required_days) * 100, 2) if required_days else 0
    repair_required = missing_days_count > 0
    now = datetime.now(timezone.utc).isoformat()

    payload = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "coverage_days_required": required_days,
        "coverage_days_actual": coverage_days_actual,
        "coverage_percent": coverage_percent,
        "coverage_from": coverage_from.isoformat(),
        "coverage_to": coverage_to.isoformat(),
        "first_available_date": min(loaded_days).isoformat() if loaded_days else None,
        "last_available_date": max(loaded_days).isoformat() if loaded_days else None,
        "missing_days_count": missing_days_count,
        "repair_required": repair_required,
        "repair_from": missing_days[0].isoformat() if missing_days else None,
        "repair_to": missing_days[-1].isoformat() if missing_days else None,
        "updated_at": now,
    }

    if not repair_required and coverage_days_actual >= required_days:
        payload["status"] = "success"
        payload["error_code"] = None
        payload["error_message"] = None

    supabase.table("system_sync_state").upsert(
        payload,
        on_conflict="user_id,shop_id,marketplace,source_name",
    ).execute()

    return payload


def calculate_source_coverage(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    today: date | None = None,
) -> dict[str, Any]:
    source = get_sync_source(marketplace=marketplace, source_name=source_name)
    if not source:
        raise RuntimeError(f"Sync source not found or disabled: {marketplace}/{source_name}")

    rule = get_sync_rule(marketplace=marketplace, source_name=source_name)
    required_days = get_required_coverage_days(rule)
    coverage_to = today or utc_today()
    coverage_from = coverage_to - timedelta(days=required_days - 1)

    sync_strategy = (source.get("sync_strategy") or (rule or {}).get("sync_strategy") or "").lower()

    if sync_strategy == "incremental":
        day_counts = fetch_coverage_day_counts(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            source_name=source_name,
            date_from=coverage_from,
            date_to=coverage_to,
        )
    else:
        raw_table_name = source["raw_table_name"]
        date_column = get_date_column(source)

        day_counts = fetch_loaded_day_counts(
            raw_table_name=raw_table_name,
            date_column=date_column,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            date_from=coverage_from,
            date_to=coverage_to,
        )

    raw_loaded_days = set(day_counts.keys())

    required_day_set = set(iter_days(coverage_from, coverage_to))
    missing_days = sorted(required_day_set - raw_loaded_days)

    min_rows_ratio = float((rule or {}).get("min_day_rows_ratio") or 0.75)

    if sync_strategy == "incremental":
        damaged_days = []
    else:
        damaged_days = detect_damaged_days(
            day_counts=day_counts,
            min_rows_ratio=min_rows_ratio,
        )
    repair_days = sorted(set(missing_days) | set(damaged_days))
    valid_loaded_days = raw_loaded_days - set(damaged_days)

    state_payload = update_coverage_state(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=source_name,
        coverage_from=coverage_from,
        coverage_to=coverage_to,
        required_days=required_days,
        loaded_days=valid_loaded_days,
        missing_days=repair_days,
    )

    return {
        "source": source,
        "rule": rule,
        "state": state_payload,
        "coverage_from": coverage_from,
        "coverage_to": coverage_to,
        "required_days": required_days,
        "loaded_days": sorted(valid_loaded_days),
        "raw_loaded_days": sorted(raw_loaded_days),
        "missing_days": missing_days,
        "damaged_days": damaged_days,
        "repair_days": repair_days,
        "missing_days_count": len(repair_days),
        "repair_required": bool(repair_days),
        "day_counts": day_counts,
    }


if __name__ == "__main__":
    result = calculate_source_coverage(
        user_id=1,
        shop_id=1,
        marketplace="wb",
        source_name="funnel",
    )
    print(
        {
            "marketplace": result["source"]["marketplace"],
            "source_name": result["source"]["source_name"],
            "coverage_from": result["coverage_from"].isoformat(),
            "coverage_to": result["coverage_to"].isoformat(),
            "required_days": result["required_days"],
            "loaded_days": len(result["loaded_days"]),
            "missing_days_count": result["missing_days_count"],
            "repair_required": result["repair_required"],
            "missing_days": [day.isoformat() for day in result["missing_days"]],
            "damaged_days": [day.isoformat() for day in result["damaged_days"]],
            "repair_days": [day.isoformat() for day in result["repair_days"]],
        }
    )