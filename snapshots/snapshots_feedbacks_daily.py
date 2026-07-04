

import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "normalized_feedbacks"
TARGET_TABLE = "snapshots_feedbacks_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7


def to_int(value: Any, default: int = 0) -> int:
    if value in [None, ""]:
        return default
    try:
        return int(value)
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


def fetch_feedbacks_for_dates(dates_to_build: List[date]) -> List[Dict[str, Any]]:
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
            .gte("created_at", start_date.isoformat())
            .lt("created_at", end_date_exclusive.isoformat())
            .order("created_at")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []

        for row in batch:
            feedback_day = parse_date(row.get("created_at"))
            if feedback_day in allowed_dates:
                rows.append(row)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_group_key(row: Dict[str, Any]) -> Optional[Tuple[Any, Any, str, str, date]]:
    feedback_day = parse_date(row.get("created_at"))
    product_key = row.get("product_key")

    if not feedback_day or not product_key:
        return None

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        product_key,
        feedback_day,
    )


def build_empty_group(row: Dict[str, Any], key: Tuple[Any, Any, str, str, date]) -> Dict[str, Any]:
    user_id, shop_id, marketplace, product_key, snapshot_date = key

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": snapshot_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "brand": row.get("brand"),
        "title": row.get("product_name"),
        "subject_id": row.get("subject_id"),
        "subject_name": row.get("subject_name"),
        "seller_sku": row.get("seller_sku"),
        "feedbacks_count": 0,
        "rating_sum": 0,
        "avg_rating": 0,
        "ratings_1_count": 0,
        "ratings_2_count": 0,
        "ratings_3_count": 0,
        "ratings_4_count": 0,
        "ratings_5_count": 0,
        "with_text_count": 0,
        "with_pros_count": 0,
        "with_cons_count": 0,
        "with_photo_count": 0,
        "with_video_count": 0,
        "photo_count": 0,
        "answered_count": 0,
        "unanswered_count": 0,
        "viewed_count": 0,
        "unviewed_count": 0,
        "matching_size_ok_count": 0,
        "matching_size_bad_count": 0,
        "order_statuses_count": 0,
    }


def has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def is_matching_size_ok(value: Any) -> bool:
    return str(value or "").strip().lower() in {"ok", "соответствует", "true", "1"}


def build_snapshots(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]] = {}
    order_statuses: Dict[Tuple[Any, Any, str, str, date], Set[str]] = defaultdict(set)

    for row in rows:
        key = build_group_key(row)
        if key is None:
            continue

        if key not in groups:
            groups[key] = build_empty_group(row, key)

        item = groups[key]
        rating = to_int(row.get("rating"))

        item["feedbacks_count"] += 1
        item["rating_sum"] += rating

        if rating == 1:
            item["ratings_1_count"] += 1
        elif rating == 2:
            item["ratings_2_count"] += 1
        elif rating == 3:
            item["ratings_3_count"] += 1
        elif rating == 4:
            item["ratings_4_count"] += 1
        elif rating == 5:
            item["ratings_5_count"] += 1

        if has_text(row.get("text")):
            item["with_text_count"] += 1
        if has_text(row.get("pros")):
            item["with_pros_count"] += 1
        if has_text(row.get("cons")):
            item["with_cons_count"] += 1
        if row.get("has_photo") is True:
            item["with_photo_count"] += 1
        if row.get("has_video") is True:
            item["with_video_count"] += 1
        if row.get("has_answer") is True:
            item["answered_count"] += 1
        else:
            item["unanswered_count"] += 1
        if row.get("was_viewed") is True:
            item["viewed_count"] += 1
        else:
            item["unviewed_count"] += 1

        item["photo_count"] += to_int(row.get("photo_count"))

        matching_size = row.get("matching_size")
        if matching_size:
            if is_matching_size_ok(matching_size):
                item["matching_size_ok_count"] += 1
            else:
                item["matching_size_bad_count"] += 1

        order_status = row.get("order_status")
        if order_status:
            order_statuses[key].add(str(order_status))

    result: List[Dict[str, Any]] = []

    for key, item in groups.items():
        count = item["feedbacks_count"]
        item["avg_rating"] = round(item["rating_sum"] / count, 2) if count else 0
        item["order_statuses_count"] = len(order_statuses[key])
        result.append(item)

    return result


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
    print("Resolving feedbacks daily snapshot coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="created_at",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No feedback snapshots to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching normalized feedbacks for selected dates...")
    feedbacks = fetch_feedbacks_for_dates(dates_to_build)
    print(f"Normalized feedbacks fetched: {len(feedbacks)}")

    snapshots = build_snapshots(feedbacks)
    print(f"Feedback snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No feedback snapshots to upsert")
        return {
            "rows_read": len(feedbacks),
            "rows_upserted": 0,
            "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
        }

    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(feedbacks),
        "rows_upserted": sent,
        "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
    }


def build_snapshots_feedbacks_daily() -> None:
    result = run_snapshot_job(
        job={},
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_snapshots_feedbacks_daily()