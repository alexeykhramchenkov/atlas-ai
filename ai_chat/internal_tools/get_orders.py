"""Orders facts: approved period totals and per-product breakdown, tenant scoped."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation

PAGE_SIZE = 1000


class IncompleteOrdersError(ValueError):
    def __init__(self, start_date, end_date):
        self.start_date = start_date
        self.end_date = end_date
        super().__init__(f"Orders data is incomplete for {start_date} — {end_date}")


def get_orders(user_id, shop_id, marketplace="wb", product_key=None,
               period_days=None, start_date=None, end_date=None, level="product", *, supabase=None):
    if supabase is None:
        raise ValueError("Supabase client is required")
    if not user_id or not shop_id or not marketplace:
        raise ValueError("Complete tenant context is required")
    if level not in {"product","variant"}:
        raise ValueError("level must be product or variant")
    explicit = start_date is not None or end_date is not None
    if (period_days is not None) == explicit:
        raise ValueError("Specify period_days OR both start_date and end_date")
    completed = datetime.now(ZoneInfo("Europe/Moscow")).date() - timedelta(days=1)
    if explicit:
        if start_date is None or end_date is None:
            raise ValueError("Both dates are required")
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    else:
        if type(period_days) is not int or not 1 <= period_days <= 365:
            raise ValueError("period_days must be an integer from 1 to 365")
        end = completed
        start = end - timedelta(days=period_days - 1)
    if start > end or end > completed:
        raise ValueError("Invalid period or unfinished calendar day")
    start_date, end_date = start.isoformat(), end.isoformat()
    # Coverage is checked across the shop, not the selected product. A product
    # with zero orders need not have a row on every day.
    table = "metrics_orders_variants_daily" if level == "variant" else "metrics_orders_daily"
    dimensions = ",variant_key,size_name" if level == "variant" else ""
    rows = []
    offset = 0
    while True:
        batch = (supabase.table(table)
                 .select("id,snapshot_date,product_key,orders_count,cancelled_orders_count,gross_order_value,net_order_value"+dimensions)
                 .eq("user_id", user_id).eq("shop_id", shop_id).eq("marketplace", marketplace)
                 .gte("snapshot_date", start_date).lte("snapshot_date", end_date)
                 .order("snapshot_date").order("product_key").order("id")
                 .range(offset, offset + PAGE_SIZE - 1).execute().data or [])
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    dates = {str(row["snapshot_date"])[:10] for row in rows}
    if any((start + timedelta(days=n)).isoformat() not in dates for n in range((end-start).days+1)):
        raise IncompleteOrdersError(start_date, end_date)
    totals = {}
    for row in rows:
        key = row.get("product_key")
        if not key:
            raise ValueError("Order metric lacks product_key")
        if product_key is not None and key != product_key:
            continue
        values = []
        for field in ("orders_count", "cancelled_orders_count"):
            value = row.get(field)
            if value is None or isinstance(value, bool):
                raise ValueError(f"Missing order fact: {field}")
            try:
                number = Decimal(str(value))
            except InvalidOperation:
                raise ValueError(f"Invalid order fact: {field}") from None
            if not number.is_finite() or number < 0 or number != number.to_integral_value():
                raise ValueError(f"Invalid order fact: {field}")
            values.append(int(number))
        group_key = (key, row.get("variant_key")) if level == "variant" else key
        if level == "variant" and not group_key[1]:
            raise ValueError("Order metric lacks variant_key")
        item = totals.setdefault(group_key, {"product_key":key,"title":None,"orders_count":0,"cancelled_orders_count":0,
                                      "orders_amount":Decimal(0),"cancelled_orders_amount":Decimal(0)})
        if level == "variant":
            if "size_name" in item and item["size_name"] != row.get("size_name"):
                raise ValueError("Conflicting variant size")
            item.update(variant_key=row["variant_key"],size_name=row.get("size_name"))
        item["orders_count"] += values[0]
        item["cancelled_orders_count"] += values[1]
        amounts = []
        for field in ("gross_order_value", "net_order_value"):
            value = row.get(field)
            if value is None:
                amounts.append(None)
                continue
            if isinstance(value, bool): raise ValueError(f"Invalid order amount: {field}")
            try: number = Decimal(str(value))
            except InvalidOperation: raise ValueError(f"Invalid order amount: {field}") from None
            if not number.is_finite() or number < 0: raise ValueError(f"Invalid order amount: {field}")
            amounts.append(number)
        gross, net = amounts
        if gross is not None and net is not None and net > gross:
            raise ValueError("Net order value exceeds gross")
        for field, amount in (("orders_amount", gross), ("cancelled_orders_amount", gross-net if gross is not None and net is not None else None)):
            item[field] = None if item[field] is None or amount is None else item[field]+amount
    from ._common import product_titles
    from ._common import json_number
    for item in totals.values():
        for field in ("orders_amount", "cancelled_orders_amount"):
            if item[field] is not None: item[field] = json_number(item[field])
    products=product_titles(supabase,[totals[key] for key in sorted(totals)],user_id,shop_id,marketplace)
    return {"start_date":start_date,"end_date":end_date,
            "orders_count":sum(row["orders_count"] for row in products),
            "cancelled_orders_count":sum(row["cancelled_orders_count"] for row in products),
            **{field:None if any(row[field] is None for row in products) else json_number(sum((Decimal(str(row[field])) for row in products),Decimal(0)))
               for field in ("orders_amount", "cancelled_orders_amount")},
            "variants" if level == "variant" else "products":products}
