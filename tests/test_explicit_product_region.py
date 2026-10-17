import unittest
from unittest.mock import patch

class ExplicitProductRegion(unittest.TestCase):
 def test_explicit_product_beats_list_without_llm_scope_question(self):
  from ai_chat.routing.llm_fallback import clarify_request
  draft={'is_valid_question':True,'dataset':'orders','metric':'orders_count','entity':'region','product_key':'a','product':{'product_key':'a','match_type':'exact'}}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json') as llm:
   r=clarify_request('explicit named product',draft=draft,memory={'shown_product_keys':['b','c']})
  self.assertEqual(r['product_key'],'a');self.assertEqual(r['entity'],'region');self.assertEqual(r['action'],'execute');llm.assert_not_called()
 def test_region_from_rules_not_question_prefix(self):
  from ai_chat.routing.route import _route_request
  product={'product_key':'a','title':'Dress','match_type':'exact'}
  with patch('ai_chat.routing.llm_fallback.resolve_shown_orders',return_value=None),patch('ai_chat.routing.llm_fallback.resolve_funnel_change',return_value=None),patch('ai_chat.routing.route.resolve_entity',return_value='region'),patch('ai_chat.routing.route.resolve_product',return_value=product):
   r=_route_request('Named product destination question',memory={'shown_product_keys':['b'],'last_product_key':'b'},request_context={'user_id':1,'shop_id':1})
  self.assertEqual(r['entity'],'region');self.assertEqual(r['product_key'],'a');self.assertEqual(r['period_days'],7)
 def test_memory_product_still_checked_for_ambiguity(self):
  from ai_chat.routing.llm_fallback import clarify_request
  draft={'is_valid_question':True,'dataset':'stocks','metric':'stock_qty','entity':'product','product_key':'a','product':{'match_type':'memory'}}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',side_effect=RuntimeError()) as llm:
   r=clarify_request('ambiguous',draft=draft,memory={'shown_product_keys':['a','b']})
  llm.assert_called_once();self.assertFalse(r['is_valid_question'])
