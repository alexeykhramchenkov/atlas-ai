"""Only persisted, allowlisted metrics. Does not calculate days_left or ratios."""
from datetime import date
from ._common import tenant_query,pages,period,number,json_number,product_titles,DataUnavailableError

# Server-owned column allowlist, not expressions or question-specific functions.
METRICS={}
for table,fields in {
 'metrics_stocks_daily':('stock_growth_1d_pct','stock_growth_7d_pct','stock_growth_30d_pct','total_stock_value'),
 'metrics_sales_daily':('return_rate','avg_sale_value','sales_growth_1d_pct','sales_growth_7d_pct','sales_growth_30d_pct'),
 'metrics_funnel_daily':('open_to_cart_pct','cart_to_order_pct','order_to_buyout_pct','cancel_rate_pct','buyout_rate_pct','feedback_rating'),
 'metrics_financial_daily':('gross_margin_pct','net_margin_pct','expense_rate_pct','profit_growth_1d_pct','profit_growth_7d_pct','profit_growth_30d_pct'),
}.items():
 for field in fields:METRICS[field]=(table,field)


def get_metric(user_id,shop_id,metric,marketplace='wb',product_key=None,as_of=None,period_days=None,start_date=None,end_date=None,*,supabase=None):
    if metric not in METRICS:raise ValueError('Metric is not a supported persisted fact')
    table,field=METRICS[metric]
    history=period_days is not None or start_date is not None or end_date is not None
    if as_of is not None and history:raise ValueError('Choose snapshot OR period')
    def query():return tenant_query(supabase,table,'id,snapshot_date,product_key,'+field,user_id,shop_id,marketplace)
    if history:
        start,end=period(period_days,start_date,end_date);context={'start_date':start,'end_date':end}
    else:
        if as_of is None:
            found=query().order('snapshot_date',desc=True).order('id').limit(1).execute().data or []
            if not found:raise DataUnavailableError('No persisted metrics')
            as_of=str(found[0]['snapshot_date'])[:10]
        date.fromisoformat(as_of);context={'as_of':as_of}
    q=query()
    if product_key is not None:q=q.eq('product_key',product_key)
    q=q.gte('snapshot_date',start).lte('snapshot_date',end) if history else q.eq('snapshot_date',as_of)
    rows=pages(q.order('snapshot_date').order('product_key').order('id'))
    if not rows:raise DataUnavailableError('No persisted metric for selection')
    values=[];seen=set()
    for row in rows:
        key=(row.get('product_key'),str(row['snapshot_date'])[:10])
        if key[0] is None or key in seen:raise ValueError('Missing or duplicate metric identity')
        seen.add(key)
        value=None if row.get(field) is None else json_number(number(row[field],signed=True))
        values.append({'product_key':key[0],'snapshot_date':key[1],'value':value})
    return {'metric':metric,**context,'products':product_titles(supabase,values,user_id,shop_id,marketplace)}
