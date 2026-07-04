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
COSTS_TABLE = "normalized_product_costs"
EVENT_TYPE = "slow_moving_stock"
EVENT_DOMAIN = "inventory"
EVENT_GROUP = "slow_moving"
ENTITY_TYPE = "product"


@dataclass
class SlowMovingStockDetector:
    name: str = EVENT_TYPE
    user_id: int = 1
    shop_id: int = 1
    marketplace: str = "wb"
    lookback_days: int = 30
    min_stock_qty: float = 10.0
    min_orders_lookback: float = 1.0
    min_avg_daily_orders: float = 0.2
    days_to_sell_out_threshold: float = 90.0
    critical_days_to_sell_out: float = 365.0
    warning_days_to_sell_out: float = 180.0
    sell_through_threshold: float = 0.05
    alert_threshold: float = 0.75
    impact_reference_money: float = 100_000.0
    share_reference: float = 0.20
    priority_multiplier: float = 1.0
    check_only_latest_date: bool = True
    cooldown_days: int = 7
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

    def get_market_stock_value(self, row: Dict[str, Any]) -> float:
        for key in (
            "total_stock_value",
            "stock_value",
            "market_price_stock_value",
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
                "cost_price": 0.0,
                "stock_cost_value": 0.0,
                "market_price_stock_value": 0.0,
            },
            "sales_velocity": {
                "lookback_days": self.lookback_days,
                "orders": 0.0,
                "revenue": 0.0,
                "aov": 0.0,
                "avg_daily_orders": 0.0,
            },
            "turnover": {
                "days_to_sell_out": None,
                "sell_through_rate": 0.0,
            },
            "store": {
                "total_orders": 0.0,
                "total_revenue": 0.0,
                "orders_share_pct": 0.0,
                "revenue_share_pct": 0.0,
            },
            "impact": {
                "money": 0.0,
                "frozen_stock_value": 0.0,
            },
            "reason": {
                "low_avg_daily_orders": False,
                "high_days_to_sell_out": False,
                "low_sell_through": False,
            },
        }

    def fetch_costs(self, product_keys: Set[str], metric_date: date) -> Dict[str, float]:
        if not product_keys:
            return {}

        query = (
            supabase.table(COSTS_TABLE)
            .select("product_key,cost_price,effective_from,effective_to,is_active")
            .eq("user_id", self.user_id)
            .eq("shop_id", self.shop_id)
            .eq("marketplace", self.marketplace)
            .in_("product_key", list(product_keys))
        )
        response = query.execute()

        costs: Dict[str, float] = {}
        for item in response.data or []:
            product_key = str(item.get("product_key"))
            if product_key not in product_keys:
                continue

            is_active = bool(item.get("is_active"))
            effective_from_value = item.get("effective_from")
            effective_to_value = item.get("effective_to")

            effective_from = date.fromisoformat(str(effective_from_value)) if effective_from_value else None
            effective_to = date.fromisoformat(str(effective_to_value)) if effective_to_value else None

            date_matches = (
                (effective_from is None or effective_from <= metric_date)
                and (effective_to is None or effective_to >= metric_date)
            )

            if is_active or date_matches:
                cost_price = self.safe_float(item.get("cost_price"))
                if cost_price > 0:
                    costs[product_key] = cost_price

        return costs

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
        period_end = metric_date
        period_start = period_end - timedelta(days=self.lookback_days - 1)

        contexts: Dict[str, Dict[str, Any]] = {
            product_key: self.empty_context()
            for product_key in product_keys
        }

        for row in valid_rows:
            product_key = str(row.get("product_key"))
            context = contexts.get(product_key)
            if not context:
                continue
            current_qty = self.get_stock_qty(row)
            market_stock_value = self.get_market_stock_value(row)
            context["stock"]["current_qty"] = round(current_qty, 2)
            context["stock"]["market_price_stock_value"] = round(market_stock_value, 2)
            context["nm_id"] = row.get("marketplace_product_id")
            context["product_key"] = product_key

        costs = self.fetch_costs(product_keys, metric_date)

        orders_query = (
            supabase.table(ORDERS_TABLE)
            .select("product_key,orders_count,net_order_value,snapshot_date")
            .eq("user_id", self.user_id)
            .eq("shop_id", self.shop_id)
            .eq("marketplace", self.marketplace)
            .gte("snapshot_date", period_start.isoformat())
            .lte("snapshot_date", period_end.isoformat())
        )
        if product_keys:
            orders_query = orders_query.in_("product_key", list(product_keys))
        orders_response = orders_query.execute()

        total_orders = 0.0
        total_revenue = 0.0

        for item in orders_response.data or []:
            product_key = str(item.get("product_key"))
            orders = self.safe_float(item.get("orders_count"))
            revenue = self.safe_float(item.get("net_order_value"))
            total_orders += orders
            total_revenue += revenue
            if product_key in contexts:
                contexts[product_key]["sales_velocity"]["orders"] += orders
                contexts[product_key]["sales_velocity"]["revenue"] += revenue

        for product_key, context in contexts.items():
            stock = context["stock"]
            velocity = context["sales_velocity"]
            turnover = context["turnover"]
            store = context["store"]
            impact = context["impact"]
            reason = context["reason"]

            current_qty = self.safe_float(stock.get("current_qty"))
            market_stock_value = self.safe_float(stock.get("market_price_stock_value"))
            orders = self.safe_float(velocity.get("orders"))
            revenue = self.safe_float(velocity.get("revenue"))
            avg_daily_orders = orders / self.lookback_days if self.lookback_days > 0 else 0.0
            aov = revenue / orders if orders > 0 else 0.0
            days_to_sell_out = current_qty / avg_daily_orders if avg_daily_orders > 0 else None
            sell_through_rate = orders / (orders + current_qty) if (orders + current_qty) > 0 else 0.0
            cost_price = costs.get(product_key, 0.0)
            stock_cost_value = current_qty * cost_price if cost_price > 0 else market_stock_value
            orders_share_pct = orders / total_orders * 100 if total_orders > 0 else 0.0
            revenue_share_pct = revenue / total_revenue * 100 if total_revenue > 0 else 0.0

            stock.update({
                "current_qty": round(current_qty, 2),
                "cost_price": round(cost_price, 2),
                "stock_cost_value": round(stock_cost_value, 2),
                "market_price_stock_value": round(market_stock_value, 2),
            })
            velocity.update({
                "orders": round(orders, 2),
                "revenue": round(revenue, 2),
                "aov": round(aov, 2),
                "avg_daily_orders": round(avg_daily_orders, 4),
            })
            turnover.update({
                "days_to_sell_out": round(days_to_sell_out, 2) if days_to_sell_out is not None else None,
                "sell_through_rate": round(sell_through_rate, 4),
            })
            store.update({
                "total_orders": round(total_orders, 2),
                "total_revenue": round(total_revenue, 2),
                "orders_share_pct": round(orders_share_pct, 2),
                "revenue_share_pct": round(revenue_share_pct, 2),
            })
            impact.update({
                "money": round(stock_cost_value, 2),
                "frozen_stock_value": round(stock_cost_value, 2),
            })
            reason.update({
                "low_avg_daily_orders": avg_daily_orders < self.min_avg_daily_orders,
                "high_days_to_sell_out": days_to_sell_out is not None and days_to_sell_out > self.days_to_sell_out_threshold,
                "low_sell_through": sell_through_rate < self.sell_through_threshold,
            })

        print(
            "Slow moving stock window:",
            f"orders={period_start.isoformat()}..{period_end.isoformat()}",
            f"stock_date={metric_date.isoformat()}",
        )
        print(f"Slow moving contexts loaded: {len(contexts)}")
        return contexts

    def calculate_priority(self, context: Dict[str, Any]) -> Dict[str, Any]:
        stock = context.get("stock", {})
        velocity = context.get("sales_velocity", {})
        turnover = context.get("turnover", {})
        store = context.get("store", {})
        impact = context.get("impact", {})

        days_value = turnover.get("days_to_sell_out")
        days_to_sell_out = self.safe_float(days_value) if days_value is not None else 9999.0
        sell_through_rate = self.safe_float(turnover.get("sell_through_rate"))
        orders = self.safe_float(velocity.get("orders"))
        impact_money = self.safe_float(impact.get("money"))
        revenue_share_pct = self.safe_float(store.get("revenue_share_pct"))
        current_qty = self.safe_float(stock.get("current_qty"))

        if days_to_sell_out >= self.critical_days_to_sell_out:
            severity_score = 1.0
        elif days_to_sell_out >= self.warning_days_to_sell_out:
            severity_score = 0.75
        elif days_to_sell_out >= self.days_to_sell_out_threshold:
            severity_score = 0.50
        elif sell_through_rate < self.sell_through_threshold:
            severity_score = 0.35
        else:
            severity_score = 0.25

        if current_qty <= 0:
            severity_score = 0.0

        impact_score = min(impact_money / self.impact_reference_money, 1.0) if self.impact_reference_money > 0 else 0.0
        share_score = min((revenue_share_pct / 100) / self.share_reference, 1.0) if self.share_reference > 0 else 0.0
        urgency_score = 0.3 if days_to_sell_out >= self.critical_days_to_sell_out else 0.4 if days_to_sell_out >= self.warning_days_to_sell_out else 0.5
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
            turnover = context.get("turnover", {})
            reason = context.get("reason", {})

            current_qty = self.safe_float(stock.get("current_qty"))
            orders = self.safe_float(velocity.get("orders"))
            avg_daily_orders = self.safe_float(velocity.get("avg_daily_orders"))
            days_to_sell_out = turnover.get("days_to_sell_out")
            sell_through_rate = self.safe_float(turnover.get("sell_through_rate"))

            if current_qty < self.min_stock_qty:
                continue
            if orders < self.min_orders_lookback:
                continue
            if not (
                avg_daily_orders < self.min_avg_daily_orders
                or (days_to_sell_out is not None and days_to_sell_out > self.days_to_sell_out_threshold)
                or sell_through_rate < self.sell_through_threshold
            ):
                continue
            if not any(reason.values()):
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
        turnover = row.get("turnover", {})
        store = row.get("store", {})
        impact = row.get("impact", {})
        priority = row.get("priority", {})
        reason = row.get("reason", {})

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
            title=EVENT_TYPE,
            description="",
            source_table=STOCKS_TABLE,
            payload={
                "event_code": EVENT_TYPE,
                "event_domain": EVENT_DOMAIN,
                "event_group": EVENT_GROUP,
                "entity_type": ENTITY_TYPE,
                "product_key": product_key,
                "nm_id": nm_id,
                "lookback_days": self.lookback_days,
                "stock": stock,
                "sales_velocity": velocity,
                "turnover": turnover,
                "store": store,
                "impact": impact,
                "reason": reason,
                "priority": priority,
            },
            meta={
                "detector": EVENT_TYPE,
                "text_generated": False,
                "interpretation_source": "payload",
                "lookback_days": self.lookback_days,
                "cooldown_days": self.cooldown_days,
                "min_stock_qty": self.min_stock_qty,
                "min_orders_lookback": self.min_orders_lookback,
                "min_avg_daily_orders": self.min_avg_daily_orders,
                "days_to_sell_out_threshold": self.days_to_sell_out_threshold,
                "critical_days_to_sell_out": self.critical_days_to_sell_out,
                "warning_days_to_sell_out": self.warning_days_to_sell_out,
                "sell_through_threshold": self.sell_through_threshold,
                "alert_threshold": self.alert_threshold,
                "impact_reference_money": self.impact_reference_money,
                "share_reference": self.share_reference,
                "priority_multiplier": self.priority_multiplier,
                "priority_weights": {
                    "severity": self.severity_weight,
                    "impact": self.impact_weight,
                    "share": self.share_weight,
                    "urgency": self.urgency_weight,
                    "confidence": self.confidence_weight,
                },
                "check_only_latest_date": self.check_only_latest_date,
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
        print(f"Min stock qty: {self.min_stock_qty}")
        print(f"Min avg daily orders: {self.min_avg_daily_orders}")
        print(f"Days to sell out threshold: {self.days_to_sell_out_threshold}")
        print(f"Sell through threshold: {self.sell_through_threshold}")
        return [self.build_event(row) for row in rows]


def main() -> None:
    detector = SlowMovingStockDetector()
    events = detector.run()
    write_events(events)
    print(f"Events written: {len(events)}")


if __name__ == "__main__":
    main()