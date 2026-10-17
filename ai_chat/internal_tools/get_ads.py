"""Additive advertising facts. Ratios and comparisons belong to Analysis."""
from ._common import tenant_query,pages,period,sum_rows,product_titles,DataUnavailableError
FIELDS=('views','clicks','orders','canceled','add_to_cart','spend','revenue')
COUNTS=('views','clicks','orders','canceled','add_to_cart')

def get_ads(user_id,shop_id,marketplace='wb',product_key=None,campaign_id=None,level='campaign',period_days=None,start_date=None,end_date=None,*,supabase=None):
    if level not in {'campaign','product'}:raise ValueError('Invalid ads level')
    if product_key is not None and level!='product':raise ValueError('Product filter requires product level')
    start,end=period(period_days,start_date,end_date)
    table='metrics_ads_product_daily' if level=='product' else 'metrics_ads_daily'
    keys=['ad_id']+(['product_key'] if level=='product' else [])
    q=tenant_query(supabase,table,'id,snapshot_date,ad_id,campaign_id,currency,'+('product_key,' if level=='product' else '')+','.join(FIELDS),user_id,shop_id,marketplace)
    if campaign_id is not None:q=q.eq('campaign_id',campaign_id)
    if product_key is not None:q=q.eq('product_key',product_key)
    rows=pages(q.gte('snapshot_date',start).lte('snapshot_date',end).order('snapshot_date').order('ad_id').order('id'))
    if not rows:
        if marketplace=='wb' and _confirmed_empty_period(supabase,user_id,shop_id,marketplace,start,end,level):
            return {'start_date':start,'end_date':end,'level':level,'currency':'RUB',
                    **{field:0 for field in FIELDS},'products' if level=='product' else 'campaigns':[]}
        raise DataUnavailableError('No advertising facts')
    currencies={r.get('currency') for r in rows}
    if len(currencies)!=1 or None in currencies:raise ValueError('Missing or mixed advertising currencies')
    totals,items=sum_rows(rows,FIELDS,keys,integer_fields=COUNTS)
    identities={}
    for row in rows:identities.setdefault(tuple(row[k] for k in keys),set()).add(row.get('campaign_id'))
    for item in items:
        ids=identities[tuple(item[k] for k in keys)]
        if len(ids)!=1:raise ValueError('Conflicting campaign identities')
        item['campaign_id']=next(iter(ids))
    if level=='product':items=product_titles(supabase,items,user_id,shop_id,marketplace)
    return {'start_date':start,'end_date':end,'level':level,'currency':next(iter(currencies)),**totals,
            'products' if level=='product' else 'campaigns':items}


def _confirmed_empty_period(db,user_id,shop_id,marketplace,start,end,level):
    """An absent metric is zero only after empty API facts reached every stage."""
    from datetime import date,datetime,timedelta
    def timestamp(value):
        if not value:return None
        try:parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        except (ValueError,TypeError):return None
        return parsed if parsed.tzinfo is not None else None
    def latest(table,key,value):
        rows=(tenant_query(db,table,'id,status,finished_at',user_id,shop_id,marketplace)
              .eq(key,value).order('id',desc=True).limit(1).execute().data or [])
        row=rows[0] if rows else {}
        return timestamp(row.get('finished_at')) if row.get('status')=='success' else None
    normalization=latest('system_normalization_jobs','source_name','ads_stats')
    snapshot=latest('system_snapshot_jobs','snapshot_name','ads_product_daily' if level=='product' else 'ads_daily')
    metric=latest('system_metric_jobs','metric_name','ads_product_daily_metrics' if level=='product' else 'ads_daily_metrics')
    if not all((normalization,snapshot,metric)) or not normalization<=snapshot<=metric:return False
    jobs=pages(tenant_query(db,'system_sync_jobs','id,status,date_from,date_to,finished_at',user_id,shop_id,marketplace)
               .eq('source_name','ads_stats').order('id'))
    raw=pages(tenant_query(db,'raw_wb_ads_stats','id,date_from,date_to,payload,loaded_at,updated_at',user_id,shop_id,marketplace)
              .gte('date_from',start).lte('date_to',end).order('id'))
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    for offset in range((last-first).days+1):
        day=(first+timedelta(days=offset)).isoformat()
        attempts=[j for j in jobs if str(j.get('date_from') or '')[:10]<=day<=str(j.get('date_to') or '')[:10]]
        if not attempts:return False
        job=max(attempts,key=lambda j:j['id'])
        finished=timestamp(job.get('finished_at'))
        if job.get('status')!='success' or finished is None or finished>normalization:return False
        facts=[r for r in raw if str(r.get('date_from'))[:10]==day and str(r.get('date_to'))[:10]==day]
        if not facts:return False
        for fact in facts:
            updated=timestamp(fact.get('updated_at') or fact.get('loaded_at'))
            payload=fact.get('payload')
            if updated is None or updated>finished:return False
            if not isinstance(payload,dict) or payload.get('data')!=[] or payload.get('empty_reason') not in {'empty_api_payload','no_advert_ids'}:
                return False
    return True
