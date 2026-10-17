import unittest
from ai_chat.analysis.analysis_type.filter import run

class AnalysisFilter(unittest.TestCase):
 def test_conditions_and_missing(self):
  rows=[{'product_key':'a','v':3},{'product_key':'b','v':2},{'product_key':'c'},{'product_key':'d','v':None}]
  self.assertEqual(run(rows=rows,conditions=[{'field':'v','operator':'gte','value':3}])['rows'],rows[:1])
  self.assertEqual(run(rows=rows,conditions=[{'field':'v','operator':'ne','value':3}])['rows'],rows[1:2])
 def test_operators_and_and(self):
  rows=[{'v':1},{'v':2},{'v':3}]
  for op,value,expected in [('eq',2,[2]),('ne',2,[1,3]),('gt',2,[3]),('gte',2,[2,3]),('lt',2,[1]),('lte',2,[1,2]),('in',[2],[2]),('not_in',[2],[1,3])]:
   self.assertEqual([r['v'] for r in run(rows=rows,conditions=[{'field':'v','operator':op,'value':value}])['rows']],expected)
  self.assertEqual(run(rows=rows,conditions=[{'field':'v','operator':'gt','value':1},{'field':'v','operator':'lt','value':3}])['rows'],[{'v':2}])
 def test_crossing_ties_and_zero(self):
  rows=[{'product_key':k,'v':v} for k,v in [('b',3),('a',3),('z',8),('c',0)]]
  original=[dict(r) for r in rows]
  result=run(rows=rows,cumulative={'field':'v','share':.8})['rows']
  self.assertEqual([r['product_key'] for r in result],['z','a','b'])
  self.assertEqual(rows,original)
  self.assertEqual(run(rows=[{'v':0}],cumulative={'field':'v','share':.8}),{'rows':[]})
 def test_conditions_before_share(self):
  rows=[{'product_key':'a','v':100,'keep':False},{'product_key':'b','v':8,'keep':True},{'product_key':'c','v':2,'keep':True}]
  self.assertEqual(run(rows=rows,conditions=[{'field':'keep','operator':'eq','value':True}],cumulative={'field':'v','share':.8})['rows'],rows[1:2])
 def test_invalid_numbers_and_share(self):
  for v in [None,True,-1,float('nan'),float('inf'),'bad']:
   with self.assertRaises(ValueError):run(rows=[{'v':v}],cumulative={'field':'v','share':.8})
  for v in [0,-1,1.1,None,True]:
   with self.assertRaises(ValueError):run(rows=[],cumulative={'field':'v','share':v})
 def test_executor_default_and_all_keep_totals(self):
  from unittest.mock import patch
  from ai_chat.executor import Executor
  fields=('open_count','cart_count','order_count','buyout_count','cancel_count')
  products=[{'product_key':k,'title':k,**{f:v for f in fields}} for k,v in [('a',10),('b',10),('c',10)]]
  facts={'start_date':'2026-10-09','end_date':'2026-10-15','products':products,**{f:30 for f in fields}}
  previous={**facts,'products':[{**r,**{f:20 for f in fields}} for r in products],**{f:60 for f in fields}}
  stocks={'products':[{'product_key':'a','total_quantity':80},{'product_key':'b','total_quantity':15},{'product_key':'c','total_quantity':5}]}
  outputs=[]
  for scope in ('top','all'):
   with patch('ai_chat.internal_tools.get_funnel.get_funnel',side_effect=[facts,previous]),patch('ai_chat.internal_tools.get_stocks.get_stocks',return_value=stocks) as get:
    outputs.append(Executor(object()).execute({'dataset':'funnel','analysis':'compare','metric':'open_count','entity':'product','view':'contributors','direction':'negative','answer_scope':scope,'user_id':7,'shop_id':9,'period_days':7}))
    self.assertEqual(get.call_count,1 if scope=='top' else 0)
  self.assertEqual([len(o['rows']) for o in outputs],[1,3])
  self.assertEqual(outputs[0]['comparison'],outputs[1]['comparison'])
