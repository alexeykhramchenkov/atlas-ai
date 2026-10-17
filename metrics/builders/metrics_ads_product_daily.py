

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "snapshots_ads_product_daily"
TARGET_TABLE = "metrics_ads_product_daily"
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
            .gte("date", start_date.isoformat())
            .lt("date", end_date_exclusive.isoformat())
            .order("date")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_lookup(rows: List[Dict[str, Any]]) -> Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]]:
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]] = {}

    for row in rows:
        snapshot_date = parse_date(row.get("date"))
        campaign_id = row.get("campaign_id") or str(row.get("ad_id")) if row.get("ad_id") is not None else None
        ad_platform = row.get("ad_platform") or "wb_ads"
        product_key = row.get("product_key")
        user_id = row.get("user_id")
        shop_id = row.get("shop_id")
        marketplace = row.get("marketplace") or MARKETPLACE

        if snapshot_date is None or not campaign_id or not product_key or user_id is None or shop_id is None:
            continue

        lookup[(user_id, shop_id, marketplace, ad_platform, str(campaign_id), product_key, snapshot_date)] = row

    return lookup


def sum_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    ad_platform: str,
    campaign_id: str,
    product_key: str,
    end_date: date,
    days: int,
    field: str,
) -> float:
    total = 0.0

    for index in range(days):
        item_date = end_date - timedelta(days=index)
        row = lookup.get((user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, item_date))
        if row:
            total += to_float(row.get(field))

    return total


def previous_period_value(
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]],
    user_id: Any,
    shop_id: Any,
    marketplace: str,
    ad_platform: str,
    campaign_id: str,
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
        ad_platform=ad_platform,
        campaign_id=campaign_id,
        product_key=product_key,
        end_date=period_end,
        days=days,
        field=field,
    )


def build_metric_row(
    row: Dict[str, Any],
    lookup: Dict[Tuple[Any, Any, str, str, str, str, date], Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    metric_date = parse_date(row.get("date"))
    campaign_id = row.get("campaign_id") or str(row.get("ad_id")) if row.get("ad_id") is not None else None
    ad_platform = row.get("ad_platform") or "wb_ads"
    product_key = row.get("product_key")
    user_id = row.get("user_id")
    shop_id = row.get("shop_id")
    marketplace = row.get("marketplace") or MARKETPLACE

    if metric_date is None or not campaign_id or not product_key or user_id is None or shop_id is None:
        return None

    campaign_id = str(campaign_id)

    views = to_float(row.get("views"))
    clicks = to_float(row.get("clicks"))
    orders = to_float(row.get("orders"))
    canceled = to_float(row.get("canceled"))
    spend = to_float(row.get("spend"))
    revenue = to_float(row.get("revenue"))
    add_to_cart = to_float(row.get("add_to_cart"))
    shks = to_float(row.get("shks"))

    previous_day = metric_date - timedelta(days=1)
    previous_row = lookup.get((user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, previous_day))

    previous_views = to_float(previous_row.get("views")) if previous_row else 0
    previous_clicks = to_float(previous_row.get("clicks")) if previous_row else 0
    previous_orders = to_float(previous_row.get("orders")) if previous_row else 0
    previous_spend = to_float(previous_row.get("spend")) if previous_row else 0
    previous_revenue = to_float(previous_row.get("revenue")) if previous_row else 0

    current_7d_spend = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 7, 1, "spend")
    previous_7d_spend = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 7, 8, "spend")
    current_30d_spend = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 30, 1, "spend")
    previous_30d_spend = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 30, 31, "spend")

    current_7d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 7, 1, "orders")
    previous_7d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 7, 8, "orders")
    current_30d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 30, 1, "orders")
    previous_30d_orders = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 30, 31, "orders")

    current_7d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 7, 1, "revenue")
    previous_7d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 7, 8, "revenue")
    current_30d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 30, 1, "revenue")
    previous_30d_revenue = previous_period_value(lookup, user_id, shop_id, marketplace, ad_platform, campaign_id, product_key, metric_date, 30, 31, "revenue")

    ctr_pct = round(safe_divide(clicks, views) * 100, 2)
    cart_rate_pct = round(safe_divide(add_to_cart, clicks) * 100, 2)
    order_rate_pct = round(safe_divide(orders, clicks) * 100, 2)
    cancel_rate_pct = round(safe_divide(canceled, orders) * 100, 2)
    cpc = round(safe_divide(spend, clicks), 2)
    cpm = round(safe_divide(spend, views) * 1000, 2)
    cpo = round(safe_divide(spend, orders), 2)
    roas = round(safe_divide(revenue, spend), 2)
    acos_pct = round(safe_divide(spend, revenue) * 100, 2)

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": metric_date.isoformat(),
        "ad_id": row.get("ad_id"),
        "ad_platform": ad_platform,
        "campaign_id": campaign_id,
        "currency": row.get("currency") or "RUB",

        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id"),
        "variant_key": row.get("variant_key"),
        "marketplace_variant_id": row.get("marketplace_variant_id"),
        "seller_sku": row.get("seller_sku"),
        "title": row.get("title"),
        "brand": row.get("brand"),
        "subject_id": row.get("subject_id"),
        "subject_name": row.get("subject_name"),

        "views": round(views, 2),
        "clicks": round(clicks, 2),
        "orders": round(orders, 2),
        "canceled": round(canceled, 2),
        "add_to_cart": round(add_to_cart, 2),
        "shks": round(shks, 2),
        "spend": round(spend, 2),
        "revenue": round(revenue, 2),

        "ctr_pct": ctr_pct,
        "cart_rate_pct": cart_rate_pct,
        "order_rate_pct": order_rate_pct,
        "cancel_rate_pct": cancel_rate_pct,
        "cpc": cpc,
        "cpm": cpm,
        "cpo": cpo,
        "roas": roas,
        "acos_pct": acos_pct,

        "views_growth_1d_pct": growth_pct(views, previous_views),
        "clicks_growth_1d_pct": growth_pct(clicks, previous_clicks),
        "orders_growth_1d_pct": growth_pct(orders, previous_orders),
        "spend_growth_1d_pct": growth_pct(spend, previous_spend),
        "revenue_growth_1d_pct": growth_pct(revenue, previous_revenue),

        "spend_growth_7d_pct": growth_pct(current_7d_spend, previous_7d_spend),
        "orders_growth_7d_pct": growth_pct(current_7d_orders, previous_7d_orders),
        "revenue_growth_7d_pct": growth_pct(current_7d_revenue, previous_7d_revenue),

        "spend_growth_30d_pct": growth_pct(current_30d_spend, previous_30d_spend),
        "orders_growth_30d_pct": growth_pct(current_30d_orders, previous_30d_orders),
        "revenue_growth_30d_pct": growth_pct(current_30d_revenue, previous_30d_revenue),
    }


def build_metrics(rows: List[Dict[str, Any]], dates_to_build: List[date]) -> List[Dict[str, Any]]:
    lookup = build_lookup(rows)
    target_dates: Set[date] = set(dates_to_build)
    metrics: List[Dict[str, Any]] = []

    for row in rows:
        row_date = parse_date(row.get("date"))
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
                on_conflict="user_id,shop_id,marketplace,ad_platform,campaign_id,product_key,snapshot_date",
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(rows)}")

    return sent


def run_metric_job(job, state, registry_entry) -> Dict[str, Any]:
    user_id, shop_id = int(job["user_id"]), int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    user_id = job.get("user_id")
    shop_id = job.get("shop_id")
    marketplace = job.get("marketplace") or MARKETPLACE

    source_table = registry_entry.get("source_table_name") or SOURCE_TABLE
    target_table = registry_entry.get("target_table_name") or TARGET_TABLE

    print(
        f"Resolving ads product metrics coverage "
        f"for user_id={user_id} shop_id={shop_id} marketplace={marketplace}..."
    )

    dates_to_build = get_dates_to_build(
        normalized_table=source_table,
        normalized_date_column="date",
        snapshot_table=target_table,
        snapshot_date_column="snapshot_date",
        marketplace=marketplace,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No ads product metrics to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching ads product snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)

    if user_id is not None:
        snapshots = [row for row in snapshots if row.get("user_id") == user_id]

    if shop_id is not None:
        snapshots = [row for row in snapshots if row.get("shop_id") == shop_id]

    print(f"Ads product snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Ads product metrics prepared: {len(metrics)}")

    rows_upserted = upsert_metrics(metrics)
    last_processed_date = max(dates_to_build).isoformat() if dates_to_build else None

    return {
        "rows_read": len(snapshots),
        "rows_upserted": rows_upserted,
        "last_processed_date": last_processed_date,
    }

def main( *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> None:
    print("Resolving ads product metrics coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="date",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No ads product metrics to build")
        return

    print("Fetching ads product snapshots with history...")
    snapshots = fetch_snapshots_for_metric_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Ads product snapshots fetched: {len(snapshots)}")

    metrics = build_metrics(snapshots, dates_to_build)
    print(f"Ads product metrics prepared: {len(metrics)}")

    sent = upsert_metrics(metrics)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")


if __name__ == "__main__":
    main()