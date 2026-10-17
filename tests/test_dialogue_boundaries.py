import unittest,json
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from pathlib import Path
from ai_chat.memory import resolve_last_product_context
from ai_chat.routing.route import route,resolve_product_from_memory,resolve_clarification_reply
from ai_chat.answer_builder.templates import apply_template
CTX={'telegram_user_id':10,'telegram_chat_id':20,'user_id':1,'shop_id':1,'marketplace':'wb'}
class Boundaries(unittest.TestCase):
 def setUp(self):
  rules=[{'entity':'region','aliases_ru':['регион','регионы','куда чаще всего заказывают'],'aliases_en':[],'priority':20,'is_active':True}]
  fixture=patch('ai_chat.routing.entity.load_entity_rules',return_value=rules)
  fixture.start();self.addCleanup(fixture.stop)

 def db(self,row):
  q=MagicMock()
  for name in ['table','select','eq','order','limit']:getattr(q,name).return_value=q
  q.execute.return_value=SimpleNamespace(data=[row]);return q
 def row(self,**changes):
  row={'router_request':{**CTX,'metric':'orders_count','analysis':'best','entity':'product','answer_scope':'single','limit':1},'result':{'status':'ok','date_from':'2026-10-07','date_to':'2026-10-13','rows':[{'product_key':'a'}]},'status':'success','created_at':datetime.now(timezone.utc).isoformat()};row.update(changes);return row
 def memory(self,row):return resolve_last_product_context(**CTX,supabase=self.db(row))
 def pending(self):return self.row(router_request=route('Куда чаще всего заказывают товар?',memory={},request_context=CTX),result=None,status='invalid_question')
 def test_fresh_and_expired(self):
  self.assertEqual(self.memory(self.row())['last_product_key'],'a')
  self.assertEqual(self.memory(self.row(created_at=(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat())),{})
 def test_failure_and_tenant_barriers(self):
  for status in ['invalid_question','error','blocked']:self.assertEqual(self.memory(self.row(status=status)),{})
  for change in [{'shop_id':2},{'telegram_chat_id':99}]:self.assertEqual(self.memory(self.row(router_request={**CTX,**change})),{})
 def test_incomplete_barrier(self):self.assertEqual(self.memory(self.row(result={'status':'incomplete'})),{})
 @patch('ai_chat.routing.route.resolve_product', return_value=None)
 def test_new_topic_and_explicit_reference(self, _product):
  self.assertNotIn('product_key',route('Какие товары скоро закончатся?',memory={'last_product_key':'a'},request_context=CTX))
  for question in ['А на каком складе больше?','В каких регионах заказывают?']:self.assertIsNone(resolve_product_from_memory(question=question,memory={'last_product_key':'a'}))
  self.assertEqual(resolve_product_from_memory(question='Где его заказывают?',memory={'last_product_key':'a'})['product_key'],'a')
 def test_store_drops_product(self):
  m=self.memory(self.row(router_request={**CTX,'metric':'orders_count','entity':'store'},result={'status':'ok','date_from':'2026-10-07','date_to':'2026-10-13','rows':[]}));self.assertIsNone(m['last_product_key'])
 def test_period_override(self):
  m={'date_from':'2026-10-07','date_to':'2026-10-13','last_metric':'orders_count','last_analysis':'best','last_scope':'product','last_product_key':'a'}
  for question in ['Какой товар лучший за месяц?','А за месяц?']:
   x=route(question,memory=m,request_context=CTX);self.assertEqual(x['period_days'],30);self.assertNotIn('date_from',x)
 def test_no_product_clarifies(self):self.assertFalse(route('Куда чаще всего заказывают товар?',memory={},request_context=CTX)['is_valid_question'])
 def test_unknown_explicit_no_fallback(self):
  with patch('ai_chat.routing.route.resolve_product',return_value=None):x=route('Куда чаще всего заказывают товар 999999999?',memory={'last_product_key':'a'},request_context=CTX)
  self.assertFalse(x['is_valid_question']);self.assertIsNone(x['product_key'])
 def test_clarification_reply(self):
  with patch('ai_chat.routing.route.resolve_product',return_value={'product_key':'b','marketplace_product_id':'236348866','title':'Платье'}):x=resolve_clarification_reply(question='236348866',request_context=CTX,supabase=self.db(self.pending()))
  self.assertTrue(x['is_valid_question']);self.assertEqual(x['product_key'],'b')
 def test_new_question_cancels_pending(self):
  with patch('ai_chat.routing.route.resolve_product') as resolve:
   self.assertIsNone(resolve_clarification_reply(question='Сколько продаж за неделю?',request_context=CTX,supabase=self.db(self.pending())));resolve.assert_not_called()
 def test_expired_pending(self):
  row=self.pending();row['created_at']=(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat();self.assertIsNone(resolve_clarification_reply(question='236348866',request_context=CTX,supabase=self.db(row)))
 def test_status_before_empty(self):
  rule=json.loads((Path(__file__).resolve().parents[1]/'setup/friendly-answer-release/applied.json').read_text())[2]
  for status,fragment in [('no_product','Сначала спроси'),('incomplete','не хватает данных')]:self.assertIn(fragment,apply_template(rule=rule,fields=[],language='ru',data={'status':status,'rows':[]},request={}))

 def test_sizes_need_explicit_reference(self):
  from ai_chat.routing.route import resolve_product_size_sales_follow_up
  m={'last_product_key':'a'}
  self.assertIsNone(resolve_product_size_sales_follow_up(question='Какие размеры лучше продаются?',memory=m,request_context=CTX))
  self.assertEqual(resolve_product_size_sales_follow_up(question='Какие его размеры лучше продаются?',memory=m,request_context=CTX)['product_key'],'a')
