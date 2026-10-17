import unittest
from unittest.mock import patch
import test_get_orders_contract as fixtures
from ai_chat.internal_tools.get_orders import get_orders
from ai_chat.routing.llm_fallback import resolve_shown_orders

class OrdersAmountMemory(unittest.TestCase):
 def test_all_orders_and_cancellations_separate(self):
  db=fixtures.GetOrdersContract().db()
  r=get_orders(1,1,start_date='2026-10-06',end_date='2026-10-07',supabase=db)
  self.assertEqual((r['orders_amount'],r['cancelled_orders_amount']),(1200,300))
  self.assertEqual(r['products'][0]['orders_amount'],500)
 def test_unknown_amount_not_zero(self):
  db=fixtures.GetOrdersContract().db();db.data['metrics_orders_daily'][0]['gross_order_value']=None
  r=get_orders(1,1,start_date='2026-10-06',end_date='2026-10-07',supabase=db)
  self.assertIsNone(r['orders_amount']);self.assertIsNone(r['cancelled_orders_amount'])
 def test_decimal_and_invalid(self):
  db=fixtures.GetOrdersContract().db()
  for row in db.data['metrics_orders_daily']:
   row.update(gross_order_value='0.30',net_order_value='0.10')
  r=get_orders(1,1,start_date='2026-10-06',end_date='2026-10-07',supabase=db)
  self.assertEqual((r['orders_amount'],r['cancelled_orders_amount']),(0.9,0.6))
  db.data['metrics_orders_daily'][0]['net_order_value']=9
  with self.assertRaises(ValueError):get_orders(1,1,start_date='2026-10-06',end_date='2026-10-07',supabase=db)
 def test_memory_uses_delivered_rows_not_hidden_losses(self):
  from ai_chat.memory import resolve_last_product_context
  row={'status':'success','delivery_status':'sent','router_request':{'entity':'product'},'result':{'status':'ok','rows':[{'product_key':'a'},{'product_key':'b'}],'losses':[{'product_key':'hidden'}]}}
  with patch('ai_chat.memory.latest_dialogue_row',return_value=row):
   memory=resolve_last_product_context(telegram_user_id=1,user_id=1,shop_id=1,marketplace='wb',supabase=object())
  self.assertEqual(memory['shown_product_keys'],['a','b'])
  row['delivery_status']='failed'
  with patch('ai_chat.memory.latest_dialogue_row',return_value=row):
   self.assertEqual(resolve_last_product_context(telegram_user_id=1,user_id=1,shop_id=1,marketplace='wb',supabase=object()),{})
 def test_reference_and_no_reference(self):
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'applicable':True,'period_days':7}):
   r=resolve_shown_orders('reference',memory={'shown_product_keys':['b','a']},request_context={'user_id':9,'shop_id':8})
   self.assertEqual(r['product_keys'],['b','a']);self.assertEqual(r['period_days'],7)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'applicable':False,'period_days':None}):
   self.assertIsNone(resolve_shown_orders('store total',memory={'shown_product_keys':['a']},request_context={}))
 def test_executor_sum_only_selected_keys(self):
  from ai_chat.executor import Executor
  db=fixtures.GetOrdersContract().db()
  req={'dataset':'orders','analysis':'metric_value','metric':'orders_amount','entity':'product','user_id':1,'shop_id':1,'date_from':'2026-10-06','date_to':'2026-10-07','product_keys':['a']}
  result=Executor(db).execute(req)
  self.assertEqual(result['value'],500);self.assertEqual([r['product_key'] for r in result['rows']],['a'])
 def test_generic_sum_empty_dimensions_decimal(self):
  from ai_chat.analysis.analysis_type.ranked import group_rows
  r=group_rows([{'amount':0.1},{'amount':0.2}],{'group_by':[],'value_field':'amount','aggregation':'sum'})
  self.assertEqual(r[0]['amount'],0.3)

class UnifiedRevenue(unittest.TestCase):
 def test_legacy_alias_and_breakdown_same_getter(self):
  from ai_chat.executor import Executor
  db=fixtures.GetOrdersContract().db()
  base={'dataset':'orders','analysis':'metric_value','user_id':1,'shop_id':1,'date_from':'2026-10-06','date_to':'2026-10-07'}
  store=Executor(db).execute({**base,'metric':'orders_revenue','entity':'store'})
  products=Executor(db).execute({**base,'metric':'orders_amount','entity':'product','answer_scope':'all'})
  self.assertEqual(store['value'],products['value'])
  self.assertEqual(products['value'],sum(r['orders_amount'] for r in products['rows']))
  self.assertEqual([r['orders_amount'] for r in products['rows']],[700,500])
 def test_breakdown_keeps_store_scope_not_old_cohort(self):
  memory={'last_dataset':'orders','last_metric':'orders_amount','last_scope':'store','date_from':'2026-10-06','date_to':'2026-10-07','shown_product_keys':['stale']}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'applicable':True,'breakdown':True,'period_days':None}):
   request=resolve_shown_orders('details',memory=memory,request_context={'user_id':1,'shop_id':1})
  self.assertNotIn('product_keys',request)
  self.assertEqual(request['date_from'],'2026-10-06')

class ZeroAmountDisplay(unittest.TestCase):
 def test_hide_and_restore_zeros_without_total_change(self):
  from ai_chat.executor import Executor
  db=fixtures.GetOrdersContract().db()
  for row in db.data['metrics_orders_daily']:
   if row['product_key']=='a': row.update(gross_order_value=0,net_order_value=0)
  base={'dataset':'orders','analysis':'metric_value','metric':'orders_amount','entity':'product','user_id':1,'shop_id':1,'date_from':'2026-10-06','date_to':'2026-10-07'}
  for cohort in (False,True):
   req={**base,**({'product_keys':['a','b']} if cohort else {})}
   default=Executor(db).execute({**req,'answer_scope':'top'})
   all_rows=Executor(db).execute({**req,'answer_scope':'all'})
   self.assertEqual(default['value'],all_rows['value'])
   self.assertEqual([r['product_key'] for r in default['rows']],['b'])
   self.assertEqual([r['product_key'] for r in all_rows['rows']],['b','a'])
 def test_zero_followup_keeps_original_population(self):
  memory={'last_dataset':'orders','last_metric':'orders_amount','last_scope':'product','shown_product_keys':['a'],'product_keys':['a','zero'],'date_from':'2026-10-06','date_to':'2026-10-07'}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'applicable':True,'breakdown':True,'answer_scope':'all','period_days':None}):
   request=resolve_shown_orders('include zeros',memory=memory,request_context={})
  self.assertEqual(request['product_keys'],['a','zero'])
  memory.update(last_scope='store',product_keys=None)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'applicable':True,'breakdown':True,'answer_scope':'all','period_days':None}):
   request=resolve_shown_orders('include zeros',memory=memory,request_context={})
  self.assertNotIn('product_keys',request)

class CurrentMetricWins(unittest.TestCase):
 def test_other_metric_cannot_inherit_revenue_even_if_applicable_is_wrong(self):
  parsed={'requested_metric':'other','applicable':True,'breakdown':False,'period_days':None}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   self.assertIsNone(resolve_shown_orders('a different measure for them',memory={'shown_product_keys':['a'],'last_dataset':'orders','last_metric':'orders_amount'},request_context={}))
