import sys
import types
import unittest
from datetime import date
from unittest.mock import patch


class FakeResponse:
    data = []


class FakeQuery:
    def __init__(self):
        self.filters = []
        self.conflict = None

    def __getattr__(self, name):
        def method(*args, **kwargs):
            if name == "eq":
                self.filters.append((args[0], args[1]))
            if name == "upsert":
                self.conflict = kwargs.get("on_conflict")
            if name == "execute":
                return FakeResponse()
            return self

        return method


class FakeSupabase:
    def __init__(self):
        self.queries = []

    def table(self, _table_name):
        query = FakeQuery()
        self.queries.append(query)
        return query


fake_db_client = types.ModuleType("db.client")
fake_db_client.supabase = FakeSupabase()
sys.modules.setdefault("db.client", fake_db_client)

from metrics.builders import metrics_orders_daily
from normalized import normalized_wb_orders
from snapshots import snapshots_orders_daily


class OrdersTenantIsolationTests(unittest.TestCase):
    def test_snapshot_query_is_tenant_scoped(self):
        fake = FakeSupabase()
        snapshots_orders_daily.supabase = fake

        snapshots_orders_daily.fetch_orders_for_dates(
            [date(2026, 8, 12)],
            user_id=7,
            shop_id=9,
            marketplace="wb",
        )

        self.assertIn(("user_id", 7), fake.queries[0].filters)
        self.assertIn(("shop_id", 9), fake.queries[0].filters)
        self.assertIn(("marketplace", "wb"), fake.queries[0].filters)

    def test_metric_query_is_tenant_scoped(self):
        fake = FakeSupabase()
        metrics_orders_daily.supabase = fake

        metrics_orders_daily.fetch_snapshots_for_metric_dates(
            [date(2026, 8, 12)],
            user_id=7,
            shop_id=9,
            marketplace="wb",
        )

        self.assertIn(("user_id", 7), fake.queries[0].filters)
        self.assertIn(("shop_id", 9), fake.queries[0].filters)
        self.assertIn(("marketplace", "wb"), fake.queries[0].filters)

    def test_jobs_require_complete_tenant_context(self):
        with self.assertRaisesRegex(ValueError, "shop_id"):
            snapshots_orders_daily.require_tenant_context({"user_id": 7})

        with self.assertRaisesRegex(ValueError, "user_id"):
            metrics_orders_daily.require_tenant_context({"shop_id": 9})

    def test_snapshot_coverage_is_tenant_scoped(self):
        with patch.object(
            snapshots_orders_daily,
            "get_dates_to_build",
            return_value=[],
        ) as coverage:
            snapshots_orders_daily.run_snapshot_job(
                {"user_id": 7, "shop_id": 9, "marketplace": "wb"},
                state=None,
                registry_entry={},
            )

        self.assertEqual(coverage.call_args.kwargs["user_id"], 7)
        self.assertEqual(coverage.call_args.kwargs["shop_id"], 9)
        self.assertEqual(coverage.call_args.kwargs["marketplace"], "wb")

    def test_metric_coverage_is_tenant_scoped(self):
        with patch.object(
            metrics_orders_daily,
            "get_dates_to_build",
            return_value=[],
        ) as coverage:
            metrics_orders_daily.run_metric_job(
                {"user_id": 7, "shop_id": 9, "marketplace": "wb"},
                state=None,
                registry_entry={},
            )

        self.assertEqual(coverage.call_args.kwargs["user_id"], 7)
        self.assertEqual(coverage.call_args.kwargs["shop_id"], 9)
        self.assertEqual(coverage.call_args.kwargs["marketplace"], "wb")

    def test_normalized_order_rejects_missing_tenant(self):
        row = normalized_wb_orders.build_normalized_order(
            {
                "payload": {
                    "srid": "order-1",
                    "date": "2026-08-12T10:00:00Z",
                }
            }
        )
        self.assertIsNone(row)

    def test_normalized_upsert_uses_tenant_conflict_key(self):
        fake = FakeSupabase()
        normalized_wb_orders.supabase = fake

        normalized_wb_orders.upsert_orders(
            [
                {
                    "user_id": 7,
                    "shop_id": 9,
                    "marketplace": "wb",
                    "srid": "order-1",
                }
            ]
        )

        self.assertEqual(
            fake.queries[0].conflict,
            "user_id,shop_id,marketplace,srid",
        )


if __name__ == "__main__":
    unittest.main()
