import unittest
from datetime import date
from unittest.mock import Mock,patch
from copy import deepcopy
from db.stock_state import load_raw_snapshot,replace_stock_rows,replace_stock_metric_dates
from normalized import normalized_wb_stocks as normalizer
import test_get_stocks_contract as stock_contract
from test_get_stocks_contract import StockDB

T={'user_id':1,'shop_id':1,'marketplace':'wb'}
def source(day='2026-10-17',qty=60,warehouse='Current',pk=123):
 return {**T,'id':1,'snapshot_date':day,'payload':{'nmId':pk,'barcode':'v1','warehouseName':warehouse,'quantity':qty,'inWayToClient':7,'inWayFromClient':5}}
EMPTY={**T,'id':2,'snapshot_date':'2026-10-17','payload':{'data':[],'empty_reason':'empty_api_payload'}}

class StockSnapshotReplacementTests(unittest.TestCase):
 def test_reads_one_full_date_not_an_incremental_mix(self):
  db=StockDB({'raw_wb_stocks':[source('2026-10-16',999),source(),{**source('2026-10-18',999),'user_id':2}]})
  day,rows=load_raw_snapshot(db,**T)
  self.assertEqual(day,'2026-10-17');self.assertEqual(len(rows),1)
  self.assertEqual(rows[0]['payload']['quantity'],60)
  with self.assertRaises(ValueError):load_raw_snapshot(db,**T,snapshot_date='2026-10-15')
 def test_watermark_does_not_retain_old_warehouses(self):
  db=Mock();db.rpc.return_value.execute.return_value.data=1
  with patch.object(normalizer,'supabase',db),patch('db.stock_state.load_raw_snapshot',return_value=('2026-10-17',[source()])):
   normalizer.run_normalization_job(T,{'last_raw_id':999,'last_raw_updated_at':'future'})
  args=db.rpc.call_args.args[1]
  self.assertEqual(len(args['p_rows']),1);self.assertEqual(args['p_rows'][0]['quantity'],60)
  self.assertEqual(args['p_table'],'normalized_stocks');self.assertIsNone(args['p_snapshot_date'])
 def test_confirmed_empty_replaces_but_malformed_source_fails(self):
  self.assertEqual(normalizer.build_complete_stock_rows([EMPTY]),[])
  for rows in ([],[{**EMPTY,'payload':{}}],[source(),EMPTY],[{**source(),'payload':{'nmId':123}}]):
   with self.assertRaises(ValueError):normalizer.build_complete_stock_rows(rows)
 def test_conflicting_duplicate_identity_fails(self):
  with self.assertRaises(ValueError):normalizer.build_complete_stock_rows([source(),source(qty=99)])
 def test_replacement_validates_boundary_and_uses_single_rpc(self):
  db=Mock();db.rpc.return_value.execute.return_value.data=1
  row={**T,'snapshot_date':'2026-10-17','product_key':'a','total_quantity':1}
  for table,rows,kw in [('orders',[row],{}),('metrics_stocks_daily',[{**row,'shop_id':2}],{'snapshot_date':'2026-10-17'}),('metrics_stocks_daily',[row],{'snapshot_date':'2026-10-16'})]:
   with self.assertRaises(ValueError):replace_stock_rows(db,table,rows,**T,**kw)
  db.rpc.assert_not_called()
  self.assertEqual(replace_stock_rows(db,'metrics_stocks_daily',[row],**T,snapshot_date='2026-10-17'),1)
  self.assertEqual(db.rpc.call_count,1)
 def test_empty_metric_date_is_replaced_too(self):
  db=Mock();db.rpc.return_value.execute.return_value.data=0
  self.assertEqual(replace_stock_metric_dates(db,'metrics_stocks_daily',[],[date(2026,10,17)],**T),0)
  self.assertEqual(db.rpc.call_args.args[1]['p_rows'],[])
  self.assertEqual(db.rpc.call_args.args[1]['p_snapshot_date'],'2026-10-17')
 def test_stock_reader_does_not_fall_back_after_new_empty_source(self):
  from ai_chat.internal_tools.get_stocks import get_stocks,StockDataUnavailableError
  db=stock_contract.StockContract().db();db.data['raw_wb_stocks'].append({**T,'id':3,'snapshot_date':'2026-10-15'})
  with self.assertRaises(StockDataUnavailableError):get_stocks(1,1,supabase=db)
  self.assertEqual(get_stocks(1,1,as_of='2026-10-14',supabase=db)['total_quantity'],171)
 def test_variant_builder_uses_exact_source_not_old_normalized_state(self):
  from snapshots import snapshots_stocks_variants_daily as builder
  db=Mock();db.rpc.return_value.execute.return_value.data=1
  with patch.object(builder,'supabase',db),patch.object(builder,'fetch_normalized_stocks',side_effect=AssertionError('Do not mix current state')),patch('db.stock_state.load_raw_snapshot',return_value=('2026-10-17',[source()])):
   builder.run_snapshot_job({**T,'date_to':'2026-10-17'},None,{})
  self.assertEqual(db.rpc.call_args.args[1]['p_rows'][0]['quantity'],60)
 def test_variant_builder_clears_confirmed_empty_snapshot(self):
  from snapshots import snapshots_stocks_variants_daily as builder
  db=Mock();db.rpc.return_value.execute.return_value.data=0
  with patch.object(builder,'supabase',db),patch('db.stock_state.load_raw_snapshot',return_value=('2026-10-17',[EMPTY])):
   builder.run_snapshot_job({**T,'date_to':'2026-10-17'},None,{})
  self.assertEqual(db.rpc.call_args.args[1]['p_rows'],[])
 def test_product_snapshot_rebuild_ignores_obsolete_variant_rows(self):
  from snapshots import snapshots_stocks_daily as builder
  db=Mock();db.rpc.return_value.execute.return_value.data=1
  with patch.object(builder,'supabase',db),patch.object(builder,'fetch_variant_snapshots',side_effect=AssertionError('Stale derived state')),patch.object(builder,'fetch_products',return_value={}),patch('db.stock_state.load_raw_snapshot',return_value=('2026-10-17',[source()])):
   builder.run_snapshot_job({**T,'date_to':'2026-10-17'},None,{})
  row=db.rpc.call_args.args[1]['p_rows'][0]
  self.assertEqual((row['total_quantity'],row['total_in_way_to_client'],row['total_in_way_from_client']),(60,7,5))
 def test_metric_runner_clears_empty_source_date_even_without_snapshot_rows(self):
  from metrics.builders import metrics_stocks_daily,metrics_stocks_variants_daily
  for builder in (metrics_stocks_daily,metrics_stocks_variants_daily):
   with patch.object(builder,'supabase',Mock()),patch.object(builder,'get_dates_to_build',return_value=[]),patch.object(builder,'fetch_snapshots_for_metric_dates',return_value=[]),patch('db.stock_state.load_raw_snapshot',return_value=('2026-10-17',[EMPTY])),patch('db.stock_state.replace_stock_metric_dates',return_value=0) as writer:
    builder.run_metric_job(T,None,{})
   self.assertEqual(writer.call_args.args[2],[])
   self.assertEqual(writer.call_args.args[3],[date(2026,10,17)])
