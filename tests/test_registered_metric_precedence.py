import unittest
from unittest.mock import patch
from ai_chat.routing.metrics import MetricMatch

class RegisteredMetricPrecedenceTests(unittest.TestCase):
 def test_fuzzy_conversion_alias_does_not_override_cart_decline(self):
  from ai_chat.routing.route import _route_request
  semantic={'dataset':'funnel','metric':'cart_count','analysis':'compare','direction':'negative'}
  with patch('ai_chat.routing.llm_fallback.resolve_buyer_questions',return_value=None),patch('ai_chat.routing.route.resolve_metrics',return_value=[MetricMatch('funnel','conversion_decline','product','у каких товаров упала конверсия',80)]),patch('ai_chat.routing.llm_fallback.resolve_funnel_change',return_value=semantic):
   r=_route_request('У каких товаров упали корзины?',memory={},request_context={'user_id':1,'shop_id':1})
  self.assertEqual(r,semantic)
