import unittest
from unittest.mock import patch
from ai_chat.executor import Executor
class SelectionTotalsTests(unittest.TestCase):
 def test_selection_totals_exclude_other_products(self):
  rows=[dict(product_key=k,title=k,warehouse_quantity=w,to_customer_quantity=t,from_customer_quantity=f,total_quantity=w+t+f) for k,w,t,f in [('a',60,10,2),('b',1,5,0),('c',0,1,0),('other',9,20,11)]]
  facts={'as_of':'2026-10-16','products':rows,**{field:sum(r[field] for r in rows) for field in ('warehouse_quantity','to_customer_quantity','from_customer_quantity','total_quantity')}}
  with patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=facts):
   result=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,marketplace='wb',dataset='stocks',analysis='metric_value',metric='stock_qty',entity='product',product_keys=['a','b','c']))
  self.assertEqual(result['value'],79)
  self.assertEqual(result['total_quantity'],79)
  self.assertEqual(result['warehouse_quantity'],61)
  self.assertEqual({r['product_key'] for r in result['products']},{'a','b','c'})
