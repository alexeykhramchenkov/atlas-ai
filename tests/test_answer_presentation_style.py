import unittest
from ai_chat.answer_builder.templates import apply_template
from telegram_bot.text_formatting import prepare_text

class PresentationStyleTests(unittest.TestCase):
 def render(self,data):
  rule={'template_name':'compact_text','title_template':'<b>Остатки</b>{period_heading}\n\n{items}',
   'fields':[{'template':{'telegram_format':'html_bold','omit_same_year':True,'sections':[
    {'name':'items','rows_path':'rows','item_fields':[
     {'name':'title','path':'title','fallback_paths':['product_name'],'formatter':'html_text'},
     {'name':'value','path':'value','formatter':'number'}],
     'item_template':'• {title}: <b>{value}</b>'}]}}]}
  answer=apply_template(rule=rule,fields=[],data=data,request={},language='ru')
  return prepare_text(answer,rule)
 def test_snapshot_has_date_without_invented_period(self):
  text,spans=self.render({'as_of':'2026-10-16','rows':[{'product_name':'Платье <А>','value':72}]})
  self.assertEqual(text,'Остатки\n16.10.2026\n\n• Платье <А>: 72')
  self.assertEqual(len(spans),2)
 def test_period_heading_counts_inclusive_days(self):
  text,_=self.render({'date_from':'2026-09-17','date_to':'2026-10-16','rows':[]})
  self.assertTrue(text.startswith('Остатки · 30 дней\n17 сентября — 16 октября'))
