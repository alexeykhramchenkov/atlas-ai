import unittest
from telegram_bot.text_formatting import prepare_text,message_chunks,utf16_length
from ai_chat.answer_builder.templates import apply_template
from ai_chat.answer_builder.formatters import format_value
import json
from pathlib import Path

class TextFormattingTests(unittest.TestCase):
 def test_opt_in_bold_and_visible_text(self):
  rule={'fields':[{'template':{'telegram_format':'html_bold'}}]}
  text,spans=prepare_text('<b>Платье</b>\n• &lt;b&gt;текст покупателя&lt;/b&gt;',rule)
  self.assertEqual(text,'Платье\n• <b>текст покупателя</b>')
  self.assertEqual(spans,[(0,6)])
  self.assertEqual(prepare_text('<b>literal</b>',{}),('<b>literal</b>',[]))
 def test_utf16_chunks_and_split_bold(self):
  text='😀Платье';chunks=list(message_chunks(text,[(0,len(text))],4))
  self.assertEqual(''.join(c for c,e in chunks),text)
  for c,entities in chunks:
   self.assertLessEqual(utf16_length(c),4)
   self.assertEqual(entities[0].length,utf16_length(c))
 def test_rule_layout_and_verbatim_question(self):
  root=Path(__file__).resolve().parents[1]
  rule=json.loads((root/'setup/followups-layout-release/rule-after.json').read_text())[0]
  data={'questions_count':2,'rows':[{'title':'Куртка','question_created_at':'2026-09-15T17:00:00+00:00',
    'question_text':'Здравствуйте. <b>Будет 110?</b>'},
    {'title':'Платье','question_created_at':'2026-09-13T17:00:00+00:00','question_text':'Бант отдельно?'}]}
  rendered=apply_template(rule=rule,fields=[],language='ru',data=data,request={})
  text,spans=prepare_text(rendered,rule)
  self.assertIn('Куртка · 15 сентября\n• Здравствуйте. <b>Будет 110?</b>\n\nПлатье · 13 сентября',text)
  self.assertEqual(len(spans),2)
