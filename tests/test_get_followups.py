import unittest
from unittest.mock import patch
from test_get_stocks_contract import StockDB
from ai_chat.internal_tools.get_followups import get_followups
from ai_chat.analysis.question_topics import summarize
from ai_chat.routing.llm_fallback import resolve_buyer_questions

T={'user_id':1,'shop_id':1,'marketplace':'wb'}
class FollowupsTests(unittest.TestCase):
    def db(self):
        q={**T,'id':1,'question_id':'q1','product_key':'a','question_text':'Снимаются?',
           'question_created_at':'2026-09-15T12:00:00+03:00','is_answered':False,
           'answer_text':None,'answer_created_at':None}
        return StockDB({'normalized_questions':[q,{**q,'id':2,'question_id':'q2','is_answered':True},
            {**q,'id':3,'user_id':2},{**q,'id':4,'shop_id':2}],
            'normalized_products':[{**T,'id':1,'product_key':'a','title':'A'}]})
    def test_facts_tenant_and_filters(self):
        db=self.db();r=get_followups(**T,is_answered=False,supabase=db)
        self.assertEqual(r['questions_count'],1)
        self.assertEqual(r['questions'][0]['title'],'A')
        self.assertNotIn('raw_payload',r['questions'][0])
        for q in db.queries:
            for k,v in T.items():self.assertIn((k,'eq',v),q.filters)
        self.assertEqual(get_followups(**T,supabase=db)['questions_count'],2)
        self.assertEqual(get_followups(**T,product_key='b',supabase=db)['questions_count'],0)
    def test_optional_period_and_invalid_filters(self):
        db=self.db()
        self.assertEqual(get_followups(**T,start_date='2026-10-01',end_date='2026-10-02',supabase=db)['questions_count'],0)
        for kw in ({'start_date':'2026-10-01'},{'is_answered':'false'}):
            with self.assertRaises(ValueError):get_followups(**T,supabase=db,**kw)
    def test_dedup_and_conflicts(self):
        db=self.db();db.data['normalized_questions'].append(dict(db.data['normalized_questions'][0]))
        self.assertEqual(get_followups(**T,supabase=db)['questions_count'],2)
        db.data['normalized_questions'][-1]['question_text']='Other'
        with self.assertRaises(ValueError):get_followups(**T,supabase=db)
    def test_count_is_computed_and_ids_checked(self):
        rows=[{'question_id':'q1','question_text':'A'},{'question_id':'q2','question_text':'B'}]
        with patch('ai_chat.analysis.question_topics.generate_openai_json',return_value={'groups':[{'topic':'Крылья','question_ids':['q1','q2']}] } ):
            r=summarize(rows);self.assertEqual(r[0]['questions_count'],2)
        for ids in (['invented'],['q1'],['q1','q1','q2']):
            with patch('ai_chat.analysis.question_topics.generate_openai_json',return_value={'groups':[{'topic':'A','question_ids':ids}]}):
                with self.assertRaises(ValueError):summarize(rows)
    def test_router_no_default_period_and_product_memory(self):
        parsed={'applicable':True,'mode':'topics','product_reference':True,'start_date':None,'end_date':None}
        with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
            r=resolve_buyer_questions('О чём спрашивают по этому товару?',memory={},request_context=T,
                resolve_explicit=lambda q:None,resolve_reference=lambda q,m:{'product_key':'a','match_type':'memory'})
        self.assertEqual(r['product_key'],'a');self.assertNotIn('period_days',r)
        self.assertIsNone(r['is_answered'])
    def test_missing_catalog_title_uses_source_name(self):
        db=self.db();db.data['normalized_products']=[]
        db.data['normalized_questions'][0]['product_name']='Исходное название'
        r=get_followups(**T,is_answered=False,supabase=db)
        self.assertEqual(r['questions'][0]['title'],'Исходное название')
        self.assertNotIn('product_name',r['questions'][0])
    def test_batch_merge_preserves_source_memberships(self):
        rows=[{'question_id':str(i),'question_text':'Размер?'} for i in range(61)]
        answers=[[{'topic':'Размер','question_ids':[str(i) for i in range(60)]}],
                 [{'topic':'Размеры','question_ids':['60']}],
                 [{'topic':'Размеры','question_ids':['0','1']}]]
        with patch('ai_chat.analysis.question_topics._partition',side_effect=answers):
            r=summarize(rows)
        self.assertEqual(r[0]['questions_count'],61)
        self.assertEqual(len(set(r[0]['question_ids'])),61)
    def test_date_formatter_uses_moscow(self):
        from ai_chat.answer_builder.formatters import format_value
        self.assertEqual(format_value(value='2026-09-15T23:00:00+00:00',formatter='date',language='ru'),'16.09.2026')
