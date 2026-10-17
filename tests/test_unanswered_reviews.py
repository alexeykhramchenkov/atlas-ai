import unittest
from unittest.mock import patch
from ai_chat.routing.llm_fallback import resolve_buyer_questions
from ai_chat.executor import Executor

class UnansweredReviewTests(unittest.TestCase):
 def test_new_reviews_have_no_implicit_date_or_old_product(self):
  parsed=dict(applicable=True,mode='reviews_unanswered',product_query=None,product_reference=False,start_date=None,end_date=None)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   r=resolve_buyer_questions('Есть новые отзывы?',memory={'product_key':'old'},request_context={'user_id':1,'shop_id':1},resolve_explicit=lambda q:None,resolve_reference=lambda q,m: (_ for _ in ()).throw(AssertionError('Sticky product')))
  self.assertEqual(r['dataset'],'reviews');self.assertEqual(r['view'],'unanswered')
  self.assertNotIn('period_days',r);self.assertNotIn('product_key',r)
 def test_only_explicit_false_is_unanswered(self):
  facts={'start_date':None,'end_date':None,'reviews_count':3,'reviews':[{'feedback_id':'a','has_answer':False,'text':'Текст','created_at':'2026-10-15T12:00:00Z'},{'feedback_id':'b','has_answer':True,'text':'Текст','created_at':'2026-10-15T12:00:00Z'},{'feedback_id':'c','has_answer':None,'text':'Текст','created_at':'2026-10-15T12:00:00Z'}]}
  with patch('ai_chat.internal_tools.get_reviews.get_reviews',return_value=facts) as getter:
   r=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,dataset='reviews',analysis='metric_value',metric='reviews_count',view='unanswered',answer_scope='all'))
  self.assertEqual([x['feedback_id'] for x in r['rows']],['a']);self.assertEqual(r['reviews_count'],1)
  self.assertIsNone(getter.call_args.kwargs['period_days'])

 def test_empty_texts_hidden_pros_kept_and_newest_first(self):
  reviews=[dict(feedback_id='old',has_answer=False,text=' Старый ',created_at='2026-10-12T00:00:00Z'),dict(feedback_id='empty',has_answer=False,text='  ',pros=None,cons='',created_at='2026-10-16T00:00:00Z'),dict(feedback_id='new',has_answer=False,text=None,pros=' Хорошо ',created_at='2026-10-15T00:00:00Z')]
  with patch('ai_chat.internal_tools.get_reviews.get_reviews',return_value=dict(start_date=None,end_date=None,reviews_count=3,reviews=reviews)):
   r=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,dataset='reviews',analysis='metric_value',metric='reviews_count',view='unanswered',answer_scope='all'))
  self.assertEqual([x['feedback_id'] for x in r['rows']],['new','old'])
  self.assertEqual(r['reviews_count'],2);self.assertEqual(r['rows'][0]['text'],'Хорошо')

 def test_catalog_filter_keeps_archive_available_explicitly(self):
  reviews=[dict(feedback_id='current',product_key='dress',has_answer=False,text='Текст',created_at='2026-10-16T00:00:00Z'),dict(feedback_id='archive',product_key='camera',has_answer=False,text='Архив',created_at='2022-10-16T00:00:00Z')]
  facts=dict(start_date=None,end_date=None,reviews_count=2,reviews=reviews)
  req=dict(user_id=1,shop_id=1,dataset='reviews',analysis='metric_value',metric='reviews_count',view='unanswered')
  for updates,expected in [({},['current']),({'answer_scope':'all'},['current','archive']),({'product_key':'camera'},['current','archive'])]:
   with patch('ai_chat.internal_tools.get_reviews.get_reviews',return_value=facts),patch('ai_chat.internal_tools.get_products.get_products',return_value={'products':[{'product_key':'dress'}]}) as catalog:
    r=Executor(supabase=object()).execute({**req,**updates})
    self.assertEqual([x['feedback_id'] for x in r['rows']],expected)
    self.assertEqual(facts['reviews_count'],2)
    if updates:catalog.assert_not_called()

 def test_explicit_archive_scope_passes_through_semantic_router(self):
  parsed=dict(applicable=True,mode='reviews_unanswered',product_query=None,product_reference=False,answer_scope='all',start_date=None,end_date=None)
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   r=resolve_buyer_questions('Покажи отзывы включая старые товары',memory={},request_context={'user_id':1,'shop_id':1},resolve_explicit=lambda q:None,resolve_reference=lambda q,m:None)
  self.assertEqual(r['answer_scope'],'all')
