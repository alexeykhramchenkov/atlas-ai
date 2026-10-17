import unittest
from datetime import date,timedelta
from ai_chat.routing.seller_questions import resolve_seller_question
from ai_chat.metric.seller_questions import calculate
CTX={'user_id':1,'shop_id':1,'marketplace':'wb'}
class StockAuditRegressions(unittest.TestCase):
 def route(self,text,memory=None):
  return resolve_seller_question(text,memory or {},CTX,resolve_explicit=lambda q:{'product_key':'a','match_type':'exact'} if '123456789' in q else None,resolve_reference=lambda q,m:{'product_key':m['last_product_key'],'match_type':'memory'} if m.get('last_product_key') else None,resolve_registered=lambda _:None)
 def test_negation_cannot_be_risk(self):
  for text in ('Какие товары пока не нужно пополнять?','Какие товары не стоит закупать?'):
   r=self.route(text);self.assertFalse(r['is_valid_question']);self.assertEqual(r['error_code'],'unsupported_metric')
 def test_short_dovoz_and_article(self):
  self.assertEqual(self.route('Сколько довезти на две недели?')['metric'],'replenishment_qty')
  self.assertEqual(self.route('Сколько довезти на две недели для товара 123456789?')['product_key'],'a')
 def test_sizes_inherit_only_immediate_context(self):
  text='Какие размеры заканчиваются?';self.assertFalse(self.route(text)['is_valid_question'])
  r=self.route(text,{'last_product_key':'a','date_from':'2026-10-07','date_to':'2026-10-13'})
  self.assertEqual(r['product_key'],'a');self.assertEqual(r['date_to'],'2026-10-13')
 def facts(self):
  return {'products':[{'product_key':k,'title':k} for k in ('a','b')],'orders':[{'snapshot_date':(date(2026,10,7)+timedelta(days=i)).isoformat(),'product_key':k,'orders_count':1} for i in range(7) for k in ('a','b')],'stocks':[{'snapshot_date':'2026-10-14','product_key':k,'total_quantity':1,'warehouse_quantity':1} for k in ('a','b')]}
 def request(self,metric):return {**CTX,'metric':metric,'dataset':'stocks','analysis':'best','entity':'product','period_days':7,'date_from':'2026-10-07','date_to':'2026-10-13','product_key':'a','limit':5}
 def test_dovoz_filters_article(self):
  r=calculate(self.request('replenishment_qty'),self.facts());self.assertEqual([x['product_key'] for x in r['rows']],['a']);self.assertEqual(r['rows'][0]['value'],13)
 def test_missing_size_is_incomplete_not_no_risk(self):
  f=self.facts();f.update(stock_sizes=[{'product_key':'a','size_name':None,'quantity':1}],order_events=[{'product_key':'a','srid':'1','size_name':'90'}]);r=calculate(self.request('size_stock_days'),f);self.assertEqual(r['status'],'incomplete')
 def test_known_size_risk(self):
  f=self.facts();f.update(stock_sizes=[{'product_key':'a','size_name':'90','quantity':1}],order_events=[{'product_key':'a','srid':'1','size_name':'90'}]);r=calculate(self.request('size_stock_days'),f);self.assertEqual(r['rows'][0]['value'],7)
