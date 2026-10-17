from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from db.client import supabase


SOURCE_TABLE = "metrics_realization_daily"
COSTS_TABLE = "normalized_product_costs"
TARGET_TABLE = "snapshots_financial_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 1000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_date(value: Any) -> date | None:
    if not value:
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return datetime.fromisoformat(value[:10]).date()

    return None


def to_float(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    return float(value)


def safe_pct(part: float, total: float) -> float:
    if not total:
        return 0.0
    return round((part / total) * 100, 2)


def safe_div(part: float, total: float) -> float:
    if not total:
        return 0.0
    return round(part / total, 2)


def fetch_realization_metrics(batch_size: int = BATCH_SIZE, *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
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
        print(f"Fetched realization metrics batch: {len(rows)}")

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def fetch_product_costs(batch_size: int = BATCH_SIZE, *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0

    while True:
        response = (
            supabase
            .table(COSTS_TABLE)
            .select("*")
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
            .eq("is_active", True)
            .order("product_key", desc=False)
            .order("effective_from", desc=False)
            .order("id", desc=False)
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        if not batch:
            break

        rows.extend(batch)
        print(f"Fetched product costs batch: {len(rows)}")

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_cost_index(cost_rows: list[dict[str, Any]]) -> dict[tuple[Any, Any, str, str], list[dict[str, Any]]]:
    index: dict[tuple[Any, Any, str, str], list[dict[str, Any]]] = {}

    for row in cost_rows:
        product_key = row.get("product_key")
        if not product_key:
            continue

        key = (
            row.get("user_id"),
            row.get("shop_id"),
            row.get("marketplace") or MARKETPLACE,
            str(product_key),
        )
        index.setdefault(key, []).append(row)

    for rows in index.values():
        rows.sort(key=lambda item: parse_date(item.get("effective_from")) or date.min)

    return index


def find_cost_price(
    cost_index: dict[tuple[Any, Any, str, str], list[dict[str, Any]]],
    metric_row: dict[str, Any],
) -> float | None:
    product_key = metric_row.get("product_key")
    snapshot_date = parse_date(metric_row.get("snapshot_date"))

    if not product_key or not snapshot_date:
        return None

    key = (
        metric_row.get("user_id"),
        metric_row.get("shop_id"),
        metric_row.get("marketplace") or MARKETPLACE,
        str(product_key),
    )
    cost_rows = cost_index.get(key, [])

    matched_cost = None
    for cost_row in cost_rows:
        effective_from = parse_date(cost_row.get("effective_from"))
        effective_to = parse_date(cost_row.get("effective_to"))

        if not effective_from:
            continue

        if effective_from <= snapshot_date and (effective_to is None or snapshot_date <= effective_to):
            matched_cost = to_float(cost_row.get("cost_price"))

    return matched_cost


def build_financial_snapshot_row(
    metric_row: dict[str, Any],
    cost_index: dict[tuple[Any, Any, str, str], list[dict[str, Any]]],
) -> dict[str, Any] | None:
    product_key = metric_row.get("product_key")
    snapshot_date = parse_date(metric_row.get("snapshot_date"))

    if not product_key or not snapshot_date:
        return None

    sales_count = to_float(metric_row.get("sales_count"))
    returns_count = to_float(metric_row.get("returns_count"))
    net_sales_count = sales_count - returns_count

    sales_amount = to_float(metric_row.get("sales_amount"))
    returns_amount = to_float(metric_row.get("returns_amount"))
    net_sales_amount = to_float(metric_row.get("net_sales_amount"))

    commission_amount = to_float(metric_row.get("wb_commission_amount"))
    logistics_amount = to_float(metric_row.get("logistics_amount"))
    storage_amount = to_float(metric_row.get("storage_amount"))
    acquiring_amount = to_float(metric_row.get("acquiring_amount"))
    penalty_amount = to_float(metric_row.get("penalty_amount"))
    deduction_amount = to_float(metric_row.get("deduction_amount"))
    acceptance_amount = to_float(metric_row.get("acceptance_amount"))
    other_income_amount = to_float(metric_row.get("other_income_amount"))
    other_expense_amount = to_float(metric_row.get("other_expense_amount"))

    seller_payout = to_float(metric_row.get("seller_payout"))

    cost_price = find_cost_price(cost_index, metric_row)
    if cost_price is None:
        return None
    cogs_amount = round(net_sales_count * cost_price, 2)

    marketplace_expense_amount = round(
        commission_amount
        + logistics_amount
        + storage_amount
        + acquiring_amount
        + penalty_amount
        + deduction_amount
        + acceptance_amount
        + other_expense_amount,
        2,
    )

    gross_profit = round(net_sales_amount - cogs_amount, 2)
    net_profit = round(gross_profit - marketplace_expense_amount + other_income_amount, 2)

    return {
        "user_id": metric_row.get("user_id"),
        "shop_id": metric_row.get("shop_id"),
        "marketplace": metric_row.get("marketplace") or MARKETPLACE,
        "snapshot_date": snapshot_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": str(metric_row.get("marketplace_product_id")) if metric_row.get("marketplace_product_id") is not None else None,
        "sales_count": sales_count,
        "returns_count": returns_count,
        "net_sales_count": net_sales_count,
        "sales_amount": sales_amount,
        "returns_amount": returns_amount,
        "net_sales_amount": net_sales_amount,
        "cost_price": cost_price,
        "cogs_amount": cogs_amount,
        "commission_amount": commission_amount,
        "logistics_amount": logistics_amount,
        "storage_amount": storage_amount,
        "acquiring_amount": acquiring_amount,
        "penalty_amount": penalty_amount,
        "deduction_amount": deduction_amount,
        "acceptance_amount": acceptance_amount,
        "other_expense_amount": other_expense_amount,
        "other_income_amount": other_income_amount,
        "marketplace_expense_amount": marketplace_expense_amount,
        "seller_payout": seller_payout,
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "gross_margin_pct": safe_pct(gross_profit, net_sales_amount),
        "net_margin_pct": safe_pct(net_profit, net_sales_amount),
        "expense_rate_pct": safe_pct(marketplace_expense_amount, net_sales_amount),
        "profit_per_sale": safe_div(net_profit, net_sales_count),
        "source_type": "actual_realization",
        "created_at": utc_now_iso(),
    }


def build_financial_snapshots(
    metric_rows: list[dict[str, Any]],
    cost_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cost_index = build_cost_index(cost_rows)
    rows: list[dict[str, Any]] = []
    skipped_rows = 0

    for metric_row in metric_rows:
        financial_row = build_financial_snapshot_row(metric_row, cost_index)
        if not financial_row:
            skipped_rows += 1
            continue
        rows.append(financial_row)

    print(f"Financial snapshot rows skipped: {skipped_rows}")
    return rows


def upsert_financial_snapshots(rows: list[dict[str, Any]], batch_size: int = BATCH_SIZE) -> int:
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
        print(f"Rows sent to snapshots_financial_daily: {total}")

    return total


def run_snapshot_job(
    job: dict[str, Any],
    state: dict[str, Any] | None,
    registry_entry: dict[str, Any],
) -> dict[str, Any]:
    user_id, shop_id = job.get("user_id"), job.get("shop_id")
    marketplace = job.get("marketplace") or MARKETPLACE
    if user_id is None or shop_id is None:
        raise ValueError("Complete tenant context is required")
    print("Fetching realization metrics...")
    metric_rows = fetch_realization_metrics(user_id=user_id,shop_id=shop_id,marketplace=marketplace)
    print(f"Realization metrics fetched: {len(metric_rows)}")

    print("Fetching product costs...")
    cost_rows = fetch_product_costs(user_id=user_id,shop_id=shop_id,marketplace=marketplace)
    print(f"Product costs fetched: {len(cost_rows)}")

    financial_rows = build_financial_snapshots(metric_rows=metric_rows, cost_rows=cost_rows)
    print(f"Financial snapshots prepared: {len(financial_rows)}")

    if not financial_rows:
        print("No financial snapshots to upsert")
        return {
            "rows_read": len(metric_rows),
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    upserted = upsert_financial_snapshots(financial_rows)
    print(f"Financial snapshots upserted: {upserted}")

    last_processed_date = max(row.get("snapshot_date") for row in financial_rows if row.get("snapshot_date"))

    return {
        "rows_read": len(metric_rows),
        "rows_upserted": upserted,
        "last_processed_date": last_processed_date,
    }


def build_snapshots_financial_daily() -> None:
    result = run_snapshot_job(
        job={},
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_snapshots_financial_daily()
