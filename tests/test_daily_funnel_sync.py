import unittest
from contextlib import ExitStack
from datetime import date
from unittest.mock import patch
from ingestion.marketplaces.wb.sync import sync_funnel as funnel
from ingestion.orchestrators.sync_all import DEFAULT_MAX_JOBS


class DailyFunnelSyncTests(unittest.TestCase):
    def run_job(self, kind):
        with ExitStack() as stack:
            stack.enter_context(patch.object(funnel, 'get_marketplace_product_ids', return_value=[123]))
            stack.enter_context(patch.object(funnel, 'is_raw_funnel_day_loaded', side_effect=lambda **kw: kw['day'] != '2026-10-15'))
            delete = stack.enter_context(patch.object(funnel, 'delete_raw_funnel_day'))
            api = stack.enter_context(patch.object(funnel, 'get_sales_funnel_products', return_value={}))
            stack.enter_context(patch.object(funnel, 'extract_funnel_items', return_value=[]))
            stack.enter_context(patch.object(funnel, 'insert_raw_funnel_items', return_value=1))
            state = stack.enter_context(patch.object(funnel, 'upsert_sync_state'))
            stack.enter_context(patch.object(funnel.AdaptiveRateLimiter, 'sleep'))
            result = funnel.run_sync_job(dict(user_id=1, shop_id=1, marketplace='wb', job_type=kind,
                date_from='2026-10-17', date_to='2026-10-17'), dict(api_token='test'), dict(daily_window_days=3))
            return result, api.call_args_list, state.call_args.kwargs, delete.call_args_list

    def test_auto_loads_completed_day_and_recovers_gap(self):
        result, calls, state, deletes = self.run_job('auto_sync')
        self.assertEqual([c.kwargs['date_from'] for c in calls], ['2026-10-15', '2026-10-16'])
        self.assertEqual((state['date_from'], state['date_to']), (date(2026,10,14),date(2026,10,16)))
        self.assertEqual(result['days_skipped'], 1)
        self.assertTrue(all(c.kwargs['user_id']==1 and c.kwargs['shop_id']==1 for c in deletes))

    def test_explicit_repair_keeps_exact_requested_dates(self):
        result, calls, state, _ = self.run_job('coverage_repair')
        self.assertFalse(calls)
        self.assertEqual((state['date_from'],state['date_to']), (date(2026,10,17),date(2026,10,17)))
        self.assertEqual(result['days_skipped'],1)

    def test_daily_budget_covers_all_registered_sources(self):
        self.assertGreaterEqual(DEFAULT_MAX_JOBS, 100)

class DailyAdvertisingSyncTests(unittest.TestCase):
    def test_refreshes_last_completed_day_even_when_raw_exists(self):
        from ingestion.marketplaces.wb.sync import sync_ads_stats as ads
        for ids in ([], [123]):
            with self.subTest(ids=ids), ExitStack() as stack:
                stack.enter_context(patch.object(ads,'load_advert_ids',return_value=ids))
                stack.enter_context(patch.object(ads,'is_raw_ads_stats_day_loaded',return_value=True))
                stack.enter_context(patch.object(ads,'delete_raw_ads_stats_day'))
                insert=stack.enter_context(patch.object(ads,'insert_raw_ads_stats',return_value=1))
                api=stack.enter_context(patch.object(ads,'get_ads_fullstats',return_value={}))
                state=stack.enter_context(patch.object(ads,'upsert_sync_state'))
                result=ads.run_sync_job(dict(user_id=1,shop_id=1,job_type='auto_sync',date_from='2026-10-17',date_to='2026-10-17'),{},dict(daily_window_days=3))
                self.assertEqual(insert.call_args.kwargs['day'],'2026-10-16')
                self.assertEqual(state.call_args.kwargs['date_to'],date(2026,10,16))
                self.assertEqual(result['days_loaded'],1)
                if ids:self.assertEqual(api.call_args.kwargs['date_to'],'2026-10-16')
