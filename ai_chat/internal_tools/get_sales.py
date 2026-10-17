"""Buyout and return facts from the sales statistics, not the funnel."""
from ._common import tenant_query,pages,period,sum_rows,product_titles,DataUnavailableError
FIELDS=('sales_count','return_count')

def get_sales(user_id,shop_id,marketplace='wb',product_key=None,period_days=None,start_date=None,end_date=None,*,supabase=None):
    start,end=period(period_days,start_date,end_date)
    q=tenant_query(supabase,'metrics_sales_daily','id,snapshot_date,product_key,'+','.join(FIELDS),user_id,shop_id,marketplace)
    if product_key is not None:q=q.eq('product_key',product_key)
    rows=pages(q.gte('snapshot_date',start).lte('snapshot_date',end).order('snapshot_date').order('product_key').order('id'))
    if not rows:raise DataUnavailableError('No sales facts')
    totals,products=sum_rows(rows,FIELDS,['product_key'],integer_fields=FIELDS)
    products=product_titles(supabase,products,user_id,shop_id,marketplace)
    return {'start_date':start,'end_date':end,**totals,'products':products}
