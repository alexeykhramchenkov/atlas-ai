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

class CountryGroupingTests(unittest.TestCase):
 def test_country_header_once_and_escaped(self):
  rule={'template_name':'compact_text','title_template':'<b>Регионы</b>\n{items}','fields':[{'template':{
   'telegram_format':'html_bold','rows_path':'rows','group_by':'country_name','group_header_template':'<b>{group}</b>:',
   'item_fields':[{'name':'region','path':'region_name','formatter':'html_text'},{'name':'value','path':'value','formatter':'number'}],
   'item_template':'• {region}: <b>{value}</b>'}}]}
  data={'rows':[{'country_name':'Россия <А>','region_name':'Москва','value':4},{'country_name':'Россия <А>','region_name':'Татарстан','value':2},{'country_name':'Казахстан','region_name':'Алматы','value':1}]}
  answer=apply_template(rule=rule,fields=[],data=data,request={},language='ru');text,spans=prepare_text(answer,rule)
  self.assertEqual(text.count('Россия <А>:'),1)
  self.assertIn('• Москва: 4\n• Татарстан: 2',text)
  self.assertEqual(len(spans),6)

class ItemFormattingOptionsTests(unittest.TestCase):
 def test_item_days_uses_rule_rounding_options(self):
  rule={'template_name':'compact_text','title_template':'{items}','fields':[{'template':{
   'rows_path':'rows','item_fields':[{'name':'days','path':'value','formatter':'days','options':{'decimals':0}}],
   'item_template':'Примерно {days}'}}]}
  answer=apply_template(rule=rule,fields=[],data={'rows':[{'value':102.86}]},request={},language='ru')
  self.assertEqual(answer,'Примерно 103 дня')
