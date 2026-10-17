import unittest
from ai_chat.analysis.analysis_type.compare import compare_rows
from ai_chat.routing.route import route

class FunnelContributors(unittest.TestCase):
 def test_reconciliation_new_lost_and_unchanged(self):
  result=compare_rows(current=[{'product_key':'a','order_count':5},{'product_key':'b','order_count':2},{'product_key':'new','order_count':2}],previous=[{'product_key':'a','order_count':9},{'product_key':'b','order_count':2},{'product_key':'old','order_count':1}],metric='order_count')
  self.assertEqual(result['loss_total'],5)
  self.assertEqual(result['gain_total'],2)
  self.assertEqual(result['losses'][0]['product_key'],'old')
  self.assertEqual(result['gain_total']-result['loss_total'],9-12)
 def test_no_changes_and_empty(self):
  for rows in ([],[{'product_key':'a','order_count':0}]):
   result=compare_rows(current=rows,previous=rows,metric='order_count')
   self.assertEqual(result,{'losses':[],'gains':[],'loss_total':0,'gain_total':0})
 def test_displayed_percent_sort_and_zero_baseline_last(self):
  before=[{'product_key':k,'order_count':v} for k,v in [('a',100),('b',2),('c',100),('d',2)]]
  now=[{'product_key':k,'order_count':v} for k,v in [('a',90),('b',0),('c',110),('d',4),('e',3)]]
  result=compare_rows(current=now,previous=before,metric='order_count')
  self.assertEqual([r['change_pct'] for r in result['losses']],[-100,-10])
  self.assertEqual([r['change_pct'] for r in result['gains']],[100,10,None])
  self.assertEqual((result['loss_total'],result['gain_total']),(12,15))
 def test_followup_keeps_funnel_period_and_drops_product(self):
  memory={'last_dataset':'funnel','last_analysis':'compare','last_scope':'store','date_from':'2026-10-09','date_to':'2026-10-15','last_product_key':'stale'}
  from unittest.mock import patch
  parsed={'applicable':True,'metric':'order_count','direction':'negative','period_days':None,'start_date':None,'end_date':None}
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=parsed):
   req=route('Покажи какие товары просели по заказам',memory=memory,request_context={'user_id':7,'shop_id':9,'marketplace':'wb'})
  self.assertEqual(req['dataset'],'funnel');self.assertEqual(req['metric'],'order_count')
  self.assertEqual(req['date_from'],memory['date_from']);self.assertNotIn('product_key',req)
 def test_memory_audit(self):
  from telegram_bot.handlers import journal_memory_used
  req={'dataset':'funnel','view':'contributors','context_dates_inherited':True,'date_from':'2026-10-09','date_to':'2026-10-15'}
  used=journal_memory_used('followup',req,{'last_dataset':'funnel','last_analysis':'compare','last_scope':'store'},{'id':42})
  self.assertEqual(used['source_question_id'],42);self.assertEqual(used['dataset'],'funnel')
