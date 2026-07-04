from __future__ import annotations

from datetime import date, timedelta
from typing import Any


ORDERS_TABLE = "metrics_orders_daily"
FINANCIAL_TABLE = "metrics_financial_daily"


def run(request: dict, supabase) -> dict:
    scope = request.get("scope") or request.get("entity") or "store"

    if scope != "store":
        raise ValueError(f"Unsupported overview scope: {scope}")

    today = date.today()
    latest_complete_day = _latest_complete_orders_day(
        request=request,
        supabase=supabase,
        today=today,
    )

    if not latest_complete_day:
        latest_available_date = _latest_orders_date(
            request=request,
            supabase=supabase,
        )
        return {
            "dataset": "store",
            "analysis": "overview",
            "scope": "store",
            "period": "latest_complete_day",
            "compare_to": "previous_day",
            "status": "no_current_data",
            "requested_date": today.isoformat(),
            "latest_available_date": latest_available_date,
            "metrics": {},
            "meta": {
                "orders_table": ORDERS_TABLE,
                "profit_table": FINANCIAL_TABLE,
            },
        }

    previous_day = latest_complete_day - timedelta(days=1)
    current_orders = _fetch_orders_totals(
        request=request,
        supabase=supabase,
        snapshot_date=latest_complete_day,
    )
    previous_orders = _fetch_orders_totals(
        request=request,
        supabase=supabase,
        snapshot_date=previous_day,
    )
    revenue = _compare_metric(
        metric="revenue",
        field="gross_order_value",
        current=current_orders["gross_order_value"],
        previous=previous_orders["gross_order_value"],
    )
    orders = _compare_metric(
        metric="orders",
        field="orders_count",
        current=current_orders["orders_count"],
        previous=previous_orders["orders_count"],
    )
    profit = _build_profit_metric(
        request=request,
        supabase=supabase,
        latest_complete_day=latest_complete_day,
        previous_day=previous_day,
    )

    return {
        "dataset": "store",
        "analysis": "overview",
        "scope": "store",
        "period": "latest_complete_day",
        "compare_to": "previous_day",
        "status": "success",
        "latest_complete_day": latest_complete_day.isoformat(),
        "previous_day": previous_day.isoformat(),
        "metrics": {
            "revenue": revenue,
            "orders": orders,
            "profit": profit,
        },
        "summary": {
            "revenue_direction": _direction(revenue.get("change_abs")),
            "orders_direction": _direction(orders.get("change_abs")),
            "profit_status": profit.get("status"),
        },
        "meta": {
            "today": today.isoformat(),
            "orders_table": ORDERS_TABLE,
            "profit_table": FINANCIAL_TABLE,
            "revenue_field": "gross_order_value",
            "orders_field": "orders_count",
            "profit_field": "net_profit",
            "orders_current_rows_count": current_orders["rows_count"],
            "orders_previous_rows_count": previous_orders["rows_count"],
        },
    }


def _latest_complete_orders_day(request: dict, supabase, today: date) -> date | None:
    response = (
        supabase
        .table(ORDERS_TABLE)
        .select("snapshot_date")
        .eq("user_id", request["user_id"])
        .eq("shop_id", request["shop_id"])
        .eq("marketplace", request.get("marketplace", "wb"))
        .lt("snapshot_date", today.isoformat())
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []

    if not rows:
        return None

    return date.fromisoformat(str(rows[0]["snapshot_date"]))


def _latest_orders_date(request: dict, supabase) -> str | None:
    response = (
        supabase
        .table(ORDERS_TABLE)
        .select("snapshot_date")
        .eq("user_id", request["user_id"])
        .eq("shop_id", request["shop_id"])
        .eq("marketplace", request.get("marketplace", "wb"))
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []

    if not rows:
        return None

    return rows[0].get("snapshot_date")


def _fetch_orders_totals(request: dict, supabase, snapshot_date: date) -> dict[str, float]:
    rows = _fetch_rows(
        request=request,
        supabase=supabase,
        table=ORDERS_TABLE,
        snapshot_date=snapshot_date,
        select_fields="orders_count,gross_order_value,net_order_value",
    )

    return {
        "rows_count": len(rows),
        "orders_count": sum(_safe_float(row.get("orders_count")) for row in rows),
        "gross_order_value": sum(_safe_float(row.get("gross_order_value")) for row in rows),
        "net_order_value": sum(_safe_float(row.get("net_order_value")) for row in rows),
    }


def _build_profit_metric(
    request: dict,
    supabase,
    latest_complete_day: date,
    previous_day: date,
) -> dict[str, Any]:
    latest_profit_date = _latest_profit_date(request=request, supabase=supabase)
    current_rows = _fetch_rows(
        request=request,
        supabase=supabase,
        table=FINANCIAL_TABLE,
        snapshot_date=latest_complete_day,
        select_fields="net_profit,gross_profit",
    )

    if not current_rows:
        return {
            "status": "no_fresh_data",
            "current": None,
            "previous": None,
            "change_abs": None,
            "change_pct": None,
            "field": "net_profit",
            "latest_profit_date": latest_profit_date,
        }

    previous_rows = _fetch_rows(
        request=request,
        supabase=supabase,
        table=FINANCIAL_TABLE,
        snapshot_date=previous_day,
        select_fields="net_profit,gross_profit",
    )
    current = sum(_safe_float(row.get("net_profit")) for row in current_rows)
    previous = sum(_safe_float(row.get("net_profit")) for row in previous_rows)
    result = _compare_metric(
        metric="profit",
        field="net_profit",
        current=current,
        previous=previous,
    )
    result["status"] = "success"
    result["latest_profit_date"] = latest_profit_date
    return result


def _latest_profit_date(request: dict, supabase) -> str | None:
    response = (
        supabase
        .table(FINANCIAL_TABLE)
        .select("snapshot_date")
        .eq("user_id", request["user_id"])
        .eq("shop_id", request["shop_id"])
        .eq("marketplace", request.get("marketplace", "wb"))
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    rows = response.data or []

    if not rows:
        return None

    return rows[0].get("snapshot_date")


def _fetch_rows(
    request: dict,
    supabase,
    table: str,
    snapshot_date: date,
    select_fields: str,
) -> list[dict]:
    response = (
        supabase
        .table(table)
        .select(select_fields)
        .eq("user_id", request["user_id"])
        .eq("shop_id", request["shop_id"])
        .eq("marketplace", request.get("marketplace", "wb"))
        .eq("snapshot_date", snapshot_date.isoformat())
        .range(0, 9999)
        .execute()
    )

    return response.data or []


def _compare_metric(metric: str, field: str, current: float, previous: float) -> dict:
    change_abs = current - previous

    return {
        "metric": metric,
        "current": round(current, 2),
        "previous": round(previous, 2),
        "change_abs": round(change_abs, 2),
        "change_pct": _change_pct(current=current, previous=previous),
        "field": field,
    }


def _change_pct(current: float, previous: float) -> float | None:
    if previous == 0:
        return 0.0 if current == 0 else None

    return round(((current - previous) / previous) * 100, 2)


def _direction(change_abs: Any) -> str:
    value = _safe_float(change_abs)

    if value > 0:
        return "up"

    if value < 0:
        return "down"

    return "flat"


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
