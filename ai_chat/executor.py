try:
    from ai_chat.datasets.orders import OrdersDataset
except ModuleNotFoundError:
    OrdersDataset = None
from copy import deepcopy
from typing import Any

from ai_chat.analysis.executor import analysis_executor
from db.client import supabase


class Executor:
    """
    Main coordinator.

    Router
      ↓
    Dataset
      ↓
    Analysis
      ↓
    Result
    """

    def __init__(self, supabase=None):
        self.supabase = supabase

        self.datasets = {}

        if OrdersDataset is not None:
            self.datasets["orders"] = OrdersDataset()

    def execute(self, request: dict):

        from ai_chat.internal_tools._common import DataUnavailableError
        try:
            if request.get("question_type") == "lookup_chain" or request.get("plan"):
                return self.execute_plan(request)
            return self._execute_single_request(request)
        except DataUnavailableError:
            return {**{k:request[k] for k in ('dataset','analysis','metric','entity','period_days','date_from','date_to') if k in request},
                    'status':'no_data','rows':[]}

    def _execute_single_request(self, request: dict):

        dataset_name = request["dataset"]
        analysis_name = request["analysis"]
        limit = request.get("limit", 10)

        if dataset_name == 'reviews' and request.get('view') == 'unanswered':
            from ai_chat.internal_tools.get_reviews import get_reviews
            from ai_chat.analysis.analysis_type.filter import run as filter_rows
            dates = {'start_date':request.get('date_from'),'end_date':request.get('date_to')}
            if not any(dates.values()):
                dates = {'period_days':request.get('period_days')}
            facts = get_reviews(request['user_id'],request['shop_id'],
                marketplace=request.get('marketplace','wb'),product_key=request.get('product_key'),
                supabase=self.supabase,**dates)
            from core.text_analysis import text_payload
            from datetime import datetime
            from ai_chat.analysis.analysis_type.rank import run as rank
            prepared = []
            for review in facts['reviews']:
                content = text_payload('review', review)
                text = '\n'.join(value for value in content.values() if value)
                prepared.append({**review, 'text':text, 'has_text':bool(text),
                    'created_timestamp':datetime.fromisoformat(review['created_at'].replace('Z','+00:00')).timestamp()})
            rows = filter_rows(rows=prepared,conditions=[
                {'field':'has_answer','operator':'eq','value':False},
                {'field':'has_text','operator':'eq','value':True}])['rows']
            if not request.get('product_key') and request.get('answer_scope') != 'all':
                from ai_chat.internal_tools.get_products import get_products
                catalog = get_products(request['user_id'],request['shop_id'],
                    marketplace=request.get('marketplace','wb'),supabase=self.supabase)
                rows = filter_rows(rows=rows,conditions=[{'field':'product_key','operator':'in',
                    'value':[product['product_key'] for product in catalog['products']]}])['rows']
            if rows:
                rows = rank(rows=rows,metric='created_timestamp',direction='desc',limit=len(rows))['rows']
            return {'dataset':dataset_name,'analysis':analysis_name,'metric':'reviews_count',
                    'entity':request.get('entity'),'view':'unanswered','status':'ok',
                    **facts,'rows':rows,'reviews_count':len(rows),
                    'date_from':facts['start_date'],'date_to':facts['end_date']}

        if dataset_name == 'reviews' and request.get('view') in ('negative','positive'):
            from ai_chat.internal_tools.get_reviews import get_reviews
            from ai_chat.analysis.persisted_topics import summarize
            dates = {'start_date':request.get('date_from'),'end_date':request.get('date_to')}
            if not dates['start_date'] and not dates['end_date']:
                dates = {'period_days':request.get('period_days')}
            facts = get_reviews(request['user_id'],request['shop_id'],
                marketplace=request.get('marketplace','wb'),product_key=request.get('product_key'),
                include_topics=True,
                supabase=self.supabase,**dates)
            analysis = summarize(facts['reviews'],source_type='review',sentiment=request['view'])
            return {'dataset':dataset_name,'analysis':analysis_name,'metric':'reviews_count',
                    'entity':request.get('entity'),'view':request['view'],'status':'ok',
                    'date_from':facts['start_date'],'date_to':facts['end_date'],**facts,**analysis,
                    'total_reviews_count':facts['reviews_count'],'reviews_count':analysis['matched_sources_count']}

        if dataset_name == 'followups':
            from ai_chat.internal_tools.get_followups import get_followups
            from ai_chat.analysis.persisted_topics import summarize
            start,end=request.get('date_from'),request.get('date_to')
            if start is None and end is None and request.get('period_days') is not None:
                from ai_chat.internal_tools._common import period
                start,end=period(period_days=request['period_days'])
            facts = get_followups(request['user_id'],request['shop_id'],
                marketplace=request.get('marketplace','wb'),product_key=request.get('product_key'),
                is_answered=request.get('is_answered'),start_date=start,
                end_date=end,include_topics=request.get('view')=='topics',supabase=self.supabase)
            analysis = summarize(facts['questions'],source_type='question') if request.get('view')=='topics' else {'rows':facts['questions'],'status':'ok'}
            return {'dataset':dataset_name,'analysis':analysis_name,'metric':'questions_count',
                    'entity':request.get('entity'),'view':request.get('view'),'status':'ok',
                    'date_from':start,'date_to':end,**facts,**analysis}

        from ai_chat.internal_tools.get_ads import FIELDS as AD_FACTS
        from ai_chat.internal_tools.get_profit import PROFIT_FIELDS, EXPENSE_FIELDS
        from ai_chat.internal_tools.get_metric import METRICS as PERSISTED_METRICS
        fact_metrics={'sales':{'sales_count','return_count'},'ads':{*AD_FACTS,'ads_spend'},
            'profit':set(PROFIT_FIELDS)|set(EXPENSE_FIELDS),'reviews':{'reviews_count'},
            'prices':{'final_price','base_price','discount_percent'},'products':{'products_count'},'metric':set(PERSISTED_METRICS)}
        if request.get('metric') in fact_metrics.get(dataset_name,set()) and analysis_name in {'metric_value','best','worst','rank'}:
            from ai_chat.internal_tools.get_sales import get_sales
            from ai_chat.internal_tools.get_ads import get_ads
            from ai_chat.internal_tools.get_profit import get_profit
            from ai_chat.internal_tools.get_reviews import get_reviews
            from ai_chat.internal_tools.get_prices import get_prices
            from ai_chat.internal_tools.get_products import get_products
            from ai_chat.internal_tools.get_metric import get_metric
            from ai_chat.analysis.analysis_type.rank import run as rank
            common=dict(user_id=request['user_id'],shop_id=request['shop_id'],marketplace=request.get('marketplace','wb'),
                        product_key=request.get('product_key'),supabase=self.supabase)
            dates=dict(start_date=request.get('date_from'),end_date=request.get('date_to'))
            if not any(dates.values()):dates={'period_days':request.get('period_days',30)}
            field='spend' if dataset_name=='ads' and request['metric']=='ads_spend' else request['metric']
            if dataset_name=='sales':
                facts=get_sales(**common,**dates);rows=facts['products']
            elif dataset_name=='ads':
                level='product' if request.get('entity')=='product' or request.get('product_key') else 'campaign'
                facts=get_ads(**common,**dates,level=level,campaign_id=request.get('campaign_id'))
                rows=facts.get('products',facts.get('campaigns',[]))
            elif dataset_name=='profit':
                from ai_chat.internal_tools.get_profit import EXPENSE_FIELDS
                facts=get_profit(**common,**dates,view='expenses' if field in EXPENSE_FIELDS else 'profit');rows=facts['products']
            elif dataset_name=='reviews':
                facts=get_reviews(**common,**dates,rating_min=request.get('rating_min'),rating_max=request.get('rating_max'))
                from ai_chat.analysis.analysis_type.ranked import group_rows
                rows=group_rows(facts['reviews'],{'group_by':'product_key','group_fields':['product_key','title'],
                    'aggregation':'count','value_alias':'reviews_count'})
            elif dataset_name=='prices':
                facts=get_prices(**common,as_of=request.get('as_of'),variant_key=request.get('variant_key'));rows=facts['prices']
                if field not in {'final_price','base_price','discount_percent'}:raise ValueError('Unsupported price field')
            elif dataset_name=='products':
                facts=get_products(**common);rows=facts['products']
            else:
                facts=get_metric(**common,metric=field,as_of=request.get('as_of'));rows=facts['products'];field='value'
            context={'dataset':dataset_name,'analysis':analysis_name,'metric':request['metric'],
                'entity':request.get('entity','store'),'status':'ok',**facts}
            if 'start_date' in facts:context.update(date_from=facts['start_date'],date_to=facts['end_date'])
            if dataset_name=='ads' and request.get('entity')=='product':
                from ai_chat.analysis.analysis_type.ranked import group_rows
                rows=group_rows(rows,{'group_by':'product_key','group_fields':['product_key','title'],
                    'value_field':field,'aggregation':'sum'})
            if analysis_name in {'best','worst','rank'}:
                rows=rank(rows=rows,metric=field,direction=request.get('direction') or ('asc' if analysis_name=='worst' else 'desc'),limit=int(request.get('limit',1)))['rows']
            context['rows']=[{**row,**({'value':row[field]} if field in row else {})} for row in rows]
            if field in facts:context['value']=facts[field]
            return context

        if (dataset_name == "orders" and request.get("metric") in {"orders_count", "orders_amount", "cancelled_orders_amount", "orders_revenue"}
                and request.get("entity") in {"store", "product", "variant"}
                and analysis_name in {"metric_value", "best", "worst", "rank", "compare"}):
            from ai_chat.internal_tools.get_orders import get_orders, IncompleteOrdersError
            from ai_chat.analysis.analysis_type.rank import run as rank
            dates = {"start_date": request.get("date_from"), "end_date": request.get("date_to")}
            if not any(dates.values()):
                dates = {"period_days": request.get("period_days", 30)}
            field = "orders_amount" if request["metric"] == "orders_revenue" else request["metric"]
            context = {"dataset":"orders", "analysis":analysis_name,"metric":request["metric"],
                       "entity":request.get("entity"),"rows":[]}
            try:
                facts = get_orders(user_id=request["user_id"],shop_id=request["shop_id"],
                    marketplace=request.get("marketplace","wb"),product_key=request.get("product_key"),
                    supabase=self.supabase,**({'level':'variant'} if request.get('entity')=='variant' else {}),**dates)
            except IncompleteOrdersError as error:
                return {**context,"status":"incomplete","date_from":error.start_date,
                        "date_to":error.end_date,"period_days":request.get("period_days",30)}
            from datetime import date
            context.update(date_from=facts["start_date"],date_to=facts["end_date"],
                period_days=(date.fromisoformat(facts["end_date"])-date.fromisoformat(facts["start_date"])).days+1)
            if request.get('entity')=='variant':
                from ai_chat.analysis.analysis_type.filter import run as filter_rows
                rows=filter_rows(rows=facts['variants'],conditions=[{'field':field,'operator':'gt','value':0}])['rows']
                ranked=rank(rows=rows,metric=field,direction=request.get('direction') or ('asc' if analysis_name=='worst' else 'desc'),limit=int(request.get('limit',5)))
                return {**context,**facts,'status':'ok','rows':[{**row,'value':row[field]} for row in ranked['rows']]}
            if analysis_name == "compare":
                from datetime import timedelta
                from ai_chat.analysis.analysis_type.compare import run as compare, compare_rows
                from ai_chat.analysis.analysis_type.filter import run as filter_rows
                end = date.fromisoformat(facts['start_date']) - timedelta(days=1)
                start = end - timedelta(days=context['period_days']-1)
                try:
                    previous = get_orders(user_id=request['user_id'],shop_id=request['shop_id'],
                        marketplace=request.get('marketplace','wb'),product_key=request.get('product_key'),
                        start_date=str(start),end_date=str(end),supabase=self.supabase)
                except IncompleteOrdersError:
                    return {**context,'status':'incomplete','rows':[]}
                if facts.get(field) is None or previous.get(field) is None:
                    return {**context,'status':'no_data','rows':[]}
                current_rows,previous_rows = facts['products'],previous['products']
                if request.get('product_keys') is not None:
                    condition=[{'field':'product_key','operator':'in','value':request['product_keys']}]
                    current_rows=filter_rows(rows=current_rows,conditions=condition)['rows']
                    previous_rows=filter_rows(rows=previous_rows,conditions=condition)['rows']
                if any(row.get(field) is None for row in current_rows+previous_rows):
                    return {**context,'status':'no_data','rows':[]}
                changes = compare_rows(current=current_rows,previous=previous_rows,metric=field)
                operator = 'gt' if request.get('direction')=='positive' else 'lt'
                selected = filter_rows(rows=changes['gains']+changes['losses'],conditions=[
                    {'field':'change_abs','operator':operator,'value':0}])['rows']
                if field == 'orders_amount' and operator == 'lt':
                    if request.get('answer_scope') != 'all' and not request.get('product_key') and request.get('product_keys') is None:
                        relevant=filter_rows(rows=previous_rows,cumulative={'field':field,'share':0.8})['rows']
                        selected=filter_rows(rows=selected,conditions=[{'field':'product_key','operator':'in',
                            'value':[row['product_key'] for row in relevant]}])['rows']
                    rows=rank(rows=selected,metric='change_abs',direction='asc',limit=max(1,len(selected)))['rows']
                else:
                    # Defined percentages first; growth from zero has no finite percentage.
                    numeric=filter_rows(rows=selected,conditions=[{'field':'change_pct','operator':'ne','value':None}])['rows']
                    ranked=rank(rows=numeric,metric='change_pct',direction='desc' if operator=='gt' else 'asc',limit=max(1,len(numeric)))['rows']
                    rows=ranked+[row for row in selected if row['change_pct'] is None]
                return {**context,'status':'ok','view':request.get('view'),'rows':rows,
                    'previous_date_from':str(start),'previous_date_to':str(end),
                    'comparison':compare(current=facts,previous=previous,metrics=[field])}
            if analysis_name == "metric_value":
                if request.get("product_keys") is not None:
                    from ai_chat.analysis.analysis_type.filter import run as filter_rows
                    from ai_chat.analysis.analysis_type.ranked import group_rows
                    selected = filter_rows(rows=facts["products"], conditions=[{"field":"product_key", "operator":"in", "value":request["product_keys"]}])["rows"]
                    if any(row.get(field) is None for row in selected): return {**context,"status":"no_data"}
                    aggregated = group_rows(rows=selected, config={"group_by":[],"group_fields":[],"value_field":field,"aggregation":"sum"})
                    if field in {"orders_amount", "cancelled_orders_amount"} and request.get("answer_scope") != "all":
                        selected = filter_rows(rows=selected, conditions=[{"field":field,"operator":"gt","value":0}])["rows"]
                    selected = rank(rows=selected,metric=field,direction="desc",limit=max(1,len(selected)))["rows"]
                    return {**context,"status":"ok","value":aggregated[0][field] if aggregated else 0,
                            "shown_products_count":len(request["product_keys"]),"rows":selected}
                if facts.get(field) is None: return {**context,"status":"no_data"}
                rows = facts["products"]
                if request.get("entity") == "product" and not request.get("product_key"):
                    if field in {"orders_amount", "cancelled_orders_amount"} and request.get("answer_scope") != "all":
                        from ai_chat.analysis.analysis_type.filter import run as filter_rows
                        rows = filter_rows(rows=rows,conditions=[{"field":field,"operator":"gt","value":0}])["rows"]
                    rows = rank(rows=rows, metric=field, direction="desc", limit=max(1,len(rows)))["rows"]
                return {**context,**facts,"status":"ok","value":facts[field],"rows":rows if request.get("entity") == "product" else [],
                        **({"orders_revenue":facts[field]} if request["metric"] == "orders_revenue" else {})}
            ranked = rank(rows=facts["products"],metric=field,
                          direction=request.get("direction") or ("asc" if analysis_name=="worst" else "desc"),
                          limit=int(request.get("limit",1)))
            # value is the existing renderer's alias, not a recalculation.
            rows = [{**row,"value":row[field]} for row in ranked["rows"]]
            return {**context,"status":"ok" if rows else "no_data","rows":rows}

        funnel_fields={"funnel", "open_count", "cart_count", "order_count", "buyout_count", "cancel_count"}
        if (dataset_name == "funnel" and request.get("metric") in funnel_fields
                and request.get("entity") in {"store", "product", "variant"}
                and analysis_name in {"metric_value", "best", "worst", "rank", "compare"}):
            from ai_chat.internal_tools.get_funnel import get_funnel
            from ai_chat.analysis.analysis_type.rank import run as rank
            dates={"start_date":request.get("date_from"),"end_date":request.get("date_to")}
            if not any(dates.values()):
                dates={"period_days":request.get("period_days",30)}
            facts=get_funnel(user_id=request["user_id"],shop_id=request["shop_id"],
                marketplace=request.get("marketplace","wb"),product_key=request.get("product_key"),
                supabase=self.supabase,**dates)
            context={"dataset":"funnel","analysis":analysis_name,"metric":request["metric"],
                "entity":request.get("entity"),"date_from":facts["start_date"],"date_to":facts["end_date"],
                "period_days":request.get("period_days",30),"status":"ok"}
            if analysis_name == "compare":
                from datetime import date, timedelta
                from ai_chat.analysis.analysis_type.compare import run as compare
                start, end = date.fromisoformat(facts["start_date"]), date.fromisoformat(facts["end_date"])
                days = (end - start).days + 1
                previous_end = start - timedelta(days=1)
                previous_start = previous_end - timedelta(days=days - 1)
                previous = get_funnel(user_id=request["user_id"], shop_id=request["shop_id"],
                    marketplace=request.get("marketplace", "wb"), product_key=request.get("product_key"),
                    start_date=str(previous_start), end_date=str(previous_end), supabase=self.supabase)
                fields = ["open_count", "cart_count", "order_count", "buyout_count", "cancel_count"]
                product = next(iter(facts["products"]), {}) if request.get("product_key") else {}
                attribution = {}
                if request.get("view") == "contributors":
                    from ai_chat.analysis.analysis_type.compare import compare_rows
                    attribution = compare_rows(current=facts["products"], previous=previous["products"], metric=request["metric"])
                    attribution["rows"] = attribution["gains"] if request.get("direction") == "positive" else attribution["losses"]
                    if request.get("answer_scope") != "all":
                        from ai_chat.internal_tools.get_stocks import get_stocks
                        from ai_chat.analysis.analysis_type.filter import run as filter_rows
                        stocks = get_stocks(user_id=request["user_id"], shop_id=request["shop_id"],
                            marketplace=request.get("marketplace", "wb"), supabase=self.supabase)
                        selected = filter_rows(rows=stocks["products"],
                            cumulative={"field":"total_quantity", "share":0.8})["rows"]
                        attribution["rows"] = filter_rows(rows=attribution["rows"], conditions=[{
                            "field":"product_key", "operator":"in", "value":[row["product_key"] for row in selected]}])["rows"]
                return {**context, "period_days":days, "title":product.get("title"),
                    **attribution,
                    "previous_date_from":str(previous_start), "previous_date_to":str(previous_end),
                    "comparison":compare(current=facts, previous=previous, metrics=fields)}
            if analysis_name == "metric_value":
                return {**context,**facts,**({"value":facts[request["metric"]]} if request["metric"]!="funnel" else {})}
            if request["metric"] == "funnel":
                raise ValueError("Rank requires a numeric funnel field")
            rows=rank(rows=facts["products"],metric=request["metric"],
                direction=request.get("direction") or ("asc" if analysis_name=="worst" else "desc"),
                limit=int(request.get("limit",1)))["rows"]
            return {**context,"rows":[{**row,"value":row[request["metric"]]} for row in rows]}

        stock_fields={"stock":"total_quantity","stock_qty":"total_quantity","total_stock_qty":"total_quantity",
                      "stock_qty_full":"total_quantity","total_quantity":"total_quantity","warehouse_quantity":"warehouse_quantity",
                      "stock_in_way_to_client":"to_customer_quantity","stock_in_way_from_client":"from_customer_quantity",
                      "to_customer_quantity":"to_customer_quantity","from_customer_quantity":"from_customer_quantity"}
        if dataset_name=="stocks" and request.get("metric") in {*stock_fields,"days_left"} and analysis_name in {"metric_value","best","worst","rank"}:
            from ai_chat.internal_tools.get_stocks import get_stocks, StockDataUnavailableError
            from ai_chat.analysis.analysis_type.rank import run as rank
            entity=request.get("entity","store")
            context={"dataset":"stocks","analysis":analysis_name,"metric":request["metric"],"entity":entity,"rows":[]}
            try:
                facts=get_stocks(user_id=request["user_id"],shop_id=request["shop_id"],marketplace=request.get("marketplace","wb"),
                    product_key=request.get("product_key"),variant_key=request.get("variant_key"),warehouse_key=request.get("warehouse_key"),
                    as_of=request.get("as_of") or request.get("snapshot_date"),
                    level="variant" if entity in {"variant","warehouse","variant_warehouse","product_warehouse"} else "product",supabase=self.supabase)
            except StockDataUnavailableError as error:
                return {**context,"status":"no_data","as_of":error.as_of}
            if request['metric']=='days_left':
                from ai_chat.internal_tools.get_orders import get_orders, IncompleteOrdersError
                from ai_chat.metric.stocks import _calculate_days_left
                dates={'start_date':request.get('date_from'),'end_date':request.get('date_to')}
                if not any(dates.values()):dates={'period_days':request.get('period_days',30)}
                try:
                    orders=get_orders(user_id=request['user_id'],shop_id=request['shop_id'],
                        marketplace=request.get('marketplace','wb'),product_key=request.get('product_key'),
                        supabase=self.supabase,**dates)
                except IncompleteOrdersError:
                    return {**context,'status':'incomplete'}
                from datetime import date
                days=(date.fromisoformat(orders['end_date'])-date.fromisoformat(orders['start_date'])).days+1
                from ai_chat.analysis.analysis_type.filter import run as filter_rows
                stock_rows=facts['products']
                if request.get('product_keys') is not None:
                    stock_rows=filter_rows(rows=stock_rows,conditions=[{'field':'product_key','operator':'in','value':request['product_keys']}])['rows']
                counts={row['product_key']:row['orders_count'] for row in orders['products']}
                rows=[{**row,'days_left':_calculate_days_left(row.get('warehouse_quantity'),counts.get(row['product_key'],0)/days)} for row in stock_rows]
                value=rows[0]['days_left'] if len(rows)==1 else None
                if analysis_name=='rank':
                    rows=filter_rows(rows=rows,conditions=[{'field':'days_left','operator':'lte','value':14}])['rows']
                    rows=rank(rows=rows,metric='days_left',direction='asc',limit=max(1,len(rows)) if request.get('answer_scope')=='all' else int(request.get('limit',5)))['rows']
                return {**context,**facts,'rows':rows,'value':value,'checked_products':len(stock_rows),
                    'date_from':orders['start_date'],'date_to':orders['end_date'],
                    'status':'ok' if analysis_name=='rank' or value is not None else 'no_orders'}
            field=stock_fields[request["metric"]]
            rows=facts["products"]
            selected_value = facts[field]
            if request.get("product_keys") is not None:
                from ai_chat.analysis.analysis_type.filter import run as filter_rows
                from ai_chat.analysis.analysis_type.ranked import group_rows
                rows = filter_rows(rows=rows, conditions=[{"field":"product_key","operator":"in","value":request["product_keys"]}])["rows"]
                total = group_rows(rows=rows,config={"group_by":[],"group_fields":[],"value_field":field,"aggregation":"sum"})
                selected_value = total[0][field] if total else 0
            dimensions={"variant":["product_key","variant_key"],"warehouse":["warehouse_key"],
                        "product_warehouse":["product_key","warehouse_key"],
                        "variant_warehouse":["product_key","variant_key","warehouse_key"]}
            labels={"variant":["title","size_name"],"warehouse":["warehouse_name"],
                    "product_warehouse":["title","warehouse_name"],
                    "variant_warehouse":["title","size_name","warehouse_name"]}
            if entity in dimensions:
                from ai_chat.analysis.analysis_type.ranked import group_rows
                rows=group_rows(rows=rows,config={"group_by":dimensions[entity],"group_fields":
                    [*dimensions[entity],*labels[entity]],"value_field":field,"aggregation":"sum"})
            if analysis_name in {"best","worst","rank"}:
                rows=rank(rows=rows,metric=field,direction=request.get("direction") or ("asc" if analysis_name=="worst" else "desc"),
                          limit=int(request.get("limit",1)))["rows"]
            elif analysis_name == "metric_value":
                rows=rank(rows=rows,metric=field,direction=request.get("direction") or "desc",
                          limit=max(1,len(rows)))["rows"]
            return {**context,**facts,"value":selected_value,
                    "rows":[{**row,"value":row[field]} for row in rows],"status":"ok"}

        dataset = self.datasets.get(dataset_name)

        if analysis_name in {"metric_value", "best", "worst", "explain_change", "overview"}:
            return analysis_executor.execute(
                dataset_name=dataset_name,
                analysis_name=analysis_name,
                rows=[],
                limit=limit,
                metric=request.get("metric"),
                request=request,
                supabase=self.supabase,
            )

        if dataset is None:
            raise ValueError(
                f"Dataset '{dataset_name}' is not available for analysis '{analysis_name}'"
            )

        dataset_result = dataset.get_data(
            supabase=self.supabase,
            user_id=request["user_id"],
            shop_id=request["shop_id"],
            marketplace=request["marketplace"],
            period_days=request.get("period_days", 30),
        )

        result = analysis_executor.execute(
            dataset_name=dataset_name,
            analysis_name=analysis_name,
            rows=dataset_result["rows"],
            limit=limit,
            metric=request.get("metric"),
            request=request,
            supabase=self.supabase,
        )

        return result

    def execute_plan(self, request: dict) -> dict:
        plan = request.get("plan") or []

        if not plan:
            raise ValueError("plan is required for lookup_chain")

        step_results: dict[str, dict] = {}
        executed_steps = []

        for index, step in enumerate(plan, start=1):
            step_id = step.get("id") or f"step{index}"
            step_request = self.build_step_request(
                parent_request=request,
                step=step,
                step_results=step_results,
            )

            step_result = self._execute_single_request(step_request)
            step_results[step_id] = step_result
            executed_steps.append(
                {
                    "id": step_id,
                    "request": step_request,
                    "result": step_result,
                }
            )

        final_step = executed_steps[-1]

        return {
            "question_type": "lookup_chain",
            "steps": executed_steps,
            "result": final_step["result"],
            "meta": {
                "steps_count": len(executed_steps),
                "final_step": final_step["id"],
            },
        }

    def build_step_request(
        self,
        parent_request: dict,
        step: dict,
        step_results: dict[str, dict],
    ) -> dict:
        step_request = {
            "is_valid_question": True,
            "question_type": "plan_step",
            "dataset": step["dataset"],
            "analysis": step["analysis"],
            "metric": step["metric"],
            "entity": step.get("entity") or "store",
            "period_days": step.get("period_days", parent_request.get("period_days", 30)),
            "answer_scope": step.get("answer_scope", parent_request.get("answer_scope", "single")),
            "limit": step.get("limit", parent_request.get("limit", 1)),
            "user_id": parent_request["user_id"],
            "shop_id": parent_request["shop_id"],
            "marketplace": parent_request.get("marketplace", "wb"),
        }

        if parent_request.get("language"):
            step_request["language"] = parent_request["language"]

        for key, value in step.items():
            if key not in {"id", "inputs"} and key not in step_request:
                step_request[key] = deepcopy(value)

        for key, reference in (step.get("inputs") or {}).items():
            step_request[key] = self.resolve_plan_reference(
                reference=reference,
                step_results=step_results,
            )

        return step_request

    def resolve_plan_reference(
        self,
        reference: Any,
        step_results: dict[str, dict],
    ) -> Any:
        if not isinstance(reference, dict):
            return reference

        from_step = reference.get("from_step")
        path = reference.get("path")

        if not from_step or not path:
            return reference

        if from_step not in step_results:
            raise ValueError(f"Plan step result not found: {from_step}")

        return self.extract_path(
            data=step_results[from_step],
            path=path,
        )

    def extract_path(self, data: Any, path: str) -> Any:
        current = data

        for part in path.split("."):
            if isinstance(current, list):
                if not current:
                    raise ValueError(
                        f"Cannot extract path '{path}': step returned empty rows"
                    )

                index = int(part)

                if index < 0 or index >= len(current):
                    raise ValueError(
                        f"Cannot extract path '{path}': index {part} out of range"
                    )

                current = current[index]
                continue

            if isinstance(current, dict):
                if part not in current:
                    raise ValueError(
                        f"Cannot extract path '{path}': key '{part}' not found"
                    )

                current = current[part]
                continue

            raise ValueError(f"Cannot extract path '{path}'")

        return current


executor = Executor(supabase=supabase)
