import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from types import SimpleNamespace
from ai_chat.internal_tools.get_orders import get_orders,IncompleteOrdersError


class Query:
    def __init__(self,db,table):self.db=db;self.table=table;self.filters=[];self.sorts=[];self.bounds=None
    def select(self,*a,**k):return self
    def eq(self,k,v):self.filters.append((k,'eq',v));return self
    def gte(self,k,v):self.filters.append((k,'gte',v));return self
    def lte(self,k,v):self.filters.append((k,'lte',v));return self
    def lt(self,k,v):self.filters.append((k,'lt',v));return self
    def in_(self,k,v):self.filters.append((k,'in',v));return self
    def order(self,k,desc=False):self.sorts.append((k,desc));return self
    def range(self,a,b):self.bounds=(a,b);return self
    def execute(self):
        rows=list(self.db.data.get(self.table,[]))
        for k,op,v in self.filters:
            rows=[r for r in rows if {'eq':lambda:r.get(k)==v,'gte':lambda:r.get(k)>=v,
                'lte':lambda:r.get(k)<=v,'lt':lambda:r.get(k)<v,'in':lambda:r.get(k) in v}[op]()]
        for k,desc in reversed(self.sorts):rows.sort(key=lambda r:r.get(k,''),reverse=desc)
        if self.bounds:rows=rows[self.bounds[0]:self.bounds[1]+1]
        return SimpleNamespace(data=rows)


class DB:
    def __init__(self,data):self.data=data;self.queries=[]
    def table(self,name):
        q=Query(self,name);self.queries.append(q);return q


class GetOrdersContract(unittest.TestCase):
    def db(self):
        tenant={'user_id':1,'shop_id':1,'marketplace':'wb'}
        rows=[{**tenant,'id':i,'snapshot_date':f'2026-10-{d:02}','product_key':p,
               'orders_count':n,'cancelled_orders_count':c,'gross_order_value':n*100,'net_order_value':(n-c)*100}
              for i,(d,p,n,c) in enumerate([(6,'a',2,1),(7,'a',3,0),(6,'b',7,2)],1)]
        rows += [{**rows[0],'id':99,'user_id':2,'orders_count':999},
                 {**rows[0],'id':100,'shop_id':2,'orders_count':999}]
        return DB({'metrics_orders_daily':rows,'normalized_products':[
            {**tenant,'id':1,'product_key':'a','title':'A'},
            {**tenant,'id':2,'product_key':'b','title':'B'},
            {**tenant,'id':3,'user_id':2,'product_key':'a','title':'Wrong tenant'}]})
    def get(self,db,**kw):return get_orders(user_id=1,shop_id=1,supabase=db,**kw)
    def test_exact_contract_and_inclusive_period_and_tenant(self):
        db=self.db();x=self.get(db,start_date='2026-10-06',end_date='2026-10-07')
        self.assertEqual(set(x),{'start_date','end_date','orders_count','cancelled_orders_count','orders_amount','cancelled_orders_amount','products'})
        self.assertEqual((x['orders_count'],x['cancelled_orders_count']),(12,3))
        self.assertEqual(x['products'][0],{'product_key':'a','title':'A','orders_count':5,'cancelled_orders_count':1,'orders_amount':500,'cancelled_orders_amount':100})
        self.assertEqual(x['products'][1]['orders_count'],7)
        for q in db.queries:
            self.assertIn(('user_id','eq',1),q.filters);self.assertIn(('shop_id','eq',1),q.filters)
    def test_missing_day_raises_not_partial_total(self):
        with self.assertRaises(IncompleteOrdersError):self.get(self.db(),start_date='2026-10-06',end_date='2026-10-08')
    def test_unknown_product_is_zero_only_after_shop_day_check(self):
        x=self.get(self.db(),product_key='missing',start_date='2026-10-06',end_date='2026-10-07')
        self.assertEqual(x['orders_count'],0);self.assertEqual(x['products'],[])
    def test_period_days_uses_completed_moscow_days(self):
        end=datetime.now(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1)
        db=self.db();db.data['metrics_orders_daily']=[{**db.data['metrics_orders_daily'][0],'id':i,
            'snapshot_date':str(end-timedelta(days=i))} for i in range(30)]
        x=self.get(db,period_days=30)
        self.assertEqual(x['start_date'],str(end-timedelta(days=29)));self.assertEqual(x['end_date'],str(end))
        self.assertEqual(x['orders_count'],60)
    def test_pagination_keeps_all_products(self):
        db=self.db();base=db.data['metrics_orders_daily'][0]
        db.data['metrics_orders_daily']=[{**base,'id':i,'product_key':f'p{i:05}'} for i in range(2001)]
        x=self.get(db,start_date='2026-10-06',end_date='2026-10-06')
        self.assertEqual(len(x['products']),2001);self.assertEqual(x['orders_count'],4002)
    def test_period_validation(self):
        for kw in ({},{'period_days':0},{'period_days':True},{'start_date':'2026-10-06'},
                   {'period_days':30,'start_date':'2026-10-06','end_date':'2026-10-07'},
                   {'start_date':'2026-10-07','end_date':'2026-10-06'}):
            with self.assertRaises(ValueError):self.get(self.db(),**kw)
    def test_missing_quantity_is_not_zero(self):
        db=self.db();db.data['metrics_orders_daily'][0]['orders_count']=None
        with self.assertRaises(ValueError):self.get(db,start_date='2026-10-06',end_date='2026-10-07')

class ComparisonMigration(unittest.TestCase):
    def test_compare_reads_contract_totals_without_legacy_flags(self):
        from unittest.mock import patch
        from ai_chat.metric_adapter import compare_metric
        current={'start_date':'2026-10-06','end_date':'2026-10-12','orders_count':15,'cancelled_orders_count':8,
                 'products':[{'product_key':'a','title':'A','orders_count':15,'cancelled_orders_count':8}]}
        previous={'start_date':'2026-09-29','end_date':'2026-10-05','orders_count':10,'cancelled_orders_count':2,
                  'products':[{'product_key':'a','title':'A','orders_count':10,'cancelled_orders_count':2}]}
        with patch('ai_chat.metric_adapter.get_orders',side_effect=[current,previous]) as getter:
            result=compare_metric(metric='orders',supabase=object(),user_id=1,shop_id=1,period_days=7)
        self.assertEqual((result['current'],result['previous'],result['change_abs'],result['change_pct']),(15,10,5,50))
        self.assertEqual(getter.call_args_list[1].kwargs['start_date'],'2026-09-29')
        for call in getter.call_args_list:self.assertNotIn('latest_only',call.kwargs)

    def test_tied_leaders_render_from_table_template(self):
        import json
        from pathlib import Path
        from ai_chat.answer_builder.templates import apply_template
        rule=json.loads((Path(__file__).resolve().parents[1]/'setup/get-orders-contract-release/answer-rule-after.json').read_text())
        data={'date_from':'2026-10-01','date_to':'2026-10-07','status':'ok','rows':[
            {'title':'A','orders_count':10,'value':10,'cancelled_orders_count':1},
            {'title':'B','orders_count':10,'value':10,'cancelled_orders_count':0}]}
        text=apply_template(rule=rule,fields=[],language='ru',data=data,request={})
        self.assertIn('A — 10 заказов',text);self.assertIn('B — 10 заказов',text)
        self.assertIn('Отменили 1.',text);self.assertNotIn('Отменили 0.',text)
