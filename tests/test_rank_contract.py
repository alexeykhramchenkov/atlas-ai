import unittest
from copy import deepcopy
from ai_chat.analysis.analysis_type.rank import run
from unittest.mock import patch
from ai_chat.executor import Executor


class RankContract(unittest.TestCase):
    def test_sort_preserves_facts_and_does_not_mutate(self):
        rows=[{'product_key':'a','orders_count':45,'cancelled_orders_count':3},
              {'product_key':'b','orders_count':75,'cancelled_orders_count':5}]
        original=deepcopy(rows)
        self.assertEqual(run(rows=rows,metric='orders_count')['rows'],[{**rows[1],'rank':1}])
        self.assertEqual(rows,original)
        self.assertEqual(set(run(rows=rows,metric='orders_count')),{'rows'})

    def test_ascending_and_ties_are_places(self):
        rows=[{'value':3},{'value':3},{'value':8},{'value':12}]
        self.assertEqual([r['rank'] for r in run(rows=rows,metric='value',direction='asc',limit=2)['rows']],[1,1,2])
        self.assertEqual(run(rows=[],metric='value'),{'rows':[]})

    def test_bad_arguments_are_not_silently_zero(self):
        for rows in ([{}],[{'value':None}],[{'value':'NaN'}],[{'value':True}]):
            with self.assertRaises(ValueError):run(rows=rows,metric='value')
        for limit in (0,-1,True):
            with self.assertRaises(ValueError):run(rows=[],metric='value',limit=limit)

    def test_executor_passes_products_to_rank_without_period(self):
        from ai_chat.analysis.analysis_type import rank
        facts={'start_date':'2026-10-01','end_date':'2026-10-02','orders_count':14,
               'cancelled_orders_count':2,'products':[{'product_key':'a','title':'A','orders_count':4,'cancelled_orders_count':1},
                 {'product_key':'b','title':'B','orders_count':10,'cancelled_orders_count':1}]}
        with patch('ai_chat.internal_tools.get_orders.get_orders',return_value=facts) as getter, patch.object(rank,'run',wraps=rank.run) as sorter:
            result=Executor(supabase=object()).execute({'dataset':'orders','metric':'orders_count','analysis':'best',
                'entity':'product','user_id':1,'shop_id':1,'period_days':2,'limit':1})
        self.assertEqual(result['rows'][0]['product_key'],'b')
        self.assertEqual(result['rows'][0]['orders_count'],10)
        self.assertEqual(result['rows'][0]['rank'],1)
        self.assertEqual(result['date_from'],'2026-10-01')
        self.assertEqual(set(sorter.call_args.kwargs),{'rows','metric','direction','limit'})
        self.assertEqual(sorter.call_args.kwargs['rows'],facts['products'])
