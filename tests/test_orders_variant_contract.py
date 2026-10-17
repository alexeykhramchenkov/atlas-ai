import unittest
from unittest.mock import patch
import test_get_orders_contract as orders_fixture
from ai_chat.internal_tools.get_orders import get_orders
from ai_chat.executor import Executor
from ai_chat.routing.llm_fallback import clarify_request

class OrdersVariantsTests(unittest.TestCase):
 def db(self):
  db=orders_fixture.GetOrdersContract().db()
  db.data['metrics_orders_variants_daily']=[{**row,'variant_key':'v'+row['product_key'],'size_name':'90'} for row in db.data['metrics_orders_daily']]
  return db
 def test_variant_contract_and_tenant(self):
  db=self.db();r=get_orders(1,1,level='variant',start_date='2026-10-06',end_date='2026-10-07',supabase=db)
  self.assertNotIn('products',r);self.assertEqual(r['orders_count'],12)
  self.assertEqual(r['variants'][0]['variant_key'],'va');self.assertEqual(r['variants'][0]['orders_count'],5)
  self.assertEqual(r['orders_amount'],sum(x['orders_amount'] for x in r['variants']))
 def test_invalid_level(self):
  with self.assertRaises(ValueError):get_orders(1,1,level='other',period_days=30,supabase=self.db())
 def test_executor_uses_get_orders_then_rank(self):
  facts=dict(start_date='2026-10-06',end_date='2026-10-07',orders_count=12,variants=[dict(product_key='a',variant_key='v1',size_name='80',orders_count=5),dict(product_key='a',variant_key='v2',size_name='90',orders_count=7)])
  with patch('ai_chat.internal_tools.get_orders.get_orders',return_value=facts) as getter:
   r=Executor(supabase=object()).execute(dict(user_id=1,shop_id=1,dataset='orders',metric='orders_count',entity='variant',analysis='rank',product_key='a',period_days=30,limit=5))
  self.assertEqual(getter.call_args.kwargs['level'],'variant');self.assertEqual([x['size_name'] for x in r['rows']],['90','80'])
 def test_context_selection_preserves_variant_and_dates(self):
  decision=dict(action='execute',updates=[dict(field='product_key',value='a'),dict(field='date_from',value='2026-09-17'),dict(field='date_to',value='2026-10-16')])
  memory=dict(last_product_key='a',last_product={'product_key':'a','title':'A'},shown_product_keys=['a'],date_from='2026-09-17',date_to='2026-10-16')
  with patch('ai_chat.routing.llm_fallback.generate_openai_json',return_value=decision):
   r=clarify_request('Какие размеры чаще заказывают?',draft=dict(is_valid_question=True,dataset='orders',metric='orders_count',entity='variant',analysis='rank',period_days=30),memory=memory)
  self.assertEqual((r['entity'],r['product_key'],r['date_from']),('variant','a','2026-09-17'));self.assertNotIn('period_days',r)
  self.assertEqual(r['product']['match_type'],'memory')
