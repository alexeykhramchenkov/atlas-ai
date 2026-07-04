

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


STOCKS_TABLE = "metrics_stocks_daily"
ORDERS_TABLE = "metrics_orders_daily"
EVENT_TYPE = "out_of_stock_risk"
EVENT_DOMAIN = "inventory"
EVENT_GROUP = "risk"
ENTITY_TYPE = "product"


@dataclass
class OutOfStockRiskDetector:
    name: str = EVENT_TYPE
    user_id: int = 1
    shop_id: int = 1
    marketplace: str = "wb"
    lookback_days: int = 7
    risk_days_threshold: float = 7.0
    critical_days_threshold: float = 3.0
    min_avg_daily_orders: float = 0.2
    min_stock_qty: float = 1.0
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
    def severity_label(priority_score: float) -> str:
        if priority_score >= 0.75:
            return "critical"
        if priority_score >= 0.40:
            return "warning"
        return "info"

    def get_stock_qty(self, row: Dict[str, Any]) -> float:
        for key in (
            "total_quantity",
            "total_quantity_full",
            "quantity",
            "stock_qty",
            "stock_quantity",
            "available_quantity",
            "current_stock",
        ):
            if key in row and row.get(key) is not None:
                return self.safe_float(row.get(key))
        return 0.0

    def fetch_latest_date(self) -> Optional[str]:
        response = (
            supabase.table(STOCKS_TABLE)
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
            supabase.table(STOCKS_TABLE)
            .select("*")
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
            "stock": {
                "current_qty": 0.0,
                "days_left": None,
            },
            "sales_velocity": {
                "lookback_days": self.lookback_days,
                "orders": 0.0,
                "revenue": 0.0,
                "aov": 0.0,
                "avg_daily_orders": 0.0,
            },
            "store": {
                "previous_total_orders": 0.0,
                "previous_total_revenue": 0.0,
                "orders_share_pct": 0.0,
                "revenue_share_pct": 0.0,
            },
            "risk": {
                "risk_days_threshold": self.risk_days_threshold,
                "critical_days_threshold": self.critical_days_threshold,
                "is_out_of_stock": False,
                "is_critical": False,
            },
            "impact": {
                "potential_lost_orders": 0.0,
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
        previous_end = metric_date
        previous_start = previous_end - timedelta(days=self.lookback_days - 1)

        contexts: Dict[str, Dict[str, Any]] = {
            product_key: self.empty_context()
            for product_key in product_keys
        }

        for row in valid_rows:
            product_key = str(row.get("product_key"))
            context = contexts.get(product_key)
            if not context:
                continue
            context["stock"]["current_qty"] = round(self.get_stock_qty(row), 2)
            context["nm_id"] = row.get("marketplace_product_id")
            context["product_key"] = product_key

        orders_query = (
            supabase.table(ORDERS_TABLE)
            .select("product_key,orders_count,net_order_value,snapshot_date")
            .eq("user_id", self.user_id)
            .eq("shop_id", self.shop_id)
            .eq("marketplace", self.marketplace)
            .gte("snapshot_date", previous_start.isoformat())
            .lte("snapshot_date", previous_end.isoformat())
        )
        if product_keys:
            orders_query = orders_query.in_("product_key", list(product_keys))
        orders_response = orders_query.execute()

        previous_total_orders = 0.0
        previous_total_revenue = 0.0

        for item in orders_response.data or []:
            product_key = str(item.get("product_key"))
            orders = self.safe_float(item.get("orders_count"))
            revenue = self.safe_float(item.get("net_order_value"))

            previous_total_orders += orders
            previous_total_revenue += revenue

            if product_key in contexts:
                contexts[product_key]["sales_velocity"]["orders"] += orders
                contexts[product_key]["sales_velocity"]["revenue"] += revenue

        for context in contexts.values():
            stock = context["stock"]
            velocity = context["sales_velocity"]
            store = context["store"]
            risk = context["risk"]
            impact = context["impact"]

            current_qty = self.safe_float(stock.get("current_qty"))
            orders = self.safe_float(velocity.get("orders"))
            revenue = self.safe_float(velocity.get("revenue"))
            avg_daily_orders = orders / self.lookback_days if self.lookback_days > 0 else 0.0
            aov = revenue / orders if orders > 0 else 0.0
            days_left = current_qty / avg_daily_orders if avg_daily_orders > 0 else None
            days_left_for_impact = days_left if days_left is not None else self.risk_days_threshold
            potential_lost_days = max(self.risk_days_threshold - days_left_for_impact, 0.0)
            potential_lost_orders = potential_lost_days * avg_daily_orders
            impact_money = potential_lost_orders * aov
            orders_share_pct = orders / previous_total_orders * 100 if previous_total_orders > 0 else 0.0
            revenue_share_pct = revenue / previous_total_revenue * 100 if previous_total_revenue > 0 else 0.0

            stock["current_qty"] = round(current_qty, 2)
            stock["days_left"] = round(days_left, 2) if days_left is not None else None

            velocity.update({
                "orders": round(orders, 2),
                "revenue": round(revenue, 2),
                "aov": round(aov, 2),
                "avg_daily_orders": round(avg_daily_orders, 4),
            })

            store.update({
                "previous_total_orders": round(previous_total_orders, 2),
                "previous_total_revenue": round(previous_total_revenue, 2),
                "orders_share_pct": round(orders_share_pct, 2),
                "revenue_share_pct": round(revenue_share_pct, 2),
            })

            risk.update({
                "is_out_of_stock": current_qty <= 0,
                "is_critical": days_left is not None and days_left <= self.critical_days_threshold,
            })

            impact.update({
                "potential_lost_orders": round(potential_lost_orders, 2),
                "money": round(impact_money, 2),
            })

        print(
            "Stock risk window:",
            f"orders={previous_start.isoformat()}..{previous_end.isoformat()}",
            f"stock_date={metric_date.isoformat()}",
        )
        print(f"Stock risk contexts loaded: {len(contexts)}")
        return contexts

    def calculate_priority(self, context: Dict[str, Any]) -> Dict[str, Any]:
        stock = context.get("stock", {})
        velocity = context.get("sales_velocity", {})
        store = context.get("store", {})
        risk = context.get("risk", {})
        impact = context.get("impact", {})

        current_qty = self.safe_float(stock.get("current_qty"))
        days_left_value = stock.get("days_left")
        days_left = self.safe_float(days_left_value) if days_left_value is not None else 9999.0
        avg_daily_orders = self.safe_float(velocity.get("avg_daily_orders"))
        orders = self.safe_float(velocity.get("orders"))
        aov = self.safe_float(velocity.get("aov"))
        impact_money = self.safe_float(impact.get("money"))
        revenue_share_pct = self.safe_float(store.get("revenue_share_pct"))

        if current_qty <= 0 and avg_daily_orders > 0:
            severity_score = 1.0
        elif days_left <= self.critical_days_threshold:
            severity_score = 0.90
        elif days_left <= self.risk_days_threshold:
            severity_score = min((self.risk_days_threshold - days_left) / self.risk_days_threshold + 0.35, 0.85)
        else:
            severity_score = 0.0

        impact_reference_money = self.impact_reference_orders * aov if aov > 0 else 1.0
        impact_score = min(impact_money / impact_reference_money, 1.0) if impact_reference_money > 0 else 0.0
        share_score = min((revenue_share_pct / 100) / self.share_reference, 1.0) if self.share_reference > 0 else 0.0
        urgency_score = 1.0 if risk.get("is_out_of_stock") else 0.9 if risk.get("is_critical") else 0.6
        confidence_score = 0.95 if orders >= 30 else 0.75 if orders >= 10 else 0.60

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
            stock = context.get("stock", {})
            velocity = context.get("sales_velocity", {})
            store = context.get("store", {})

            current_qty = self.safe_float(stock.get("current_qty"))
            days_left = stock.get("days_left")
            avg_daily_orders = self.safe_float(velocity.get("avg_daily_orders"))

            if current_qty < self.min_stock_qty:
                pass
            elif days_left is None or days_left > self.risk_days_threshold:
                continue

            if avg_daily_orders < self.min_avg_daily_orders:
                continue
            if velocity.get("orders", 0) <= 0:
                continue
            if velocity.get("revenue", 0) <= 0:
                continue
            if (store.get("orders_share_pct", 0) / 100) < self.min_orders_share:
                continue
            if (store.get("revenue_share_pct", 0) / 100) < self.min_revenue_share:
                continue

            priority = self.calculate_priority(context)
            if priority.get("severity_score", 0) <= 0:
                continue

            context["priority"] = priority
            row.update(context)
            result.append(row)

        return result

    def build_event(self, row: Dict[str, Any]) -> DetectorEvent:
        product_key = row.get("product_key")
        nm_id = row.get("nm_id") or row.get("marketplace_product_id")
        metric_date = row.get("snapshot_date") or self.current_date
        stock = row.get("stock", {})
        velocity = row.get("sales_velocity", {})
        store = row.get("store", {})
        risk = row.get("risk", {})
        impact = row.get("impact", {})
        priority = row.get("priority", {})

        # 1. Replace title/description block
        title = EVENT_TYPE
        description = ""

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
            title=title,
            description=description,
            source_table=STOCKS_TABLE,
            payload={
                "product_key": product_key,
                "nm_id": nm_id,
                "lookback_days": self.lookback_days,
                "stock": stock,
                "sales_velocity": velocity,
                "store": store,
                "risk": risk,
                "impact": impact,
                "priority": priority,
                "event_code": EVENT_TYPE,
                "event_domain": EVENT_DOMAIN,
                "event_group": EVENT_GROUP,
                "entity_type": ENTITY_TYPE,
            },
            meta={
                "detector": EVENT_TYPE,
                "text_generated": False,
                "interpretation_source": "payload",
                "lookback_days": self.lookback_days,
                "cooldown_days": self.cooldown_days,
                "risk_days_threshold": self.risk_days_threshold,
                "critical_days_threshold": self.critical_days_threshold,
                "min_avg_daily_orders": self.min_avg_daily_orders,
                "min_stock_qty": self.min_stock_qty,
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
        print(f"Risk days threshold: {self.risk_days_threshold}")
        print(f"Critical days threshold: {self.critical_days_threshold}")
        print(f"Min avg daily orders: {self.min_avg_daily_orders}")
        return [self.build_event(row) for row in rows]


def main() -> None:
    detector = OutOfStockRiskDetector()
    events = detector.run()
    write_events(events)
    print(f"Events written: {len(events)}")


if __name__ == "__main__":
    main()