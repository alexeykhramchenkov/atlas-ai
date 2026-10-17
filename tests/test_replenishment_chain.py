import unittest
from unittest.mock import patch
from ai_chat.executor import Executor
from ai_chat.routing.llm_fallback import clarify_request
from ai_chat.internal_tools.get_orders import IncompleteOrdersError

class ReplenishmentChain(unittest.TestCase):
 def request(self,**kw):return dict(user_id=1,shop_id=1,marketplace='wb',dataset='stocks',metric='days_left',analysis='rank',entity='product',period_days=30,limit=5,**kw)
 def stocks(self):return dict(as_of='2026-10-16',total_quantity=90,products=[dict(product_key=k,total_quantity=n,warehouse_quantity=n) for k,n in [('slow',72),('urgent',3),('empty',0),('no_demand',15)]])
 def orders(self):return dict(start_date='2026-09-17',end_date='2026-10-16',orders_count=111,products=[dict(product_key=k,orders_count=n) for k,n in [('slow',21),('urgent',60),('empty',30)]])
 def execute(self,req):
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=self.stocks()),patch('ai_chat.internal_tools.get_orders.get_orders',return_value=self.orders()) as getter:
   r=Executor(supabase=object()).execute(req)
  self.assertEqual(getter.call_args.kwargs['period_days'],30)
  return r
 def test_whole_store_threshold_sort_and_no_demand(self):
  r=self.execute(self.request());self.assertEqual([x['product_key'] for x in r['rows']],['empty','urgent'])
  self.assertEqual([x['days_left'] for x in r['rows']],[0,1.5]);self.assertEqual(r['checked_products'],4)
 def test_previous_list_selection(self):
  r=self.execute(self.request(product_keys=['urgent','slow']))
  self.assertEqual([x['product_key'] for x in r['rows']],['urgent']);self.assertEqual(r['checked_products'],2)
 def test_incomplete_not_empty_safe_list(self):
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=self.stocks()),patch('ai_chat.internal_tools.get_orders.get_orders',side_effect=IncompleteOrdersError('2026-09-17','2026-10-16')):
   r=Executor(supabase=object()).execute(self.request())
  self.assertEqual(r['status'],'incomplete')
 def test_scope_updates_accept_existing_days_left_metric(self):
  memory={'shown_product_keys':['slow','urgent']}
  for choice in ('store','shown_products'):
   decision={'action':'execute','updates':[{'field':'selection','value':choice}]}
   with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=decision):
    r=clarify_request('test',draft={**self.request(),'is_valid_question':True},memory=memory)
   self.assertEqual(r['metric'],'days_left');self.assertEqual(r['analysis'],'rank')
   self.assertEqual(r.get('product_keys'),['slow','urgent'] if choice=='shown_products' else None)
 def test_legacy_handler_is_not_registered(self):
  from ai_chat.analysis.executor import ANALYSIS_TYPE_HANDLERS
  self.assertNotIn('risk_check',ANALYSIS_TYPE_HANDLERS)

 def test_warehouse_basis_and_fourteen_day_threshold(self):
  stocks=self.stocks(); stocks['products']=[dict(product_key='urgent',total_quantity=100,warehouse_quantity=24),dict(product_key='slow',total_quantity=100,warehouse_quantity=11),dict(product_key='unknown',total_quantity=5)]
  # urgent: 24 / (60/30) = 12 days. slow: 11 / (21/30) > 14.
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=stocks),patch('ai_chat.internal_tools.get_orders.get_orders',return_value=self.orders()):
   result=Executor(supabase=object()).execute(self.request())
  self.assertEqual([(x['product_key'],x['days_left']) for x in result['rows']],[('urgent',12)])
  self.assertEqual(result['rows'][0]['total_quantity'],100)
