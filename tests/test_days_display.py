import unittest
from ai_chat.answer_builder.formatters import format_value
class DaysDisplayTests(unittest.TestCase):
 def test_rounding_and_word_forms(self):
  for value,expected in [(102.86,'103 дня'),(1,'1 день'),(2,'2 дня'),(5,'5 дней'),(11,'11 дней'),(21,'21 день'),(22,'22 дня'),(0,'0 дней'),(2.5,'3 дня')]:
   self.assertEqual(format_value(value=value,formatter='days',language='ru',options={'decimals':0}),expected)
 def test_default_is_unchanged(self):
  self.assertEqual(format_value(value=102.86,formatter='number',language='ru'),'102.86')
