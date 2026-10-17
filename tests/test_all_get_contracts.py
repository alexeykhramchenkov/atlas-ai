import unittest
from unittest.mock import patch
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from test_get_stocks_contract import StockDB
from ai_chat.internal_tools._common import DataUnavailableError
from ai_chat.internal_tools.get_sales import get_sales
from ai_chat.internal_tools.get_ads import get_ads,FIELDS as ADS_FIELDS
from ai_chat.internal_tools.get_profit import get_profit,PROFIT_FIELDS,EXPENSE_FIELDS
from ai_chat.internal_tools.get_reviews import get_reviews
from ai_chat.internal_tools.get_prices import get_prices
from ai_chat.internal_tools.get_products import get_products
from ai_chat.internal_tools.get_metric import get_metric

T={'user_id':1,'shop_id':1,'marketplace':'wb'}
D={'start_date':'2026-10-06','end_date':'2026-10-07'}
class AllGetContracts(unittest.TestCase):
 def db(self,table,rows):
  facts=[{**T,'id':i,'snapshot_date':'2026-10-06','product_key':'a',**r} for i,r in enumerate(rows,1)]
  # A different user's and a different shop's records must never contribute.
  if facts:facts.extend([{**facts[0],'id':10000,'user_id':2},{**facts[0],'id':10001,'shop_id':2}])
  return StockDB({table:facts,'normalized_products':[{**T,'id':1,'product_key':'a','title':'A'},
    {**T,'id':2,'shop_id':2,'product_key':'a','title':'Wrong'}]})
 def call(self,fn,db,**kw):return fn(user_id=1,shop_id=1,supabase=db,**kw)
 def assert_tenant(self,db):
  for q in db.queries:
   for key,val in T.items():self.assertIn((key,'eq',val),q.filters)
 def test_sales_exact_period_totals_and_names(self):
  db=self.db('metrics_sales_daily',[{'sales_count':2,'return_count':1},{'snapshot_date':'2026-10-07','sales_count':3,'return_count':0}])
  r=self.call(get_sales,db,**D)
  self.assertEqual(r,{'start_date':D['start_date'],'end_date':D['end_date'],'sales_count':5,'return_count':1,
   'products':[{'product_key':'a','title':'A','sales_count':5,'return_count':1}]});self.assert_tenant(db)
 def test_sales_pagination_and_product_filter(self):
  db=self.db('metrics_sales_daily',[{'id':i,'product_key':f'p{i:04}','sales_count':1,'return_count':0} for i in range(2001)])
  self.assertEqual(self.call(get_sales,db,**D)['sales_count'],2001)
  self.assertEqual(self.call(get_sales,db,product_key='p0002',**D)['sales_count'],1)
 def test_sales_bad_counts_rejected(self):
  for v in [None,True,-1,0.5,'NaN']:
   with self.assertRaises(ValueError):self.call(get_sales,self.db('metrics_sales_daily',[{'sales_count':v,'return_count':0}]),**D)
 def ad(self,**kw):return {'ad_id':'c1','campaign_id':'c1','currency':'RUB',**{f:1 for f in ADS_FIELDS},**kw}
 def test_ads_campaign_sums_and_decimal_money(self):
  db=self.db('metrics_ads_daily',[self.ad(spend='0.1'),self.ad(spend='0.2',snapshot_date='2026-10-07')])
  r=self.call(get_ads,db,**D);self.assertEqual(r['spend'],0.3);self.assertEqual(r['orders'],2)
  self.assertEqual(len(r['campaigns']),1);self.assertNotIn('products',r);self.assert_tenant(db)
 def test_ads_product_and_campaign_filters(self):
  db=self.db('metrics_ads_product_daily',[self.ad(),self.ad(ad_id='c2',campaign_id='c2',product_key='b')])
  r=self.call(get_ads,db,level='product',product_key='a',campaign_id='c1',**D)
  self.assertEqual(r['orders'],1);self.assertEqual(r['products'][0]['title'],'A')
  with self.assertRaises(ValueError):self.call(get_ads,db,product_key='a',**D)
 def test_ads_mixed_or_missing_currency_rejected(self):
  for currency in ['USD',None]:
   with self.assertRaises(ValueError):self.call(get_ads,self.db('metrics_ads_daily',[self.ad(),self.ad(currency=currency)]),**D)
 def test_finance_signed_money_and_no_daily_percentage_sums(self):
  base={f:0 for f in PROFIT_FIELDS};db=self.db('metrics_financial_daily',[{**base,'net_profit':-10},{**base,'net_profit':4}])
  r=self.call(get_profit,db,**D);self.assertEqual(r['net_profit'],-6);self.assertNotIn('net_margin_pct',r);self.assert_tenant(db)
 def test_finance_unknown_cost_propagates_null(self):
  base={f:0 for f in PROFIT_FIELDS};db=self.db('metrics_financial_daily',[{**base,'cogs_amount':None},{**base,'cogs_amount':20}])
  self.assertIsNone(self.call(get_profit,db,**D)['cogs_amount'])
 def test_expenses_use_realization_not_profit(self):
  base={f:0 for f in EXPENSE_FIELDS};db=self.db('metrics_realization_daily',[{**base,'total_expense_amount':200,'other_income_amount':-5}])
  r=self.call(get_profit,db,view='expenses',**D);self.assertEqual(r['total_expense_amount'],200);self.assertNotIn('net_profit',r)
  self.assertTrue(all(q.table!='metrics_financial_daily' for q in db.queries))
 def feedback(self,**kw):return {'feedback_id':'f1','rating':2,'text':'text','created_at':'2026-10-06T12:00:00+03:00',**kw}
 def test_reviews_dedup_filter_and_no_private_identity(self):
  db=self.db('normalized_feedbacks',[self.feedback(),self.feedback(),self.feedback(feedback_id='f2',rating=5)])
  r=self.call(get_reviews,db,rating_max=3,**D);self.assertEqual(r['reviews_count'],1);self.assertEqual(r['reviews'][0]['title'],'A')
  self.assertNotIn('user_name',r['reviews'][0]);self.assert_tenant(db)
 def test_reviews_conflicting_duplicate_rejected(self):
  db=self.db('normalized_feedbacks',[self.feedback(),self.feedback(text='different')])
  with self.assertRaises(ValueError):self.call(get_reviews,db,**D)
 def test_reviews_range_and_creation_boundaries(self):
  db=self.db('normalized_feedbacks',[self.feedback(),self.feedback(feedback_id='last',created_at='2026-10-07T23:59:59+03:00'),self.feedback(feedback_id='outside',created_at='2026-10-08T00:00:00+03:00')])
  self.assertEqual(self.call(get_reviews,db,**D)['reviews_count'],2)
  with self.assertRaises(ValueError):self.call(get_reviews,db,rating_min=4,rating_max=2,**D)
 def price(self,**kw):return {'variant_key':'v1','size_name':'S','base_price':100,'final_price':80,'discount_percent':20,'currency':'RUB',**kw}
 def test_prices_snapshot_and_history_do_not_average_variants(self):
  db=self.db('snapshots_prices_daily',[self.price(),self.price(variant_key='v2',size_name='M',final_price=90),self.price(snapshot_date='2026-10-07',final_price=70)])
  r=self.call(get_prices,db,as_of='2026-10-06');self.assertEqual([x['final_price'] for x in r['prices']],[80,90])
  self.assertEqual(len(self.call(get_prices,db,**D)['prices']),3);self.assert_tenant(db)
 def test_prices_latest_is_store_date_not_selected_product(self):
  db=self.db('snapshots_prices_daily',[self.price(),self.price(product_key='b',snapshot_date='2026-10-07')])
  with self.assertRaises(DataUnavailableError):self.call(get_prices,db,product_key='a')
 def test_prices_selector_and_conflict_validation(self):
  db=self.db('snapshots_prices_daily',[self.price(),self.price(final_price=75)])
  with self.assertRaises(ValueError):self.call(get_prices,db,as_of='2026-10-06')
  with self.assertRaises(ValueError):self.call(get_prices,db,as_of='2026-10-06',**D)
 def test_catalog_count_and_multiple_keys_tenant(self):
  db=self.db('unused',[]);r=self.call(get_products,db);self.assertEqual(r['products_count'],1);self.assertEqual(r['products'][0]['title'],'A')
  self.assertEqual(self.call(get_products,db,product_keys=[])['products_count'],0);self.assert_tenant(db)
 def test_catalog_paginates_beyond_default_limit(self):
  db=self.db('unused',[]);db.data['normalized_products']=[{**T,'id':i,'product_key':str(i),'title':str(i)} for i in range(2001)]
  self.assertEqual(self.call(get_products,db)['products_count'],2001)
 def test_persisted_metric_is_not_recalculated_or_summed(self):
  db=self.db('metrics_funnel_daily',[{'open_to_cart_pct':20},{'snapshot_date':'2026-10-07','open_to_cart_pct':40}])
  r=self.call(get_metric,db,metric='open_to_cart_pct',**D)
  self.assertEqual([x['value'] for x in r['products']],[20,40]);self.assertNotIn('value',r);self.assert_tenant(db)
 def test_metric_cannot_access_arbitrary_table_or_calculate_days_left(self):
  for name in ['days_left','system_users','unknown']:
   with self.assertRaises(ValueError):self.call(get_metric,self.db('unused',[]),metric=name)
 def test_metric_null_remains_unknown(self):
  r=self.call(get_metric,self.db('metrics_stocks_daily',[{'total_stock_value':None}]),metric='total_stock_value',as_of='2026-10-06')
  self.assertIsNone(r['products'][0]['value'])
 def test_all_period_gets_reject_ambiguous_period(self):
  for fn in [get_sales,get_ads,get_profit,get_reviews]:
   with self.assertRaises(ValueError):self.call(fn,self.db('unused',[]),period_days=30,**D)
 def test_missing_tenant_fails_closed(self):
  for fn,kw in [(get_sales,D),(get_ads,D),(get_profit,D),(get_reviews,D),(get_products,{}),(get_prices,{'as_of':'2026-10-06'}),(get_metric,{'metric':'total_stock_value','as_of':'2026-10-06'})]:
   with self.assertRaises(ValueError):fn(user_id=None,shop_id=1,supabase=self.db('unused',[]),**kw)
 def test_no_records_are_not_zero_money_or_sales(self):
  for fn,table in [(get_sales,'metrics_sales_daily'),(get_ads,'metrics_ads_daily'),(get_profit,'metrics_financial_daily'),(get_reviews,'normalized_feedbacks')]:
   with self.assertRaises(DataUnavailableError):self.call(fn,self.db(table,[]),**D)
 def test_executor_no_data_is_not_database_connection_error(self):
  from ai_chat.executor import Executor
  r=Executor(supabase=self.db('metrics_ads_daily',[])).execute({'user_id':1,'shop_id':1,'dataset':'ads','metric':'spend','analysis':'metric_value','entity':'store',**{'date_from':D['start_date'],'date_to':D['end_date']}})
  self.assertEqual(r['status'],'no_data');self.assertNotIn('value',r)
 def test_ads_rank_groups_product_across_campaigns(self):
  from ai_chat.executor import Executor
  db=self.db('metrics_ads_product_daily',[self.ad(spend=10),self.ad(ad_id='c2',campaign_id='c2',spend=20),self.ad(product_key='b',ad_id='c3',campaign_id='c3',spend=25)])
  r=Executor(supabase=db).execute({'user_id':1,'shop_id':1,'dataset':'ads','metric':'spend','analysis':'best','entity':'product','date_from':D['start_date'],'date_to':D['end_date'],'limit':1})
  self.assertEqual(r['rows'][0]['product_key'],'a');self.assertEqual(r['rows'][0]['value'],30)
 def test_enricher_requires_tenant_and_preserves_rows(self):
  from ai_chat.enrichers.product import enrich_products
  db=self.db('unused',[]);original=[{'product_key':'a','value':5}]
  r=enrich_products(original,db,user_id=1,shop_id=1);self.assertEqual(r[0]['title'],'A');self.assertEqual(original,[{'product_key':'a','value':5}]);self.assert_tenant(db)
