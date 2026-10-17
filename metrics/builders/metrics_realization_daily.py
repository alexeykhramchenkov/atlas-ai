

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "snapshots_realization_daily"
TARGET_TABLE = "metrics_realization_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7
HISTORY_DAYS = 61


def parse_date(value: Any) -> Optional[date]:
    if value in [None, ""]:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def to_float(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0
    return numerator / denominator


def growth_pct(current_value: float, previous_value: float) -> float:
    if previous_value == 0:
        return 0
    return round((current_value - previous_value) / previous_value * 100, 2)


def fetch_snapshots_for_metric_dates(dates_to_build: List[date], *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> List[Dict[str, Any]]:
    if not dates_to_build:
        return []

    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    start_date = min(dates_to_build) - timedelta(days=HISTORY_DAYS)
    end_date_exclusive = max(dates_to_build) + timedelta(days=1)

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
            .gte("snapshot_date", start_date.isoformat())
            .lt("snapshot_date", end_date_exclusive.isoformat())
            .order("snapshot_date")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_lookup(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]]:
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]] = {}

    for row in rows:
        snapshot_date = parse_date(row.get("snapshot_date"))
        product_key = row.get("product_key")
        user_id = row.get("user_id")
        shop_id = row.get("shop_id")
        marketplace = row.get("marketplace") or MARKETPLACE

        if snapshot_date is None or not product_key or user_id is None or shop_id is None:
            continue

        lookup[(user_id, shop_id, marketplace, product_key, snapshot_date)] = row

    return lookup


def sum_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    product_key: str,
    end_date: date,
    days: int,
    field: str,
) -> float:
    total = 0.0

    for index in range(days):
        item_date = end_date - timedelta(days=index)
        row = lookup.get((user_id, shop_id, marketplace, product_key, item_date))
        if row:
            total += to_float(row.get(field))

    return total


def previous_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    product_key: str,
    metric_date: date,
    days: int,
    offset_days: int,
    field: str,
) -> float:
    period_end = metric_date - timedelta(days=offset_days)
    return sum_period_value(
        lookup=lookup,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        product_key=product_key,
        end_date=period_end,
        days=days,
        field=field,
    )


def build_metric_row(
    row: Dict[str, Any],
    lookup: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    metric_date = parse_date(row.get("snapshot_date"))
    product_key = row.get("product_key")
    user_id = row.get("user_id")
    shop_id = row.get("shop_id")
    marketplace = row.get("marketplace") or MARKETPLACE

    if metric_date is None or not product_key or user_id is None or shop_id is None:
        return None

    sales_count = to_float(row.get("sales_count"))
    returns_count = to_float(row.get("returns_count"))
    sales_amount = to_float(row.get("sales_amount"))
    returns_amount = to_float(row.get("returns_amount"))
    wb_commission_amount = to_float(row.get("wb_commission_amount"))
    logistics_amount = to_float(row.get("logistics_amount"))
    storage_amount = to_float(row.get("storage_amount"))
    acquiring_amount = to_float(row.get("acquiring_amount"))
    penalty_amount = to_float(row.get("penalty_amount"))
    deduction_amount = to_float(row.get("deduction_amount"))
    acceptance_amount = to_float(row.get("acceptance_amount"))
    compensation_amount = to_float(row.get("compensation_amount"))
    reimbursement_amount = to_float(row.get("reimbursement_amount"))
    other_income_amount = to_float(row.get("other_income_amount"))
    other_expense_amount = to_float(row.get("other_expense_amount"))
    seller_payout = to_float(row.get("seller_payout"))
    realization_events_count = to_float(row.get("realization_events_count"))

    net_sales_amount = sales_amount - returns_amount
    total_expense_amount = (
        wb_commission_amount
        + logistics_amount
        + storage_amount
        + acquiring_amount
        + penalty_amount
        + deduction_amount
        + acceptance_amount
        + other_expense_amount
    )
    total_income_amount = (
        sales_amount
        + compensation_amount
        + reimbursement_amount
        + other_income_amount
    )
    wb_net_result = (
        sales_amount
        - returns_amount
        - total_expense_amount
        + compensation_amount
        + reimbursement_amount
        + other_income_amount
    )
    gross_margin_before_cost = seller_payout
    expense_rate_pct = round(safe_divide(total_expense_amount, sales_amount) * 100, 2)
    payout_rate_pct = round(safe_divide(seller_payout, sales_amount) * 100, 2)
    return_rate_pct = round(safe_divide(returns_count, sales_count) * 100, 2)
    return_amount_rate_pct = round(safe_divide(returns_amount, sales_amount) * 100, 2)
    avg_sale_amount = round(safe_divide(sales_amount, sales_count), 2)
    avg_payout_per_sale = round(safe_divide(seller_payout, sales_count), 2)

    previous_day = metric_date - timedelta(days=1)
    previous_row = lookup.get((user_id, shop_id, marketplace, product_key, previous_day))

    previous_seller_payout = to_float(previous_row.get("seller_payout")) if previous_row else 0
    previous_sales_amount = to_float(previous_row.get("sales_amount")) if previous_row else 0
    previous_expense_amount = 0
    if previous_row:
        previous_expense_amount = (
            to_float(previous_row.get("wb_commission_amount"))
            + to_float(previous_row.get("logistics_amount"))
            + to_float(previous_row.get("storage_amount"))
            + to_float(previous_row.get("acquiring_amount"))
            + to_float(previous_row.get("penalty_amount"))
            + to_float(previous_row.get("deduction_amount"))
            + to_float(previous_row.get("acceptance_amount"))
            + to_float(previous_row.get("other_expense_amount"))
        )

    current_7d_payout = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "seller_payout")
    previous_7d_payout = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "seller_payout")
    current_30d_payout = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "seller_payout")
    previous_30d_payout = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "seller_payout")

    current_7d_sales_amount = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "sales_amount")
    previous_7d_sales_amount = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "sales_amount")
    current_30d_sales_amount = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "sales_amount")
    previous_30d_sales_amount = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "sales_amount")

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": metric_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "seller_sku": row.get("seller_sku"),

        "sales_count": round(sales_count, 2),
        "returns_count": round(returns_count, 2),
        "sales_amount": round(sales_amount, 2),
        "returns_amount": round(returns_amount, 2),
        "net_sales_amount": round(net_sales_amount, 2),

        "wb_commission_amount": round(wb_commission_amount, 2),
        "logistics_amount": round(logistics_amount, 2),
        "storage_amount": round(storage_amount, 2),
        "acquiring_amount": round(acquiring_amount, 2),
        "penalty_amount": round(penalty_amount, 2),
        "deduction_amount": round(deduction_amount, 2),
        "acceptance_amount": round(acceptance_amount, 2),
        "compensation_amount": round(compensation_amount, 2),
        "reimbursement_amount": round(reimbursement_amount, 2),
        "other_income_amount": round(other_income_amount, 2),
        "other_expense_amount": round(other_expense_amount, 2),
        "seller_payout": round(seller_payout, 2),
        "realization_events_count": round(realization_events_count, 2),

        "total_income_amount": round(total_income_amount, 2),
        "total_expense_amount": round(total_expense_amount, 2),
        "gross_margin_before_cost": round(gross_margin_before_cost, 2),
        "wb_net_result": round(wb_net_result, 2),

        "return_rate_pct": return_rate_pct,
        "return_amount_rate_pct": return_amount_rate_pct,
        "expense_rate_pct": expense_rate_pct,
        "payout_rate_pct": payout_rate_pct,
        "avg_sale_amount": avg_sale_amount,
        "avg_payout_per_sale": avg_payout_per_sale,

        "payout_growth_1d_pct": growth_pct(seller_payout, previous_seller_payout),
        "sales_amount_growth_1d_pct": growth_pct(sales_amount, previous_sales_amount),
        "expense_growth_1d_pct": growth_pct(total_expense_amount, previous_expense_amount),

        "payout_growth_7d_pct": growth_pct(current_7d_payout, previous_7d_payout),
        "sales_amount_growth_7d_pct": growth_pct(current_7d_sales_amount, previous_7d_sales_amount),

        "payout_growth_30d_pct": growth_pct(current_30d_payout, previous_30d_payout),
        "sales_amount_growth_30d_pct": growth_pct(current_30d_sales_amount, previous_30d_sales_amount),
    }


def build_metrics(rows: List[Dict[str, Any]], dates_to_build: List[date]) -> List[Dict[str, Any]]:
    lookup = build_lookup(rows)
    target_dates: Set[date] = set(dates_to_build)
    metrics: List[Dict[str, Any]] = []

    for row in rows:
        row_date = parse_date(row.get("snapshot_date"))
        if row_date not in target_dates:
            continue

        metric_row = build_metric_row(row, lookup)
        if metric_row is not None:
            metrics.append(metric_row)

    return metrics


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_metrics(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        print("Nothing to upsert")
        return 0

    sent = 0

    for batch in chunked(rows, BATCH_SIZE):
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(
                batch,
                on_conflict="user_id,shop_id,marketplace,product_key,snapshot_date",
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(rows)}")

    return sent



# Job runner for metric_worker
def run_metric_job(job, state, registry_entry) -> Dict[str, Any]:
    user_id, shop_id = int(job["user_id"]), int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    user_id = job.get("user_id")
    shop_id = job.get("shop_id")
    marketplace = job.get("marketplace") or MARKETPLACE

    source_table = registry_entry.get("source_table_name") or SOURCE_TABLE
    target_table = registry_entry.get("target_table_name") or TARGET_TABLE

    print(
        f"Resolving realization metrics coverage "
        f"for user_id={user_id} shop_id={shop_id} marketplace={marketplace}..."
    )

    dates_to_build = get_dates_to_build(
        normalized_table=source_table,
        normalized_date_column="snapshot_date",
        snapshot_table=target_table,
        snapshot_date_column="snapshot_date",
        marketplace=marketplace,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No realization metrics to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching realization snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)

    if user_id is not None:
        snapshots = [row for row in snapshots if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshots = [row for row in snapshots if row.get("shop_id") == shop_id]

    if marketplace:
        snapshots = [row for row in snapshots if (row.get("marketplace") or MARKETPLACE) == marketplace]

    print(f"Realization snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Realization metrics prepared: {len(metrics)}")

    rows_upserted = upsert_metrics(metrics)
    last_processed_date = max(dates_to_build).isoformat() if dates_to_build else None

    return {
        "rows_read": len(snapshots),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def main( *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> None:
    print("Resolving realization metrics coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="snapshot_date",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No realization metrics to build")
        return

    print("Fetching realization snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Realization snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Realization metrics prepared: {len(metrics)}")

    sent = upsert_metrics(metrics)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")


if __name__ == "__main__":
    main()