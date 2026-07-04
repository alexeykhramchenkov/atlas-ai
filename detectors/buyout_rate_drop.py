

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from detectors.detector_types import DetectorEvent
from detectors.orchestrators.detector_event_writer import write_events


SOURCE_TABLE = "metrics_funnel_daily"
ORDERS_TABLE = "metrics_orders_daily"
EVENT_TYPE = "buyout_rate_drop"
EVENT_DOMAIN = "conversion"
EVENT_GROUP = "funnel"
ENTITY_TYPE = "product"


@dataclass
class BuyoutRateDropDetector:
    name: str = EVENT_TYPE
    user_id: int = 1
    shop_id: int = 1
    marketplace: str = "wb"
    lookback_days: int = 7
    warning_threshold: float = -0.30
    critical_threshold: float = -0.60
    min_sample_size: int = 3
    min_orders_share: float = 0.0
    min_revenue_share: float = 0.0
    alert_threshold: float = 0.75
    share_reference: float = 0.20
    impact_reference_orders: float = 30.0
    priority_multiplier: float = 1.0
    check_only_latest_date: bool = True
    cooldown_days: int = 3
    current_date: Optional[str] = None

    severity_weight: float = 0.30
    impact_weight: float = 0.30
    share_weight: float = 0.20
    urgency_weight: float = 0.15
    confidence_weight: float = 0.05

    def apply_rule(self) -> bool:
        return True

    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(float(value or default))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def severity_label(priority_score: float) -> str:
        if priority_score >= 0.75:
            return "critical"
        if priority_score >= 0.40:
            return "warning"
        return "info"

    def fetch_latest_date(self) -> Optional[str]:
        response = (
            supabase.table(SOURCE_TABLE)
            .select("snapshot_date")
            .eq("user_id", self.user_id)
            .eq("shop_id", self.shop_id)
            .eq("marketplace", self.marketplace)
            .order("snapshot_date", desc=True)
            .limit(1)
            .execute()
        )
        if not response.data:
            return None
        return str(response.data[0].get("snapshot_date"))

    def fetch_rows(self) -> List[Dict[str, Any]]:
        if not self.current_date:
            self.current_date = self.fetch_latest_date()
        if not self.current_date:
            return []

        query = (
            supabase.table(SOURCE_TABLE)
            .select("user_id,shop_id,marketplace,snapshot_date,product_key,marketplace_product_id,order_count,buyout_count")
            .eq("user_id", self.user_id)
            .eq("shop_id", self.shop_id)
            .eq("marketplace", self.marketplace)
        )

        if self.check_only_latest_date:
            query = query.eq("snapshot_date", self.current_date)

        response = query.execute()
        return response.data or []

    def empty_context(self) -> Dict[str, Any]:
        return {
            "previous_period": {
                "orders": 0.0,
                "buyouts": 0.0,
                "revenue": 0.0,
                "aov": 0.0,
                "buyout_rate": 0.0,
            },
            "current_period": {
                "orders": 0.0,
                "buyouts": 0.0,
                "revenue": 0.0,
                "buyout_rate": 0.0,
            },
            "expected": {
                "buyouts": 0.0,
                "lost_buyouts": 0.0,
                "lost_revenue": 0.0,
            },
            "store": {
                "previous_total_orders": 0.0,
                "previous_total_revenue": 0.0,
                "orders_share_pct": 0.0,
                "revenue_share_pct": 0.0,
            },
            "change": {
                "buyout_rate_change_pct": 0.0,
            },
            "impact": {
                "money": 0.0,
            },
        }

    def fetch_period_contexts(self, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        valid_rows = [
            row for row in rows
            if row.get("product_key")
            and row.get("user_id") is not None
            and row.get("shop_id") is not None
            and row.get("marketplace")
            and row.get("snapshot_date")
        ]
        if not valid_rows:
            return {}

        product_keys: Set[str] = {str(row.get("product_key")) for row in valid_rows if row.get("product_key")}
        sample = valid_rows[0]
        metric_date = date.fromisoformat(str(sample.get("snapshot_date")))

        current_end = metric_date
        current_start = current_end - timedelta(days=self.lookback_days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=self.lookback_days - 1)

        funnel_query = (
            supabase.table(SOURCE_TABLE)
            .select("product_key,marketplace_product_id,snapshot_date,order_count,buyout_count")
            .eq("user_id", self.user_id)
            .eq("shop_id", self.shop_id)
            .eq("marketplace", self.marketplace)
            .gte("snapshot_date", previous_start.isoformat())
            .lte("snapshot_date", current_end.isoformat())
        )
        if product_keys:
            funnel_query = funnel_query.in_("product_key", list(product_keys))
        funnel_response = funnel_query.execute()

        orders_query = (
            supabase.table(ORDERS_TABLE)
            .select("product_key,orders_count,net_order_value,snapshot_date")
            .eq("user_id", self.user_id)
            .eq("shop_id", self.shop_id)
            .eq("marketplace", self.marketplace)
            .gte("snapshot_date", previous_start.isoformat())
            .lte("snapshot_date", current_end.isoformat())
        )
        orders_response = orders_query.execute()

        contexts: Dict[str, Dict[str, Any]] = {
            product_key: self.empty_context()
            for product_key in product_keys
        }
        nm_ids: Dict[str, Any] = {}

        for item in funnel_response.data or []:
            product_key = str(item.get("product_key"))
            if product_key not in contexts:
                continue

            item_date_value = item.get("snapshot_date")
            if not item_date_value:
                continue

            item_date = date.fromisoformat(str(item_date_value))
            orders = self.safe_float(item.get("order_count"))
            buyouts = self.safe_float(item.get("buyout_count"))
            nm_ids[product_key] = item.get("marketplace_product_id") or nm_ids.get(product_key)

            if previous_start <= item_date <= previous_end:
                contexts[product_key]["previous_period"]["orders"] += orders
                contexts[product_key]["previous_period"]["buyouts"] += buyouts

            if current_start <= item_date <= current_end:
                contexts[product_key]["current_period"]["orders"] += orders
                contexts[product_key]["current_period"]["buyouts"] += buyouts

        previous_total_orders = 0.0
        previous_total_revenue = 0.0

        for item in orders_response.data or []:
            item_date_value = item.get("snapshot_date")
            if not item_date_value:
                continue

            item_date = date.fromisoformat(str(item_date_value))
            product_key = str(item.get("product_key"))
            orders = self.safe_float(item.get("orders_count"))
            revenue = self.safe_float(item.get("net_order_value"))

            if previous_start <= item_date <= previous_end:
                previous_total_orders += orders
                previous_total_revenue += revenue
                if product_key in contexts:
                    contexts[product_key]["previous_period"]["revenue"] += revenue

            if current_start <= item_date <= current_end and product_key in contexts:
                contexts[product_key]["current_period"]["revenue"] += revenue

        for product_key, context in contexts.items():
            previous_period = context["previous_period"]
            current_period = context["current_period"]
            expected = context["expected"]
            store = context["store"]
            change = context["change"]
            impact = context["impact"]

            previous_orders = self.safe_float(previous_period.get("orders"))
            previous_buyouts = self.safe_float(previous_period.get("buyouts"))
            previous_revenue = self.safe_float(previous_period.get("revenue"))
            current_orders = self.safe_float(current_period.get("orders"))
            current_buyouts = self.safe_float(current_period.get("buyouts"))

            previous_buyout_rate = previous_buyouts / previous_orders if previous_orders > 0 else 0.0
            current_buyout_rate = current_buyouts / current_orders if current_orders > 0 else 0.0
            buyout_rate_change_pct = (
                (current_buyout_rate - previous_buyout_rate) / previous_buyout_rate
                if previous_buyout_rate > 0
                else 0.0
            )

            previous_aov = previous_revenue / previous_orders if previous_orders > 0 else 0.0
            expected_buyouts = current_orders * previous_buyout_rate
            lost_buyouts = max(expected_buyouts - current_buyouts, 0.0)
            impact_money = lost_buyouts * previous_aov
            orders_share_pct = previous_orders / previous_total_orders * 100 if previous_total_orders > 0 else 0.0
            revenue_share_pct = previous_revenue / previous_total_revenue * 100 if previous_total_revenue > 0 else 0.0

            previous_period.update({
                "orders": round(previous_orders, 2),
                "buyouts": round(previous_buyouts, 2),
                "revenue": round(previous_revenue, 2),
                "aov": round(previous_aov, 2),
                "buyout_rate": round(previous_buyout_rate, 4),
            })
            current_period.update({
                "orders": round(current_orders, 2),
                "buyouts": round(current_buyouts, 2),
                "buyout_rate": round(current_buyout_rate, 4),
            })
            expected.update({
                "buyouts": round(expected_buyouts, 2),
                "lost_buyouts": round(lost_buyouts, 2),
                "lost_revenue": round(impact_money, 2),
            })
            store.update({
                "previous_total_orders": round(previous_total_orders, 2),
                "previous_total_revenue": round(previous_total_revenue, 2),
                "orders_share_pct": round(orders_share_pct, 2),
                "revenue_share_pct": round(revenue_share_pct, 2),
            })
            change["buyout_rate_change_pct"] = round(buyout_rate_change_pct, 4)
            impact["money"] = round(impact_money, 2)
            context["product_key"] = product_key
            context["nm_id"] = nm_ids.get(product_key)

        print(
            "Buyout period windows:",
            f"previous={previous_start.isoformat()}..{previous_end.isoformat()}",
            f"current={current_start.isoformat()}..{current_end.isoformat()}",
        )
        print(f"Buyout period contexts loaded: {len(contexts)}")
        return contexts

    def calculate_priority(self, context: Dict[str, Any]) -> Dict[str, Any]:
        change = abs(self.safe_float(context.get("change", {}).get("buyout_rate_change_pct")))
        impact_money = self.safe_float(context.get("impact", {}).get("money"))
        revenue_share_pct = self.safe_float(context.get("store", {}).get("revenue_share_pct"))
        previous_orders = self.safe_float(context.get("previous_period", {}).get("orders"))
        current_buyout_rate = self.safe_float(context.get("current_period", {}).get("buyout_rate"))

        if change >= abs(self.critical_threshold):
            severity_score = 1.0
        else:
            severity_score = min(change / abs(self.critical_threshold), 1.0)

        previous_aov = self.safe_float(context.get("previous_period", {}).get("aov"))
        impact_reference_money = self.impact_reference_orders * previous_aov if previous_aov > 0 else 1.0
        impact_score = min(impact_money / impact_reference_money, 1.0) if impact_reference_money > 0 else 0.0
        share_score = min((revenue_share_pct / 100) / self.share_reference, 1.0) if self.share_reference > 0 else 0.0
        urgency_score = 1.0 if current_buyout_rate == 0 else 0.7 if change >= 0.5 else 0.5
        confidence_score = 0.95 if previous_orders >= 30 else 0.75 if previous_orders >= 10 else 0.60

        priority_score = (
            severity_score * self.severity_weight
            + impact_score * self.impact_weight
            + share_score * self.share_weight
            + urgency_score * self.urgency_weight
            + confidence_score * self.confidence_weight
        ) * self.priority_multiplier

        priority_score = min(round(priority_score, 4), 1.0)

        return {
            "severity_score": round(severity_score, 4),
            "impact_score": round(impact_score, 4),
            "share_score": round(share_score, 4),
            "urgency_score": round(urgency_score, 4),
            "confidence_score": round(confidence_score, 4),
            "priority_score": priority_score,
            "severity_label": self.severity_label(priority_score),
        }

    def filter_rows_by_rule(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        contexts = self.fetch_period_contexts(rows)

        for row in rows:
            product_key = row.get("product_key")
            if not product_key:
                continue

            context = contexts.get(str(product_key), self.empty_context())
            previous_period = context.get("previous_period", {})
            current_period = context.get("current_period", {})
            change = context.get("change", {})
            impact = context.get("impact", {})

            if previous_period.get("orders", 0) < self.min_sample_size:
                continue
            if previous_period.get("revenue", 0) <= 0:
                continue
            if current_period.get("orders", 0) <= 0:
                continue
            if previous_period.get("buyout_rate", 0) <= 0:
                continue
            if change.get("buyout_rate_change_pct", 0) >= self.warning_threshold:
                continue
            if impact.get("money", 0) <= 0:
                continue
            if (context.get("store", {}).get("orders_share_pct", 0) / 100) < self.min_orders_share:
                continue
            if (context.get("store", {}).get("revenue_share_pct", 0) / 100) < self.min_revenue_share:
                continue

            priority = self.calculate_priority(context)
            context["priority"] = priority
            row.update(context)
            result.append(row)

        return result

    def build_event(self, row: Dict[str, Any]) -> DetectorEvent:
        product_key = row.get("product_key")
        nm_id = row.get("nm_id") or row.get("marketplace_product_id")
        metric_date = row.get("snapshot_date") or self.current_date
        previous_period = row.get("previous_period", {})
        current_period = row.get("current_period", {})
        expected = row.get("expected", {})
        store = row.get("store", {})
        change = row.get("change", {})
        impact = row.get("impact", {})
        priority = row.get("priority", {})

        change_pct = self.safe_float(change.get("buyout_rate_change_pct"))
        impact_money = self.safe_float(impact.get("money"))
        previous_rate = self.safe_float(previous_period.get("buyout_rate"))
        current_rate = self.safe_float(current_period.get("buyout_rate"))

        return DetectorEvent(
            user_id=self.user_id,
            shop_id=self.shop_id,
            marketplace=self.marketplace,
            event_domain=EVENT_DOMAIN,
            event_type=EVENT_TYPE,
            event_group=EVENT_GROUP,
            entity_type=ENTITY_TYPE,
            entity_id=str(product_key),
            sub_entity_type=None,
            sub_entity_id=None,
            severity=priority.get("severity_score", 0),
            confidence=priority.get("confidence_score", 0),
            priority=priority.get("priority_score", 0),
            is_alert=priority.get("priority_score", 0) >= self.alert_threshold,
            event_date=date.fromisoformat(str(metric_date)),
            title="Падение выкупа",
            description=(
                f"Выкуп товара снизился на {round(abs(change_pct) * 100, 1)}% за последние {self.lookback_days} дней. "
                f"Было {round(previous_rate * 100, 2)}%, стало {round(current_rate * 100, 2)}%. "
                f"Оценка потерь: {round(impact_money, 2)}."
            ),
            source_table=SOURCE_TABLE,
            payload={
                "product_key": product_key,
                "nm_id": nm_id,
                "lookback_days": self.lookback_days,
                "previous_period": previous_period,
                "current_period": current_period,
                "expected": expected,
                "store": store,
                "change": change,
                "impact": impact,
                "priority": priority,
            },
            meta={
                "detector": EVENT_TYPE,
                "lookback_days": self.lookback_days,
                "cooldown_days": self.cooldown_days,
                "warning_threshold": self.warning_threshold,
                "critical_threshold": self.critical_threshold,
                "min_sample_size": self.min_sample_size,
                "alert_threshold": self.alert_threshold,
                "priority_multiplier": self.priority_multiplier,
                "priority_weights": {
                    "severity": self.severity_weight,
                    "impact": self.impact_weight,
                    "share": self.share_weight,
                    "urgency": self.urgency_weight,
                    "confidence": self.confidence_weight,
                },
                "impact_reference_orders": self.impact_reference_orders,
                "share_reference": self.share_reference,
                "check_only_latest_date": self.check_only_latest_date,
                "min_orders_share": self.min_orders_share,
                "min_revenue_share": self.min_revenue_share,
            },
        )

    def run(self) -> List[DetectorEvent]:
        if not self.apply_rule():
            print(f"Detector {self.name} is disabled by rule")
            return []

        rows = self.fetch_rows()
        print(f"Rows matched before rule filters: {len(rows)}")
        print("Period context mode: batched")
        rows = self.filter_rows_by_rule(rows)
        print(f"Rows matched after rule filters: {len(rows)}")
        print(f"Current date: {self.current_date or 'all dates'}")
        print(f"Lookback days: {self.lookback_days}")
        print(f"Warning threshold: {self.warning_threshold}")
        print(f"Min sample size: {self.min_sample_size}")
        return [self.build_event(row) for row in rows]


def main() -> None:
    detector = BuyoutRateDropDetector()
    events = detector.run()
    write_events(events)
    print(f"Events written: {len(events)}")


if __name__ == "__main__":
    main()