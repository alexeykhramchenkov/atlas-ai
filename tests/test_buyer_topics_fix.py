import unittest
from unittest.mock import patch
from ai_chat.routing.product import resolve_product
from ai_chat.routing.llm_fallback import resolve_buyer_questions
from ai_chat.analysis.question_topics import summarize

T={'user_id':1,'shop_id':1,'marketplace':'wb'}
class BuyerTopicFixTests(unittest.TestCase):
 def products(self):return [{'product_key':'angel','title':'Платье с крыльями ангела'},
                           {'product_key':'other','title':'Платье с бантом'}]
 def test_unique_inflected_title_word(self):
  with patch('ai_chat.routing.product.load_products',return_value=self.products()):
   self.assertEqual(resolve_product(question='о чем негатив по ангелам',supabase=None,**T)['product_key'],'angel')
   self.assertIsNone(resolve_product(question='о чем вопросы по платьям',supabase=None,**T))
 def test_ambiguous_nickname_is_not_arbitrary(self):
  products=self.products()+[{'product_key':'angel2','title':'Костюм ангела'}]
  with patch('ai_chat.routing.product.load_products',return_value=products):
   self.assertIsNone(resolve_product(question='по ангелам',supabase=None,**T))
 def test_topics_are_shared_but_membership_names_are_source_specific(self):
  with patch('ai_chat.analysis.question_topics.generate_openai_json',return_value={
    'groups':[{'topic':'Качество','question_ids':['r1','r2']}]}):
   r=summarize([{'feedback_id':'r1','text':'a'},{'feedback_id':'r2','text':'b'}],
     id_field='feedback_id',text_fields=('text',),membership_field='feedback_ids',count_field='reviews_count')
  self.assertEqual(r[0]['reviews_count'],2);self.assertEqual(r[0]['feedback_ids'],['r1','r2'])
  self.assertNotIn('question_ids',r[0])
 def test_sentiment_route_filters_and_no_implicit_product(self):
  for view,lo,hi in [('negative',1,2),('positive',4,5)]:
   parsed={'applicable':True,'mode':view,'product_query':'ангелам','product_reference':False,'start_date':None,'end_date':None}
   with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
    r=resolve_buyer_questions('о чем '+('негатив' if view=='negative' else 'позитив')+' по ангелам',memory={},request_context=T,
      resolve_explicit=lambda q:{'product_key':'angel'},resolve_reference=lambda q,m:None)
   self.assertEqual(r['dataset'],'reviews')
   self.assertNotIn('period_days',r)
   self.assertNotIn('rating_min',r)
 def test_unresolved_named_product_never_becomes_whole_store(self):
  parsed={'applicable':True,'mode':'unanswered','product_query':'неизвестный','product_reference':False,'start_date':None,'end_date':None}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   r=resolve_buyer_questions('вопросы по неизвестному',memory={},request_context=T,
      resolve_explicit=lambda q:None,resolve_reference=lambda q,m:None)
  self.assertFalse(r['is_valid_question'])
 def test_rating_without_text_does_not_invent_a_topic(self):
  with patch('ai_chat.analysis.question_topics.generate_openai_json') as llm:
   r=summarize([{'feedback_id':'r1','text':None,'pros':'','cons':None}],
      id_field='feedback_id',text_fields=('text','pros','cons'),membership_field='feedback_ids',count_field='reviews_count')
  self.assertEqual(r,[]);llm.assert_not_called()
 def test_pending_product_reply_must_resolve_a_real_product(self):
  from ai_chat.routing.llm_fallback import resume_clarification
  pending={**T,'dataset':'followups','metric':'questions_count','analysis':'metric_value','action':'clarify','is_valid_question':False,'clarification':{
    'parameter':'product_key','context':{},'question':'Какой товар?',
    'options':[{'label':'Укажу название','updates':[]},{'label':'По магазину','updates':[{'field':'selection','value':'store'}]}]}}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'action':'select','option':1}):
   r=resume_clarification('ангелам',pending=pending,request_context=T,resolve_product=lambda q:{'product_key':'angel'})
   self.assertEqual(r['product_key'],'angel');self.assertTrue(r['is_valid_question'])
   self.assertEqual(resume_clarification('подумай',pending=pending,request_context=T,resolve_product=lambda q:None),pending)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value={'action':'new_question','option':0}):
   self.assertIsNone(resume_clarification('о чем позитив по ангелам',pending=pending,request_context=T))
 def test_invalid_request_without_result_uses_message_rule(self):
  from ai_chat.answer_builder.answer import build_answer
  from ai_chat.answer_builder.templates import apply_template
  rule={'template_name':'compact_text','title_template':'{message}',
        'fields':[{'path':'request.message','label':'message','formatter':'text'}]}
  request={'is_valid_question':False,'message':'Напиши название или артикул WB.'}
  with patch('ai_chat.answer_builder.answer.resolve_answer_rule',return_value=rule):
   answer=build_answer(request=request,result=None,supabase=object(),language='ru')
  self.assertEqual(answer,request['message']);self.assertNotIn('JSON',answer)
