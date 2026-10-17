import unittest
from ai_chat.metric.seller_questions import calculate,handles
from ai_chat.routing.llm_fallback import validate_clarification_updates

class FunnelGapTests(unittest.TestCase):
 def result(self,metric):
  req={'dataset':'funnel','analysis':'worst','metric':metric,'entity':'product','period_days':7,'date_from':'2026-10-10','date_to':'2026-10-16','limit':5}
  rows=[{'product_key':'a','open_count':10,'cart_count':0,'order_count':2},
        {'product_key':'b','open_count':20,'cart_count':3,'order_count':0},
        {'product_key':'c','open_count':0,'cart_count':0,'order_count':0}]
  return calculate(req,{'products':[],'funnel':{'products':rows}})
 def test_relative_period_is_accepted_by_existing_adapter(self):
  self.assertTrue(handles({'question_type':'simple','metric':'regions_store','entity':'region','period_days':7}))
 def test_explicit_dates_do_not_require_relative_period(self):
  req={'dataset':'funnel','analysis':'worst','metric':'carts_without_orders','entity':'product','date_from':'2026-10-10','date_to':'2026-10-16','limit':5}
  self.assertEqual(calculate(req,{'funnel':{'products':[]}})['period_days'],7)
 def test_views_without_carts_does_not_require_zero_orders(self):
  self.assertEqual([r['product_key'] for r in self.result('views_without_carts')['rows']],['a'])
 def test_carts_without_orders_excludes_zero_carts(self):
  self.assertEqual([r['product_key'] for r in self.result('carts_without_orders')['rows']],['b'])
 def test_store_scope_retains_region_dimension(self):
  req={'dataset':'orders','analysis':'best','metric':'regions_store','entity':'region','product_keys':['old']}
  out=validate_clarification_updates([{'field':'selection','value':'store'}],request=req,memory={})
  self.assertEqual((out['entity'],out['scope']),('region','store'));self.assertNotIn('product_keys',out)
 def test_store_scope_keeps_product_list_dimension(self):
  req={'dataset':'funnel','analysis':'worst','metric':'carts_without_orders','entity':'product'}
  out=validate_clarification_updates([{'field':'selection','value':'store'}],request=req,memory={})
  self.assertEqual((out['entity'],out['scope']),('product','store'))
 def test_existing_gap_metrics_survive_clarification(self):
  req={'dataset':'funnel','analysis':'worst','metric':'carts_without_orders','entity':'product'}
  self.assertEqual(validate_clarification_updates([],request=req,memory={})['metric'],'carts_without_orders')
