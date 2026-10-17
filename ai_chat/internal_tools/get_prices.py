"""Recorded variant prices: one store snapshot OR dated history; never averaged."""
from datetime import date
from ._common import tenant_query,pages,period,number,json_number,product_titles,DataUnavailableError
FIELDS='id,snapshot_date,product_key,variant_key,size_name,base_price,final_price,discount_percent,currency'

def get_prices(user_id,shop_id,marketplace='wb',product_key=None,variant_key=None,as_of=None,period_days=None,start_date=None,end_date=None,*,supabase=None):
    history=period_days is not None or start_date is not None or end_date is not None
    if as_of is not None and history:raise ValueError('Choose snapshot OR period')
    def query():return tenant_query(supabase,'snapshots_prices_daily',FIELDS,user_id,shop_id,marketplace)
    if history:
        start,end=period(period_days,start_date,end_date);context={'start_date':start,'end_date':end}
    else:
        if as_of is None:
            found=query().order('snapshot_date',desc=True).order('id').limit(1).execute().data or []
            if not found:raise DataUnavailableError('No price snapshot')
            as_of=str(found[0]['snapshot_date'])[:10]
        date.fromisoformat(as_of);context={'as_of':as_of}
    q=query()
    if product_key is not None:q=q.eq('product_key',product_key)
    if variant_key is not None:q=q.eq('variant_key',variant_key)
    q=q.gte('snapshot_date',start).lte('snapshot_date',end) if history else q.eq('snapshot_date',as_of)
    rows=pages(q.order('snapshot_date').order('product_key').order('id'))
    if not rows:raise DataUnavailableError('No price facts for selection')
    unique={}
    for row in rows:
        if not row.get('product_key'):raise ValueError('Missing price product')
        key=(str(row['snapshot_date'])[:10],row['product_key'],row.get('variant_key'))
        item={k:row.get(k) for k in FIELDS.split(',') if k!='id'}
        for field in ('base_price','final_price','discount_percent'):
            item[field]=None if row.get(field) is None else json_number(number(row[field]))
        if item['discount_percent'] is not None and item['discount_percent']>100:raise ValueError('Invalid discount')
        if key in unique and unique[key]!=item:raise ValueError('Conflicting prices for variant/date')
        unique[key]=item
    prices=product_titles(supabase,list(unique.values()),user_id,shop_id,marketplace)
    return {**context,'prices':prices}
