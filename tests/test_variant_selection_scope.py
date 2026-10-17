import unittest
from unittest.mock import patch
from ai_chat.executor import Executor

class VariantSelectionScopeTests(unittest.TestCase):
 def test_selected_products_are_applied_before_size_ranking_and_totals(self):
  def row(pk,size,count):return {'product_key':pk,'variant_key':size,'size_name':size,'orders_count':count,'cancelled_orders_count':0,'orders_amount':count*100,'cancelled_orders_amount':0}
  data={'start_date':'2026-09-17','end_date':'2026-10-16','orders_count':99,'orders_amount':9900,'variants':[row('a','80',13),row('a','90',8),row('b','100',78)]}
  req={'user_id':1,'shop_id':1,'dataset':'orders','metric':'orders_count','analysis':'best','entity':'variant','product_keys':['a'],'period_days':30,'limit':5}
  with patch('ai_chat.internal_tools.get_orders.get_orders',return_value=data):r=Executor(object()).execute(req)
  self.assertEqual([x['size_name'] for x in r['rows']],['80','90'])
  self.assertEqual((r['orders_count'],r['orders_amount']),(21,2100))
  self.assertEqual(data['orders_count'],99)
