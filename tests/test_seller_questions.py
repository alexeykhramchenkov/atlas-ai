import unittest
from unittest.mock import MagicMock
from datetime import date,timedelta
from ai_chat.routing.seller_questions import QUESTIONS,resolve_seller_question
from ai_chat.metric.seller_questions import calculate
from ai_chat.internal_tools.get_seller_facts import get_seller_facts
CTX={'user_id':1,'shop_id':1,'marketplace':'wb'}
class SellerQuestions(unittest.TestCase):
 def request(self,metric,**extra):
  q=next(q for q in QUESTIONS if q[2]==metric)
  return {**CTX,'metric':metric,'dataset':q[3],'analysis':q[4],'entity':q[5],'period_days':7,'date_from':'2026-10-07','date_to':'2026-10-13','limit':5,**extra}
 def rows(self,**fields):
  return [{'snapshot_date':(date(2026,9,30)+timedelta(days=i)).isoformat(),'product_key':'a',**fields} for i in range(14)]
 def facts(self,**extra):return {'products':[{'product_key':'a','title':'A'}],'orders':self.rows(orders_count=1,cancelled_orders_count=1),'stocks':[{'snapshot_date':'2026-10-14','product_key':'a','total_quantity':2}],**extra}
 def test_all_25_questions_route_without_contract_keys(self):
  for q in QUESTIONS:
   r=resolve_seller_question(q[1],{},CTX,resolve_explicit=lambda _:None,resolve_reference=lambda q,m:None)
   self.assertEqual(r['metric'],q[2]);self.assertIn(r['analysis'],{'metric_value','best','worst'})
   self.assertFalse(set(r)-set(CTX)-{'metric','dataset','analysis','entity','scope','period_days','date_from','date_to','limit','answer_scope','question_type','is_valid_question','error_code','message'})
 def test_profit_and_jam_questions_not_in_catalog(self):
  self.assertFalse({11,12,13,15,24}&{q[0] for q in QUESTIONS})
 def test_comparison_requires_previous_week(self):
  f=self.facts(orders=self.rows(orders_count=1)[7:]);r=calculate(self.request('orders_week_change'),f)
  self.assertEqual(r['status'],'incomplete')
 def test_comparison_sum_not_average_daily_percent(self):
  rows=self.rows(orders_count=1)
  for r in rows[7:]:r['orders_count']=3
  out=calculate(self.request('orders_week_change'),self.facts(orders=rows))
  self.assertEqual((out['current'],out['previous'],out['change_pct']),(21,7,200))
 def test_stock_includes_cancelled_orders_and_horizon14(self):
  self.assertEqual(calculate(self.request('stock_days',product_key='a'),self.facts())['rows'][0]['value'],2)
  self.assertEqual(calculate(self.request('replenishment_qty'),self.facts())['rows'][0]['value'],12)
 def test_stale_stock_suppresses_estimate(self):
  self.assertEqual(calculate(self.request('stock_days',product_key='a'),self.facts(stocks=[{'snapshot_date':'2026-10-01','product_key':'a','total_quantity':2}]))['status'],'incomplete')
 def test_no_orders_does_not_mean_infinite_stock_days(self):
  self.assertEqual(calculate(self.request('stock_days',product_key='a'),self.facts(orders=self.rows(orders_count=0)))['status'],'no_orders')
 def test_regions_count_cancellations_and_deduplicate(self):
  events=[{'srid':'1','product_key':'a','region_name':'Москва','is_cancel':True}]*2+[{'srid':'empty:day','product_key':None}]
  out=calculate(self.request('regions_store'),self.facts(order_events=events))
  self.assertEqual(out['rows'][0]['value'],1);self.assertEqual(out['rows'][0]['cancelled_orders_count'],1)
 def test_buyout_rate_excludes_in_transit(self):
  out=calculate(self.request('buyout_rate'),self.facts(funnel=self.rows(order_count=20,buyout_count=3,cancel_count=1)))
  self.assertEqual(out['value'],75)
 def test_conversion_is_weighted_cart_to_order(self):
  rows=self.rows(cart_count=10,order_count=5)
  for r in rows[7:]:r['order_count']=1
  out=calculate(self.request('conversion_decline'),self.facts(funnel=rows))
  self.assertEqual((out['rows'][0]['previous'],out['rows'][0]['current']),(50,10))
 def test_ads_unloaded_is_not_zero(self):
  self.assertEqual(calculate(self.request('ads_spend'),self.facts(ads=[],loads=[]))['status'],'incomplete')
 def test_ads_zero_requires_coverage_and_cost_is_ratio_of_sums(self):
  loads=[{'date_from':'2026-10-07','date_to':'2026-10-13'}]
  self.assertEqual(calculate(self.request('ads_spend'),self.facts(ads=[],loads=loads))['value'],0)
  self.assertEqual(calculate(self.request('ads_cpo'),self.facts(ads=self.rows(spend=10,orders=2),loads=loads))['value'],5)
 def test_reviews_are_evidence_based_and_skip_positive(self):
  out=calculate(self.request('review_complaints'),self.facts(loads=[{}],reviews=[{'feedback_id':'a','rating':1,'text':'Шов порвался'},{'feedback_id':'b','rating':5,'text':'Размер хороший'}]))
  self.assertEqual(out['rows'][0]['title'],'Качество и дефекты');self.assertEqual(out['rows'][0]['value'],1)
 def test_current_price_alone_cannot_prove_change(self):
  self.assertEqual(calculate(self.request('price_change_orders',product_key='a'),self.facts(prices=[{'snapshot_date':'2026-10-07','product_key':'a','final_price':100}]))['status'],'incomplete')
 def test_price_change_with_complete_before_after(self):
  prices=[{'snapshot_date':'2026-10-06','product_key':'a','final_price':100},{'snapshot_date':'2026-10-07','product_key':'a','final_price':120}]
  out=calculate(self.request('price_change_orders',product_key='a'),self.facts(prices=prices))
  self.assertEqual((out['previous'],out['current']),(7,7));self.assertIn('не доказывает',out['meta']['note'])
 def test_tools_apply_tenant_filters_before_pagination(self):
  db=MagicMock();q=db.table.return_value
  for name in ('select','eq','order','range','gte','lt'):getattr(q,name).return_value=q
  q.execute.return_value.data=[]
  get_seller_facts(db,self.request('orders_today'),'orders','2026-10-07','2026-10-13')
  q.eq.assert_any_call('user_id',1);q.eq.assert_any_call('shop_id',1);q.eq.assert_any_call('marketplace','wb')
  q.range.assert_called_once_with(0,999)
 def test_finance_adapter_keeps_legacy_fields_and_source(self):
  from ingestion.marketplaces.wb.api.endpoints.finance import legacy_field_aliases
  original={'reportId':1,'sellerOperName':'Доставка','deliveryService':'10.25','paidStorage':'2.50','ppvzSalesCommission':'0','rrDate':'2026-10-01'}
  out=legacy_field_aliases(original)
  self.assertEqual(out['storage_fee'],'2.50');self.assertEqual(out['delivery_rub'],'10.25');self.assertEqual(out['supplier_oper_name'],'Доставка')
  self.assertTrue(all(out[k]==v for k,v in original.items()))
 def test_financial_return_reverses_commission_and_delivery_alias(self):
  from snapshots.snapshots_realization_daily import build_empty_group,apply_realization_row
  row=build_empty_group({},(1,1,'wb','a',date(2026,10,1)))
  apply_realization_row(row,{'event_type':'Продажа','operation_type':'Продажа','quantity':1,'raw_payload':{'supplier_oper_name':'Продажа','ppvz_sales_commission':'20'}})
  apply_realization_row(row,{'event_type':'Возврат','operation_type':'Возврат','quantity':1,'raw_payload':{'supplier_oper_name':'Возврат','ppvz_sales_commission':'5'}})
  apply_realization_row(row,{'operation_type':'Доставка','raw_payload':{'supplier_oper_name':'Доставка','deliveryService':'7'}})
  apply_realization_row(row,{'operation_type':'Хранение','raw_payload':{'supplier_oper_name':'Хранение','paidStorage':'3'}})
  self.assertEqual(row['wb_commission_amount'],15);self.assertEqual(row['logistics_amount'],7);self.assertEqual(row['storage_amount'],3)
 def test_api_success_without_finished_metrics_is_not_zero(self):
  from ai_chat.internal_tools.get_seller_facts import get_successful_loads
  from types import SimpleNamespace
  db=MagicMock();q=db.table.return_value
  for name in ('select','eq','order','limit','range'):getattr(q,name).return_value=q
  load={'date_from':'2026-10-07','date_to':'2026-10-13','finished_at':'2026-10-14T02:00:00+00:00'}
  q.execute.side_effect=[SimpleNamespace(data=[{'finished_at':'2026-10-14T01:00:00+00:00'}]),SimpleNamespace(data=[load])]
  self.assertEqual(get_successful_loads(db,self.request('ads_spend'),'ads_stats'),[])
  q.execute.side_effect=[SimpleNamespace(data=[{'finished_at':'2026-10-14T03:00:00+00:00'}]),SimpleNamespace(data=[load])]
  self.assertEqual(get_successful_loads(db,self.request('ads_spend'),'ads_stats'),[load])
 def test_equal_dates_on_new_topic_are_not_memory(self):
  from telegram_bot.handlers import journal_memory_used
  memory={'date_from':'2026-10-07','date_to':'2026-10-13'}
  self.assertEqual(journal_memory_used('Какие товары смотрят, но не заказывают?',self.request('views_without_orders'),memory,{'id':100}),{})
 def test_explicit_numeric_period_overrides_product_memory(self):
  memory={'date_from':'2026-10-07','date_to':'2026-10-13','last_metric':'stock_days'}
  r=resolve_seller_question('А за 14 дней?',memory,CTX,resolve_explicit=lambda _:None,resolve_reference=lambda q,m:{'product_key':'a','match_type':'memory'})
  self.assertEqual(r['period_days'],14)
  self.assertEqual((date.fromisoformat(r['date_to'])-date.fromisoformat(r['date_from'])).days+1,14)
