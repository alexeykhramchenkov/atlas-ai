import unittest
from unittest.mock import patch
from ai_chat.routing.llm_fallback import resolve_funnel_change, FUNNEL_METRICS

class GenericFunnelRouter(unittest.TestCase):
 def memory(self):return {'last_dataset':'funnel','last_analysis':'compare','last_metric':'order_count','date_from':'2026-10-09','date_to':'2026-10-15'}
 def parsed(self,**kw):return dict(applicable=True,metric='open_count',direction='positive',period_days=None,start_date=None,end_date=None,**kw)
 def call(self,parsed,memory=None):
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   return resolve_funnel_change('arbitrary wording',memory=memory or self.memory(),request_context={'user_id':9,'shop_id':8})
 def test_all_metrics_and_directions_same_path(self):
  for metric in FUNNEL_METRICS:
   for direction in ('positive','negative'):
    p=self.parsed();p.update(metric=metric,direction=direction)
    r=self.call(p)
    self.assertEqual(r['metric'],metric);self.assertEqual(r['direction'],direction)
    self.assertEqual(r['date_from'],'2026-10-09');self.assertEqual(r['shop_id'],8)
    self.assertTrue(r['context_dates_inherited']);self.assertNotIn('product_key',r)
 def test_explicit_period_overrides_memory(self):
  p=self.parsed();p['period_days']=30
  r=self.call(p);self.assertEqual(r['period_days'],30);self.assertFalse(r['context_dates_inherited'])
 def test_explicit_dates(self):
  p=self.parsed();p.update(start_date='2026-09-01',end_date='2026-09-30')
  r=self.call(p);self.assertEqual(r['date_from'],'2026-09-01');self.assertFalse(r['context_dates_inherited'])
 def test_decline_invalid_and_unrelated(self):
  for update in ({'applicable':False},{'metric':'profit'},{'direction':'invented'},{'period_days':True},{'start_date':'bad'},{'start_date':'2026-10-15','end_date':'2026-10-01'}):
   p=self.parsed();p.update(update);self.assertIsNone(self.call(p))
 def test_unrelated_metric_is_rejected_semantically_without_context(self):
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'applicable':False}) as api:
   self.assertIsNone(resolve_funnel_change('остатки',memory={},request_context={}))
   api.assert_called_once()
 def test_percent_zero_baseline(self):
  from ai_chat.answer_builder.formatters import format_value
  self.assertEqual(format_value(value=None,formatter='signed_percent',language='ru',options={'zero_baseline':'было 0'}),'было 0')

class ResolvedPopulation(unittest.TestCase):
 def test_new_search_does_not_inherit_old_list_or_reclarify(self):
  from ai_chat.routing.llm_fallback import clarify_request
  memory={'shown_product_keys':['old'],'last_dataset':'stocks'}
  parsed=dict(applicable=True,selection='store',metric='cart_count',direction='positive',period_days=7,start_date=None,end_date=None)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   r=resolve_funnel_change('new product search',memory=memory,request_context={})
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',side_effect=AssertionError('Do not ask twice')):
   self.assertEqual(clarify_request('new product search',draft=r,memory=memory),r)
  self.assertNotIn('product_keys',r);self.assertEqual(r['scope'],'store')
 def test_explicit_reference_uses_server_owned_selection(self):
  parsed=dict(applicable=True,selection='shown_products',metric='open_count',direction='negative',period_days=7,start_date=None,end_date=None)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   r=resolve_funnel_change('reference',memory={'shown_product_keys':['a','b']},request_context={})
  self.assertEqual(r['product_keys'],['a','b'])
