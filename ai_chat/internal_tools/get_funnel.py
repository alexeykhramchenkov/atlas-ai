

from supabase import Client


PAGE_SIZE = 1000


def get_funnel(
    supabase: Client,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = 30,
    product_key: str | None = None,
    latest_only: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
):
    """
    Read funnel metrics from metrics_funnel_daily.

    Parameters:
        supabase: Supabase client
        user_id: User ID
        shop_id: Shop ID
        marketplace: Marketplace name
        period_days: Reserved for future history queries
        product_key: Optional product filter
        latest_only: If True returns only latest snapshot rows
        start_date: Optional inclusive snapshot_date lower bound
        end_date: Optional inclusive snapshot_date upper bound
    """

    query = (
        supabase
        .table("metrics_funnel_daily")
        .select(
            """
            snapshot_date,
            product_key,
            marketplace_product_id,
            seller_sku,
            open_count,
            cart_count,
            order_count,
            buyout_count,
            cancel_count,
            order_sum,
            buyout_sum,
            cancel_sum,
            wishlist_adds,
            avg_price,
            stocks_wb,
            stocks_mp,
            stock_balance_sum,
            product_rating,
            feedback_rating,
            localization_pct,
            open_to_cart_pct,
            cart_to_order_pct,
            order_to_buyout_pct,
            cancel_rate_pct,
            buyout_rate_pct,
            wishlist_rate_pct,
            open_growth_1d_pct,
            cart_growth_1d_pct,
            order_growth_1d_pct,
            buyout_growth_1d_pct,
            order_sum_growth_1d_pct,
            buyout_sum_growth_1d_pct,
            open_growth_7d_pct,
            order_growth_7d_pct,
            buyout_sum_growth_7d_pct,
            open_growth_30d_pct,
            order_growth_30d_pct,
            buyout_sum_growth_30d_pct
            """
        )
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .order("snapshot_date", desc=True)
    )

    if product_key:
        query = query.eq("product_key", product_key)

    if start_date:
        query = query.gte("snapshot_date", start_date)

    if end_date:
        query = query.lte("snapshot_date", end_date)

    rows = _execute_query(query=query, paginated=bool(start_date or end_date) or not latest_only)

    if latest_only and rows:
        latest_date = rows[0]["snapshot_date"]
        rows = [row for row in rows if row["snapshot_date"] == latest_date]

    return rows


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


if __name__ == "__main__":
    print("get_funnel tool")
    print("Ready")
