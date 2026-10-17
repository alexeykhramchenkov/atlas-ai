import unittest
from unittest.mock import patch
from ai_chat.analysis.analysis_type.compare import run
from ai_chat.answer_builder.formatters import format_value

class FunnelComparison(unittest.TestCase):
    def test_increase_decrease_and_zero(self):
        result=run(current={'a':115,'b':93,'c':0,'d':2,'e':0},previous={'a':100,'b':100,'c':0,'d':0,'e':2},metrics=['a','b','c','d','e'])
        self.assertEqual([result[k]['change_pct'] for k in result],[15,-7,0,None,-100])
        self.assertEqual(result['b']['change_abs'],-7)
    def test_executor_two_equal_adjacent_periods_and_product_scope(self):
        from ai_chat.executor import Executor
        for product in (None,'wb_236348866'):
            facts={'start_date':'2026-10-09','end_date':'2026-10-15','products':[{'title':'Dress'}],**{f:10 for f in ('open_count','cart_count','order_count','buyout_count','cancel_count')}}
            previous={**facts,'start_date':'2026-10-02','end_date':'2026-10-08','open_count':5}
            with patch('ai_chat.internal_tools.get_funnel.get_funnel',side_effect=[facts,previous]) as getter:
                result=Executor(object()).execute({'dataset':'funnel','analysis':'compare','metric':'funnel','entity':'product' if product else 'store','user_id':9,'shop_id':8,'product_key':product,'period_days':7})
            self.assertEqual(result['comparison']['open_count']['change_pct'],100)
            calls=getter.call_args_list
            self.assertEqual(calls[1].kwargs['start_date'],'2026-10-02')
            self.assertEqual(calls[1].kwargs['end_date'],'2026-10-08')
            for call in calls:
                self.assertEqual(call.kwargs['product_key'],product)
                self.assertEqual(call.kwargs['shop_id'],8)
                self.assertEqual(call.kwargs['user_id'],9)
    def test_rule_config_controls_zero_wording(self):
        options={'zero_baseline':'ZERO','unchanged':'SAME'}
        for pct,expected in [(None,'ZERO'),(0,'SAME'),(15,'+15%'),(-7,'−7%')]:
            self.assertEqual(format_value(value={'change_pct':pct},formatter='change',language='ru',options=options),expected)
