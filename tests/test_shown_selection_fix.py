import unittest
from unittest.mock import patch
from ai_chat.memory import resolve_last_product_context
from ai_chat.routing.llm_fallback import clarify_request

class ShownSelectionTests(unittest.TestCase):
 def test_store_comparison_keeps_actual_displayed_rows(self):
  req=dict(dataset='orders',metric='orders_amount',analysis='compare',view='contributors',entity='store')
  row=dict(status='success',delivery_status='sent',router_request=req,result=dict(status='ok',rows=[{'product_key':'a'},{'product_key':'b'},{'product_key':'a'}]))
  with patch('ai_chat.memory.latest_dialogue_row',return_value=row):
   m=resolve_last_product_context(telegram_user_id=1,user_id=1,shop_id=1,marketplace='wb',supabase=object())
  self.assertEqual(m['shown_product_keys'],['a','b'])
 def test_resolved_selection_skips_second_llm_clarification(self):
  draft=dict(is_valid_question=True,dataset='orders',metric='orders_amount',product_keys=['a','b'])
  with patch('ai_chat.routing.llm_fallback.generate_openai_json') as llm:
   r=clarify_request('Какая у них выручка?',draft=draft,memory={'shown_product_keys':['a','b']})
  llm.assert_not_called();self.assertEqual(r['action'],'execute')
 def test_stock_reference_uses_common_llm_selection(self):
  decision=dict(action='execute',updates=[{'field':'selection','value':'shown_products'}])
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=decision):
   r=clarify_request('Покажи их остатки',draft=dict(is_valid_question=True,dataset='stocks',metric='stock_qty',entity='store'),memory={'shown_product_keys':['a','b']})
  self.assertEqual(r['product_keys'],['a','b']);self.assertEqual(r['action'],'execute')
