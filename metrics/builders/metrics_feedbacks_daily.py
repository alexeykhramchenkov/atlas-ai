

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "snapshots_feedbacks_daily"
TARGET_TABLE = "metrics_feedbacks_daily"
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


def fetch_snapshots_for_metric_dates(dates_to_build: List[date]) -> List[Dict[str, Any]]:
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
            .eq("marketplace", MARKETPLACE)
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

    feedbacks_count = to_float(row.get("feedbacks_count"))
    rating_sum = to_float(row.get("rating_sum"))
    avg_rating = to_float(row.get("avg_rating"))

    ratings_1_count = to_float(row.get("ratings_1_count"))
    ratings_2_count = to_float(row.get("ratings_2_count"))
    ratings_3_count = to_float(row.get("ratings_3_count"))
    ratings_4_count = to_float(row.get("ratings_4_count"))
    ratings_5_count = to_float(row.get("ratings_5_count"))

    with_text_count = to_float(row.get("with_text_count"))
    with_pros_count = to_float(row.get("with_pros_count"))
    with_cons_count = to_float(row.get("with_cons_count"))
    with_photo_count = to_float(row.get("with_photo_count"))
    with_video_count = to_float(row.get("with_video_count"))
    photo_count = to_float(row.get("photo_count"))

    answered_count = to_float(row.get("answered_count"))
    unanswered_count = to_float(row.get("unanswered_count"))
    viewed_count = to_float(row.get("viewed_count"))
    unviewed_count = to_float(row.get("unviewed_count"))
    matching_size_ok_count = to_float(row.get("matching_size_ok_count"))
    matching_size_bad_count = to_float(row.get("matching_size_bad_count"))
    order_statuses_count = to_float(row.get("order_statuses_count"))

    previous_day = metric_date - timedelta(days=1)
    previous_row = lookup.get((user_id, shop_id, marketplace, product_key, previous_day))

    previous_feedbacks_count = to_float(previous_row.get("feedbacks_count")) if previous_row else 0
    previous_avg_rating = to_float(previous_row.get("avg_rating")) if previous_row else 0
    previous_unanswered_count = to_float(previous_row.get("unanswered_count")) if previous_row else 0

    current_7d_feedbacks = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "feedbacks_count")
    previous_7d_feedbacks = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "feedbacks_count")
    current_30d_feedbacks = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "feedbacks_count")
    previous_30d_feedbacks = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "feedbacks_count")

    current_7d_unanswered = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 1, "unanswered_count")
    previous_7d_unanswered = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 7, 8, "unanswered_count")
    current_30d_unanswered = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 1, "unanswered_count")
    previous_30d_unanswered = previous_period_value(lookup, user_id, shop_id, marketplace, product_key, metric_date, 30, 31, "unanswered_count")

    low_rating_count = ratings_1_count + ratings_2_count + ratings_3_count
    high_rating_count = ratings_4_count + ratings_5_count

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": metric_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "seller_sku": row.get("seller_sku"),
        "title": row.get("title"),
        "brand": row.get("brand"),
        "subject_id": row.get("subject_id"),
        "subject_name": row.get("subject_name"),

        "feedbacks_count": round(feedbacks_count, 2),
        "rating_sum": round(rating_sum, 2),
        "avg_rating": round(avg_rating, 2),

        "ratings_1_count": round(ratings_1_count, 2),
        "ratings_2_count": round(ratings_2_count, 2),
        "ratings_3_count": round(ratings_3_count, 2),
        "ratings_4_count": round(ratings_4_count, 2),
        "ratings_5_count": round(ratings_5_count, 2),

        "low_rating_count": round(low_rating_count, 2),
        "high_rating_count": round(high_rating_count, 2),
        "low_rating_share_pct": round(safe_divide(low_rating_count, feedbacks_count) * 100, 2),
        "high_rating_share_pct": round(safe_divide(high_rating_count, feedbacks_count) * 100, 2),

        "with_text_count": round(with_text_count, 2),
        "with_pros_count": round(with_pros_count, 2),
        "with_cons_count": round(with_cons_count, 2),
        "with_photo_count": round(with_photo_count, 2),
        "with_video_count": round(with_video_count, 2),
        "photo_count": round(photo_count, 2),

        "text_share_pct": round(safe_divide(with_text_count, feedbacks_count) * 100, 2),
        "pros_share_pct": round(safe_divide(with_pros_count, feedbacks_count) * 100, 2),
        "cons_share_pct": round(safe_divide(with_cons_count, feedbacks_count) * 100, 2),
        "photo_share_pct": round(safe_divide(with_photo_count, feedbacks_count) * 100, 2),
        "video_share_pct": round(safe_divide(with_video_count, feedbacks_count) * 100, 2),

        "answered_count": round(answered_count, 2),
        "unanswered_count": round(unanswered_count, 2),
        "viewed_count": round(viewed_count, 2),
        "unviewed_count": round(unviewed_count, 2),
        "answer_rate_pct": round(safe_divide(answered_count, feedbacks_count) * 100, 2),
        "unanswered_rate_pct": round(safe_divide(unanswered_count, feedbacks_count) * 100, 2),
        "viewed_rate_pct": round(safe_divide(viewed_count, feedbacks_count) * 100, 2),
        "unviewed_rate_pct": round(safe_divide(unviewed_count, feedbacks_count) * 100, 2),

        "matching_size_ok_count": round(matching_size_ok_count, 2),
        "matching_size_bad_count": round(matching_size_bad_count, 2),
        "matching_size_bad_rate_pct": round(safe_divide(matching_size_bad_count, matching_size_ok_count + matching_size_bad_count) * 100, 2),
        "order_statuses_count": round(order_statuses_count, 2),

        "feedbacks_growth_1d_pct": growth_pct(feedbacks_count, previous_feedbacks_count),
        "avg_rating_change_1d": round(avg_rating - previous_avg_rating, 2) if previous_avg_rating else 0,
        "unanswered_growth_1d_pct": growth_pct(unanswered_count, previous_unanswered_count),

        "feedbacks_growth_7d_pct": growth_pct(current_7d_feedbacks, previous_7d_feedbacks),
        "unanswered_growth_7d_pct": growth_pct(current_7d_unanswered, previous_7d_unanswered),

        "feedbacks_growth_30d_pct": growth_pct(current_30d_feedbacks, previous_30d_feedbacks),
        "unanswered_growth_30d_pct": growth_pct(current_30d_unanswered, previous_30d_unanswered),
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


def run_metric_job(job, state, registry_entry) -> Dict[str, Any]:
    user_id = job.get("user_id")
    shop_id = job.get("shop_id")
    marketplace = job.get("marketplace") or MARKETPLACE

    source_table = registry_entry.get("source_table_name") or SOURCE_TABLE
    target_table = registry_entry.get("target_table_name") or TARGET_TABLE

    print(
        f"Resolving feedback metrics coverage "
        f"for user_id={user_id} shop_id={shop_id} marketplace={marketplace}..."
    )

    dates_to_build = get_dates_to_build(
        normalized_table=source_table,
        normalized_date_column="snapshot_date",
        snapshot_table=target_table,
        snapshot_date_column="snapshot_date",
        marketplace=marketplace,
        repair_days=REPAIR_DAYS,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No feedback metrics to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching feedback snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)

    if user_id is not None:
        snapshots = [row for row in snapshots if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshots = [row for row in snapshots if row.get("shop_id") == shop_id]

    print(f"Feedback snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Feedback metrics prepared: {len(metrics)}")

    rows_upserted = upsert_metrics(metrics)
    last_processed_date = max(dates_to_build).isoformat() if dates_to_build else None

    return {
        "rows_read": len(snapshots),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def main() -> None:
    print("Resolving feedback metrics coverage...")
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
        print("No feedback metrics to build")
        return

    print("Fetching feedback snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build)
    print(f"Feedback snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Feedback metrics prepared: {len(metrics)}")

    sent = upsert_metrics(metrics)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")


if __name__ == "__main__":
    main()