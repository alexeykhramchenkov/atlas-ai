from __future__ import annotations

from typing import Any


PRODUCTS_TABLE = "normalized_products"


def enrich_products(
    rows: list[dict],
    supabase,
) -> list[dict]:

    if not rows:
        return rows

    product_keys = sorted(
        {
            row.get("product_key")
            for row in rows
            if row.get("product_key")
        }
    )

    if not product_keys:
        return rows

    try:

        response = (
            supabase
            .table(PRODUCTS_TABLE)
            .select(
                """
                product_key,
                title,
                brand,
                seller_sku,
                subject_name,
                main_photo_url,
                marketplace_product_id
                """
            )
            .in_("product_key", product_keys)
            .execute()
        )

        products = response.data or []

    except Exception:
        return rows

    products_map = {
        product["product_key"]: product
        for product in products
    }

    enriched_rows = []

    for row in rows:

        enriched_row = dict(row)

        product = products_map.get(
            row.get("product_key")
        )

        if product:

            enriched_row["title"] = (
                product.get("title")
            )

            enriched_row["brand"] = (
                product.get("brand")
            )

            enriched_row["seller_sku"] = (
                product.get("seller_sku")
            )

            enriched_row["subject_name"] = (
                product.get("subject_name")
            )

            enriched_row["main_photo_url"] = (
                product.get("main_photo_url")
            )

            enriched_row["marketplace_product_id"] = (
                product.get("marketplace_product_id")
            )

        enriched_rows.append(
            enriched_row
        )

    return enriched_rows
