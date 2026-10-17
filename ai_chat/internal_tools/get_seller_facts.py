"""Paginated tenant-bound reads for derived metrics; return existing list-of-dicts facts."""
SOURCES = {
    'orders': ('metrics_orders_daily', 'snapshot_date', 'snapshot_date,product_key,orders_count,cancelled_orders_count'),
    'order_events': ('normalized_orders', 'order_date', 'srid,product_key,order_date,is_cancel,region_name,country_name,size_name'),
    'reports': ('normalized_realization_reports', None, 'report_id,report_from,report_to'),
}


def get_seller_facts(supabase, request, source, date_from=None, date_to=None, *, latest=False):
    common=dict(user_id=request['user_id'],shop_id=request['shop_id'],marketplace=request.get('marketplace','wb'),
                product_key=request.get('product_key'),supabase=supabase)
    dates=dict(start_date=date_from,end_date=date_to)
    if source == 'products':
        from .get_products import get_products
        return get_products(**{**common,'product_key':None})['products']
    if source in {'ads_products','ads_campaigns'}:
        from .get_ads import get_ads
        return get_ads(**common,**dates,level='product' if source=='ads_products' else 'campaign')
    if source == 'returns':
        from .get_sales import get_sales
        return get_sales(**common,**dates)
    if source == 'expenses':
        from .get_profit import get_profit
        return get_profit(**common,**dates,view='expenses')
    if source == 'reviews':
        from .get_reviews import get_reviews
        return get_reviews(**common,**dates)['reviews']
    if source == 'prices':
        from .get_prices import get_prices
        return get_prices(**common,**dates)['prices']
    if source == "funnel":
        from ai_chat.internal_tools.get_funnel import get_funnel
        return get_funnel(user_id=request["user_id"],shop_id=request["shop_id"],
            marketplace=request.get("marketplace","wb"),product_key=request.get("product_key"),
            start_date=date_from,end_date=date_to,supabase=supabase)["products"]
    from datetime import date, timedelta
    if source in {"stocks", "stock_sizes"}:
        from ai_chat.internal_tools.get_stocks import get_stocks, StockDataUnavailableError
        try:
            facts=get_stocks(user_id=request["user_id"],shop_id=request["shop_id"],
                marketplace=request.get("marketplace","wb"),as_of=request.get("snapshot_date"),
                level="variant" if source=="stock_sizes" else "product",supabase=supabase)
        except StockDataUnavailableError:
            return []
        # Preserve the current derived Analysis input names, without another DB read.
        return [{**row,"snapshot_date":facts["as_of"],"quantity":row["total_quantity"]} for row in facts["products"]]
    table, date_field, fields = SOURCES[source]
    def query():
        return (supabase.table(table).select(fields).eq('user_id', request['user_id'])
                .eq('shop_id', request['shop_id']).eq('marketplace', request.get('marketplace', 'wb')))
    latest_date = None
    if latest:
        found = query().order(date_field, desc=True).limit(1).execute().data or []
        if not found:return []
        latest_date = str(found[0][date_field])[:10]
    rows=[]; offset=0
    while True:
        q=query()
        if date_field:
            if latest_date:q=q.eq(date_field, latest_date)
            else:
                if date_from:q=q.gte(date_field, date_from)
                if date_to:q=q.lt(date_field,(date.fromisoformat(date_to)+timedelta(days=1)).isoformat())
        # Products are read as a catalog; event/metric reads remain bounded.
        q=q.order('product_key' if source=='products' else 'id')
        batch=q.range(offset,offset+999).execute().data or [];rows.extend(batch)
        if len(batch)<1000:return rows
        offset+=1000


def get_successful_loads(supabase, request, source):
    """Empty data is zero only after a successful load covering the requested interval."""
    from datetime import datetime
    processed = {
        'ads_stats': ('system_metric_jobs', 'metric_name', 'ads_daily_metrics' if request.get('metric') == 'ads_decline' else 'ads_product_daily_metrics'),
        'sales': ('system_metric_jobs', 'metric_name', 'sales_daily_metrics'),
        'realization': ('system_metric_jobs', 'metric_name', 'realization_daily_metrics'),
        'feedbacks': ('system_normalization_jobs', 'source_name', 'feedbacks'),
    }.get(source)
    ready_at = None
    if processed:
        table, field, name = processed
        ready = (supabase.table(table).select('finished_at').eq('user_id',request['user_id'])
            .eq('shop_id',request['shop_id']).eq('marketplace',request.get('marketplace','wb'))
            .eq(field,name).eq('status','success').order('finished_at',desc=True).limit(1).execute().data or [])
        if not ready or not ready[0].get('finished_at'):return []
        ready_at = datetime.fromisoformat(str(ready[0]['finished_at']).replace('Z','+00:00'))
    rows=[];offset=0
    while True:
        batch=(supabase.table('system_sync_jobs').select('date_from,date_to,finished_at')
            .eq('user_id',request['user_id']).eq('shop_id',request['shop_id'])
            .eq('marketplace',request.get('marketplace','wb')).eq('source_name',source)
            .eq('status','success').order('id').range(offset,offset+999).execute().data or [])
        # A completed API request alone does not prove that its data reached the metrics.
        rows.extend(r for r in batch if ready_at is None or
            (r.get('finished_at') and datetime.fromisoformat(str(r['finished_at']).replace('Z','+00:00')) <= ready_at))
        if len(batch)<1000:return rows
        offset+=1000
