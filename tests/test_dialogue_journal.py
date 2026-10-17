import unittest
from types import SimpleNamespace
from unittest.mock import patch,MagicMock,AsyncMock
from telegram_bot import handlers as h
CTX={'telegram_user_id':10,'telegram_chat_id':20,'user_id':1,'shop_id':1,'marketplace':'wb'}
class Journal(unittest.IsolatedAsyncioTestCase):
 def update(self,text):return SimpleNamespace(message=SimpleNamespace(text=text,reply_text=AsyncMock()),effective_user=SimpleNamespace(id=10),effective_chat=SimpleNamespace(id=20,type='private'))
 async def run_case(self,question,*,request=None,result=None,memory=None,previous=None,error=None,format_error=None,valid=True):
  request=request or {**CTX,'is_valid_question':valid,'metric':'orders_count','analysis':'metric_value','entity':'store','period_days':7}
  writes=[]
  with patch('telegram_bot.wb_connection.intercept',AsyncMock(return_value=False)),patch.object(h,'log_ai_question',return_value=101) as insert,patch.object(h,'resolve_active_telegram_context',return_value=CTX),patch.object(h,'resolve_last_product_context',return_value=memory or {}),patch('ai_chat.memory.latest_dialogue_row',return_value=previous),patch('ai_chat.routing.route.resolve_clarification_reply',return_value=None),patch.object(h,'route',return_value=request),patch.object(h.executor,'execute',side_effect=error,return_value=result or {'status':'ok','orders_count':11}),patch.object(h,'build_answer',side_effect=format_error,return_value='Точный ответ\nС новой строкой.'),patch.object(h,'log_ai_error') as errors,patch.object(h,'update_journal_question',side_effect=lambda id,**p: writes.append((id,p)) or True):
   u=self.update(question);await h.handle_message(u,SimpleNamespace(user_data={}))
   insert.assert_called_once();self.assertEqual(insert.call_args.kwargs['question'],question)
   self.assertEqual(u.message.reply_text.call_count,1)
   self.assertEqual(writes[-1][1]['answer_text'],u.message.reply_text.call_args.args[0]);self.assertEqual(writes[-1][1]['delivery_status'],'sent')
   return writes,errors.call_count
 async def test_exact_raw_question_and_no_memory(self):
  writes,_=await self.run_case('  Сколько продаж за неделю?  ')
  self.assertEqual(writes[0][1]['memory_used'],{})
 async def test_incomplete_is_blocked(self):
  writes,_=await self.run_case('А за месяц?',result={'status':'incomplete'})
  self.assertEqual(writes[0][1]['status'],'blocked');self.assertEqual(writes[0][1]['error_message'],'incomplete')
 async def test_invalid_and_clarification(self):
  for req in [{**CTX,'is_valid_question':False,'error_code':'unsupported_metric'},{**CTX,'is_valid_question':False,'metric':'orders_count','entity':'region','error_code':'unclear_question'}]:
   writes,_=await self.run_case('Вопрос',request=req);self.assertEqual(writes[0][1]['status'],'invalid_question')
 async def test_formatting_error_one_journal_row(self):
  for options in [{'error':RuntimeError('controlled error')},{'format_error':RuntimeError('formatter failed')}]:
   writes,n=await self.run_case('Вопрос',**options)
   self.assertEqual(writes[0][1]['status'],'error');self.assertEqual(n,1)
 async def test_memory_used_not_available_memory(self):
  memory={'last_product_key':'a','date_from':'2026-10-07','date_to':'2026-10-13'}
  writes,_=await self.run_case('Другой вопрос',memory=memory,previous={'id':100})
  self.assertEqual(writes[0][1]['memory_used'],{})
  request={**CTX,'is_valid_question':True,'entity':'region','metric':'orders_count','product_key':'a','date_from':'2026-10-07','date_to':'2026-10-13'}
  writes,_=await self.run_case('Куда заказывают?',request=request,memory=memory,previous={'id':100})
  self.assertEqual(writes[0][1]['memory_used'],{**{k:v for k,v in memory.items() if k!='last_product_key'},'product_key':'a','source_question_id':100})
 async def test_delivery_failure_and_partial_exact_prefix(self):
  for fail_after in [0,1]:
   u=self.update('Q');answer='A'*(h.TELEGRAM_MESSAGE_LIMIT+5)
   u.message.reply_text.side_effect=([RuntimeError('offline')] if not fail_after else [None,RuntimeError('offline')])
   writes=[]
   with patch.object(h,'log_ai_error'),patch.object(h,'update_journal_question',side_effect=lambda id,**p:writes.append(p) or True):
    await h.send_journal_reply(u,101,answer,request=CTX,result={},status='success')
   self.assertEqual(writes[-1]['delivery_status'],'partial' if fail_after else 'failed')
   self.assertEqual(writes[-1]['answer_text'],answer[:h.TELEGRAM_MESSAGE_LIMIT] if fail_after else None)
 async def test_missing_shop_still_journaled(self):
  writes=[]
  with patch('telegram_bot.wb_connection.intercept',AsyncMock(return_value=False)),patch.object(h,'log_ai_question',return_value=101) as insert,patch.object(h,'resolve_active_telegram_context',return_value=None),patch.object(h,'update_journal_question',side_effect=lambda id,**p:writes.append(p) or True):
   await h.handle_message(self.update('Вопрос'),SimpleNamespace(user_data={}))
  insert.assert_called_once();self.assertEqual(writes[0]['error_message'],'missing_active_shop');self.assertEqual(writes[-1]['delivery_status'],'sent')
 async def test_credential_never_journaled(self):
  with patch('telegram_bot.wb_connection.intercept',AsyncMock(return_value=True)),patch.object(h,'log_ai_question') as insert:
   await h.handle_message(self.update('credential'),SimpleNamespace(user_data={}));insert.assert_not_called()
 def test_explicit_product_is_not_memory(self):
  self.assertEqual(h.journal_memory_used('товар a',{'product_key':'a','product':{'match_type':'exact'}},{'last_product_key':'a'},{'id':100}),{})
 def test_clarification_context(self):
  pending={'id':100,'router_request':{'analysis':'best','metric':'orders_count','entity':'region','period_days':7}}
  used=h.journal_memory_used('236348866',{'product_key':'a'}, {},pending,True)
  self.assertEqual(used['kind'],'clarification');self.assertEqual(used['source_question_id'],100);self.assertNotIn('product_key',used)

 async def test_timeout_does_not_claim_definite_non_delivery(self):
  from telegram.error import TimedOut
  u=self.update('Q');u.message.reply_text.side_effect=TimedOut()
  writes=[]
  with patch.object(h,'log_ai_error'),patch.object(h,'update_journal_question',side_effect=lambda id,**p:writes.append(p) or True):
   await h.send_journal_reply(u,101,'Ответ',request=CTX,result={},status='success')
  self.assertEqual(writes[-1]['delivery_status'],'unknown');self.assertEqual(writes[-1]['answer_text'],'Ответ')

 async def test_saves_text_confirmed_by_telegram(self):
  u=self.update('Q');u.message.reply_text.return_value=SimpleNamespace(text='Текст, подтверждённый Telegram')
  writes=[]
  with patch.object(h,'update_journal_question',side_effect=lambda id,**p:writes.append(p) or True):
   await h.send_journal_reply(u,101,'Исходный текст',request=CTX,result={},status='success')
  self.assertEqual(writes[-1]['answer_text'],'Текст, подтверждённый Telegram')
