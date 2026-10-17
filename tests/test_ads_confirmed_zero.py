import unittest
from copy import deepcopy
from test_get_stocks_contract import StockDB
from ai_chat.internal_tools.get_ads import get_ads,FIELDS
from ai_chat.internal_tools._common import DataUnavailableError
T={'user_id':1,'shop_id':1,'marketplace':'wb'}
class ConfirmedEmptyAds(unittest.TestCase):
 def db(self):
  def stage(**kw):return {**T,'id':1,'status':'success','finished_at':'2026-10-08T12:05:00+00:00',**kw}
  return StockDB({'metrics_ads_daily':[],
   'system_sync_jobs':[stage(source_name='ads_stats',date_from='2026-10-06',date_to='2026-10-07',finished_at='2026-10-08T12:04:00+00:00')],
   'system_normalization_jobs':[stage(source_name='ads_stats')],
   'system_snapshot_jobs':[stage(snapshot_name='ads_daily',finished_at='2026-10-08T12:06:00+00:00')],
   'system_metric_jobs':[stage(metric_name='ads_daily_metrics',finished_at='2026-10-08T12:07:00+00:00')],
   'raw_wb_ads_stats':[{**T,'id':i,'date_from':day,'date_to':day,'updated_at':'2026-10-08T12:03:00+00:00',
     'payload':{'data':[],'empty_reason':'empty_api_payload'}} for i,day in enumerate(['2026-10-06','2026-10-07'],1)]})
 def get(self,db,**kw):return get_ads(user_id=1,shop_id=1,start_date='2026-10-06',end_date='2026-10-07',supabase=db,**kw)
 def test_proven_empty_returns_existing_contract_zero(self):
  db=self.db();r=self.get(db)
  self.assertEqual(r,{'start_date':'2026-10-06','end_date':'2026-10-07','level':'campaign','currency':'RUB',**{f:0 for f in FIELDS},'campaigns':[]})
  for q in db.queries:
   for k,v in T.items():self.assertIn((k,'eq',v),q.filters)
 def test_missing_day_not_zero(self):
  db=self.db();db.data['raw_wb_ads_stats'].pop()
  with self.assertRaises(DataUnavailableError):self.get(db)
 def test_success_without_explicit_empty_payload_not_zero(self):
  for payload in ({},None,{'data':[]},{'data':[{'spend':100}],'empty_reason':'empty_api_payload'}):
   db=self.db();db.data['raw_wb_ads_stats'][0]['payload']=payload
   with self.assertRaises(DataUnavailableError):self.get(db)
 def test_failed_sync_not_zero(self):
  db=self.db();db.data['system_sync_jobs'][0]['status']='failed'
  with self.assertRaises(DataUnavailableError):self.get(db)
 def test_recent_pending_sync_not_zero(self):
  db=self.db();db.data['system_sync_jobs'].append({**db.data['system_sync_jobs'][0],'id':2,'status':'pending','finished_at':None})
  with self.assertRaises(DataUnavailableError):self.get(db)
 def test_failed_or_unfinished_downstream_not_zero(self):
  for table in ['system_normalization_jobs','system_snapshot_jobs','system_metric_jobs']:
   for status in ['failed','running','pending']:
    db=self.db();db.data[table][0]['status']=status
    with self.assertRaises(DataUnavailableError):self.get(db)
 def test_successful_sync_after_pipeline_not_zero(self):
  db=self.db();db.data['system_sync_jobs'][0]['finished_at']='2026-10-08T12:08:00+00:00'
  with self.assertRaises(DataUnavailableError):self.get(db)
 def test_raw_changed_after_sync_not_zero(self):
  db=self.db();db.data['raw_wb_ads_stats'][0]['updated_at']='2026-10-08T12:08:00+00:00'
  with self.assertRaises(DataUnavailableError):self.get(db)
 def test_foreign_shop_or_user_proof_not_used(self):
  for key,value in [('shop_id',2),('user_id',2)]:
   db=self.db();db.data['system_sync_jobs'][0][key]=value
   with self.assertRaises(DataUnavailableError):self.get(db)
 def test_absent_normalization_cannot_be_replaced_by_metric_success(self):
  db=self.db();db.data['system_normalization_jobs']=[]
  with self.assertRaises(DataUnavailableError):self.get(db)
 def test_product_level_requires_its_pipeline(self):
  db=self.db();db.data['system_snapshot_jobs'][0]['snapshot_name']='ads_product_daily';db.data['system_metric_jobs'][0]['metric_name']='ads_product_daily_metrics'
  r=self.get(db,level='product');self.assertEqual(r['products'],[]);self.assertEqual(r['spend'],0)
 def test_known_no_campaigns_marker_is_accepted(self):
  db=self.db()
  for r in db.data['raw_wb_ads_stats']:r['payload']['empty_reason']='no_advert_ids'
  self.assertEqual(self.get(db)['spend'],0)
