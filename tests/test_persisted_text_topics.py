import unittest
from unittest.mock import patch
from test_get_stocks_contract import StockDB
from ai_chat.internal_tools.get_reviews import get_reviews
from ai_chat.internal_tools.get_followups import get_followups
from db.text_analysis_store import attach_analyses
from core.text_analysis import text_hash,ANALYSIS_VERSION
from ai_chat.analysis.persisted_topics import summarize
from ai_chat.analysis.text_annotation import annotate

T={'user_id':1,'shop_id':1,'marketplace':'wb'}
class PersistedTopicsTests(unittest.TestCase):
 def db(self):
  review={**T,'id':1,'feedback_id':'r1','product_key':'p','rating':5,'text':'Ткань хорошая, размер мал.',
          'pros':'','cons':'','created_at':'2024-01-01T12:00:00+00:00'}
  q={**T,'id':1,'question_id':'q1','product_key':'p','question_text':'Какой размер?',
     'question_created_at':'2024-01-01T12:00:00+00:00','is_answered':False}
  a={**T,'analysis_id':'a1','source_type':'review','source_id':'r1','product_key':'p',
     'text_hash':text_hash('review',review),'analysis_version':ANALYSIS_VERSION,'status':'ready'}
  return StockDB({'normalized_feedbacks':[review,{**review,'id':2,'user_id':2}],
   'normalized_questions':[q], 'normalized_products':[{**T,'id':1,'product_key':'p','title':'P'}],
   'text_analyses':[a,{**a,'user_id':2,'analysis_id':'wrong'}],
   'text_topics':[{**T,'topic_id':'fabric','title':'Ткань','category':'','merged_into':None}],
   'text_analysis_topics':[{**T,'analysis_id':'a1','topic_id':'fabric','summary':'Хорошая ткань','sentiment':'positive'}]})
 def test_reviews_all_dates_by_default_and_opt_in_shape(self):
  db=self.db();plain=get_reviews(**T,supabase=db)
  self.assertIsNone(plain['start_date']);self.assertEqual(plain['reviews_count'],1)
  self.assertNotIn('topic_analysis',plain['reviews'][0])
  enriched=get_reviews(**T,supabase=db,include_topics=True)
  self.assertEqual(enriched['reviews'][0]['topic_analysis']['topics'][0]['title'],'Ткань')
  for query in db.queries:
   for k,v in T.items():self.assertIn((k,'eq',v),query.filters)
 def test_old_annotation_is_pending_after_text_change(self):
  db=self.db();db.data['normalized_feedbacks'][0]['text']='Изменённый отзыв'
  r=get_reviews(**T,supabase=db,include_topics=True)['reviews'][0]['topic_analysis']
  self.assertEqual(r['status'],'pending');self.assertEqual(r['topics'],[])
 def test_followups_can_read_pending_without_shape_change_by_default(self):
  db=self.db();plain=get_followups(**T,supabase=db)
  self.assertNotIn('topic_analysis',plain['questions'][0])
  r=get_followups(**T,supabase=db,include_topics=True)
  self.assertEqual(r['questions'][0]['topic_analysis']['status'],'pending')
 def test_aspects_can_have_both_sentiments_and_count_source_once(self):
  row={'feedback_id':'r1','topic_analysis':{'status':'ready','topics':[
    {'topic_id':'a','title':'Ткань','summary':'Мягкая','sentiment':'positive'},
    {'topic_id':'b','title':'Размер','summary':'Мал','sentiment':'negative'},
    {'topic_id':'b','title':'Размер','summary':'Ещё жалоба','sentiment':'negative'}]}}
  r=summarize([row],source_type='review',sentiment='negative')
  self.assertEqual(r['matched_sources_count'],1);self.assertEqual(r['rows'][0]['reviews_count'],1)
  self.assertEqual(summarize([row],source_type='review',sentiment='positive')['rows'][0]['topic'],'Ткань')
 def test_pending_is_never_zero_negative(self):
  r=summarize([{'feedback_id':'r1','topic_analysis':{'status':'pending','topics':[]}}],source_type='review',sentiment='negative')
  self.assertEqual(r['status'],'incomplete')
 def test_merged_topic_resolves_without_reanalysis(self):
  db=self.db();db.data['text_topics'][0]['merged_into']='root'
  db.data['text_topics'].append({**T,'topic_id':'root','title':'Материал','category':'','merged_into':None})
  r=get_reviews(**T,supabase=db,include_topics=True)['reviews'][0]
  self.assertEqual(r['topic_analysis']['topics'][0]['topic_id'],'root')
 def test_annotator_validates_ids_and_reuses_names(self):
  items=[{'source_type':'review','text':'Ткань хорошая','category':'Платья'}]
  topics=[{'topic_id':'a','title':'Ткань','category':'','merged_into':None}]
  payload={'annotations':[{'item_id':'0','topics':[{'topic_name':' ТКАНЬ ',
    'category':'','summary':'Хорошая ткань','sentiment':'positive'}]}]}
  with patch('ai_chat.analysis.text_annotation.generate_openai_json',return_value=payload):
   self.assertEqual(annotate(items,topics)[0][0]['topic_id'],'a')
  payload['annotations'][0]['item_id']='999'
  with patch('ai_chat.analysis.text_annotation.generate_openai_json',return_value=payload):
   with self.assertRaises(ValueError):annotate(items,topics)
 def test_same_source_id_other_tenant_is_not_used(self):
  db=self.db();db.data['text_analyses']=db.data['text_analyses'][1:]
  r=get_reviews(**T,supabase=db,include_topics=True)['reviews'][0]
  self.assertEqual(r['topic_analysis']['status'],'pending')
 def test_background_skips_unchanged_and_retries_only_changed(self):
  from metrics.builders import text_topics as runner
  source={'source_type':'question','source_id':'q1','product_key':'p','question_text':'Размер?',
          'text_hash':'same','source_created_at':'2026-01-01T00:00:00+00:00'}
  old={**source,'status':'ready'}
  with patch.object(runner,'load_sources',return_value=[source]),patch.object(runner,'load_analyses',return_value=[old]),patch.object(runner,'annotate') as llm,patch.object(runner,'save_batch') as save:
   result=runner.run_metric_job({**T},None,{})
   self.assertEqual(result['rows_upserted'],0);llm.assert_not_called();save.assert_not_called()
  with patch.object(runner,'load_sources',return_value=[{**source,'text_hash':'changed'}]),patch.object(runner,'load_analyses',return_value=[old]),patch.object(runner,'load_topics',return_value=[]),patch.object(runner,'annotate',return_value=[[]]) as llm,patch.object(runner,'save_batch',return_value=1):
   result=runner.run_metric_job({**T},None,{})
   self.assertEqual(result['rows_upserted'],1);llm.assert_called_once()
 def test_background_no_text_does_not_call_llm(self):
  from metrics.builders import text_topics as runner
  source={'source_type':'review','source_id':'r1','product_key':'p','text':'','pros':None,'cons':None,
          'text_hash':'empty','source_created_at':None}
  with patch.object(runner,'load_sources',return_value=[source]),patch.object(runner,'load_analyses',return_value=[]),patch.object(runner,'annotate') as llm,patch.object(runner,'save_batch',return_value=1):
   result=runner.run_metric_job({**T},None,{})
   self.assertEqual(result['rows_upserted'],1);llm.assert_not_called()
 def test_annotation_unknown_topic_never_persists(self):
  items=[{'source_type':'question','question_text':'Размер?','category':''}]
  payload={'annotations':[{'item_id':'0','topics':[{'topic_name':'',
   'category':'','summary':'Размер','sentiment':'neutral'}]}]}
  with patch('ai_chat.analysis.text_annotation.generate_openai_json',return_value=payload):
   with self.assertRaises(ValueError):annotate(items,[])
 def test_executor_request_path_has_no_llm_and_keeps_aspect_sentiment(self):
  from ai_chat.executor import Executor
  db=self.db()
  # Five-star review has a negative aspect too: stars do not hide the complaint.
  db.data['text_analysis_topics'].append({**T,'analysis_id':'a1','topic_id':'fabric','summary':'Просвечивает','sentiment':'negative'})
  with patch('ai_chat.llm_client.generate_openai_json',side_effect=AssertionError('No LLM allowed')):
   r=Executor(db).execute({**T,'dataset':'reviews','metric':'reviews_count','analysis':'metric_value',
      'entity':'product','view':'negative','product_key':'p'})
  self.assertEqual(r['reviews_count'],1);self.assertEqual(r['rows'][0]['feedback_ids'],['r1'])
  self.assertIsNone(r['date_from'])
 def test_repeated_fragments_in_same_topic_are_one_aspect(self):
  items=[{'source_type':'review','text':'Ткань мягкая и приятная','category':''}]
  topics=[{'topic_id':'a','title':'Ткань','category':'','merged_into':None}]
  aspects=[{'topic_name':'Ткань','category':'','summary':summary,'sentiment':'positive'} for summary in ['Мягкая','Приятная']]
  with patch('ai_chat.analysis.text_annotation.generate_openai_json',return_value={'annotations':[{'item_id':'0','topics':aspects}]}):
   r=annotate(items,topics)
  self.assertEqual(len(r[0]),1);self.assertEqual(r[0][0]['summary'],'Мягкая; Приятная')
 def test_niche_topic_is_not_available_to_another_category(self):
  items=[{'source_type':'question','question_text':'Есть мой размер?','category':'Платья'}]
  topics=[{'topic_id':'jacket','title':'Наличие куртки','category':'Куртки','merged_into':None}]
  payload={'annotations':[{'item_id':'0','topics':[{'topic_name':'Наличие куртки',
   'category':'Куртки','summary':'Размер','sentiment':'neutral'}]}]}
  with patch('ai_chat.analysis.text_annotation.generate_openai_json',return_value=payload) as llm:
   with self.assertRaises(ValueError):annotate(items,topics)
   self.assertNotIn('Наличие куртки',llm.call_args.kwargs['prompt'].split('Тексты:')[0])
 def test_more_than_200_ids_use_independent_queries(self):
  from db.text_analysis_store import load_analyses
  rows=[{**T,'analysis_id':f'a{i:04}','source_type':'review','source_id':f'r{i}',
          'analysis_version':ANALYSIS_VERSION,'status':'ready'} for i in range(2401)]
  db=StockDB({'text_analyses':rows})
  loaded=load_analyses(db,1,1,'wb','review',[r['source_id'] for r in rows])
  self.assertEqual(len(loaded),2401)
  for query in db.queries:
   self.assertEqual(sum(k=='source_id' and op=='in' for k,op,v in query.filters),1)

class TopicNameIdentity(unittest.TestCase):
 def test_name_resolves_to_matching_id_not_dictionary_position(self):
  items=[{'source_type':'review','text':'Просвечивает','category':'Платья'}]
  dictionary=[{'topic_id':'camera','title':'Эффективность муляжа','category':'','merged_into':None},
              {'topic_id':'dress','title':'Прозрачность ткани','category':'','merged_into':None}]
  payload={'annotations':[{'item_id':'0','topics':[{'topic_name':'Прозрачность ткани','category':'','summary':'Просвечивает','sentiment':'negative'}]}]}
  with patch('ai_chat.analysis.text_annotation.generate_openai_json',return_value=payload) as llm:
   result=annotate(items,dictionary)
  self.assertEqual(result[0][0]['topic_id'],'dress')
  self.assertNotIn('topic_id',llm.call_args.kwargs['schema']['properties']['annotations']['items']['properties']['topics']['items']['properties'])
 def test_new_name_stays_new_instead_of_using_unrelated_topic(self):
  items=[{'source_type':'question','question_text':'Крылья съёмные?','category':'Платья'}]
  dictionary=[{'topic_id':'camera','title':'Эффективность муляжа','category':'','merged_into':None}]
  payload={'annotations':[{'item_id':'0','topics':[{'topic_name':'Крепление крыльев','category':'Платья','summary':'Снимаются ли крылья','sentiment':'neutral'}]}]}
  with patch('ai_chat.analysis.text_annotation.generate_openai_json',return_value=payload):
   result=annotate(items,dictionary)
  self.assertIsNone(result[0][0]['topic_id']);self.assertEqual(result[0][0]['new_topic'],'Крепление крыльев')

class SameNamedTopics(unittest.TestCase):
 def test_shared_and_category_topic_names_count_distinct_sources_once(self):
  def row(source,ids):
   return {'feedback_id':source,'topic_analysis':{'status':'ready','topics':[
    {'topic_id':i,'title':' Размер/посадка ' if i=='generic' else 'размер/посадка','summary':'Мало','sentiment':'negative'} for i in ids]}}
  r=summarize([row('r1',['generic','category']),row('r2',['category'])],source_type='review',sentiment='negative')
  self.assertEqual(len(r['rows']),1);self.assertEqual(r['rows'][0]['reviews_count'],2)
  self.assertEqual(r['rows'][0]['feedback_ids'],['r1','r2'])
