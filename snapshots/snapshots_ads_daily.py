import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "normalized_ads_stats"
TARGET_TABLE = "snapshots_ads_daily"
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


def to_float(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value: Any) -> Optional[date]:
    if value is None or value == "":
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


def fetch_ads_stats_for_dates(dates_to_build: List[date]) -> List[Dict[str, Any]]:
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
            .gte("date", start_date.isoformat())
            .lt("date", end_date_exclusive.isoformat())
            .order("date")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []

        for row in batch:
            row_date = parse_date(row.get("date"))
            if row_date in allowed_dates:
                rows.append(row)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_group_key(row: Dict[str, Any]) -> Optional[Tuple[Any, Any, str, str, str, str]]:
    row_date = parse_date(row.get("date"))
    campaign_id = row.get("campaign_id") or (str(row.get("ad_id")) if row.get("ad_id") is not None else None)
    ad_platform = row.get("ad_platform") or "wb_ads"

    if not row_date or not campaign_id:
        return None

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        ad_platform,
        str(campaign_id),
        row_date.isoformat(),
    )


def build_empty_group(row: Dict[str, Any], key: Tuple[Any, Any, str, str, str, str]) -> Dict[str, Any]:
    user_id, shop_id, marketplace, ad_platform, campaign_id, snapshot_date = key

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "ad_platform": ad_platform,
        "campaign_id": campaign_id,
        "ad_id": to_int(row.get("ad_id")),
        "date": snapshot_date,
        "currency": row.get("currency") or "RUB",
        "views": 0,
        "clicks": 0,
        "orders": 0,
        "canceled": 0,
        "spend": 0,
        "revenue": 0,
        "add_to_cart": 0,
        "shks": 0,
    }


def build_snapshots(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, Any, str, str, str, str], Dict[str, Any]] = {}

    for row in rows:
        key = build_group_key(row)
        if key is None:
            continue

        if key not in groups:
            groups[key] = build_empty_group(row, key)

        item = groups[key]
        item["views"] += to_int(row.get("views"))
        item["clicks"] += to_int(row.get("clicks"))
        item["orders"] += to_int(row.get("orders"))
        item["canceled"] += to_int(row.get("canceled"))
        item["spend"] += to_float(row.get("spend"))
        item["revenue"] += to_float(row.get("revenue"))
        item["add_to_cart"] += to_int(row.get("add_to_cart"))
        item["shks"] += to_int(row.get("shks"))

    result = list(groups.values())

    for row in result:
        row["spend"] = round(row["spend"], 2)
        row["revenue"] = round(row["revenue"], 2)

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
                on_conflict="user_id,shop_id,marketplace,ad_platform,campaign_id,date",
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
    print("Resolving ads daily snapshot coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="date",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No ads daily snapshots to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching normalized ads stats for selected dates...")
    ads_stats = fetch_ads_stats_for_dates(dates_to_build)
    print(f"Normalized ads stats fetched: {len(ads_stats)}")

    snapshots = build_snapshots(ads_stats)
    print(f"Ads daily snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No ads daily snapshots to upsert")
        return {
            "rows_read": len(ads_stats),
            "rows_upserted": 0,
            "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
        }

    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(ads_stats),
        "rows_upserted": sent,
        "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
    }


def build_snapshots_ads_daily() -> None:
    result = run_snapshot_job(
        job={},
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_snapshots_ads_daily()