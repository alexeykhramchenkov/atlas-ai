"""Funnel facts: period totals and per-product breakdown, tenant scoped."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation

PAGE_SIZE = 1000
FIELDS = ("open_count", "cart_count", "order_count", "buyout_count", "cancel_count")


from ._common import DataUnavailableError


class FunnelDataUnavailableError(DataUnavailableError):
    pass


def get_funnel(user_id, shop_id, marketplace="wb", product_key=None,
               period_days=None, start_date=None, end_date=None, *, supabase=None):
    if supabase is None:
        raise ValueError("Supabase client is required")
    if not user_id or not shop_id or not marketplace:
        raise ValueError("Complete tenant context is required")
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
    rows = []
    offset = 0
    while True:
        batch = (supabase.table("metrics_funnel_daily")
                 .select("id,snapshot_date,product_key,open_count,cart_count,order_count,buyout_count,cancel_count")
                 .eq("user_id", user_id).eq("shop_id", shop_id).eq("marketplace", marketplace)
                 .gte("snapshot_date", start_date).lte("snapshot_date", end_date)
                 .order("snapshot_date").order("product_key").order("id")
                 .range(offset, offset + PAGE_SIZE - 1).execute().data or [])
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    if not rows:
        raise FunnelDataUnavailableError("No funnel facts in the requested period")
    totals = {}
    for row in rows:
        key = row.get("product_key")
        if not key:
            raise ValueError("Funnel fact lacks product_key")
        if product_key is not None and key != product_key:
            continue
        values = []
        for field in ("open_count", "cart_count", "order_count", "buyout_count", "cancel_count"):
            value = row.get(field)
            if value is None or isinstance(value, bool):
                raise ValueError(f"Missing funnel fact: {field}")
            try:
                number = Decimal(str(value))
            except InvalidOperation:
                raise ValueError(f"Invalid funnel fact: {field}") from None
            if not number.is_finite() or number < 0 or number != number.to_integral_value():
                raise ValueError(f"Invalid funnel fact: {field}")
            values.append(int(number))
        item = totals.setdefault(key, {"product_key":key,"title":None,**{field:0 for field in FIELDS}})
        for field, value in zip(FIELDS, values):
            item[field] += value
    if not totals:
        raise FunnelDataUnavailableError("No funnel facts for the selected product")
    from ._common import product_titles
    products=product_titles(supabase,[totals[key] for key in sorted(totals)],user_id,shop_id,marketplace)
    return {"start_date":start_date,"end_date":end_date,
            **{field:sum(row[field] for row in products) for field in FIELDS},
            "products":products}
