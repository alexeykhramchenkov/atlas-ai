import unittest
from unittest.mock import patch
from copy import deepcopy
from test_get_orders_contract import DB,Query
from ai_chat.internal_tools.get_stocks import get_stocks,StockDataUnavailableError
from ai_chat.executor import Executor

class StockQuery(Query):
    def limit(self,n):return self.range(0,n-1)
class StockDB(DB):
    def table(self,name):
        q=StockQuery(self,name);self.queries.append(q);return q

class StockContract(unittest.TestCase):
    def db(self):
        t={'user_id':1,'shop_id':1,'marketplace':'wb'}
        a={**t,'id':1,'product_key':'a','snapshot_date':'2026-10-14','total_quantity':56,'total_in_way_to_client':7,'total_in_way_from_client':8}
        b={**a,'id':2,'product_key':'b','total_quantity':100,'total_in_way_to_client':0,'total_in_way_from_client':0}
        c={**a,'id':3,'product_key':'c','snapshot_date':'2026-10-13'}
        return StockDB({'metrics_stocks_daily':[a,b,c,{**a,'id':4,'user_id':2,'snapshot_date':'2026-10-15','total_quantity':999}],
            'normalized_products':[{**t,'id':1,'product_key':'a','title':'A'},{**t,'id':2,'product_key':'b','title':'B'},
                                   {**t,'id':3,'user_id':2,'product_key':'a','title':'Wrong'}],
            'snapshots_stocks_variants_daily':[{**t,'id':1,'snapshot_date':'2026-10-14','product_key':'a',
                'variant_key':'v1','size_name':None,'warehouse_key':'w1','warehouse_name':'W1','quantity':2,'in_way_to_client':3,'in_way_from_client':4},
                {**t,'id':2,'snapshot_date':'2026-10-14','product_key':'a','variant_key':'v1','size_name':None,
                 'warehouse_key':'w2','warehouse_name':'W2','quantity':5,'in_way_to_client':0,'in_way_from_client':1}],
            'normalized_product_variants':[{**t,'id':1,'product_key':'a','variant_key':'v1','size_name':'42'},
                                           {**t,'id':2,'user_id':2,'product_key':'a','variant_key':'v1','size_name':'Wrong'}]})
    def get(self,db,**kw):return get_stocks(user_id=1,shop_id=1,supabase=db,**kw)
    def test_contract_quantities_and_names(self):
        db=self.db();x=self.get(db,product_key='a')
        self.assertEqual(set(x),{'as_of','warehouse_quantity','to_customer_quantity','from_customer_quantity','total_quantity','products'})
        self.assertEqual(x['as_of'],'2026-10-14');self.assertEqual(x['total_quantity'],71)
        self.assertEqual(x['products'],[{'product_key':'a','title':'A','warehouse_quantity':56,'to_customer_quantity':7,'from_customer_quantity':8,'total_quantity':71}])
        for q in db.queries:
            self.assertIn(('user_id','eq',1),q.filters);self.assertIn(('shop_id','eq',1),q.filters)
    def test_exact_date_and_no_per_product_old_fallback(self):
        with self.assertRaises(StockDataUnavailableError):self.get(self.db(),product_key='c')
        self.assertEqual(self.get(self.db(),product_key='c',as_of='2026-10-13')['total_quantity'],71)
        with self.assertRaises(StockDataUnavailableError):self.get(self.db(),as_of='2026-10-12')
    def test_recorded_zero_vs_unknown(self):
        db=self.db();row=db.data['metrics_stocks_daily'][0]
        row.update(total_quantity=0,total_in_way_to_client=0,total_in_way_from_client=0)
        self.assertEqual(self.get(db,product_key='a')['total_quantity'],0)
        with self.assertRaises(StockDataUnavailableError):self.get(db,product_key='missing')
        row['total_quantity']=None
        with self.assertRaises(ValueError):self.get(db,product_key='a')
    def test_variant_warehouse_selection_and_tenant_name(self):
        x=self.get(self.db(),product_key='a',variant_key='v1',warehouse_key='w1',level='variant')
        self.assertEqual(x['total_quantity'],9);self.assertEqual(x['products'][0]['size_name'],'42')
        self.assertEqual(x['products'][0]['warehouse_key'],'w1')
        self.assertEqual(self.get(self.db(),warehouse_key='w2')['total_quantity'],6)
    def test_pagination_over_2000(self):
        db=self.db();base=db.data['metrics_stocks_daily'][0]
        db.data['metrics_stocks_daily']=[{**base,'id':i,'product_key':f'p{i:05}'} for i in range(2001)]
        x=self.get(db)
        self.assertEqual(len(x['products']),2001);self.assertEqual(x['total_quantity'],2001*71)
    def test_executor_rank_uses_total_and_preserves_dates_outside(self):
        db=self.db();db.data['metrics_stocks_daily'][1]['total_in_way_to_client']=100
        from ai_chat.analysis.analysis_type import rank
        with patch('ai_chat.internal_tools.get_stocks.get_stocks',wraps=get_stocks) as getter, patch.object(rank,'run',wraps=rank.run) as sorter:
            x=Executor(supabase=db).execute({'dataset':'stocks','analysis':'best','metric':'stock_qty','entity':'product','user_id':1,'shop_id':1,'limit':1})
        self.assertEqual(getter.call_count,1);self.assertEqual(sorter.call_count,1)
        self.assertEqual(sorter.call_args.kwargs['metric'],'total_quantity')
        self.assertEqual(set(sorter.call_args.kwargs),{'rows','metric','direction','limit'})
        self.assertEqual(x['rows'][0]['product_key'],'b');self.assertEqual(x['rows'][0]['total_quantity'],200)
        self.assertEqual(x['as_of'],'2026-10-14')
    def test_invalid_level_and_variant_selector(self):
        for kw in ({'level':'wrong'},{'variant_key':'v1'},{'as_of':'not-a-date'}):
            with self.assertRaises(ValueError):self.get(self.db(),**kw)

    def test_table_renderer_preserves_all_tied_leaders(self):
        import json
        from pathlib import Path
        from ai_chat.answer_builder.templates import apply_template
        rules=json.loads((Path(__file__).resolve().parents[1]/'setup/get-stocks-contract-release/answer-rules-inserted.json').read_text())
        rule=next(r for r in rules if any(f.get('match',{}).get('analysis')=='best' for f in r['fields']))
        rows=[{'title':'A','value':71,'rank':1},{'title':'B','value':71,'rank':1}]
        text=apply_template(rule=rule,fields=[],language='ru',data={'as_of':'2026-10-14','rows':rows},request={'limit':1})
        self.assertIn('A — 71 шт.',text);self.assertIn('B — 71 шт.',text)
        self.assertIn('2026-10-14',text)

    def test_warehouse_ranking_groups_products_and_sizes_before_rank(self):
        db=self.db();second=dict(db.data['snapshots_stocks_variants_daily'][0])
        second.update(id=3,product_key='b',variant_key='v2',quantity=10,in_way_to_client=0,in_way_from_client=0)
        db.data['snapshots_stocks_variants_daily'].append(second)
        result=Executor(supabase=db).execute({'dataset':'stocks','analysis':'best','metric':'stock_qty',
            'entity':'warehouse','user_id':1,'shop_id':1,'limit':1})
        self.assertEqual(result['rows'][0]['warehouse_key'],'w1')
        self.assertEqual(result['rows'][0]['value'],19)
