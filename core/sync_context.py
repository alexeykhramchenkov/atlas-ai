"""Shared sync context helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from db.client import supabase



ACTIVE_CONNECTIONS_VIEW = "system_active_sync_connections"
SYNC_RULES_TABLE = "system_sync_rules"
SYNC_STATE_TABLE = "system_sync_state"
SYNC_LOG_TABLE = "system_sync_log"


def build_sync_window_result(
    date_from: date,
    date_to: date,
    repair_required: bool = False,
    repair_from: date | None = None,
    repair_to: date | None = None,
    missing_days_count: int = 0,
) -> dict[str, Any]:
    return {
        "date_from": date_from,
        "date_to": date_to,
        "repair_required": repair_required,
        "repair_from": repair_from,
        "repair_to": repair_to,
        "missing_days_count": missing_days_count,
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def get_active_connections(marketplace: str | None = None) -> list[dict[str, Any]]:
    query = supabase.table(ACTIVE_CONNECTIONS_VIEW).select("*")

    if marketplace:
        query = query.eq("marketplace", marketplace)

    response = query.execute()
    return response.data or []


def get_sync_rule(source_name: str, marketplace: str = "wb") -> dict[str, Any]:
    response = (
        supabase
        .table(SYNC_RULES_TABLE)
        .select("*")
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .eq("is_enabled", True)
        .limit(1)
        .execute()
    )

    data = response.data or []

    if not data:
        raise RuntimeError(f"Sync rule not found: {marketplace}/{source_name}")

    return data[0]


def get_sync_state(
    user_id: int,
    shop_id: int,
    source_name: str,
    marketplace: str = "wb",
) -> dict[str, Any] | None:
    response = (
        supabase
        .table(SYNC_STATE_TABLE)
        .select("*")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("source_name", source_name)
        .limit(1)
        .execute()
    )

    data = response.data or []
    return data[0] if data else None


def resolve_sync_window(
    rule: dict[str, Any],
    state: dict[str, Any] | None,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or utc_now().date()

    strategy = rule["sync_strategy"]
    daily_window_days = int(rule.get("daily_window_days") or 1)
    repair_window_days = int(rule.get("repair_window_days") or 0)
    max_auto_repair_days = int(rule.get("max_auto_repair_days") or 0)
    smart_window_enabled = bool(rule.get("smart_window_enabled", True))

    if strategy in ("snapshot", "current_state", "report_based"):
        return build_sync_window_result(
            date_from=today,
            date_to=today,
        )

    repair_floor = today - timedelta(days=repair_window_days) if repair_window_days else today

    if not smart_window_enabled:
        return build_sync_window_result(
            date_from=repair_floor,
            date_to=today,
        )

    if not state or not state.get("last_loaded_date_to"):
        return build_sync_window_result(
            date_from=repair_floor,
            date_to=today,
            repair_required=bool(repair_window_days),
            repair_from=repair_floor if repair_window_days else None,
            repair_to=today if repair_window_days else None,
            missing_days_count=repair_window_days,
        )

    last_to = state["last_loaded_date_to"]

    if isinstance(last_to, str):
        last_to = date.fromisoformat(last_to)

    missing_from = last_to + timedelta(days=1)
    missing_days_count = max((today - missing_from).days + 1, 0)

    if state.get("status") == "running":
        date_from = max(missing_from, repair_floor)

        if date_from > today:
            date_from = today

        return build_sync_window_result(
            date_from=date_from,
            date_to=today,
            repair_required=bool(state.get("repair_required")),
            repair_from=state.get("repair_from"),
            repair_to=state.get("repair_to"),
            missing_days_count=missing_days_count,
        )

    repair_required = (
        max_auto_repair_days > 0
        and missing_days_count > max_auto_repair_days
    )

    overlap_from = last_to - timedelta(days=daily_window_days)
    date_from = max(overlap_from, repair_floor)

    if date_from > today:
        date_from = today

    repair_from = None
    repair_to = None

    if repair_required:
        repair_from = max(missing_from, repair_floor)
        repair_to = today

    return build_sync_window_result(
        date_from=date_from,
        date_to=today,
        repair_required=repair_required,
        repair_from=repair_from,
        repair_to=repair_to,
        missing_days_count=missing_days_count,
    )


# New helpers: should_run_sync, mark_sync_attempt
def should_run_sync(
    rule: dict[str, Any],
    state: dict[str, Any] | None,
    now: datetime | None = None,
) -> bool:
    now = now or utc_now()
    run_frequency_hours = int(rule.get("run_frequency_hours") or 0)

    if run_frequency_hours <= 0:
        return True

    if not state:
        return True

    last_attempt_at = state.get("last_attempt_at")

    if not last_attempt_at:
        return True

    if isinstance(last_attempt_at, str):
        last_attempt_at = datetime.fromisoformat(
            last_attempt_at.replace("Z", "+00:00")
        )

    next_allowed_at = last_attempt_at + timedelta(hours=run_frequency_hours)

    return now >= next_allowed_at


def mark_sync_attempt(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
) -> None:
    now = utc_now()

    supabase.table(SYNC_STATE_TABLE).upsert(
        {
            "user_id": user_id,
            "shop_id": shop_id,
            "marketplace": marketplace,
            "source_name": source_name,
            "last_attempt_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
        on_conflict="user_id,shop_id,marketplace,source_name",
    ).execute()


def write_sync_log(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    date_from: date | str,
    date_to: date | str,
    rows_fetched: int,
    rows_upserted: int,
    status: str,
    started_at: datetime,
    finished_at: datetime,
    error_message: str | None = None,
) -> None:
    duration_sec = (finished_at - started_at).total_seconds()

    supabase.table(SYNC_LOG_TABLE).insert({
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "table_name": source_name,
        "synced_at": finished_at.isoformat(),
        "date_from": str(date_from),
        "date_to": str(date_to),
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "duration_sec": duration_sec,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "status": status,
        "error_msg": error_message,
    }).execute()


def update_sync_state(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    date_from: date | str,
    date_to: date | str,
    rows_fetched: int,
    rows_upserted: int,
    status: str,
    repair_required: bool = False,
    repair_from: date | str | None = None,
    repair_to: date | str | None = None,
    error_message: str | None = None,
    missing_days_count: int = 0,
) -> None:
    now = utc_now()

    row = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "last_loaded_date_from": str(date_from),
        "last_loaded_date_to": str(date_to),
        "last_rows_fetched": rows_fetched,
        "last_rows_upserted": rows_upserted,
        "missing_days_count": missing_days_count,
        "status": status,
        "error_message": error_message,
        "repair_required": repair_required,
        "repair_from": str(repair_from) if repair_from else None,
        "repair_to": str(repair_to) if repair_to else None,
        "updated_at": now.isoformat(),
        "last_attempt_at": now.isoformat(),
    }

    if status == "success":
        row["last_success_at"] = now.isoformat()

    supabase.table(SYNC_STATE_TABLE).upsert(
        row,
        on_conflict="user_id,shop_id,marketplace,source_name",
    ).execute()
