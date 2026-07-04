import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "normalized_funnel"
TARGET_TABLE = "snapshots_funnel_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7


def to_float(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


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


def parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value

    if value in [None, ""]:
        return datetime.min

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.min


def fetch_funnel_for_dates(dates_to_build: List[date]) -> List[Dict[str, Any]]:
    if not dates_to_build:
        return []

    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    start_date = min(dates_to_build)
    end_date_exclusive = max(dates_to_build) + timedelta(days=1)
    allowed_dates = set(dates_to_build)

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", MARKETPLACE)
            .gte("snapshot_date", start_date.isoformat())
            .lt("snapshot_date", end_date_exclusive.isoformat())
            .order("snapshot_date")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []

        for row in batch:
            row_date = parse_date(row.get("snapshot_date"))
            if row_date in allowed_dates:
                rows.append(row)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_group_key(row: Dict[str, Any]) -> Optional[Tuple[Any, Any, str, str, str]]:
    snapshot_date = parse_date(row.get("snapshot_date"))
    product_key = row.get("product_key")

    if not snapshot_date or not product_key:
        return None

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        str(product_key),
        snapshot_date.isoformat(),
    )


def choose_latest_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_by_key: Dict[Tuple[Any, Any, str, str, str], Dict[str, Any]] = {}

    for row in rows:
        key = build_group_key(row)
        if key is None:
            continue

        current = latest_by_key.get(key)
        current_time = parse_datetime(current.get("created_at")) if current else datetime.min
        row_time = parse_datetime(row.get("created_at"))

        if current is None or row_time >= current_time:
            latest_by_key[key] = row

    return list(latest_by_key.values())


def build_snapshot_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "user_id": row.get("user_id"),
        "shop_id": row.get("shop_id"),
        "marketplace": row.get("marketplace") or MARKETPLACE,
        "snapshot_date": row.get("snapshot_date"),
        "period_start": row.get("period_start"),
        "period_end": row.get("period_end"),

        "product_key": row.get("product_key"),
        "marketplace_product_id": row.get("marketplace_product_id"),

        "title": row.get("title"),
        "brand_name": row.get("brand"),
        "subject_id": row.get("subject_id"),
        "subject_name": row.get("subject_name"),
        "seller_sku": row.get("seller_sku"),

        "open_count": to_float(row.get("open_count")),
        "cart_count": to_float(row.get("cart_count")),
        "order_count": to_float(row.get("order_count")),
        "buyout_count": to_float(row.get("buyout_count")),
        "cancel_count": to_float(row.get("cancel_count")),
        "order_sum": to_float(row.get("order_sum")),
        "buyout_sum": to_float(row.get("buyout_sum")),
        "cancel_sum": to_float(row.get("cancel_sum")),
        "wishlist_adds": to_float(row.get("wishlist_adds")),
        "avg_price": to_float(row.get("avg_price")),
        "localization_pct": to_float(row.get("localization_pct")),

        "stocks_wb": to_float(row.get("stocks_wb")),
        "stocks_mp": to_float(row.get("stocks_mp")),
        "stock_balance_sum": to_float(row.get("balance_sum")),
        "product_rating": to_float(row.get("product_rating")),
        "feedback_rating": to_float(row.get("feedback_rating")),

        "raw_payload": row,
        "event_hash": row.get("event_hash"),
    }


def build_snapshots(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest_rows = choose_latest_rows(rows)
    return [build_snapshot_row(row) for row in latest_rows]


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_snapshots(rows: List[Dict[str, Any]]) -> int:
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


def run_snapshot_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    registry_entry: Dict[str, Any],
) -> Dict[str, Any]:
    print("Resolving funnel daily snapshot coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="snapshot_date",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No funnel snapshots to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching normalized funnel for selected dates...")
    funnel_rows = fetch_funnel_for_dates(dates_to_build)
    print(f"Normalized funnel rows fetched: {len(funnel_rows)}")

    snapshots = build_snapshots(funnel_rows)
    print(f"Funnel snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No funnel snapshots to upsert")
        return {
            "rows_read": len(funnel_rows),
            "rows_upserted": 0,
            "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
        }

    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(funnel_rows),
        "rows_upserted": sent,
        "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
    }


def build_snapshots_funnel_daily() -> None:
    result = run_snapshot_job(
        job={},
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_snapshots_funnel_daily()