import unittest,json
from pathlib import Path
from ai_chat.answer_builder.templates import apply_template
RULES=[r for r in json.loads((Path(__file__).resolve().parents[1]/'setup/all-orders-release/rules-applied.json').read_text()) if r['id'] in (6,7,8)]
class CompactAnswers(unittest.TestCase):
 def render(self,index,data,body=None):
  rule=RULES[index] if body is None else {**RULES[index],'title_template':body}
  return apply_template(rule=rule,fields=[],language='ru',data={'date_from':'2026-10-06','date_to':'2026-10-12','status':'ok',**data},request={})
 def test_store_and_rule_driven_copy(self):
  self.assertIn('10 заказов 🎉',self.render(0,{'orders_count':10}))
  self.assertEqual(self.render(0,{'orders_count':10},'Другой текст из правила'),'Другой текст из правила')
 def test_russian_plural(self):
  for n,phrase in [(1,'1 раз'),(3,'3 раза'),(11,'11 раз'),(22,'22 раза')]:
   self.assertIn(phrase,self.render(1,{'rows':[{'title':'A','marketplace_product_id':'1','value':n}]}))
 def test_partial_ranking_does_not_claim_all_regions(self):
  rows=[{'region_name':'Москва','value':2}]
  self.assertIn('в этих регионах',self.render(2,{'orders_count':10,'rows':rows}))
 def test_empty_and_incomplete(self):
  self.assertEqual(self.render(2,{'orders_count':0,'rows':[]}), 'За выбранный период этот товар не заказывали.')
  self.assertIn('не хватает данных',self.render(0,{'status':'incomplete','rows':[]}))
 def test_cancellations_displayed_separately_and_zero_omitted(self):
  self.assertIn('Из них отменили 2.',self.render(0,{'orders_count':13,'cancelled_orders_count':2}))
  self.assertNotIn('отмен',self.render(0,{'orders_count':13,'cancelled_orders_count':0}))
  self.assertIn('Из них отменили 1.',self.render(1,{'rows':[{'title':'A','marketplace_product_id':'1','value':3,'cancelled_orders_count':1}]}))
  text=self.render(2,{'orders_count':2,'rows':[{'region_name':'Москва','value':2,'cancelled_orders_count':1}]})
  self.assertIn('2 заказа (отменили 1)',text)
  self.assertNotIn('без отмен',text)
