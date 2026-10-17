import unittest
from types import SimpleNamespace
from unittest.mock import patch,AsyncMock
from telegram_bot.clarifications import keyboard,select_request
from telegram_bot import handlers as h
CTX=dict(telegram_user_id=10,telegram_chat_id=20,user_id=1,shop_id=1,marketplace='wb',connection_id=2)
def pending():
 return {**CTX,'dataset':'stocks','metric':'stock_qty','analysis':'metric_value','entity':'store','period_days':30,'action':'clarify','is_valid_question':False,'clarification':dict(question='Какие товары?',context=dict(shown_product_keys=['a','b']),options=[dict(label='Эти товары',updates=[dict(field='selection',value='shown_products')]),dict(label='Весь магазин',updates=[dict(field='selection',value='store')])])}
class ClarificationButtons(unittest.IsolatedAsyncioTestCase):
 def test_two_buttons_reference_journal(self):
  rows=keyboard(pending(),123).inline_keyboard
  self.assertEqual(len(rows[0]),2);self.assertEqual(rows[0][0].callback_data,'clarify:123:0')
 def test_selection_keeps_period_and_never_calls_llm(self):
  with patch('ai_chat.routing.llm_fallback.generate_openai_json') as llm:
   req,label=select_request(pending(),0,CTX)
  llm.assert_not_called();self.assertEqual(req['product_keys'],['a','b']);self.assertEqual(req['period_days'],30)
  self.assertTrue(req['is_valid_question']);self.assertNotIn('clarification',req)
 def test_store_choice_and_bad_context(self):
  req,_=select_request(pending(),1,CTX);self.assertNotIn('product_keys',req)
  for change in (dict(shop_id=2),dict(telegram_user_id=11),dict(telegram_chat_id=21),dict(connection_id=3)):
   with self.assertRaises(ValueError):select_request(pending(),0,{**CTX,**change})
  with self.assertRaises(ValueError):select_request(pending(),99,CTX)
 async def test_stale_button_does_not_execute(self):
  query=SimpleNamespace(data='clarify:123:0',answer=AsyncMock())
  update=SimpleNamespace(callback_query=query,effective_user=SimpleNamespace(id=10),effective_chat=SimpleNamespace(id=20))
  with patch.object(h,'resolve_active_telegram_context',return_value=CTX),patch('ai_chat.memory.latest_dialogue_row',return_value=dict(id=124,status='success',delivery_status='sent')),patch.object(h,'handle_message',AsyncMock()) as handler:
   await h.handle_integration_callback(update,SimpleNamespace())
  handler.assert_not_called();self.assertTrue(query.answer.call_args.kwargs['show_alert'])
 async def test_button_continues_existing_pipeline(self):
  query=SimpleNamespace(data='clarify:123:0',answer=AsyncMock(),edit_message_reply_markup=AsyncMock())
  update=SimpleNamespace(callback_query=query,effective_user=SimpleNamespace(id=10),effective_chat=SimpleNamespace(id=20))
  row=dict(id=123,status='invalid_question',delivery_status='sent',router_request=pending())
  with patch.object(h,'resolve_active_telegram_context',return_value=CTX),patch('ai_chat.memory.latest_dialogue_row',return_value=row),patch.object(h,'handle_message',AsyncMock()) as handler:
   await h.handle_integration_callback(update,SimpleNamespace())
  self.assertEqual(handler.call_args.kwargs['resolved_request']['product_keys'],['a','b']);self.assertEqual(handler.call_args.kwargs['question_text'],'Выбор: Эти товары')
