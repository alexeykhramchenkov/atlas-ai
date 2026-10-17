import importlib,unittest
from datetime import date
from unittest.mock import patch
from test_get_stocks_contract import StockDB
MODULES=[('snapshots.snapshots_orders_sizes_daily','run_snapshot_job'),('snapshots.snapshots_sales_variants_daily','run_snapshot_job'),('metrics.builders.metrics_orders_variants_daily','run_metric_job'),('metrics.builders.metrics_sales_variants_daily','run_metric_job')]
class RunnerTenants(unittest.TestCase):
 def test_variant_coverage_receives_job_tenant(self):
  for name,fn in MODULES:
   with self.subTest(module=name):
    m=importlib.import_module(name)
    with patch.object(m,'get_dates_to_build',return_value=[]) as coverage:
     getattr(m,fn)({'user_id':7,'shop_id':9,'marketplace':'wb'},None,{})
    self.assertEqual(coverage.call_args.kwargs['user_id'],7);self.assertEqual(coverage.call_args.kwargs['shop_id'],9)
 def test_variant_and_finance_fetches_filter_before_execute(self):
  cases=[(MODULES[0][0],'fetch_orders_for_dates',True),(MODULES[0][0],'fetch_products_by_key',False),(MODULES[0][0],'fetch_variants',False),
         (MODULES[1][0],'fetch_sales_for_dates',True),(MODULES[1][0],'fetch_products',False),
         (MODULES[2][0],'fetch_snapshots_for_metric_dates',True),(MODULES[3][0],'fetch_snapshots_for_metric_dates',True),
         ('snapshots.snapshots_financial_daily','fetch_realization_metrics',False),('snapshots.snapshots_financial_daily','fetch_product_costs',False),
         ('metrics.builders.metrics_financial_daily','fetch_financial_snapshots',False)]
  for name,fn,dates in cases:
   with self.subTest(module=name,function=fn):
    m=importlib.import_module(name);db=StockDB({})
    with patch.object(m,'supabase',db):getattr(m,fn)(*([ [date(2026,10,15)] ] if dates else []),user_id=7,shop_id=9,marketplace='wb')
    self.assertTrue(db.queries)
    for q in db.queries:
     for k,v in [('user_id',7),('shop_id',9),('marketplace','wb')]:self.assertIn((k,'eq',v),q.filters)
