import unittest
from datetime import date, datetime
from unittest.mock import patch
from core.dates import moscow_date
from snapshots import snapshots_orders_daily as products, snapshots_orders_sizes_daily as variants

class MoscowOrders(unittest.TestCase):
 def test_utc_boundary_and_naive_wb(self):
  for module in (products,variants):
   self.assertEqual(module.parse_date('2026-09-16T22:40:58+00:00'),date(2026,9,17))
   self.assertEqual(module.parse_date(datetime.fromisoformat('2026-09-16T20:59:59+00:00')),date(2026,9,16))
   self.assertEqual(module.parse_date('2026-09-16T23:00:00'),date(2026,9,16))
   self.assertEqual(module.parse_date('2026-09-16'),date(2026,9,16))
 def test_query_midnight_and_group_agree(self):
  for module in (products,variants):
   with patch.object(module,'supabase') as db:
    query=db.table.return_value
    for method in ('select','eq','gte','lt','order','range'):getattr(query,method).return_value=query
    query.execute.return_value.data=[{'order_date':'2026-09-16T22:40:58+00:00'}]
    rows=module.fetch_orders_for_dates([date(2026,9,17)],user_id=1,shop_id=1,marketplace='wb')
    self.assertEqual(len(rows),1)
    query.gte.assert_called_once_with('order_date','2026-09-17T00:00:00+03:00')
    query.lt.assert_called_once_with('order_date','2026-09-18T00:00:00+03:00')

 def test_historical_variant_resets_previous_day(self):
  row=dict(user_id=1,shop_id=1,marketplace='wb',product_key='dress',variant_key='old_size',order_date='2026-09-16T22:40:58+00:00',price_with_disc=100)
  result=variants.build_snapshots([row],{'dress':row},[],[date(2026,9,16),date(2026,9,17)])
  self.assertEqual({x['snapshot_date']:x['orders'] for x in result},{'2026-09-16':0,'2026-09-17':1})
