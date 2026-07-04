from datetime import date, datetime, timedelta

from supabase import Client


PAGE_SIZE = 1000


def get_orders(
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = 30,
    product_key: str | None = None,
    latest_only: bool = True,
    supabase: Client | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """
    Read orders metrics from metrics_orders_daily.

    Parameters:
        supabase: Supabase client
        user_id: User ID
        shop_id: Shop ID
        marketplace: Marketplace name
        period_days: Number of days to include when latest_only is False
        product_key: Optional product filter
        latest_only: If True returns only latest snapshot rows
        start_date: Optional inclusive snapshot_date lower bound
        end_date: Optional inclusive snapshot_date upper bound
    """
    if supabase is None:
        raise ValueError(
            "Supabase client is None. Pass supabase from Executor or Dataset."
        )

    query = (
        supabase
        .table("metrics_orders_daily")
        .select(
            """
            snapshot_date,
            product_key,
            marketplace_product_id,
            seller_sku,
            orders_count,
            cancelled_orders_count,
            gross_order_value,
            net_order_value,
            cancel_rate,
            avg_order_value,
            orders_share_pct,
            revenue_share_pct,
            orders_growth_1d_pct,
            orders_growth_7d_pct,
            orders_growth_30d_pct,
            revenue_growth_1d_pct,
            revenue_growth_7d_pct,
            revenue_growth_30d_pct
            """
        )
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .order("snapshot_date", desc=True)
    )

    if start_date:
        query = query.gte("snapshot_date", start_date)

    if end_date:
        query = query.lte("snapshot_date", end_date)

    if not latest_only and not start_date:
        latest_snapshot_date = _get_latest_snapshot_date(
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            product_key=product_key,
        )
        date_from = (latest_snapshot_date - timedelta(days=period_days - 1)).isoformat()
        query = query.gte("snapshot_date", date_from)

    if product_key:
        query = query.eq("product_key", product_key)

    rows = _execute_query(query=query, paginated=bool(start_date or end_date) or not latest_only)

    if latest_only and rows:
        latest_date = rows[0]["snapshot_date"]
        rows = [row for row in rows if row["snapshot_date"] == latest_date]
        return rows

    return _aggregate_orders_rows(rows)


def _execute_query(query, paginated: bool) -> list[dict]:
    if not paginated:
        response = query.execute()
        return response.data or []

    rows: list[dict] = []
    start = 0

    while True:
        response = query.range(start, start + PAGE_SIZE - 1).execute()
        page_rows = response.data or []
        rows.extend(page_rows)

        if len(page_rows) < PAGE_SIZE:
            break

        start += PAGE_SIZE

    return rows


def _get_latest_snapshot_date(
    supabase: Client,
    user_id: int,
    shop_id: int,
    marketplace: str,
    product_key: str | None = None,
) -> date:
    query = (
        supabase
        .table("metrics_orders_daily")
        .select("snapshot_date")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .order("snapshot_date", desc=True)
        .limit(1)
    )

    if product_key:
        query = query.eq("product_key", product_key)

    response = query.execute()
    rows = response.data or []

    if not rows or not rows[0].get("snapshot_date"):
        return date.today()

    snapshot_date = rows[0]["snapshot_date"]

    if isinstance(snapshot_date, date):
        return snapshot_date

    return datetime.fromisoformat(str(snapshot_date)).date()


def _safe_float(value) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _aggregate_orders_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}

    for row in rows:
        product_key = row.get("product_key")
        if not product_key:
            continue

        current = grouped.setdefault(
            product_key,
            {
                "snapshot_date": row.get("snapshot_date"),
                "product_key": product_key,
                "marketplace_product_id": row.get("marketplace_product_id"),
                "seller_sku": row.get("seller_sku"),
                "orders_count": 0.0,
                "cancelled_orders_count": 0.0,
                "gross_order_value": 0.0,
                "net_order_value": 0.0,
                "cancelled_revenue": 0.0,
                "cancel_rate": 0.0,
                "avg_order_value": 0.0,
                "orders_share_pct": 0.0,
                "revenue_share_pct": 0.0,
                "orders_growth_1d_pct": row.get("orders_growth_1d_pct"),
                "orders_growth_7d_pct": row.get("orders_growth_7d_pct"),
                "orders_growth_30d_pct": row.get("orders_growth_30d_pct"),
                "revenue_growth_1d_pct": row.get("revenue_growth_1d_pct"),
                "revenue_growth_7d_pct": row.get("revenue_growth_7d_pct"),
                "revenue_growth_30d_pct": row.get("revenue_growth_30d_pct"),
            },
        )

        current["orders_count"] += _safe_float(row.get("orders_count"))
        current["cancelled_orders_count"] += _safe_float(row.get("cancelled_orders_count"))
        current["gross_order_value"] += _safe_float(row.get("gross_order_value"))
        current["net_order_value"] += _safe_float(row.get("net_order_value"))
        current["cancelled_revenue"] = (
            current["gross_order_value"]
            - current["net_order_value"]
        )

        if row.get("snapshot_date") and row.get("snapshot_date") > current.get("snapshot_date"):
            current["snapshot_date"] = row.get("snapshot_date")
            current["marketplace_product_id"] = row.get("marketplace_product_id")
            current["seller_sku"] = row.get("seller_sku")
            current["orders_growth_1d_pct"] = row.get("orders_growth_1d_pct")
            current["orders_growth_7d_pct"] = row.get("orders_growth_7d_pct")
            current["orders_growth_30d_pct"] = row.get("orders_growth_30d_pct")
            current["revenue_growth_1d_pct"] = row.get("revenue_growth_1d_pct")
            current["revenue_growth_7d_pct"] = row.get("revenue_growth_7d_pct")
            current["revenue_growth_30d_pct"] = row.get("revenue_growth_30d_pct")

    total_orders = sum(row["orders_count"] for row in grouped.values())
    total_revenue = sum(row["gross_order_value"] for row in grouped.values())

    for row in grouped.values():
        orders = row["orders_count"]
        cancelled = row["cancelled_orders_count"]
        revenue = row["gross_order_value"]

        row["cancel_rate"] = round((cancelled / orders) * 100, 2) if orders else 0.0
        row["avg_order_value"] = round(revenue / orders, 2) if orders else 0.0
        row["orders_share_pct"] = round((orders / total_orders) * 100, 2) if total_orders else 0.0
        row["revenue_share_pct"] = round((revenue / total_revenue) * 100, 2) if total_revenue else 0.0

    return list(grouped.values())


if __name__ == "__main__":
    print("get_orders tool")
    print("Ready")
