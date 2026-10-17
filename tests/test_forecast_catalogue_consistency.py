import unittest
from unittest.mock import patch
from ai_chat.routing.seller_questions import QUESTIONS,resolve_seller_question
from ai_chat.executor import Executor

class ForecastCatalogueTests(unittest.TestCase):
 def test_aliases_share_existing_forecast_and_default_pace(self):
  product={'product_key':'a','match_type':'memory'}
  for metric,analysis,entity in [('replenishment_risk','rank','product'),('stock_days','metric_value','product'),('size_stock_days','rank','variant')]:
   question=next(r[1] for r in QUESTIONS if r[2]==metric)
   r=resolve_seller_question(question,{'date_from':'2026-10-10','date_to':'2026-10-16'}, {},resolve_explicit=lambda _:product,resolve_reference=lambda *_:product)
   self.assertEqual((r['metric'],r['analysis'],r['entity'],r['period_days']),('days_left',analysis,entity,30))
 def test_variant_forecast_aggregates_warehouses_and_uses_variant_orders(self):
  stock={'as_of':'2026-10-16','warehouse_quantity':9,'total_quantity':90,'products':[
    {'product_key':'a','variant_key':'s','size_name':'80','title':'A','warehouse_quantity':2},
    {'product_key':'a','variant_key':'s','size_name':'80','title':'A','warehouse_quantity':1},
    {'product_key':'a','variant_key':'m','size_name':'90','title':'A','warehouse_quantity':6}]}
  orders={'start_date':'2026-09-17','end_date':'2026-10-16','variants':[
    {'product_key':'a','variant_key':'s','orders_count':10},
    {'product_key':'a','variant_key':'m','orders_count':2}]}
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=stock),patch('ai_chat.internal_tools.get_orders.get_orders',return_value=orders) as getter:
   r=Executor(object()).execute({'user_id':1,'shop_id':1,'dataset':'stocks','metric':'days_left','analysis':'rank','entity':'variant','product_key':'a','period_days':30,'limit':5})
  self.assertEqual(getter.call_args.kwargs['level'],'variant')
  self.assertEqual(len(r['rows']),1);self.assertEqual(r['rows'][0]['days_left'],9)
  self.assertEqual(r['rows'][0]['size_name'],'80')

 def test_delivery_qty_uses_only_warehouse_and_rejects_unknown_warehouse(self):
  from ai_chat.metric.seller_questions import calculate
  from datetime import date,timedelta
  request={'dataset':'stocks','metric':'replenishment_qty','analysis':'best','entity':'product','date_from':'2026-10-01','date_to':'2026-10-07','limit':5}
  facts={'products':[{'product_key':'a'}],'orders':[{'product_key':'a','snapshot_date':str(date(2026,10,1)+timedelta(days=i)),'orders_count':1} for i in range(7)],'stocks':[{'product_key':'a','snapshot_date':'2026-10-08','total_quantity':100,'warehouse_quantity':1}]}
  self.assertEqual(calculate(request,facts)['rows'][0]['value'],13)
  del facts['stocks'][0]['warehouse_quantity']
  self.assertEqual(calculate(request,facts)['status'],'incomplete')

 def test_shown_selection_preserves_breakdown_dimension(self):
  from ai_chat.routing.llm_fallback import validate_clarification_updates
  for entity in ('variant','warehouse','region'):
   r=validate_clarification_updates([{'field':'selection','value':'shown_products'}],request={'dataset':'stocks','metric':'days_left','entity':entity},memory={'shown_product_keys':['a']})
   self.assertEqual(r['entity'],entity);self.assertEqual(r['product_keys'],['a'])

 def test_registered_product_question_uses_single_context_product(self):
  q=next(x[1] for x in QUESTIONS if x[2]=='price_change_orders')
  r=resolve_seller_question(q,{}, {},resolve_explicit=lambda _:None,resolve_reference=lambda text,_:{'product_key':'a','match_type':'memory'} if text=='этот товар' else None)
  self.assertTrue(r['is_valid_question']);self.assertEqual(r['product_key'],'a')
