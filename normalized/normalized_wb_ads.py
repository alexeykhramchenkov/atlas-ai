import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


SOURCE_TABLE = "raw_wb_ads"
TARGET_TABLE = "normalized_ads"

MARKETPLACE = "wb"


def get_watermark(state: Optional[Dict[str, Any]]) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def parse_payload(payload: Any) -> Any:
    """
    Supabase usually returns jsonb as dict/list, but sometimes payload can be a string.
    """
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            return {}

    return payload


def extract_ads(payload: Any, parent_type: Optional[int] = None, parent_status: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Extract WB advert campaigns from raw_wb_ads payload into a marketplace-agnostic campaign model.

    Expected WB structure:
    {
        "all": 37,
        "adverts": [
            {
                "type": 9,
                "status": 7,
                "advert_list": [
                    {"advertId": 20794586, "changeTime": "2026-02-25T..."}
                ]
            }
        ]
    }
    """
    payload = parse_payload(payload)

    if isinstance(payload, list):
        ads: List[Dict[str, Any]] = []
        for item in payload:
            ads.extend(extract_ads(item, parent_type=parent_type, parent_status=parent_status))
        return ads

    if not isinstance(payload, dict):
        return []

    current_type = payload.get("type", parent_type)
    current_status = payload.get("status", parent_status)

    advert_id = payload.get("advertId") or payload.get("advert_id") or payload.get("id")
    change_time = payload.get("changeTime") or payload.get("change_time")

    if advert_id:
        try:
            return [
                {
                    "ad_id": int(advert_id),
                    "ad_type": current_type,
                    "ad_status": current_status,
                    "changed_at": change_time,
                }
            ]
        except (TypeError, ValueError):
            return []

    ads: List[Dict[str, Any]] = []

    for key in ("payload", "raw_payload", "data", "adverts", "advert_list"):
        value = payload.get(key)
        if isinstance(value, (dict, list, str)):
            ads.extend(extract_ads(value, parent_type=current_type, parent_status=current_status))

    return ads


def fetch_raw_ads(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
    query = (
        supabase
        .table(SOURCE_TABLE)
        .select("id,user_id,shop_id,marketplace,payload,updated_at")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
    )

    if last_raw_updated_at is not None:
        query = query.or_(
            f"updated_at.gt.{last_raw_updated_at},and(updated_at.eq.{last_raw_updated_at},id.gt.{last_raw_id})"
        )

    response = (
        query
        .order("updated_at")
        .order("id")
        .limit(limit)
        .execute()
    )

    return response.data or []


def build_normalized_ads(raw_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    user_id = raw_row.get("user_id")
    shop_id = raw_row.get("shop_id")
    marketplace = raw_row.get("marketplace") or MARKETPLACE
    payload = raw_row.get("payload") or raw_row.get("raw_payload")
    ads = extract_ads(payload)

    rows: List[Dict[str, Any]] = []

    for ad in ads:
        ad_id = ad.get("ad_id")

        if not ad_id:
            continue

        rows.append(
            {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "ad_platform": "wb_ads",
                "campaign_id": str(ad_id),
                "ad_id": ad_id,
                "ad_type": ad.get("ad_type"),
                "ad_status": ad.get("ad_status"),
                "changed_at": ad.get("changed_at"),
            }
        )

    return rows


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_ads(rows: List[Dict[str, Any]], batch_size: int = 100) -> int:
    sent = 0

    for batch in chunked(rows, batch_size):
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(
                batch,
                on_conflict="user_id,shop_id,marketplace,ad_id",
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(rows)}")

    return sent


def run_normalization_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    registry_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_rows = fetch_raw_ads(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
        limit=50000,
    )

    if not raw_rows:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    rows_by_key: Dict[tuple, Dict[str, Any]] = {}

    for raw_row in raw_rows:
        for row in build_normalized_ads(raw_row):
            key = (row["user_id"], row["shop_id"], row["marketplace"], row["ad_id"])
            rows_by_key[key] = row

    rows = list(rows_by_key.values())

    rows_upserted = 0
    if rows:
        rows_upserted = upsert_ads(rows, batch_size=100)

    newest_row = raw_rows[-1]

    return {
        "rows_read": len(raw_rows),
        "rows_upserted": rows_upserted,
        "last_raw_updated_at": newest_row.get("updated_at"),
        "last_raw_id": newest_row.get("id"),
    }


if __name__ == "__main__":
    result = run_normalization_job(
        job={"user_id": 1, "shop_id": 1},
        state=None,
        registry_entry=None,
    )

    print(result)