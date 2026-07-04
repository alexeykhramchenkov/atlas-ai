

from supabase import Client


def get_profit(
    supabase: Client,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = 30,
    product_key: str | None = None,
    latest_only: bool = True,
):
    """
    Read profit and financial metrics from metrics_financial_daily.

    Parameters:
        supabase: Supabase client
        user_id: User ID
        shop_id: Shop ID
        marketplace: Marketplace name
        period_days: Reserved for future history queries
        product_key: Optional product filter
        latest_only: If True returns only latest snapshot rows
    """

    query = (
        supabase
        .table("metrics_financial_daily")
        .select(
            """
            snapshot_date,
            product_key,
            marketplace_product_id,
            sales_count,
            returns_count,
            net_sales_count,
            sales_amount,
            returns_amount,
            net_sales_amount,
            cogs_amount,
            marketplace_expense_amount,
            commission_amount,
            logistics_amount,
            storage_amount,
            acquiring_amount,
            deduction_amount,
            gross_profit,
            net_profit,
            gross_margin_pct,
            net_margin_pct,
            expense_rate_pct,
            commission_rate_pct,
            logistics_rate_pct,
            storage_rate_pct,
            acquiring_rate_pct,
            deduction_rate_pct,
            profit_growth_1d_pct,
            profit_growth_7d_pct,
            profit_growth_30d_pct,
            net_sales_growth_1d_pct,
            net_sales_growth_7d_pct,
            net_sales_growth_30d_pct,
            source_type
            """
        )
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .order("snapshot_date", desc=True)
    )

    if product_key:
        query = query.eq("product_key", product_key)

    response = query.execute()
    rows = response.data or []

    if latest_only and rows:
        latest_date = rows[0]["snapshot_date"]
        rows = [row for row in rows if row["snapshot_date"] == latest_date]

    return rows


if __name__ == "__main__":
    print("get_profit tool")
    print("Ready")