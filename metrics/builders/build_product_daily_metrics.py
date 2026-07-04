from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, Tuple

from db.client import supabase


MARKETPLACE = "wb"
USER_ID = 1
TARGET_TABLE = "nm_daily_metrics"


def to_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def metric_key(date_value: str, nm_id: Any, barcode: Any = None, size: Any = None) -> Tuple[str, str, str, str]:
    return (
        str(date_value)[:10],
        str(nm_id) if nm_id is not None else "",
        "",
        "",
    )


def build_product_daily_metrics() -> dict:
    metrics: Dict[Tuple[str, str, str, str], dict] = defaultdict(lambda: {
        "orders_qty": 0,
        "sales_qty": 0,
        "cancel_qty": 0,
        "returns_qty": 0,
        "orders_sum": Decimal("0"),
        "sales_sum": Decimal("0"),
        "cancel_sum": Decimal("0"),
        "returns_sum": Decimal("0"),
        "payout_amount": Decimal("0"),
        "commission_rub": Decimal("0"),
        "logistics_to_client": Decimal("0"),
        "logistics_from_client": Decimal("0"),
        "stock_qty": 0,
        "stock_qty_full": 0,
        "title": None,
        "vendor_code": None,
        "brand": None,
        "category": None,
        "size": None,
        "barcode": None,
        "nm_id": None,
        "user_id": USER_ID,
        "shop_id": USER_ID,
        "marketplace": MARKETPLACE,
        "product_id": None,
        "variant_id": None,
        "marketplace_product_id": None,
        "marketplace_variant_id": None,
        "sku": None,
    })

    catalog_rows = (
        supabase.table("sku_catalog")
        .select("*")
        .eq("marketplace", MARKETPLACE)
        .execute()
        .data or []
    )

    catalog_by_nm_barcode = {}
    catalog_by_nm_size = {}
    catalog_by_nm = {}

    for item in catalog_rows:
        nm_id = str(item.get("nm_id")) if item.get("nm_id") is not None else ""
        barcode = str(item.get("barcode")) if item.get("barcode") is not None else ""
        size = str(item.get("size")) if item.get("size") is not None else ""

        if nm_id:
            catalog_by_nm[nm_id] = item

        if nm_id and barcode:
            catalog_by_nm_barcode[(nm_id, barcode)] = item

        if nm_id and size:
            catalog_by_nm_size[(nm_id, size)] = item

    def enrich_from_catalog(row: dict) -> None:
        nm_id = str(row.get("nm_id")) if row.get("nm_id") is not None else ""
        barcode = str(row.get("barcode")) if row.get("barcode") is not None else ""
        size = str(row.get("size")) if row.get("size") is not None else ""

        catalog_item = None
        exact_match = False

        if nm_id and barcode:
            catalog_item = catalog_by_nm_barcode.get((nm_id, barcode))
            exact_match = catalog_item is not None

        if catalog_item is None and nm_id and size:
            catalog_item = catalog_by_nm_size.get((nm_id, size))
            exact_match = catalog_item is not None

        if catalog_item is None and nm_id:
            catalog_item = catalog_by_nm.get(nm_id)

        if catalog_item is None:
            return

        row["title"] = catalog_item.get("title") or row.get("title") or row.get("category")
        row["vendor_code"] = catalog_item.get("vendor_code") or row.get("vendor_code")
        row["brand"] = catalog_item.get("brand") or row.get("brand")
        row["category"] = catalog_item.get("category") or row.get("category")
        row["product_id"] = catalog_item.get("product_id") or row.get("product_id")
        row["marketplace_product_id"] = catalog_item.get("marketplace_product_id") or row.get("marketplace_product_id")

        if exact_match:
            row["size"] = catalog_item.get("size") or row.get("size")
            row["barcode"] = catalog_item.get("barcode") or row.get("barcode")
            row["variant_id"] = catalog_item.get("variant_id") or row.get("variant_id")
            row["marketplace_variant_id"] = catalog_item.get("marketplace_variant_id") or row.get("marketplace_variant_id")
            row["sku"] = catalog_item.get("sku") or row.get("sku")

    orders = (
        supabase.table("orders")
        .select("*")
        .eq("marketplace", MARKETPLACE)
        .execute()
        .data or []
    )

    for order in orders:
        key = metric_key(order.get("order_date"), order.get("nm_id"))
        row = metrics[key]

        row.update({
            "metric_date": key[0],
            "nm_id": order.get("nm_id"),
            "barcode": order.get("barcode"),
            "size": order.get("tech_size") or order.get("size"),
            "vendor_code": order.get("supplier_article"),
            "brand": order.get("brand"),
            "category": order.get("category"),
            "product_id": order.get("product_id"),
            "variant_id": order.get("variant_id"),
            "marketplace_product_id": order.get("marketplace_product_id"),
            "marketplace_variant_id": order.get("marketplace_variant_id"),
            "sku": order.get("sku"),
        })

        row["orders_qty"] += 1
        row["orders_sum"] += to_decimal(order.get("finished_price"))

        if order.get("is_cancel"):
            row["cancel_qty"] += 1
            row["cancel_sum"] += to_decimal(order.get("finished_price"))

    sales = (
        supabase.table("sales")
        .select("*")
        .eq("marketplace", MARKETPLACE)
        .execute()
        .data or []
    )

    for sale in sales:
        key = metric_key(sale.get("sale_date"), sale.get("nm_id"))
        row = metrics[key]

        row.update({
            "metric_date": key[0],
            "nm_id": sale.get("nm_id"),
            "barcode": sale.get("barcode"),
            "size": sale.get("tech_size") or sale.get("size"),
            "vendor_code": sale.get("supplier_article"),
            "brand": sale.get("brand"),
            "category": sale.get("category"),
            "product_id": sale.get("product_id"),
            "variant_id": sale.get("variant_id"),
            "marketplace_product_id": sale.get("marketplace_product_id"),
            "marketplace_variant_id": sale.get("marketplace_variant_id"),
            "sku": sale.get("sku"),
        })

        quantity = int(sale.get("quantity") or 1)

        if str(sale.get("sale_id") or "").startswith("R"):
            row["returns_qty"] += quantity
            row["returns_sum"] += to_decimal(sale.get("finished_price"))
        else:
            row["sales_qty"] += quantity
            row["sales_sum"] += to_decimal(sale.get("finished_price"))
            row["payout_amount"] += to_decimal(sale.get("for_pay"))

    stocks = (
        supabase.table("stock_snapshots")
        .select("*")
        .eq("marketplace", MARKETPLACE)
        .execute()
        .data or []
    )

    for stock in stocks:
        key = metric_key(stock.get("snapshot_date"), stock.get("product_id"))
        row = metrics[key]

        row.update({
            "metric_date": key[0],
            "nm_id": int(stock["product_id"]) if stock.get("product_id") else None,
            "barcode": stock.get("barcode"),
            "size": stock.get("tech_size") or stock.get("variant_id"),
            "product_id": stock.get("product_id"),
            "variant_id": stock.get("variant_id"),
            "marketplace_product_id": stock.get("marketplace_product_id"),
            "marketplace_variant_id": stock.get("marketplace_variant_id"),
            "sku": stock.get("sku"),
        })

        row["stock_qty"] += int(stock.get("quantity") or 0)
        row["stock_qty_full"] += int(stock.get("quantity_full") or 0)

    finance = (
        supabase.table("financial_events")
        .select("*")
        .eq("marketplace", MARKETPLACE)
        .execute()
        .data or []
    )

    for event in finance:
        event_date = event.get("event_date")
        product_id = event.get("product_id")

        # Financial events from WB realization are product-level facts.
        # They are not always reliably tied to barcode/size, so we aggregate them by product + date.
        key = metric_key(event_date, product_id)
        row = metrics[key]

        row.update({
            "metric_date": key[0],
            "nm_id": int(product_id) if product_id else None,
            "barcode": None,
            "size": None,
            "product_id": product_id,
            "variant_id": None,
            "marketplace_product_id": product_id,
            "marketplace_variant_id": None,
            "sku": None,
        })

        amount = to_decimal(event.get("amount"))
        event_type = event.get("event_type")

        if event_type == "payout":
            row["payout_amount"] += amount
        elif event_type == "commission":
            row["commission_rub"] += amount
        elif event_type == "logistics_to_client":
            row["logistics_to_client"] += amount
        elif event_type in ("logistics_from_client", "rebill_logistic_cost"):
            row["logistics_from_client"] += amount

    rows = []

    for row in metrics.values():
        orders_qty = row["orders_qty"]
        sales_qty = row["sales_qty"]
        cancel_qty = row["cancel_qty"]
        returns_qty = row["returns_qty"]

        row["buyout_pct"] = float(sales_qty / orders_qty * 100) if orders_qty else None
        row["cancel_pct"] = float(cancel_qty / orders_qty * 100) if orders_qty else None
        row["return_pct"] = float(returns_qty / sales_qty * 100) if sales_qty else None
        row["profit_rub"] = None
        row["margin_pct"] = None

        enrich_from_catalog(row)

        row["barcode"] = None
        row["size"] = None
        row["variant_id"] = None
        row["marketplace_variant_id"] = None

        if not row.get("nm_id") or int(row.get("nm_id")) == 0:
            continue

        for field in (
            "orders_sum",
            "sales_sum",
            "cancel_sum",
            "returns_sum",
            "payout_amount",
            "commission_rub",
            "logistics_to_client",
            "logistics_from_client",
        ):
            row[field] = str(row[field])

        rows.append(row)

    supabase.table(TARGET_TABLE).delete().eq("marketplace", MARKETPLACE).execute()

    batch_size = 500
    for index in range(0, len(rows), batch_size):
        supabase.table(TARGET_TABLE).upsert(
            rows[index:index + batch_size],
            on_conflict="user_id,metric_date,nm_id,barcode",
        ).execute()

    result = {
        "status": "ok",
        "metrics_rows": len(rows),
    }

    print(result)
    return result


if __name__ == "__main__":
    build_product_daily_metrics()