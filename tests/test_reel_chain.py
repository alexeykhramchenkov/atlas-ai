from unittest.mock import patch
import unittest
from ai_chat.executor import Executor
from ai_chat.routing.route import route
from test_get_orders_contract import DB

class ChainTests(unittest.TestCase):
 def setUp(self):
  rules=[{'entity':'region','aliases_ru':['регион','регионы','куда чаще всего заказывают'],'aliases_en':[],'priority':20,'is_active':True}]
  fixture=patch('ai_chat.routing.entity.load_entity_rules',return_value=rules)
  fixture.start();self.addCleanup(fixture.stop)

 def db(self):
  tenant={'user_id':1,'shop_id':1,'marketplace':'wb'}
  metrics=[{'id':i,**tenant,'snapshot_date':f'2026-10-{i:02}','product_key':'a','orders_count':1,'cancelled_orders_count':1 if i==6 else 0} for i in range(6,13)]
  metrics.append({'id':13,**tenant,'snapshot_date':'2026-10-06','product_key':'b','orders_count':8,'cancelled_orders_count':7})
  events=[{'srid':'1','is_cancel':False,'region_name':'Москва','country_name':'Россия'},
          {'srid':'2','is_cancel':True,'region_name':'Казань','country_name':'Россия'},
          {'srid':'1','is_cancel':False,'region_name':'Москва','country_name':'Россия'}]
  return DB({'metrics_orders_daily':metrics,'normalized_products':[{'id':1,**tenant,'product_key':'a','title':'A'},{'id':2,**tenant,'product_key':'b','title':'B'}],
             'normalized_orders':[{'id':i,**tenant,'product_key':'a','order_date':'2026-10-06',**e} for i,e in enumerate(events)]})
 def request(self,**kw):
  return {'dataset':'orders','metric':'orders_count','entity':'store','analysis':'metric_value','question_type':'simple','answer_scope':'single',
          'user_id':1,'shop_id':1,'marketplace':'wb','date_from':'2026-10-06','date_to':'2026-10-12',**kw}
 def test_all_count_and_best_include_cancel(self):
  ex=Executor(supabase=self.db());x=ex.execute(self.request())
  self.assertEqual(x['orders_count'],15);self.assertEqual(x['cancelled_orders_count'],8)
  top=ex.execute(self.request(entity='product',analysis='best',limit=1))['rows'][0]
  self.assertEqual((top['product_key'],top['orders_count'],top['cancelled_orders_count'],top['rank']),('b',8,7,1))
 def test_regions_dedup_include_cancel(self):
  x=Executor(supabase=self.db()).execute(self.request(entity='region',analysis='best',answer_scope='top',product_key='a'))
  self.assertEqual(x['orders_count'],2);self.assertEqual(x['cancelled_orders_count'],1)
  self.assertEqual({r['region_name']:(r['value'],r['cancelled_orders_count']) for r in x['rows']},{'Москва':(1,0),'Казань':(1,1)})
 def test_missing_day_blocks(self):
  db=self.db();db.data['metrics_orders_daily']=[x for x in db.data['metrics_orders_daily'] if x['snapshot_date']!='2026-10-12']
  self.assertEqual(Executor(supabase=db).execute(self.request())['status'],'incomplete')
 def test_memory_date_and_product_inheritance(self):
  mem={'date_from':'2026-10-06','date_to':'2026-10-12','last_product_key':'a'}
  x=route('Куда чаще всего заказывают товар?',memory=mem,request_context={'user_id':1,'shop_id':1,'marketplace':'wb'})
  self.assertEqual(x['product_key'],'a');self.assertEqual(x['date_from'],mem['date_from'])
  x=route('Сколько продаж за неделю?',memory=mem,request_context={'user_id':1,'shop_id':1})
  self.assertNotIn('product_key',x);self.assertNotIn('date_from',x)

class MemoryTests(unittest.TestCase):
 def test_chat_guard_and_exact_dates(self):
  from unittest.mock import MagicMock
  from types import SimpleNamespace
  from ai_chat.memory import resolve_last_product_context
  q=MagicMock();q.table.return_value=q;q.select.return_value=q;q.eq.return_value=q;q.order.return_value=q;q.limit.return_value=q
  req={'telegram_user_id':10,'telegram_chat_id':20,'user_id':1,'shop_id':1,'marketplace':'wb','metric':'orders_count','entity':'product','limit':1}
  result={'status':'ok','date_from':'2026-10-06','date_to':'2026-10-12','rows':[{'product_key':'a'}]}
  from datetime import datetime,timezone
  q.execute.return_value=SimpleNamespace(data=[{'router_request':req,'result':result,'status':'success','created_at':datetime.now(timezone.utc).isoformat()}])
  m=resolve_last_product_context(telegram_user_id=10,telegram_chat_id=20,user_id=1,shop_id=1,marketplace='wb',supabase=q)
  self.assertEqual(m['last_product_key'],'a');self.assertEqual(m['date_from'],'2026-10-06')
  q.eq.assert_any_call('router_request->>telegram_chat_id','20')
  q.eq.assert_any_call('router_request->>telegram_user_id','10')
