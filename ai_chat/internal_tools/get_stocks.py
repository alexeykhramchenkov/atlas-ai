

from supabase import Client


PRODUCT_SELECT = """
snapshot_date,
product_key,
marketplace_product_id,
seller_sku,
total_quantity,
total_quantity_full,
total_in_way_to_client,
total_in_way_from_client,
total_stock_value,
variants_count,
warehouses_count,
avg_stock_value_per_unit,
stock_available_share_pct,
stock_in_way_to_client_share_pct,
stock_in_way_from_client_share_pct,
stock_growth_1d_pct,
available_stock_growth_1d_pct,
stock_value_growth_1d_pct,
stock_growth_7d_pct,
stock_value_growth_7d_pct,
stock_growth_30d_pct,
stock_value_growth_30d_pct
"""


VARIANT_SELECT = """
snapshot_date,
product_key,
marketplace_product_id,
variant_key,
marketplace_variant_id,
size_name,
seller_sku,
warehouse_key,
warehouse_name,
quantity,
quantity_full,
in_way_to_client,
in_way_from_client,
stock_value,
avg_stock_value_per_unit,
stock_available_share_pct,
stock_in_way_to_client_share_pct,
stock_in_way_from_client_share_pct,
stock_growth_1d_pct,
available_stock_growth_1d_pct,
stock_value_growth_1d_pct,
stock_growth_7d_pct,
stock_value_growth_7d_pct,
stock_growth_30d_pct,
stock_value_growth_30d_pct
"""


def get_stocks(
    supabase: Client,
    user_id: int,
    shop_id: int,
    marketplace: str = "wb",
    period_days: int = 30,
    product_key: str | None = None,
    variant_key: str | None = None,
    level: str = "product",
    latest_only: bool = True,
):
    """
    Read stock metrics from metrics_stocks_daily or metrics_stocks_variants_daily.

    Parameters:
        supabase: Supabase client
        user_id: User ID
        shop_id: Shop ID
        marketplace: Marketplace name
        period_days: Reserved for future history queries
        product_key: Optional product filter
        variant_key: Optional variant filter, used only for level='variant'
        level: 'product' for product aggregate, 'variant' for size/warehouse detail
        latest_only: If True returns only latest snapshot rows
    """

    if level not in {"product", "variant"}:
        raise ValueError("level must be 'product' or 'variant'")

    table_name = "metrics_stocks_daily" if level == "product" else "metrics_stocks_variants_daily"
    select_fields = PRODUCT_SELECT if level == "product" else VARIANT_SELECT

    query = (
        supabase
        .table(table_name)
        .select(select_fields)
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .order("snapshot_date", desc=True)
    )

    if product_key:
        query = query.eq("product_key", product_key)

    if level == "variant" and variant_key:
        query = query.eq("variant_key", variant_key)

    response = query.execute()
    rows = response.data or []

    if latest_only and rows:
        latest_date = rows[0]["snapshot_date"]
        rows = [row for row in rows if row["snapshot_date"] == latest_date]

    return rows


if __name__ == "__main__":
    print("get_stocks tool")
    print("Ready")