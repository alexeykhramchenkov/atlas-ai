import unittest
from unittest.mock import patch
from ai_chat.metric.seller_questions import calculate,run
from ai_chat.routing.llm_fallback import validate_clarification_updates

class StockWithoutOrdersTests(unittest.TestCase):
 def request(self,**kw):return {'user_id':1,'shop_id':2,'marketplace':'wb','question_type':'simple','metric':'stock_without_orders','dataset':'stocks','analysis':'worst','entity':'product','period_days':7,'date_from':'2026-10-10','date_to':'2026-10-16','limit':5,**kw}
 def stocks(self):return {'as_of':'2026-10-16','products':[{'product_key':'zero','title':'Zero','total_quantity':5},{'product_key':'one','title':'One','total_quantity':7},{'product_key':'empty','title':'Empty','total_quantity':0},{'product_key':'missing','title':'Missing','total_quantity':2}]}
 def orders(self):return {'products':[{'product_key':'zero','orders_count':0},{'product_key':'one','orders_count':1}]}
 def test_strict_zero_and_positive_stock(self):
  out=calculate(self.request(),{'order_facts':self.orders(),'stock_facts':self.stocks()})
  self.assertEqual([r['product_key'] for r in out['rows']],['zero','missing'])
 def test_explicit_selection_stays_bounded(self):
  out=calculate(self.request(product_keys=['missing']),{'order_facts':self.orders(),'stock_facts':self.stocks()})
  self.assertEqual([r['product_key'] for r in out['rows']],['missing'])
 def test_existing_fact_tools_receive_only_scoped_tenant_and_dates(self):
  with patch('ai_chat.internal_tools.get_orders.get_orders',return_value=self.orders()) as orders,patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=self.stocks()) as stocks:
   run(self.request(),object())
  self.assertEqual(orders.call_args.kwargs['shop_id'],2);self.assertEqual(stocks.call_args.kwargs['user_id'],1)
  self.assertEqual(orders.call_args.kwargs['start_date'],'2026-10-10')
 def test_incomplete_orders_are_not_measured_zero(self):
  from ai_chat.internal_tools.get_orders import IncompleteOrdersError
  with patch('ai_chat.internal_tools.get_orders.get_orders',side_effect=IncompleteOrdersError('2026-10-10','2026-10-16')),patch('ai_chat.internal_tools.get_stocks.get_stocks') as stocks:
   out=run(self.request(),object())
  self.assertEqual(out['status'],'incomplete');stocks.assert_not_called()
 def test_return_ranking_keeps_product_breakdown_when_store_selected(self):
  req={'dataset':'sales','metric':'return_count','analysis':'best','entity':'product'}
  out=validate_clarification_updates([{'field':'selection','value':'store'}],request=req,memory={'shown_product_keys':['old']})
  self.assertEqual(out['entity'],'product');self.assertNotIn('product_keys',out)

class ReturnRankingTests(unittest.TestCase):
 def test_positive_returns_are_filtered_before_ranking(self):
  from ai_chat.executor import Executor
  req={'user_id':1,'shop_id':2,'marketplace':'wb','question_type':'simple','dataset':'sales','metric':'return_count','analysis':'best','entity':'product','period_days':7,'limit':5}
  facts={'start_date':'2026-10-10','end_date':'2026-10-16','sales_count':4,'return_count':2,'products':[{'product_key':'a','title':'A','sales_count':2,'return_count':2},{'product_key':'b','title':'B','sales_count':2,'return_count':0}]}
  with patch('ai_chat.internal_tools.get_sales.get_sales',return_value=facts):out=Executor(object()).execute(req)
  self.assertEqual([r['product_key'] for r in out['rows']],['a']);self.assertEqual(out['return_count'],2)
 def test_explicit_product_selection_is_applied_before_return_ranking(self):
  from ai_chat.executor import Executor
  req={'user_id':1,'shop_id':2,'marketplace':'wb','question_type':'simple','dataset':'sales','metric':'return_count','analysis':'best','entity':'product','period_days':7,'limit':5,'product_keys':['b']}
  facts={'start_date':'2026-10-10','end_date':'2026-10-16','products':[{'product_key':'a','return_count':8},{'product_key':'b','return_count':1}]}
  with patch('ai_chat.internal_tools.get_sales.get_sales',return_value=facts):out=Executor(object()).execute(req)
  self.assertEqual([r['product_key'] for r in out['rows']],['b'])
