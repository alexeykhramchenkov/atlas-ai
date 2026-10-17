import unittest
from unittest.mock import patch
from ai_chat.memory import resolve_last_product_context
from ai_chat.routing.llm_fallback import clarify_request,validate_clarification_updates
from telegram_bot.handlers import journal_memory_used

class EmptySelectionMemoryTests(unittest.TestCase):
 def memory(self):return dict(shown_product_keys=[],product_keys=['a','b'],last_dataset='stocks',last_metric='days_left')
 def test_empty_result_retains_existing_input_selection(self):
  row=dict(status='success',delivery_status='sent',router_request=dict(entity='product',dataset='stocks',metric='days_left',product_keys=['a','b']),result=dict(status='ok',rows=[]))
  with patch('ai_chat.memory.latest_dialogue_row',return_value=row):
   memory=resolve_last_product_context(telegram_user_id=1,user_id=1,shop_id=1,marketplace='wb',supabase=object())
  self.assertEqual(memory['shown_product_keys'],[]);self.assertEqual(memory['product_keys'],['a','b'])
 def test_semantic_reference_can_choose_original_selection(self):
  decision=dict(action='execute',updates=[dict(field='selection',value='shown_products')])
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=decision) as llm:
   r=clarify_request('А какие у них остатки?',draft=dict(is_valid_question=True,dataset='stocks',metric='stock_qty',analysis='metric_value'),memory=self.memory())
  llm.assert_called_once();self.assertEqual(r['product_keys'],['a','b'])
 def test_store_clears_selection_and_displayed_result_takes_precedence(self):
  m=self.memory()
  r=validate_clarification_updates([dict(field='selection',value='store')],request=dict(product_keys=['a','b'],dataset='stocks',metric='stock_qty'),memory=m)
  self.assertNotIn('product_keys',r)
  r=validate_clarification_updates([dict(field='selection',value='shown_products')],request=dict(dataset='stocks',metric='stock_qty'),memory={**m,'shown_product_keys':['b']})
  self.assertEqual(r['product_keys'],['b'])
 def test_failure_never_guesses_store(self):
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',side_effect=TimeoutError):
   r=clarify_request('Их остатки',draft=dict(is_valid_question=True,dataset='stocks',metric='stock_qty'),memory=self.memory())
  self.assertFalse(r['is_valid_question'])
 def test_journal_labels_input_selection_not_displayed_rows(self):
  used=journal_memory_used('их остатки',{'product_keys':['a','b']},self.memory(),{'id':10})
  self.assertEqual(used,{'product_keys':['a','b'],'source_question_id':10})
