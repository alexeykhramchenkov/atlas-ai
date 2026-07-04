

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from db.client import supabase


SOURCE_TABLE = "snapshots_financial_daily"
TARGET_TABLE = "metrics_financial_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 1000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def safe_pct(part: float, total: float) -> float:
    if not total:
        return 0.0
    return round((part / total) * 100, 2)


def safe_growth_pct(current: float, previous: float | None) -> float | None:
    if previous is None:
        return None

    if previous == 0:
        if current == 0:
            return 0.0
        return None

    return round(((current - previous) / previous) * 100, 2)


def date_minus_days(date_value: str, days: int) -> str:
    parsed_date = datetime.fromisoformat(date_value[:10]).date()
    target_ordinal = parsed_date.toordinal() - days
    return datetime.fromordinal(target_ordinal).date().isoformat()


def fetch_financial_snapshots(batch_size: int = BATCH_SIZE) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", MARKETPLACE)
            .order("snapshot_date", desc=False)
            .order("product_key", desc=False)
            .order("id", desc=False)
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        if not batch:
            break

        rows.extend(batch)
        print(f"Fetched financial snapshots batch: {len(rows)}")

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def snapshot_key(row: dict[str, Any]) -> tuple[Any, Any, str, str, str]:
    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        row.get("product_key") or "__unknown__",
        str(row.get("snapshot_date")),
    )


def build_snapshot_index(rows: list[dict[str, Any]]) -> dict[tuple[Any, Any, str, str, str], dict[str, Any]]:
    return {snapshot_key(row): row for row in rows}


def find_previous_value(
    index: dict[tuple[Any, Any, str, str, str], dict[str, Any]],
    row: dict[str, Any],
    days: int,
    field_name: str,
) -> float | None:
    previous_date = date_minus_days(str(row.get("snapshot_date")), days)
    key = (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        row.get("product_key") or "__unknown__",
        previous_date,
    )
    previous_row = index.get(key)
    if not previous_row:
        return None

    value = previous_row.get(field_name)
    return to_float(value) if value is not None else None


def build_metric_row(
    row: dict[str, Any],
    index: dict[tuple[Any, Any, str, str, str], dict[str, Any]],
) -> dict[str, Any]:
    net_sales_amount = to_float(row.get("net_sales_amount"))
    marketplace_expense_amount = to_float(row.get("marketplace_expense_amount"))
    gross_profit = to_float(row.get("gross_profit"))
    net_profit = to_float(row.get("net_profit"))

    commission_amount = to_float(row.get("commission_amount"))
    logistics_amount = to_float(row.get("logistics_amount"))
    storage_amount = to_float(row.get("storage_amount"))
    acquiring_amount = to_float(row.get("acquiring_amount"))
    deduction_amount = to_float(row.get("deduction_amount"))

    previous_profit_1d = find_previous_value(index, row, 1, "net_profit")
    previous_profit_7d = find_previous_value(index, row, 7, "net_profit")
    previous_profit_30d = find_previous_value(index, row, 30, "net_profit")

    previous_sales_1d = find_previous_value(index, row, 1, "net_sales_amount")
    previous_sales_7d = find_previous_value(index, row, 7, "net_sales_amount")
    previous_sales_30d = find_previous_value(index, row, 30, "net_sales_amount")

    return {
        "user_id": row.get("user_id"),
        "shop_id": row.get("shop_id"),
        "marketplace": row.get("marketplace") or MARKETPLACE,
        "snapshot_date": row.get("snapshot_date"),
        "product_key": row.get("product_key") or "__unknown__",
        "marketplace_product_id": row.get("marketplace_product_id"),

        "sales_count": to_float(row.get("sales_count")),
        "returns_count": to_float(row.get("returns_count")),
        "net_sales_count": to_float(row.get("net_sales_count")),

        "sales_amount": to_float(row.get("sales_amount")),
        "returns_amount": to_float(row.get("returns_amount")),
        "net_sales_amount": net_sales_amount,

        "cogs_amount": to_float(row.get("cogs_amount")),
        "marketplace_expense_amount": marketplace_expense_amount,

        "commission_amount": commission_amount,
        "logistics_amount": logistics_amount,
        "storage_amount": storage_amount,
        "acquiring_amount": acquiring_amount,
        "deduction_amount": deduction_amount,

        "gross_profit": gross_profit,
        "net_profit": net_profit,

        "gross_margin_pct": safe_pct(gross_profit, net_sales_amount),
        "net_margin_pct": safe_pct(net_profit, net_sales_amount),
        "expense_rate_pct": safe_pct(marketplace_expense_amount, net_sales_amount),
        "commission_rate_pct": safe_pct(commission_amount, net_sales_amount),
        "logistics_rate_pct": safe_pct(logistics_amount, net_sales_amount),
        "storage_rate_pct": safe_pct(storage_amount, net_sales_amount),
        "acquiring_rate_pct": safe_pct(acquiring_amount, net_sales_amount),
        "deduction_rate_pct": safe_pct(deduction_amount, net_sales_amount),

        "profit_growth_1d_pct": safe_growth_pct(net_profit, previous_profit_1d),
        "profit_growth_7d_pct": safe_growth_pct(net_profit, previous_profit_7d),
        "profit_growth_30d_pct": safe_growth_pct(net_profit, previous_profit_30d),
        "net_sales_growth_1d_pct": safe_growth_pct(net_sales_amount, previous_sales_1d),
        "net_sales_growth_7d_pct": safe_growth_pct(net_sales_amount, previous_sales_7d),
        "net_sales_growth_30d_pct": safe_growth_pct(net_sales_amount, previous_sales_30d),

        "source_type": row.get("source_type") or "actual_realization",
        "created_at": utc_now_iso(),
    }


def build_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = build_snapshot_index(rows)
    return [build_metric_row(row, index) for row in rows]


def upsert_metrics(rows: list[dict[str, Any]], batch_size: int = BATCH_SIZE) -> int:
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
        print(f"Rows sent to metrics_financial_daily: {total}")

    return total



def run_metric_job(job, state, registry_entry) -> dict[str, Any]:
    user_id = job.get("user_id")
    shop_id = job.get("shop_id")
    marketplace = job.get("marketplace") or MARKETPLACE

    print(
        f"Fetching financial snapshots "
        f"for user_id={user_id} shop_id={shop_id} marketplace={marketplace}..."
    )

    snapshot_rows = fetch_financial_snapshots()

    if user_id is not None:
        snapshot_rows = [row for row in snapshot_rows if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshot_rows = [row for row in snapshot_rows if row.get("shop_id") == shop_id]

    if marketplace:
        snapshot_rows = [row for row in snapshot_rows if (row.get("marketplace") or MARKETPLACE) == marketplace]

    print(f"Financial snapshots fetched: {len(snapshot_rows)}")

    if not snapshot_rows:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    metric_rows = build_metrics(snapshot_rows)
    print(f"Financial metrics prepared: {len(metric_rows)}")

    rows_upserted = upsert_metrics(metric_rows)

    snapshot_dates = [row.get("snapshot_date") for row in snapshot_rows if row.get("snapshot_date")]
    last_processed_date = max(snapshot_dates) if snapshot_dates else None

    return {
        "rows_read": len(snapshot_rows),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def build_metrics_financial_daily() -> None:
    print("Fetching financial snapshots...")
    snapshot_rows = fetch_financial_snapshots()
    print(f"Financial snapshots fetched: {len(snapshot_rows)}")

    metric_rows = build_metrics(snapshot_rows)
    print(f"Financial metrics prepared: {len(metric_rows)}")

    upserted = upsert_metrics(metric_rows)
    print(f"Financial metrics upserted: {upserted}")


if __name__ == "__main__":
    build_metrics_financial_daily()