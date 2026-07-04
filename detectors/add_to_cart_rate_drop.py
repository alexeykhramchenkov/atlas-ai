import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from detectors.detector_types import DetectorEvent
from detectors.orchestrators.detector_event_writer import write_events


FUNNEL_TABLE = "metrics_funnel_daily"
ORDERS_TABLE = "metrics_orders_daily"
RULES_TABLE = "system_detector_rules"

EVENT_DOMAIN = "conversion"
EVENT_GROUP = "funnel"
EVENT_TYPE = "add_to_cart_rate_drop"

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_COOLDOWN_DAYS = 3
DEFAULT_WARNING_THRESHOLD = -0.30
DEFAULT_CRITICAL_THRESHOLD = -0.60
DEFAULT_MIN_SAMPLE_SIZE = 70
DEFAULT_MIN_PREVIOUS_CARTS = 3
DEFAULT_ALERT_THRESHOLD = 0.75

DEFAULT_SEVERITY_WEIGHT = 0.30
DEFAULT_IMPACT_WEIGHT = 0.30
DEFAULT_SHARE_WEIGHT = 0.20
DEFAULT_URGENCY_WEIGHT = 0.15
DEFAULT_CONFIDENCE_WEIGHT = 0.05
DEFAULT_PRIORITY_MULTIPLIER = 1.0

DEFAULT_IMPACT_REFERENCE_ORDERS = 30
DEFAULT_SHARE_REFERENCE = 0.20


class AddToCartRateDropDetector:
    name = EVENT_TYPE

    def __init__(self):
        self.rule: Optional[Dict[str, Any]] = None
        self.lookback_days = DEFAULT_LOOKBACK_DAYS
        self.cooldown_days = DEFAULT_COOLDOWN_DAYS
        self.warning_threshold = DEFAULT_WARNING_THRESHOLD
        self.critical_threshold = DEFAULT_CRITICAL_THRESHOLD
        self.min_sample_size = DEFAULT_MIN_SAMPLE_SIZE
        self.min_previous_carts = DEFAULT_MIN_PREVIOUS_CARTS
        self.alert_threshold = DEFAULT_ALERT_THRESHOLD

        self.severity_weight = DEFAULT_SEVERITY_WEIGHT
        self.impact_weight = DEFAULT_IMPACT_WEIGHT
        self.share_weight = DEFAULT_SHARE_WEIGHT
        self.urgency_weight = DEFAULT_URGENCY_WEIGHT
        self.confidence_weight = DEFAULT_CONFIDENCE_WEIGHT
        self.priority_multiplier = DEFAULT_PRIORITY_MULTIPLIER

        self.impact_reference_orders = DEFAULT_IMPACT_REFERENCE_ORDERS
        self.share_reference = DEFAULT_SHARE_REFERENCE

        self.check_only_latest_date = True
        self.min_revenue_share = 0.0
        self.min_cart_share = 0.0

        self.current_date: Optional[str] = None
        self.user_id: Optional[Any] = None
        self.shop_id: Optional[Any] = None
        self.marketplace: Optional[str] = None

    def load_rule(self) -> Optional[Dict[str, Any]]:
        response = (
            supabase.table(RULES_TABLE)
            .select("*")
            .eq("detector_name", self.name)
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def apply_rule(self) -> bool:
        self.rule = self.load_rule()

        if not self.rule:
            return True

        if not self.rule.get("is_enabled", True):
            return False

        rules = self.rule.get("rules") or {}
        settings = self.rule.get("settings") or {}

        self.lookback_days = int(self.rule.get("lookback_days") or DEFAULT_LOOKBACK_DAYS)
        self.cooldown_days = int(self.rule.get("cooldown_days") or DEFAULT_COOLDOWN_DAYS)

        self.warning_threshold = float(
            self.rule.get("warning_threshold")
            if self.rule.get("warning_threshold") is not None
            else DEFAULT_WARNING_THRESHOLD
        )
        self.critical_threshold = float(
            self.rule.get("critical_threshold")
            if self.rule.get("critical_threshold") is not None
            else DEFAULT_CRITICAL_THRESHOLD
        )

        self.min_sample_size = int(self.rule.get("min_sample_size") or DEFAULT_MIN_SAMPLE_SIZE)
        self.min_previous_carts = int(settings.get("min_previous_carts", DEFAULT_MIN_PREVIOUS_CARTS))
        self.alert_threshold = float(settings.get("alert_threshold", DEFAULT_ALERT_THRESHOLD))
        self.priority_multiplier = float(settings.get("priority_multiplier", DEFAULT_PRIORITY_MULTIPLIER))

        weights = settings.get("priority_weights") or {}
        self.severity_weight = float(weights.get("severity", DEFAULT_SEVERITY_WEIGHT))
        self.impact_weight = float(weights.get("impact", DEFAULT_IMPACT_WEIGHT))
        self.share_weight = float(weights.get("share", DEFAULT_SHARE_WEIGHT))
        self.urgency_weight = float(weights.get("urgency", DEFAULT_URGENCY_WEIGHT))
        self.confidence_weight = float(weights.get("confidence", DEFAULT_CONFIDENCE_WEIGHT))

        self.impact_reference_orders = int(settings.get("impact_reference_orders", DEFAULT_IMPACT_REFERENCE_ORDERS))
        self.share_reference = float(settings.get("share_reference", DEFAULT_SHARE_REFERENCE))

        self.check_only_latest_date = bool(rules.get("check_only_latest_date", True))
        self.min_revenue_share = float(rules.get("min_revenue_share", 0.0))
        self.min_cart_share = float(rules.get("min_cart_share", 0.0))

        return True

    def fetch_latest_date(self) -> Optional[str]:
        query = (
            supabase.table(FUNNEL_TABLE)
            .select("snapshot_date")
            .order("snapshot_date", desc=True)
            .limit(1)
        )

        if self.user_id is not None:
            query = query.eq("user_id", self.user_id)
        if self.shop_id is not None:
            query = query.eq("shop_id", self.shop_id)
        if self.marketplace is not None:
            query = query.eq("marketplace", self.marketplace)

        response = query.execute()
        rows = response.data or []
        return rows[0].get("snapshot_date") if rows else None

    def fetch_rows(self) -> List[Dict[str, Any]]:
        query = supabase.table(FUNNEL_TABLE).select("*")

        if self.user_id is not None:
            query = query.eq("user_id", self.user_id)
        if self.shop_id is not None:
            query = query.eq("shop_id", self.shop_id)
        if self.marketplace is not None:
            query = query.eq("marketplace", self.marketplace)

        if self.check_only_latest_date:
            self.current_date = self.fetch_latest_date()
            if not self.current_date:
                return []
            query = query.eq("snapshot_date", self.current_date)

        response = query.execute()
        return response.data or []

    @staticmethod
    def empty_period_context() -> Dict[str, Any]:
        return {
            "previous_period": {},
            "current_period": {},
            "expected": {},
            "store": {},
            "change": {},
            "impact": {},
        }

    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    def build_period_context(
        self,
        row: Dict[str, Any],
        funnel_rows: List[Dict[str, Any]],
        orders_rows: List[Dict[str, Any]],
        previous_start: date,
        previous_end: date,
        current_start: date,
        current_end: date,
    ) -> Dict[str, Any]:
        product_key = row.get("product_key")
        if not product_key:
            return self.empty_period_context()

        product_key_str = str(product_key)
        nm_id = row.get("marketplace_product_id")

        previous_opens = 0.0
        previous_carts = 0.0
        previous_funnel_orders = 0.0
        current_opens = 0.0
        current_carts = 0.0
        current_funnel_orders = 0.0
        previous_total_carts = 0.0

        for item in funnel_rows:
            item_date = date.fromisoformat(str(item.get("snapshot_date")))
            item_product_key = str(item.get("product_key"))
            opens = self.safe_float(item.get("open_count"))
            carts = self.safe_float(item.get("cart_count"))
            orders = self.safe_float(item.get("order_count"))

            if previous_start <= item_date <= previous_end:
                previous_total_carts += carts
                if item_product_key == product_key_str:
                    previous_opens += opens
                    previous_carts += carts
                    previous_funnel_orders += orders
                    nm_id = item.get("marketplace_product_id") or nm_id

            if current_start <= item_date <= current_end and item_product_key == product_key_str:
                current_opens += opens
                current_carts += carts
                current_funnel_orders += orders
                nm_id = item.get("marketplace_product_id") or nm_id

        previous_orders = 0.0
        previous_revenue = 0.0
        current_orders = 0.0
        current_revenue = 0.0
        previous_total_orders = 0.0
        previous_total_revenue = 0.0
        aov_values: List[float] = []

        for item in orders_rows:
            item_date = date.fromisoformat(str(item.get("snapshot_date")))
            item_product_key = str(item.get("product_key"))
            revenue = self.safe_float(item.get("net_order_value"))
            orders = self.safe_float(item.get("orders_count"))

            if previous_start <= item_date <= previous_end:
                previous_total_orders += orders
                previous_total_revenue += revenue
                if item_product_key == product_key_str:
                    previous_orders += orders
                    previous_revenue += revenue
                    if item.get("avg_order_value") is not None:
                        aov_values.append(self.safe_float(item.get("avg_order_value")))

            if current_start <= item_date <= current_end and item_product_key == product_key_str:
                current_orders += orders
                current_revenue += revenue

        previous_aov = (
            previous_revenue / previous_orders
            if previous_orders > 0
            else (sum(aov_values) / len(aov_values) if aov_values else 0.0)
        )

        previous_add_to_cart_rate = previous_carts / previous_opens if previous_opens > 0 else 0.0
        current_add_to_cart_rate = current_carts / current_opens if current_opens > 0 else 0.0
        previous_cart_to_order_rate = previous_orders / previous_carts if previous_carts > 0 else 0.0

        add_to_cart_rate_change_pct = (
            (current_add_to_cart_rate - previous_add_to_cart_rate) / previous_add_to_cart_rate
            if previous_add_to_cart_rate > 0
            else 0.0
        )

        expected_add_to_cart = current_opens * previous_add_to_cart_rate
        lost_add_to_cart = max(expected_add_to_cart - current_carts, 0.0)
        expected_lost_orders = lost_add_to_cart * previous_cart_to_order_rate
        impact_money = expected_lost_orders * previous_aov
        cart_share_pct = previous_carts / previous_total_carts * 100 if previous_total_carts > 0 else 0.0
        orders_share_pct = previous_orders / previous_total_orders * 100 if previous_total_orders > 0 else 0.0
        revenue_share_pct = previous_revenue / previous_total_revenue * 100 if previous_total_revenue > 0 else 0.0

        return {
            "product_key": product_key,
            "nm_id": nm_id,
            "previous_period": {
                "opens": round(previous_opens, 2),
                "add_to_cart": round(previous_carts, 2),
                "orders": round(previous_orders, 2),
                "funnel_orders": round(previous_funnel_orders, 2),
                "revenue": round(previous_revenue, 2),
                "aov": round(previous_aov, 2),
                "add_to_cart_rate": round(previous_add_to_cart_rate, 4),
                "cart_to_order_rate": round(previous_cart_to_order_rate, 4),
            },
            "current_period": {
                "opens": round(current_opens, 2),
                "add_to_cart": round(current_carts, 2),
                "orders": round(current_orders, 2),
                "funnel_orders": round(current_funnel_orders, 2),
                "revenue": round(current_revenue, 2),
                "add_to_cart_rate": round(current_add_to_cart_rate, 4),
            },
            "expected": {
                "add_to_cart": round(expected_add_to_cart, 2),
                "lost_add_to_cart": round(lost_add_to_cart, 2),
                "lost_orders": round(expected_lost_orders, 2),
            },
            "store": {
                "previous_total_add_to_cart": round(previous_total_carts, 2),
                "previous_total_orders": round(previous_total_orders, 2),
                "previous_total_revenue": round(previous_total_revenue, 2),
                "cart_share_pct": round(cart_share_pct, 2),
                "orders_share_pct": round(orders_share_pct, 2),
                "revenue_share_pct": round(revenue_share_pct, 2),
            },
            "change": {
                "add_to_cart_rate_change_pct": round(add_to_cart_rate_change_pct, 4),
            },
            "impact": {
                "money": round(impact_money, 2),
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

        product_keys: Set[str] = {str(row.get("product_key")) for row in valid_rows}
        sample = valid_rows[0]
        user_id = sample.get("user_id")
        shop_id = sample.get("shop_id")
        marketplace = sample.get("marketplace")
        metric_date = date.fromisoformat(str(sample.get("snapshot_date")))

        previous_start = metric_date - timedelta(days=self.lookback_days * 2)
        previous_end = metric_date - timedelta(days=self.lookback_days + 1)
        current_start = metric_date - timedelta(days=self.lookback_days - 1)
        current_end = metric_date

        funnel_response = (
            supabase.table(FUNNEL_TABLE)
            .select("product_key,marketplace_product_id,snapshot_date,open_count,cart_count,order_count")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .gte("snapshot_date", previous_start.isoformat())
            .lte("snapshot_date", current_end.isoformat())
            .execute()
        )

        orders_response = (
            supabase.table(ORDERS_TABLE)
            .select("product_key,net_order_value,avg_order_value,orders_count,snapshot_date")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .gte("snapshot_date", previous_start.isoformat())
            .lte("snapshot_date", current_end.isoformat())
            .execute()
        )

        funnel_rows = funnel_response.data or []
        orders_rows = orders_response.data or []

        contexts: Dict[str, Dict[str, Any]] = {}
        for row in valid_rows:
            product_key = str(row.get("product_key"))
            if product_key not in product_keys:
                continue
            contexts[product_key] = self.build_period_context(
                row=row,
                funnel_rows=funnel_rows,
                orders_rows=orders_rows,
                previous_start=previous_start,
                previous_end=previous_end,
                current_start=current_start,
                current_end=current_end,
            )

        return contexts

    def filter_rows_by_rule(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        contexts = self.fetch_period_contexts(rows)

        for row in rows:
            context = contexts.get(str(row.get("product_key")), self.empty_period_context())
            previous_period = context.get("previous_period") or {}
            current_period = context.get("current_period") or {}
            expected = context.get("expected") or {}
            store = context.get("store") or {}
            change = context.get("change") or {}

            if previous_period.get("opens", 0) < self.min_sample_size:
                continue

            if previous_period.get("add_to_cart", 0) < self.min_previous_carts:
                continue

            if expected.get("lost_add_to_cart", 0) <= 0:
                continue

            if expected.get("lost_orders", 0) <= 0:
                continue

            if expected.get("lost_orders", 0) < 0.5:
                continue

            if previous_period.get("revenue", 0) <= 0:
                continue

            if current_period.get("opens", 0) <= 0:
                continue

            if change.get("add_to_cart_rate_change_pct", 0) >= self.warning_threshold:
                continue

            if (store.get("revenue_share_pct", 0) / 100) < self.min_revenue_share:
                continue

            if (store.get("cart_share_pct", 0) / 100) < self.min_cart_share:
                continue

            row.update(context)
            result.append(row)

        return result

    @staticmethod
    def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        return max(minimum, min(value, maximum))

    def calculate_severity_score(self, row: Dict[str, Any]) -> float:
        change = float((row.get("change") or {}).get("add_to_cart_rate_change_pct") or 0.0)

        if change >= self.warning_threshold:
            return 0.0

        if self.critical_threshold == self.warning_threshold:
            return 1.0

        score = (abs(change) - abs(self.warning_threshold)) / (
            abs(self.critical_threshold) - abs(self.warning_threshold)
        )
        return round(self.clamp(score), 4)

    def calculate_impact_score(self, row: Dict[str, Any]) -> float:
        impact_money = float((row.get("impact") or {}).get("money") or 0.0)
        previous_aov = float((row.get("previous_period") or {}).get("aov") or 0.0)
        reference_money = self.impact_reference_orders * previous_aov

        if reference_money <= 0:
            return 0.0

        return round(self.clamp(impact_money / reference_money), 4)

    def calculate_share_score(self, row: Dict[str, Any]) -> float:
        revenue_share_pct = float((row.get("store") or {}).get("revenue_share_pct") or 0.0)
        share = revenue_share_pct / 100

        if self.share_reference <= 0:
            return 0.0

        return round(self.clamp(share / self.share_reference), 4)

    def calculate_urgency_score(self, row: Dict[str, Any]) -> float:
        current_rate = float((row.get("current_period") or {}).get("add_to_cart_rate") or 0.0)
        previous_rate = float((row.get("previous_period") or {}).get("add_to_cart_rate") or 0.0)
        change = abs(float((row.get("change") or {}).get("add_to_cart_rate_change_pct") or 0.0))

        if current_rate == 0 and previous_rate > 0:
            return 1.0
        if change >= 0.6:
            return 0.9
        if change >= 0.45:
            return 0.7
        if change >= 0.3:
            return 0.5
        return 0.3

    def calculate_confidence_score(self, row: Dict[str, Any]) -> float:
        previous_opens = float((row.get("previous_period") or {}).get("opens") or 0.0)

        if previous_opens >= 3000:
            confidence = 0.95
        elif previous_opens >= 1000:
            confidence = 0.9
        elif previous_opens >= 500:
            confidence = 0.85
        elif previous_opens >= 200:
            confidence = 0.75
        else:
            confidence = 0.6

        return round(confidence, 4)

    def calculate_priority_parts(self, row: Dict[str, Any]) -> Dict[str, float]:
        severity_score = self.calculate_severity_score(row)
        impact_score = self.calculate_impact_score(row)
        share_score = self.calculate_share_score(row)
        urgency_score = self.calculate_urgency_score(row)
        confidence_score = self.calculate_confidence_score(row)

        priority_score = (
            severity_score * self.severity_weight
            + impact_score * self.impact_weight
            + share_score * self.share_weight
            + urgency_score * self.urgency_weight
            + confidence_score * self.confidence_weight
        ) * self.priority_multiplier

        return {
            "severity_score": round(self.clamp(severity_score), 4),
            "impact_score": round(self.clamp(impact_score), 4),
            "share_score": round(self.clamp(share_score), 4),
            "urgency_score": round(self.clamp(urgency_score), 4),
            "confidence_score": round(self.clamp(confidence_score), 4),
            "priority_score": round(self.clamp(priority_score), 4),
        }

    def severity_label(self, priority_score: float) -> str:
        if priority_score >= 0.75:
            return "critical"
        if priority_score >= 0.45:
            return "warning"
        return "info"

    def build_event(self, row: Dict[str, Any]) -> DetectorEvent:
        product_key = row.get("product_key")
        nm_id = row.get("nm_id") or row.get("marketplace_product_id")
        metric_date = row.get("snapshot_date")
        priority_parts = self.calculate_priority_parts(row)

        previous_period = row.get("previous_period") or {}
        current_period = row.get("current_period") or {}
        change = row.get("change") or {}
        impact = row.get("impact") or {}

        previous_rate = float(previous_period.get("add_to_cart_rate") or 0.0)
        current_rate = float(current_period.get("add_to_cart_rate") or 0.0)
        change_pct = float(change.get("add_to_cart_rate_change_pct") or 0.0)
        impact_money = float(impact.get("money") or 0.0)

        payload = {
            "product_key": product_key,
            "nm_id": nm_id,
            "lookback_days": self.lookback_days,
            "previous_period": previous_period,
            "current_period": current_period,
            "expected": row.get("expected") or {},
            "store": row.get("store") or {},
            "change": change,
            "impact": impact,
            "priority": {
                "severity_score": priority_parts["severity_score"],
                "impact_score": priority_parts["impact_score"],
                "share_score": priority_parts["share_score"],
                "urgency_score": priority_parts["urgency_score"],
                "confidence_score": priority_parts["confidence_score"],
                "priority_score": priority_parts["priority_score"],
                "severity_label": self.severity_label(priority_parts["priority_score"]),
            },
        }

        return DetectorEvent(
            user_id=row.get("user_id"),
            shop_id=row.get("shop_id"),
            marketplace=row.get("marketplace"),
            event_domain=EVENT_DOMAIN,
            event_type=EVENT_TYPE,
            event_group=EVENT_GROUP,
            entity_type="product",
            entity_id=str(nm_id or product_key),
            sub_entity_type=None,
            sub_entity_id=None,
            severity=priority_parts["severity_score"],
            confidence=priority_parts["confidence_score"],
            priority=priority_parts["priority_score"],
            is_alert=priority_parts["priority_score"] >= self.alert_threshold,
            event_date=date.fromisoformat(str(metric_date)),
            title="Падение добавлений в корзину",
            description=(
                f"Конверсия из открытия в корзину снизилась на {round(abs(change_pct) * 100, 1)}% "
                f"за последние {self.lookback_days} дней. "
                f"Было {round(previous_rate * 100, 2)}%, стало {round(current_rate * 100, 2)}%. "
                f"Оценка потерь: {round(impact_money, 2)}."
            ),
            source_table=FUNNEL_TABLE,
            payload=payload,
            meta={
                "detector": EVENT_TYPE,
                "lookback_days": self.lookback_days,
                "cooldown_days": self.cooldown_days,
                "warning_threshold": self.warning_threshold,
                "critical_threshold": self.critical_threshold,
                "min_sample_size": self.min_sample_size,
                "min_previous_carts": self.min_previous_carts,
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
                "min_revenue_share": self.min_revenue_share,
                "min_cart_share": self.min_cart_share,
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
        print(f"Min previous carts: {self.min_previous_carts}")
        print(f"Min revenue share pct: {self.min_revenue_share * 100}")
        print(f"Min cart share pct: {self.min_cart_share * 100}")

        return [self.build_event(row) for row in rows]


def run_detector_job(job, state, registry_entry):
    detector = AddToCartRateDropDetector()
    detector.user_id = job.get("user_id")
    detector.shop_id = job.get("shop_id")
    detector.marketplace = job.get("marketplace")

    if not detector.apply_rule():
        print(f"Detector {detector.name} is disabled by rule")
        return {
            "rows_read": 0,
            "signals_created": 0,
            "last_processed_date": None,
        }

    rows = detector.fetch_rows()
    rows_read = len(rows)
    rows = detector.filter_rows_by_rule(rows)
    events = [detector.build_event(row) for row in rows]

    write_events(events)

    last_processed_date = detector.current_date
    if not last_processed_date and rows:
        last_processed_date = max(str(row.get("snapshot_date")) for row in rows if row.get("snapshot_date"))

    return {
        "rows_read": rows_read,
        "signals_created": len(events),
        "last_processed_date": last_processed_date,
    }


def main() -> None:
    detector = AddToCartRateDropDetector()
    events = detector.run()
    write_events(events)
    print(f"Events written: {len(events)}")


if __name__ == "__main__":
    main()