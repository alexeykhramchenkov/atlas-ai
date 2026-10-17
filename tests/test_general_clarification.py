import unittest
from unittest.mock import patch
from ai_chat.routing.llm_fallback import clarify_request,resume_clarification,validate_clarification_updates

class GeneralClarification(unittest.TestCase):
 def draft(self):return {'dataset':'stocks','metric':'stock_qty','analysis':'metric_value','entity':'store','user_id':1,'shop_id':2,'is_valid_question':True}
 def memory(self):return {'shown_product_keys':['a','b'],'last_dataset':'funnel'}
 def pending(self):
  decision={'action':'clarify','updates':[],'parameter':'selection','question':'Эти товары или магазин?','options':[{'label':'Эти товары','updates':[{'field':'selection','value':'shown_products'}]},{'label':'Магазин','updates':[{'field':'selection','value':'store'}]}]}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=decision):return clarify_request('anything',draft=self.draft(),memory=self.memory())
 def test_question_stored_without_execution(self):
  pending=self.pending();self.assertEqual(pending['action'],'clarify');self.assertFalse(pending['is_valid_question'])
  self.assertEqual(pending['clarification']['context']['shown_product_keys'],['a','b'])
 def test_semantic_selection_and_store(self):
  for index in (1,2):
   with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'action':'select','option':index}):
    req=resume_clarification('arbitrary reply',pending=self.pending(),request_context={'user_id':7,'shop_id':9})
   self.assertTrue(req['is_valid_question']);self.assertEqual(req['user_id'],7)
   self.assertEqual(req.get('product_keys'),['a','b'] if index==1 else None)
 def test_new_subject_cancels_pending(self):
  pending=self.pending()
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'action':'new_question','option':0}):
   self.assertIsNone(resume_clarification('new topic',pending=pending,request_context={}))
 def test_ambiguous_answer_remains_pending(self):
  pending=self.pending()
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'action':'clarify','option':0}):
   self.assertEqual(resume_clarification('yes',pending=pending,request_context={}),pending)
 def test_server_rejects_tenant_or_invented_product(self):
  for updates in ([{'field':'shop_id','value':'999'}],[{'field':'product_key','value':'invented'}]):
   with self.assertRaises(ValueError):validate_clarification_updates(updates,request=self.draft(),memory=self.memory())
 def test_api_failure_does_not_execute_guessed_scope(self):
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',side_effect=RuntimeError()):
   self.assertFalse(clarify_request('anything',draft=self.draft(),memory=self.memory())['is_valid_question'])
 def test_selection_gets_only_selected_stock_total(self):
  from ai_chat.executor import Executor
  facts={'as_of':'2026-10-16','total_quantity':19,'warehouse_quantity':19,'to_customer_quantity':0,'from_customer_quantity':0,'products':[{'product_key':'a','title':'A','total_quantity':3},{'product_key':'hidden','total_quantity':16}]}
  req={**self.draft(),'entity':'product','product_keys':['a']}
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=facts):r=Executor(object()).execute(req)
  self.assertEqual(r['value'],3);self.assertEqual([x['product_key'] for x in r['rows']],['a'])
 def test_summary_rows_are_not_a_displayed_list(self):
  from ai_chat.memory import resolve_last_product_context
  row={'status':'success','delivery_status':'sent','router_request':{'entity':'store'},'result':{'status':'ok','rows':[{'product_key':'not_shown'}]}}
  with patch('ai_chat.memory.latest_dialogue_row',return_value=row):
   m=resolve_last_product_context(telegram_user_id=1,user_id=1,shop_id=1,marketplace='wb',supabase=object())
  self.assertEqual(m['shown_product_keys'],[])
 def test_stock_store_list_becomes_displayed_memory(self):
  from ai_chat.memory import resolve_last_product_context
  row={'status':'success','delivery_status':'sent','router_request':{'entity':'store','dataset':'stocks','metric':'stock_qty'},'result':{'status':'ok','rows':[{'product_key':'a'},{'product_key':'b'}]}}
  with patch('ai_chat.memory.latest_dialogue_row',return_value=row):
   m=resolve_last_product_context(telegram_user_id=1,user_id=1,shop_id=1,marketplace='wb',supabase=object())
  self.assertEqual(m['shown_product_keys'],['a','b'])
