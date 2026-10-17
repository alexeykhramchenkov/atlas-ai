import unittest
from unittest.mock import patch
from ai_chat.executor import Executor

class ProductDaysLeftTests(unittest.TestCase):
 def test_single_product_is_not_limited_to_seven_days(self):
  stock=dict(as_of='2026-10-16',total_quantity=72,products=[dict(product_key='angel',total_quantity=100,warehouse_quantity=72)])
  orders=dict(start_date='2026-10-10',end_date='2026-10-16',orders_count=2,products=[{'product_key':'angel','orders_count':2}])
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=stock) as stocks,patch('ai_chat.internal_tools.get_orders.get_orders',return_value=orders) as getter:
   r=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,dataset='stocks',analysis='metric_value',metric='days_left',entity='product',product_key='angel',period_days=7))
  self.assertEqual(r['value'],252);self.assertEqual(r['status'],'ok')
  self.assertEqual(stocks.call_args.kwargs['product_key'],'angel');self.assertEqual(getter.call_args.kwargs['product_key'],'angel')
 def test_no_orders_is_not_zero_days(self):
  stock=dict(as_of='2026-10-16',total_quantity=72,products=[dict(product_key='angel',total_quantity=100,warehouse_quantity=72)])
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=stock),patch('ai_chat.internal_tools.get_orders.get_orders',return_value=dict(start_date='2026-10-10',end_date='2026-10-16',orders_count=0,products=[])):
   r=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,dataset='stocks',analysis='metric_value',metric='days_left',entity='product',product_key='angel',period_days=7))
  self.assertIsNone(r['value']);self.assertEqual(r['status'],'no_orders')
 def test_named_product_routes_to_days_left(self):
  from ai_chat.routing.route import _route_request
  with patch('ai_chat.routing.llm_fallback.resolve_buyer_questions',return_value=None),patch('ai_chat.routing.llm_fallback.resolve_shown_orders',return_value=None),patch('ai_chat.routing.llm_fallback.resolve_funnel_change',return_value=None),patch('ai_chat.routing.seller_questions.resolve_seller_question',return_value=None),patch('ai_chat.routing.route.resolve_product',return_value={'product_key':'angel','title':'Платье с крыльями ангела'}):
   r=_route_request('через сколько закончатся ангелы',memory={},request_context={'user_id':1,'shop_id':1})
  self.assertEqual((r['metric'],r['analysis'],r['product_key']),('days_left','metric_value','angel'))
  self.assertEqual(r['period_days'],30)
