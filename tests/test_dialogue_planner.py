import unittest
from unittest.mock import patch
from ai_chat import dialogue as d

C=dict(user_id=1,shop_id=2,marketplace='wb',telegram_user_id=3,telegram_chat_id=4)
def step(tool='get_orders',**args):return dict(id='one',tool=tool,args=[dict(name=k,json_value=__import__('json').dumps(v)) for k,v in args.items()])
class Query:
 def __init__(self,rows):self.rows=rows
 def __getattr__(self,name):return lambda *a,**kw:self
 def execute(self):return type('R',(),{'data':self.rows})()
class DB:
 def __init__(self,rows):self.rows=rows
 def table(self,name):return Query(self.rows)
class DialogueTests(unittest.TestCase):
 def test_protected_tenant_cannot_be_planned(self):
  with self.assertRaises(ValueError):d.validate_plan(dict(action='execute',steps=[step(user_id=9)]),C)
 def test_unknown_fact_argument_rejected(self):
  with self.assertRaises(TypeError):d.validate_plan(dict(action='execute',steps=[step(arbitrary=True)]),C)
 def test_duplicate_step_rejected(self):
  with self.assertRaises(ValueError):d.validate_plan(dict(action='execute',steps=[step(),step()]),C)
 def test_failure_does_not_erase_previous_memory(self):
  state=dict(active_product_keys=['fairy'],pending={'steps':[step('get_ads',product_key='fairy',level='product')]})
  rows=[dict(router_request=C,status='error',delivery_status='sent',result=None),dict(router_request=C,status='success',delivery_status='sent',result={'dialogue_state':state})]
  self.assertEqual(d.read_context(DB(rows),C,99)['state'],state)
 def test_shop_boundary(self):
  rows=[dict(router_request={**C,'shop_id':99},delivery_status='sent',result={'dialogue_state':{'active_product_keys':['foreign']}})]
  self.assertEqual(d.read_context(DB(rows),C,99)['state'],{})
 def test_reset_boundary(self):
  rows=[dict(router_request=C,error_message='dialogue_reset',delivery_status='sent',result={'dialogue_state':{'active_product_keys':['old']}})]
  self.assertEqual(d.read_context(DB(rows),C,99)['state'],{})
 def test_partial_failure_is_explicit_and_other_step_completes(self):
  p=dict(action='execute',steps=[step('get_ads',level='product'),{**step('get_reviews'),'id':'two'}])
  def fact(name):
   def run(**kw):
    self.assertEqual(kw['user_id'],1);self.assertEqual(kw['shop_id'],2)
    if name=='get_ads':raise ValueError('No advertising facts')
    return {'reviews_count':5}
   return run
  with patch.object(d,'getter',side_effect=fact):r=d.execute_plan(p,C,object(),object())
  self.assertEqual((r['one']['status'],r['two']['status']),('unavailable','ok'))
 def test_yes_and_reviews_planner_receives_pending_and_history(self):
  p=dict(action='execute',steps=[step('get_ads',product_key='fairy',level='product'),{**step('get_reviews',product_key='fairy',include_topics=True),'id':'two'}],question='',options=[],reply='')
  m={'state':{'pending':{'steps':[p['steps'][0]]},'active_product_keys':['fairy']},'history':[{'assistant':'Проверить рекламу?'}]}
  with patch.object(d,'generate_openai_json',return_value=p) as llm:
   r=d.plan_turn('Да, и что покупатели пишут?',C,m)
  self.assertEqual(len(r['steps']),2);self.assertIn('Проверить рекламу?',llm.call_args.kwargs['prompt']);self.assertIn('fairy',llm.call_args.kwargs['prompt'])
 def test_existing_ads_contract_checked_before_execution(self):
  with self.assertRaises(ValueError):d.validate_plan(dict(action='execute',steps=[step('get_ads',product_key='fairy',level='campaign')]),C)
 def test_forward_dependency_rejected(self):
  with self.assertRaises(ValueError):d.validate_plan(dict(action='execute',steps=[step(product_key={'from_step':'later','path':'rows.0.product_key'})]),C)
 def test_typed_arguments_need_no_json_string_encoding(self):
  s={'id':'one','tool':'get_reviews','args':[{'name':'product_key','value':'fairy'},{'name':'include_topics','value':True}]}
  self.assertEqual(d.arguments(s),{'product_key':'fairy','include_topics':True})
  d.validate_plan({'action':'execute','steps':[s]},C)
 def test_followup_period_cannot_silently_change(self):
  p={'period_source':'default','period_quote':'','steps':[step('analytics',dataset='orders',metric='orders_amount',entity='product',analysis='compare',period_days=30)]}
  d.bind_period(p,{'period':{'from':'2026-10-10','to':'2026-10-16'}},'Кто просел?')
  self.assertEqual(d.arguments(p['steps'][0])['date_from'],'2026-10-10')
  self.assertNotIn('period_days',d.arguments(p['steps'][0]))
 def test_replenishment_window_is_separate_30_days(self):
  p={'period_source':'inherit','period_quote':'','steps':[step('analytics',dataset='stocks',metric='days_left',entity='product',analysis='rank',period_days=7)]}
  d.bind_period(p,{'period':{'from':'2026-10-10','to':'2026-10-16'}},'Надо ли пополнять?')
  self.assertEqual(d.arguments(p['steps'][0])['period_days'],30)
 def test_explicit_new_period_is_honoured(self):
  p={'period_source':'explicit','period_quote':'30 дней','steps':[step('get_orders',period_days=30)]}
  d.bind_period(p,{'period':{'from':'2026-10-10','to':'2026-10-16'}},'А за 30 дней?')
  self.assertEqual(d.arguments(p['steps'][0])['period_days'],30)
