import unittest
from ai_chat.routing.period import resolve_period_days

class FunnelDefaultPeriod(unittest.TestCase):
 def test_domain_default_without_changing_other_defaults(self):
  self.assertEqual(resolve_period_days('Покажи воронку по магазину',default_period_days=7),7)
  self.assertEqual(resolve_period_days('Покажи воронку по магазину'),30)
 def test_explicit_period_wins(self):
  for question,days in [('за 30 дней',30),('за неделю',7),('за месяц',30),('за 14 дней',14)]:
   self.assertEqual(resolve_period_days(question,default_period_days=7),days)
