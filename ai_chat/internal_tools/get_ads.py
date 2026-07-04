

from supabase import Client


CAMPAIGN_SELECT = """
snapshot_date,
ad_id,
ad_platform,
campaign_id,
currency,
views,
clicks,
orders,
canceled,
add_to_cart,
shks,
spend,
revenue,
ctr_pct,
cart_rate_pct,
order_rate_pct,
cancel_rate_pct,
cpc,
cpm,
cpo,
roas,
acos_pct,
views_growth_1d_pct,
clicks_growth_1d_pct,
orders_growth_1d_pct,
spend_growth_1d_pct,
revenue_growth_1d_pct,
spend_growth_7d_pct,
orders_growth_7d_pct,
revenue_growth_7d_pct,
spend_growth_30d_pct,
orders_growth_30d_pct,
revenue_growth_30d_pct
"""


PRODUCT_SELECT = """
snapshot_date,
ad_id,
ad_platform,
campaign_id,
currency,
product_key,
marketplace_product_id,
variant_key,
marketplace_variant_id,
seller_sku,
title,
brand,
subject_id,
subject_name,
views,
clicks,
orders,
canceled,
add_to_cart,
shks,
spend,
revenue,
ctr_pct,
cart_rate_pct,
order_rate_pct,
cancel_rate_pct,
cpc,
cpm,
cpo,
roas,
acos_pct,
views_growth_1d_pct,
clicks_growth_1d_pct,
orders_growth_1d_pct,
spend_growth_1d_pct,
revenue_growth_1d_pct,
spend_growth_7d_pct,
orders_growth_7d_pct,
revenue_growth_7d_pct,
spend_growth_30d_pct,
orders_growth_30d_pct,
revenue_growth_30d_pct
"""


def get_ads(
    supabase: Client,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = 30,
    campaign_id: str | None = None,
    product_key: str | None = None,
    level: str = "campaign",
    latest_only: bool = True,
):

    if level not in {"campaign", "product"}:
        raise ValueError("level must be 'campaign' or 'product'")

    table_name = (
        "metrics_ads_daily"
        if level == "campaign"
        else "metrics_ads_product_daily"
    )

    select_fields = (
        CAMPAIGN_SELECT
        if level == "campaign"
        else PRODUCT_SELECT
    )

    query = (
        supabase
        .table(table_name)
        .select(select_fields)
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .order("snapshot_date", desc=True)
    )

    if campaign_id:
        query = query.eq("campaign_id", campaign_id)

    if level == "product" and product_key:
        query = query.eq("product_key", product_key)

    response = query.execute()
    rows = response.data or []

    if latest_only and rows:
        latest_date = rows[0]["snapshot_date"]
        rows = [r for r in rows if r["snapshot_date"] == latest_date]

    return rows


if __name__ == "__main__":
    print("get_ads tool")
    print("Ready")