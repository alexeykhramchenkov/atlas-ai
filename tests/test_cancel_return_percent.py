import unittest
from unittest.mock import patch
from ai_chat.analysis.ratios import ratio_percent,rank_rates
from ai_chat.metric.seller_questions import calculate
from ai_chat.executor import Executor

class CancelReturnPercentTests(unittest.TestCase):
 def test_ratio_rounding_zero_and_large_returns(self):
  self.assertEqual(ratio_percent(1,3),33.3)
  self.assertEqual(ratio_percent(3,3),100)
  self.assertEqual(ratio_percent(3,2),150)
  self.assertIsNone(ratio_percent(1,0))
  self.assertIsNone(ratio_percent(1,None))
 def test_cancel_ratio_uses_orders_and_ranks_by_share(self):
  req={'dataset':'orders','analysis':'best','metric':'cancelled_orders','entity':'product','date_from':'2026-10-16','date_to':'2026-10-16','limit':5}
  out=calculate(req,{'products':[],'orders':[{'snapshot_date':'2026-10-16','product_key':'more-count','orders_count':100,'cancelled_orders_count':10},{'snapshot_date':'2026-10-16','product_key':'higher-rate','orders_count':2,'cancelled_orders_count':1}]})
  self.assertEqual([r['rate_pct'] for r in out['rows']],[50,10]);self.assertEqual(out['rows'][0]['value'],1)
 def test_return_ratio_uses_buyouts_not_buyouts_plus_returns(self):
  req={'user_id':1,'shop_id':2,'marketplace':'wb','dataset':'sales','analysis':'best','metric':'return_count','entity':'product','period_days':7,'limit':5}
  facts={'start_date':'2026-10-10','end_date':'2026-10-16','sales_count':11,'return_count':4,'products':[{'product_key':'a','sales_count':1,'return_count':1},{'product_key':'b','sales_count':10,'return_count':3}]}
  with patch('ai_chat.internal_tools.get_sales.get_sales',return_value=facts):out=Executor(object()).execute(req)
  self.assertEqual([r['rate_pct'] for r in out['rows']],[100,30]);self.assertEqual(out['return_count'],4)
 def test_unknown_rate_is_not_zero_or_ranked_above_known(self):
  rows=rank_rates([{'rate_pct':None},{'rate_pct':20},{'rate_pct':0}],limit=5)
  self.assertEqual([r['rate_pct'] for r in rows],[20,0,None])
