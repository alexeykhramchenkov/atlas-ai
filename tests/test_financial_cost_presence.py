import unittest
from snapshots.snapshots_financial_daily import build_financial_snapshot_row,build_cost_index
class CostPresence(unittest.TestCase):
 def row(self):return {'user_id':1,'shop_id':1,'marketplace':'wb','product_key':'a','snapshot_date':'2026-10-15','sales_count':2,'sales_amount':100,'net_sales_amount':100,'wb_commission_amount':10}
 def cost(self,price,**kw):return {'user_id':1,'shop_id':1,'marketplace':'wb','product_key':'a','effective_from':'2026-10-01','cost_price':price,**kw}
 def test_absent_cost_does_not_create_profit(self):self.assertIsNone(build_financial_snapshot_row(self.row(),{}))
 def test_known_cost_keeps_existing_formula(self):
  r=build_financial_snapshot_row(self.row(),build_cost_index([self.cost(20)]));self.assertEqual(r['net_profit'],50)
 def test_explicit_zero_cost_is_valid(self):
  r=build_financial_snapshot_row(self.row(),build_cost_index([self.cost(0)]));self.assertEqual(r['net_profit'],90);self.assertEqual(r['cost_price'],0)
 def test_other_shop_cost_not_used(self):self.assertIsNone(build_financial_snapshot_row(self.row(),build_cost_index([self.cost(20,shop_id=2)])))
 def test_future_cost_not_used(self):self.assertIsNone(build_financial_snapshot_row(self.row(),build_cost_index([self.cost(20,effective_from='2026-11-01')])))
 def test_current_realization_snapshot_needs_no_previous_metrics(self):
  from snapshots.snapshots_financial_daily import SOURCE_TABLE
  self.assertEqual(SOURCE_TABLE,'snapshots_realization_daily')
  row={**self.row(),'returns_count':1,'returns_amount':30,'net_sales_amount':999}
  result=build_financial_snapshot_row(row,build_cost_index([self.cost(20)]))
  self.assertEqual(result['net_sales_amount'],70)
  self.assertEqual(result['net_profit'],40)
