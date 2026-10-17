import unittest
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch
from test_get_orders_contract import DB
from ai_chat.internal_tools.get_funnel import get_funnel,FIELDS,FunnelDataUnavailableError

class FunnelContract(unittest.TestCase):
    def db(self):
        t={'user_id':1,'shop_id':1,'marketplace':'wb'}
        rows=[{**t,'id':i,'snapshot_date':day,'product_key':pk,
               **dict(zip(FIELDS,values))}
              for i,(day,pk,values) in enumerate([
                ('2026-10-06','a',(10,5,3,2,1)),
                ('2026-10-07','a',(20,8,4,1,2)),
                ('2026-10-06','b',(30,15,5,3,0))],1)]
        rows += [{**rows[0],'id':99,'shop_id':2,'cart_count':999},
                 {**rows[0],'id':100,'user_id':2,'cart_count':999}]
        return DB({'metrics_funnel_daily':rows,'normalized_products':[
            {**t,'id':1,'product_key':'a','title':'A'},
            {**t,'id':2,'product_key':'b','title':'B'},
            {**t,'id':3,'shop_id':2,'product_key':'a','title':'Wrong'}]})
    def get(self,db,**kw):
        return get_funnel(user_id=1,shop_id=1,supabase=db,**kw)
    def test_exact_contract_totals_and_tenant(self):
        db=self.db();r=self.get(db,start_date='2026-10-06',end_date='2026-10-07')
        self.assertEqual(set(r),{'start_date','end_date','products',*FIELDS})
        self.assertEqual([r[f] for f in FIELDS],[60,28,12,6,3])
        self.assertEqual(r['products'][0],{'product_key':'a','title':'A',**dict(zip(FIELDS,[30,13,7,3,3]))})
        for q in db.queries:
            for f,v in [('user_id',1),('shop_id',1),('marketplace','wb')]:self.assertIn((f,'eq',v),q.filters)
    def test_product_filter_and_inclusive_dates(self):
        r=self.get(self.db(),product_key='a',start_date='2026-10-07',end_date='2026-10-07')
        self.assertEqual(r['cart_count'],8);self.assertEqual(len(r['products']),1)
    def test_last_30_completed_moscow_days(self):
        end=datetime.now(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1)
        db=self.db();base=db.data['metrics_funnel_daily'][0]
        db.data['metrics_funnel_daily']=[{**base,'id':i,'snapshot_date':str(end-timedelta(days=i))} for i in range(31)]
        r=self.get(db,period_days=30)
        self.assertEqual(r['start_date'],str(end-timedelta(days=29)));self.assertEqual(r['end_date'],str(end))
        self.assertEqual(r['cart_count'],150)
    def test_pagination_2001_rows(self):
        db=self.db();base=db.data['metrics_funnel_daily'][0]
        db.data['metrics_funnel_daily']=[{**base,'id':i,'product_key':f'p{i:05}'} for i in range(2001)]
        r=self.get(db,start_date='2026-10-06',end_date='2026-10-06')
        self.assertEqual(len(r['products']),2001);self.assertEqual(r['cart_count'],10005)
    def test_absent_facts_not_fabricated_zero(self):
        for kw in ({'product_key':'unknown'}, {'start_date':'2026-10-01','end_date':'2026-10-02'}):
            params={'start_date':'2026-10-06','end_date':'2026-10-07',**kw}
            with self.assertRaises(FunnelDataUnavailableError):self.get(self.db(),**params)
    def test_missing_days_do_not_change_requested_period(self):
        r=self.get(self.db(),start_date='2026-10-01',end_date='2026-10-10')
        self.assertEqual(r['start_date'],'2026-10-01');self.assertEqual(r['cart_count'],28)
    def test_invalid_period_and_bad_facts(self):
        for kw in ({},{'period_days':True},{'period_days':0},{'start_date':'2026-10-06'},
                   {'start_date':'2026-10-07','end_date':'2026-10-06'},
                   {'period_days':30,'start_date':'2026-10-06','end_date':'2026-10-07'}):
            with self.assertRaises(ValueError):self.get(self.db(),**kw)
        for v in (None,True,-1,0.5,'NaN'):
            db=self.db();db.data['metrics_funnel_daily'][0]['cart_count']=v
            with self.assertRaises(ValueError):self.get(db,start_date='2026-10-06',end_date='2026-10-07')
    def test_executor_get_then_rank_without_dates(self):
        from ai_chat.executor import Executor
        from ai_chat.analysis.analysis_type import rank
        db=self.db();req={'dataset':'funnel','metric':'cart_count','analysis':'best','entity':'product',
            'user_id':1,'shop_id':1,'date_from':'2026-10-06','date_to':'2026-10-07','limit':1}
        with patch('ai_chat.internal_tools.get_funnel.get_funnel',wraps=get_funnel) as reader,patch.object(rank,'run',wraps=rank.run) as sorter:
            r=Executor(supabase=db).execute(req)
        self.assertEqual(reader.call_count,1);self.assertEqual(sorter.call_count,1)
        self.assertEqual(set(sorter.call_args.kwargs),{'rows','metric','direction','limit'})
        self.assertEqual(sorter.call_args.kwargs['metric'],'cart_count');self.assertEqual(sorter.call_args.kwargs['direction'],'desc')
        self.assertEqual(r['rows'][0]['product_key'],'b');self.assertEqual(r['rows'][0]['cart_count'],15)
    def test_comparison_uses_two_contract_calls(self):
        from ai_chat.metric_adapter import compare_funnel_metrics
        cur={'products':[{'open_count':100,'cart_count':20,'order_count':10}]}
        old={'products':[{'open_count':50,'cart_count':5,'order_count':1}]}
        with patch('ai_chat.metric_adapter.get_funnel',side_effect=[cur,old]) as reader:
            r=compare_funnel_metrics(metrics=['views','cart_rate','conversion'],supabase=object(),user_id=1,shop_id=1,period_days=7)
        self.assertEqual(r['views']['current'],100);self.assertEqual(r['views']['previous'],50)
        self.assertEqual(r['cart_rate']['current'],20);self.assertEqual(r['conversion']['current'],50)
        self.assertEqual(reader.call_count,2)
        for call in reader.call_args_list:
            self.assertNotIn('latest_only',call.kwargs);self.assertIn('start_date',call.kwargs)
