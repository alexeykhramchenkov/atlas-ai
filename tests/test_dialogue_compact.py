import unittest
from unittest.mock import patch
from ai_chat.dialogue import compact_answer

class CompactTests(unittest.TestCase):
 def test_analytics_uses_existing_rule_and_actual_filtered_rows(self):
  plan={'steps':[{'id':'s','tool':'analytics','args':[{'name':k,'value':v} for k,v in dict(dataset='stocks',metric='days_left',analysis='rank',entity='product').items()]}]}
  payload={'rows':[{'title':'Бант','days_left':3.75}],'products':[{'title':'Ангелы'}]}
  with patch('ai_chat.answer_builder.resolver.resolve_answer_rule',return_value={'id':106}),patch('ai_chat.answer_builder.answer.build_answer',return_value='• Бант: примерно 4 дня') as render:
   result=compact_answer(plan,{'s':{'status':'ok','data':payload}},object(),{})
  self.assertEqual(result['answer'],'• Бант: примерно 4 дня')
  self.assertEqual(result['proposed_steps'],[])
  self.assertIs(render.call_args.kwargs['result'],payload)
 def test_missing_rule_does_not_fake_success(self):
  p={'steps':[{'id':'s','tool':'analytics','args':[]}]}
  with patch('ai_chat.answer_builder.resolver.resolve_answer_rule',return_value=None):
   self.assertIsNone(compact_answer(p,{'s':{'status':'ok','data':{}}},object(),{}))
