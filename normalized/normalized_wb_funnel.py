from datetime import datetime
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


BATCH_SIZE = 100
FETCH_PAGE_SIZE = 1000


def get_watermark(state):
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def chunked(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def fetch_raw_funnel(
    user_id,
    shop_id,
    last_raw_updated_at=None,
    last_raw_id=0,
    page_size=FETCH_PAGE_SIZE,
):
    all_rows = []
    offset = 0

    while True:
        query = (
            supabase
            .table("raw_wb_funnel")
            .select("*")
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
            .range(offset, offset + page_size - 1)
            .execute()
        )

        rows = response.data or []

        if not rows:
            break

        all_rows.extend(rows)

        if len(rows) < page_size:
            break

        offset += page_size

    return all_rows


def build_event_hash(user_id, shop_id, marketplace, snapshot_date, nm_id):
    raw = f"{user_id}_{shop_id}_{marketplace}_{snapshot_date}_{nm_id}_funnel_snapshot"

    return hashlib.md5(raw.encode()).hexdigest()


def build_product_key(marketplace_product_id):
    if marketplace_product_id in [None, ""]:
        return None

    return f"wb_{marketplace_product_id}"


def prepare_snapshot(raw_row, product):
    product_info = product.get("product", {})
    stats = product.get("statistic", {})

    selected = stats.get("selected", {})

    stocks = product_info.get("stocks", {})

    nm_id = product_info.get("nmId")

    if not nm_id:
        return None

    marketplace_product_id = str(nm_id)
    product_key = build_product_key(marketplace_product_id)
    seller_sku = product_info.get("vendorCode")

    selected_period = selected.get("period", {})
    snapshot_date = selected_period.get("end")
    period_start = selected_period.get("start")
    period_end = selected_period.get("end")

    return {
        "user_id": raw_row.get("user_id"),
        "shop_id": raw_row.get("shop_id"),
        "marketplace": "wb",

        "product_key": product_key,
        "marketplace_product_id": marketplace_product_id,

        "title": product_info.get("title"),
        "brand": product_info.get("brandName"),
        "subject_id": product_info.get("subjectId"),
        "subject_name": product_info.get("subjectName"),
        "seller_sku": seller_sku,

        "snapshot_date": snapshot_date,
        "period_start": period_start,
        "period_end": period_end,

        "open_count": selected.get("openCount", 0),
        "cart_count": selected.get("cartCount", 0),
        "order_count": selected.get("orderCount", 0),
        "buyout_count": selected.get("buyoutCount", 0),
        "cancel_count": selected.get("cancelCount", 0),

        "order_sum": selected.get("orderSum", 0),
        "buyout_sum": selected.get("buyoutSum", 0),
        "cancel_sum": selected.get("cancelSum", 0),

        "wishlist_adds": selected.get("addToWishlist", 0),
        "localization_pct": selected.get("localizationPercent", 0),
        "avg_orders_per_day": selected.get("avgOrdersCountPerDay", 0),

        "avg_price": selected.get("avgPrice", 0),

        "stocks_wb": stocks.get("wb", 0),
        "stocks_mp": stocks.get("mp", 0),
        "balance_sum": stocks.get("balanceSum", 0),

        "product_rating": product_info.get("productRating"),
        "feedback_rating": product_info.get("feedbackRating"),

        "event_hash": build_event_hash(
            raw_row.get("user_id"),
            raw_row.get("shop_id"),
            "wb",
            snapshot_date,
            nm_id,
        ),

        "created_at": datetime.utcnow().isoformat(),
    }


def insert_snapshots(rows):
    chunks = chunked(rows, BATCH_SIZE)

    sent = 0

    for chunk in chunks:
        (
            supabase
            .table("normalized_funnel")
            .upsert(
                chunk,
                on_conflict="event_hash"
            )
            .execute()
        )

        sent += len(chunk)

        print(f"Sent batch: {sent}/{len(rows)}")

    return sent


def run_normalization_job(job, state=None, registry_entry=None):
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_rows = fetch_raw_funnel(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
    )

    if not raw_rows:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    snapshots = []

    for raw_row in raw_rows:
        payload = raw_row.get("payload", {}) or {}

        if isinstance(payload, dict) and payload.get("product") and payload.get("statistic"):
            products = [payload]
        else:
            products = (
                payload
                .get("data", {})
                .get("products", [])
            )

        for product in products:
            snapshot = prepare_snapshot(raw_row, product)

            if not snapshot:
                continue

            snapshots.append(snapshot)

    rows_upserted = 0
    if snapshots:
        rows_upserted = insert_snapshots(snapshots)

    newest_row = raw_rows[-1]

    return {
        "rows_read": len(raw_rows),
        "rows_upserted": rows_upserted,
        "last_raw_updated_at": newest_row.get("updated_at"),
        "last_raw_id": newest_row.get("id"),
    }


if __name__ == "__main__":
    result = run_normalization_job(
        job={
            "user_id": 1,
            "shop_id": 1,
        },
        state=None,
        registry_entry=None,
    )

    print(result)