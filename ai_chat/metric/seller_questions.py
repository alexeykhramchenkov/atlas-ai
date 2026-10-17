"""Derived seller metrics in the existing Metric Adapter layer. No DB queries or LLM arithmetic."""
from collections import defaultdict, Counter
from datetime import date, timedelta
from math import ceil
from ai_chat.routing.seller_questions import BY_METRIC
from ai_chat.internal_tools.get_seller_facts import get_seller_facts, get_successful_loads

COMPARISONS={'orders_week_change','orders_growth','orders_decline','conversion_decline','ads_decline'}
ORDER_METRICS={'orders_today','orders_week_change','orders_growth','orders_decline','zero_orders','cancelled_orders','regions_store'}
STOCK_METRICS={'replenishment_risk','stock_days','size_stock_days','replenishment_qty','stagnant_stock'}
FUNNEL_METRICS={'views_without_orders','carts_without_orders','conversion_decline','buyout_rate'}
ADS_METRICS={'ads_spend','ads_orders','ads_without_orders','ads_cpo','ads_decline'}


def handles(request):
    return (request.get('metric') in BY_METRIC and request.get('question_type')=='simple'
            and bool(request.get('date_from') and request.get('date_to'))
            and (request.get('metric')!='cancelled_orders' or request.get('entity')=='product'))


def n(value):return float(value or 0)


def covered(rows,start,end,field='snapshot_date'):
    found={str(r.get(field) or '')[:10] for r in rows}
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    return all((first+timedelta(days=i)).isoformat() in found for i in range((last-first).days+1))


def load_covered(loads,start,end):
    first,last=date.fromisoformat(start),date.fromisoformat(end)
    return all(any(str(r.get('date_from') or '')[:10]<=str(first+timedelta(days=i))<=str(r.get('date_to') or '')[:10] for r in loads) for i in range((last-first).days+1))


def group(rows,fields,key='product_key'):
    result={}
    for row in rows:
        pk=row.get(key)
        if not pk:continue
        current=result.setdefault(pk,{key:pk,**{f:0.0 for f in fields}})
        for f in fields:current[f]+=n(row.get(f))
    return result


def run(request,supabase):
    metric=request['metric'];start,end=request['date_from'],request['date_to']
    days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1
    previous_end=(date.fromisoformat(start)-timedelta(days=1)).isoformat()
    previous_start=(date.fromisoformat(start)-timedelta(days=days)).isoformat()
    read=lambda source,a=start,b=end,**kw:get_seller_facts(supabase,request,source,a,b,**kw)
    facts={'products':read('products')}
    if metric in ORDER_METRICS|STOCK_METRICS|{'price_change_orders'}:
        facts['orders']=read('orders', (date.fromisoformat(previous_start)-timedelta(days=14)).isoformat() if metric=='price_change_orders' else previous_start if metric in COMPARISONS else start)
    if metric in {'regions_store','size_stock_days'}:facts['order_events']=read('order_events')
    if metric in STOCK_METRICS:
        facts['stocks']=read('stocks',latest=True)
        if metric=='size_stock_days':facts['stock_sizes']=read('stock_sizes',latest=True)
    if metric in FUNNEL_METRICS:
        from ai_chat.internal_tools.get_funnel import get_funnel, FunnelDataUnavailableError
        common=dict(user_id=request['user_id'],shop_id=request['shop_id'],
            marketplace=request.get('marketplace','wb'),product_key=request.get('product_key'),supabase=supabase)
        try:
            facts['funnel']=get_funnel(**common,start_date=start,end_date=end)
            if metric in COMPARISONS:
                facts['funnel_previous']=get_funnel(**common,start_date=previous_start,end_date=previous_end)
        except FunnelDataUnavailableError:
            return {'dataset':request['dataset'],'analysis':request['analysis'],'metric':metric,
                    'entity':request['entity'],'date_from':start,'date_to':end,'status':'no_data','rows':[]}

    if metric in ADS_METRICS:
        facts['ads']=read('ads_campaigns' if metric=='ads_decline' else 'ads_products')
        if metric in COMPARISONS:facts['ads_previous']=read('ads_campaigns',previous_start,previous_end)
        facts['loads']=get_successful_loads(supabase,request,'ads_stats')
    if metric=='return_count':
        facts['returns']=read('returns');facts['loads']=get_successful_loads(supabase,request,'sales')
    if metric=='wb_expenses':
        facts['expenses']=read('expenses')
        facts['loads']=get_successful_loads(supabase,request,'realization')
    if metric=='review_complaints':
        facts['reviews']=read('reviews');facts['reviews_loaded']=True
    if metric=='price_change_orders':facts['prices']=read('prices',previous_start)
    return calculate(request,facts)


def calculate(request,facts):
    metric=request['metric'];start,end=request['date_from'],request['date_to']
    days=(date.fromisoformat(end)-date.fromisoformat(start)).days+1
    previous_end=(date.fromisoformat(start)-timedelta(days=1)).isoformat()
    previous_start=(date.fromisoformat(start)-timedelta(days=days)).isoformat()
    result={k:request[k] for k in ('dataset','analysis','metric','entity','period_days','date_from','date_to')}
    result.update(status='ok',rows=[],meta={})
    products={r['product_key']:r for r in facts.get('products',[])}
    def period(rows,a=start,b=end):return [r for r in rows if a<=str(r.get('snapshot_date') or '')[:10]<=b]
    def missing(reason):return {**result,'status':'incomplete','meta':{'reason':reason}}
    def finish(rows,reverse=True):
        rows=sorted(rows,key=lambda r:(-n(r.get('value')) if reverse else n(r.get('value')),str(r.get('product_key') or r.get('title') or '')))
        result['meta'].update(total_groups=len(rows),limit=request.get('limit',5))
        result['rows']=[{'title':r.get('product_key') or 'Название не указано',**products.get(r.get('product_key'),{}),**r} for r in rows[:request.get('limit',5)]]
        return result
    if metric in ORDER_METRICS|STOCK_METRICS:
        if not covered(facts.get('orders',[]),previous_start if metric in COMPARISONS else start,end):return missing('orders_coverage')
        orders=group(period(facts['orders']),['orders_count','cancelled_orders_count'])
        if metric=='orders_today':
            result.update(value=sum(r['orders_count'] for r in orders.values()),orders_count=sum(r['orders_count'] for r in orders.values()),cancelled_orders_count=sum(r['cancelled_orders_count'] for r in orders.values()))
            result['meta']['note']='Сегодняшний день ещё не завершён. Данные на момент последней загрузки.'
            return result
        if metric in {'orders_week_change','orders_growth','orders_decline'}:
            previous=group(period(facts['orders'],previous_start,previous_end),['orders_count'])
            rows=[]
            for pk in set(orders)|set(previous):
                cur=orders.get(pk,{}).get('orders_count',0);old=previous.get(pk,{}).get('orders_count',0)
                rows.append({'product_key':pk,'value':cur-old,'current':cur,'previous':old,'change_abs':cur-old,'change_pct':round((cur-old)/old*100,2) if old else None})
            if metric=='orders_week_change':
                cur=sum(r['current'] for r in rows);old=sum(r['previous'] for r in rows)
                return {**result,'current':cur,'previous':old,'change_abs':cur-old,'change_pct':round((cur-old)/old*100,2) if old else None,
                        'meta':{'previous_date_from':previous_start,'previous_date_to':previous_end}}
            return finish([r for r in rows if r['value']>0] if metric=='orders_growth' else [r for r in rows if r['value']<0],metric=='orders_growth')
        if metric=='zero_orders':return finish([{'product_key':pk,'value':0} for pk in products if not orders.get(pk,{}).get('orders_count')])
        if metric=='cancelled_orders':return finish([{'product_key':pk,'value':r['cancelled_orders_count'],'orders_count':r['orders_count']} for pk,r in orders.items() if r['cancelled_orders_count']>0])
        if metric=='regions_store':
            seen=set();counts=Counter();cancel=Counter()
            for r in facts.get('order_events',[]):
                if not r.get('product_key') or not r.get('srid') or str(r['srid']).startswith('empty:') or r['srid'] in seen:continue
                seen.add(r['srid']);key=(r.get('country_name') or 'Страна не указана',r.get('region_name') or 'Регион не указан');counts[key]+=1
                if r.get('is_cancel'):cancel[key]+=1
            return finish([{'title':f'{country}: {region}','value':count,'cancelled_orders_count':cancel[(country,region)]} for (country,region),count in counts.items()])
        stocks=facts.get('stocks',[])
        if not stocks:return missing('stock_snapshot')
        snapshot=max(str(r['snapshot_date'])[:10] for r in stocks)
        if (date.fromisoformat(end)+timedelta(days=1)-date.fromisoformat(snapshot)).days>2:return missing('stale_stock')
        stock_by=group(stocks,['total_quantity'])
        result['meta'].update(snapshot_date=snapshot,note='Оценка по всем заказам. Остаток включает склад и движение в обе стороны; это ориентир при прежнем темпе заказов.')
        if metric=='stock_days':
            pk=request.get('product_key')
            if pk not in stock_by:return {**result,'status':'no_product'}
            qty=stock_by[pk]['total_quantity'];count=orders.get(pk,{}).get('orders_count',0)
            result['product']=products.get(pk,{'product_key':pk})
            if not count:return {**result,'status':'no_orders'}
            return {**result,'rows':[{**products.get(pk,{}),'product_key':pk,'value':round(qty/(count/days),1),'stock_qty':qty,'orders_count':count}]}
        if metric=='size_stock_days':
            pk=request.get('product_key');events={r['srid']:r for r in facts.get('order_events',[]) if r.get('product_key')==pk and r.get('srid')}
            demand=Counter(str(r.get('size_name') or 'Размер не указан') for r in events.values());quantities=Counter()
            for r in facts.get('stock_sizes',[]):
                if r.get('product_key')==pk:quantities[str(r.get('size_name') or 'Размер не указан')]+=n(r.get('quantity'))
            if not quantities:return {**result,'status':'no_product'}
            if any(not r.get('size_name') for r in facts.get('stock_sizes',[]) if r.get('product_key')==pk):
                return missing('stock_size_details')
            rows=[{'product_key':pk,'title':f"{products.get(pk,{}).get('title') or pk} · размер {size}",'value':round(qty/(demand[size]/days),1),'stock_qty':qty,'orders_count':demand[size]} for size,qty in quantities.items() if demand[size] and qty/(demand[size]/days)<=7]
            return finish(rows,False)
        rows=[]
        for pk,stock in stock_by.items():
            if request.get('product_key') and pk!=request['product_key']:continue
            qty=stock['total_quantity'];count=orders.get(pk,{}).get('orders_count',0);avg=count/days
            if metric=='stagnant_stock':
                if qty>0 and count<=1:rows.append({'product_key':pk,'value':qty,'stock_qty':qty,'orders_count':count})
            elif metric=='replenishment_qty':
                need=max(ceil(avg*14-qty),0)
                if need:rows.append({'product_key':pk,'value':need,'stock_qty':qty,'orders_count':count})
            elif avg>0 and qty/avg<=7:rows.append({'product_key':pk,'value':round(qty/avg,1),'stock_qty':qty,'orders_count':count})
        return finish(rows,metric!='replenishment_risk')
    if metric in FUNNEL_METRICS:
        source=facts.get('funnel',[])
        if isinstance(source,dict):
            current={row['product_key']:row for row in source['products']}
        else:
            if not covered(source,previous_start if metric in COMPARISONS else start,end):return missing('funnel_coverage')
            current=group(period(source),['open_count','cart_count','order_count','buyout_count','cancel_count'])
        if metric=='buyout_rate':
            buys=sum(r['buyout_count'] for r in current.values());cancels=sum(r['cancel_count'] for r in current.values())
            if not buys+cancels:return {**result,'status':'no_data'}
            return {**result,'value':round(buys/(buys+cancels)*100,2),'meta':{'buyout_count':buys,'cancel_count':cancels}}
        if metric=='conversion_decline':
            previous=({row['product_key']:row for row in facts['funnel_previous']['products']}
                      if isinstance(source,dict) else group(period(source,previous_start,previous_end),['cart_count','order_count']))
            rows=[]
            for pk,r in current.items():
                old=previous.get(pk,{})
                if r['cart_count']<=0 or old.get('cart_count',0)<=0:continue
                cur=r['order_count']/r['cart_count']*100;before=old['order_count']/old['cart_count']*100
                if cur<before:rows.append({'product_key':pk,'value':round(cur-before,2),'current':round(cur,2),'previous':round(before,2)})
            return finish(rows,False)
        field='open_count' if metric=='views_without_orders' else 'cart_count'
        return finish([{'product_key':pk,'value':r[field],'orders_count':r['order_count']} for pk,r in current.items() if r[field]>0 and r['order_count']==0])
    if metric in ADS_METRICS:
        source=facts.get('ads',[]);key='ad_id' if metric=='ads_decline' else 'product_key'
        if isinstance(source,dict):
            current=group(source.get('campaigns',source.get('products',[])),['spend','orders'],key)
        else:
            if not load_covered(facts.get('loads',[]),previous_start if metric in COMPARISONS else start,end):return missing('ads_coverage')
            current=group(period(source),['spend','orders'],key)
        spend=sum(r['spend'] for r in current.values());count=sum(r['orders'] for r in current.values())
        result['meta']['note']='Заказы, которые WB относит к рекламе. Это не доказательство, что реклама стала причиной заказа.'
        if metric=='ads_spend':return {**result,'value':spend}
        if metric=='ads_cpo':return {**result,'value':round(spend/count,2) if count else None,'status':'ok' if count else 'no_orders','meta':{**result['meta'],'spend':spend,'orders_count':count}}
        if metric=='ads_decline':
            old=group(facts['ads_previous']['campaigns'] if isinstance(source,dict) else period(source,previous_start,previous_end),['spend','orders'],key);rows=[]
            for pk,r in current.items():
                before=old.get(pk,{})
                if r['spend']<=0 or before.get('spend',0)<=0:continue
                # Deterioration is a fall in attributed orders per ruble, not a causal claim.
                cur=r['orders']/r['spend'];prev=before.get('orders',0)/before['spend']
                if cur<prev:rows.append({'ad_id':pk,'title':f'Кампания {pk}','value':round((cur-prev)/prev*100,2) if prev else 0,'orders_count':r['orders'],'spend':r['spend']})
            return finish(rows,False)
        return finish([{'product_key':pk,'value':r['orders'] if metric=='ads_orders' else r['spend'],'orders_count':r['orders'],'spend':r['spend']} for pk,r in current.items() if r['orders']>0] if metric=='ads_orders' else [{'product_key':pk,'value':r['spend'],'orders_count':r['orders'],'spend':r['spend']} for pk,r in current.items() if r['spend']>0 and not r['orders']])
    if metric=='return_count':
        source=facts.get('returns',[])
        if not isinstance(source,dict) and not load_covered(facts.get('loads',[]),start,end):return missing('sales_coverage')
        rows=group(source['products'] if isinstance(source,dict) else source,['sales_count','return_count'])
        return finish([{'product_key':pk,'value':r['return_count']} for pk,r in rows.items() if r['return_count']>0])
    if metric=='wb_expenses':
        source=facts.get('expenses',[])
        if isinstance(source,dict):
            amounts={f:source[f] for f in ('wb_commission_amount','logistics_amount','storage_amount')}
            if any(v is None for v in amounts.values()):return {**result,'status':'no_data'}
            return {**result,'value':sum(amounts.values()),'meta':amounts}
        reports=facts.get('reports',[])
        if not source or not reports:return missing('realization_coverage')
        latest=max(str(r.get('report_to') or '')[:10] for r in reports)
        if latest<end:
            end=latest;start=(date.fromisoformat(end)-timedelta(days=days-1)).isoformat()
        coverage=[{'date_from':r.get('report_from'),'date_to':r.get('report_to')} for r in reports]
        if not load_covered(coverage,start,end) or not load_covered(facts.get('loads',[]),start,end):return missing('realization_coverage')
        source=period(source,start,end)
        amounts={f:sum(n(r.get(f)) for r in source) for f in ('wb_commission_amount','logistics_amount','storage_amount')}
        return {**result,'date_from':start,'date_to':end,'value':sum(amounts.values()),'meta':amounts}
    if metric=='review_complaints':
        if not facts.get('loads') and not facts.get('reviews_loaded'):return missing('reviews_not_loaded')
        categories={'Качество и дефекты':('брак','порвал','шов','дыр','качество','дефект'), 'Размер и посадка':('размер','маломер','большемер','посадк'), 'Не соответствует описанию':('не соответств','не как на фото','другой цвет','отличается'), 'Упаковка и доставка':('упаков','достав','коробк','пакет')}
        counts=Counter();examples=defaultdict(list);seen=set()
        for r in facts.get('reviews',[]):
            if r.get('feedback_id') in seen or n(r.get('rating'))>3:continue
            seen.add(r.get('feedback_id'));text=' '.join(str(r.get(f) or '') for f in ('cons','text')).strip()
            if not text:continue
            matched=[name for name,words in categories.items() if any(w in text.lower() for w in words)] or ['Другие замечания']
            for name in matched:
                counts[name]+=1
                if len(examples[name])<2:examples[name].append(text[:180].replace('\n',' '))
        result['meta']['note']='Отзывы с оценкой 1–3. Темы выделены по словам в тексте; один отзыв может попасть в несколько тем.'
        return finish([{'title':name,'value':count,'text':' / '.join(examples[name])} for name,count in counts.items()])
    if metric=='price_change_orders':
        pk=request.get('product_key');by_day=defaultdict(set)
        for r in facts.get('prices',[]):
            if r.get('product_key')==pk and r.get('final_price') is not None:
                by_day[str(r['snapshot_date'])[:10]].add(n(r['final_price']))
        # Different prices by size require an explicit variant, not a made-up average.
        if len(by_day)<2 or any(len(v)!=1 for v in by_day.values()):return missing('price_event_history_required')
        prices=sorted((day,next(iter(values))) for day,values in by_day.items())
        changes=[(day,value,prices[i-1][1],prices[i-1][0]) for i,(day,value) in enumerate(prices) if i and value!=prices[i-1][1]]
        if not changes:return missing('price_event_history_required')
        day,new_price,old_price,previous_observation=changes[-1]
        # Only consecutive daily snapshots identify the change day reliably.
        if (date.fromisoformat(day)-date.fromisoformat(previous_observation)).days!=1:return missing('price_event_history_required')
        before_end=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
        before_start=(date.fromisoformat(day)-timedelta(days=7)).isoformat()
        after_end=(date.fromisoformat(day)+timedelta(days=6)).isoformat()
        if after_end>end or not covered(facts.get('orders',[]),before_start,after_end):return missing('price_comparison_coverage')
        selected=[r for r in facts['orders'] if r.get('product_key')==pk]
        before=sum(n(r.get('orders_count')) for r in period(selected,before_start,before_end))
        after=sum(n(r.get('orders_count')) for r in period(selected,day,after_end))
        return {**result,'date_from':day,'date_to':after_end,'period_days':7,'product':products.get(pk,{'product_key':pk}),
                'current':after,'previous':before,'change_abs':after-before,'change_pct':round((after-before)/before*100,2) if before else None,
                'meta':{'current_price':new_price,'previous_price':old_price,'previous_date_from':before_start,'previous_date_to':before_end,
                        'note':'Сравнение двух недель до и после изменения. Оно не доказывает, что изменение заказов вызвано именно ценой.'}}
    raise ValueError('Unsupported derived seller metric')
