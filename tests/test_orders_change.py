import unittest
from unittest.mock import patch
from ai_chat.executor import Executor
from ai_chat.routing.llm_fallback import resolve_funnel_change

class OrdersChangeTests(unittest.TestCase):
 def test_revenue_uses_orders_in_funnel_context(self):
  parsed=dict(applicable=True,metric='orders_amount',direction='negative',answer_scope='top',period_days=None,start_date=None,end_date=None)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   r=resolve_funnel_change('Какие товары упали по выручке по магазину?',memory=dict(last_dataset='funnel',last_analysis='compare',date_from='2026-09-17',date_to='2026-10-16'),request_context=dict(user_id=1,shop_id=1))
  self.assertEqual((r['dataset'],r['metric'],r['analysis']),('orders','orders_amount','compare'))
  self.assertEqual(r['date_from'],'2026-09-17')
 def test_two_periods_join_filter_and_rank(self):
  current=dict(start_date='2026-10-10',end_date='2026-10-16',orders_amount=130,products=[dict(product_key='a',title='A',orders_amount=80),dict(product_key='b',title='B',orders_amount=0),dict(product_key='new',title='N',orders_amount=50)])
  previous=dict(start_date='2026-10-03',end_date='2026-10-09',orders_amount=200,products=[dict(product_key='a',title='A',orders_amount=100),dict(product_key='b',title='B',orders_amount=50),dict(product_key='old',title='O',orders_amount=50)])
  with patch('ai_chat.internal_tools.get_orders.get_orders',side_effect=[current,previous]) as getter:
   r=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,dataset='orders',metric='orders_amount',analysis='compare',entity='store',view='contributors',direction='negative',period_days=7,answer_scope='all'))
  self.assertEqual(getter.call_count,2)
  self.assertEqual(getter.call_args.kwargs['start_date'],'2026-10-03')
  self.assertEqual([x['change_abs'] for x in r['rows']],[-50,-50,-20])
  self.assertEqual(r['comparison']['orders_amount']['change_abs'],-70)
 def test_unknown_amount_is_not_zero(self):
  facts=dict(start_date='2026-10-10',end_date='2026-10-16',orders_amount=None,products=[])
  with patch('ai_chat.internal_tools.get_orders.get_orders',return_value=facts):
   r=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,dataset='orders',metric='orders_amount',analysis='compare',entity='store',period_days=7))
  self.assertEqual(r['status'],'no_data')
 def test_comparison_precedes_shown_amount_resolution(self):
  from ai_chat.routing.route import _route_request as route
  expected=dict(is_valid_question=True,dataset='orders',metric='orders_amount',analysis='compare')
  with patch('ai_chat.routing.llm_fallback.resolve_buyer_questions',return_value=None), patch('ai_chat.routing.llm_fallback.resolve_funnel_change',return_value=expected), patch('ai_chat.routing.llm_fallback.resolve_shown_orders') as shown:
   result=route('Какие товары упали по выручке по магазину?',request_context=dict(user_id=1,shop_id=1),memory={})
  self.assertEqual(result,expected);shown.assert_not_called()

 def test_previous_revenue_share_hides_minor_losses_but_keeps_zero_current(self):
  previous=dict(start_date='2026-10-03',end_date='2026-10-09',orders_amount=1000,products=[dict(product_key=k,orders_amount=v) for k,v in [('major',800),('small',200)]])
  current=dict(start_date='2026-10-10',end_date='2026-10-16',orders_amount=0,products=[])
  req=dict(user_id=1,shop_id=1,dataset='orders',metric='orders_amount',analysis='compare',entity='store',view='contributors',direction='negative',period_days=7)
  for scope,expected in [('top',['major']),('all',['major','small'])]:
   with patch('ai_chat.internal_tools.get_orders.get_orders',side_effect=[current,previous]):
    r=Executor(supabase=object()).execute({**req,'answer_scope':scope})
   self.assertEqual([x['product_key'] for x in r['rows']],expected)
   self.assertEqual(r['rows'][0]['current'],0)
   self.assertEqual(r['comparison']['orders_amount']['change_abs'],-1000)

class StandaloneFunnelChange(unittest.TestCase):
 def test_current_metric_does_not_require_funnel_in_previous_turn(self):
  from ai_chat.routing.llm_fallback import resolve_funnel_change
  parsed=dict(applicable=True,metric='open_count',direction='negative',answer_scope='top',period_days=7,start_date=None,end_date=None)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   r=resolve_funnel_change('У каких товаров упали просмотры',memory={'last_dataset':'stocks'},request_context={})
  self.assertEqual((r['dataset'],r['metric'],r['direction']),('funnel','open_count','negative'))
