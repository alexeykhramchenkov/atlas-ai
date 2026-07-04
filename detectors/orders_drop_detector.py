import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from detectors.detector_types import DetectorEvent
from detectors.orchestrators.detector_event_writer import write_events


SOURCE_TABLE = "metrics_orders_daily"
RULES_TABLE = "system_detector_rules"
CATALOG_TABLE = "sku_catalog"

EVENT_DOMAIN = "orders"
EVENT_GROUP = "demand"
EVENT_TYPE = "orders_drop"

DEFAULT_LOOKBACK_DAYS = 7
DEFAULT_COOLDOWN_DAYS = 3
DEFAULT_WARNING_THRESHOLD = -0.5
DEFAULT_CRITICAL_THRESHOLD = -0.8
DEFAULT_MIN_SAMPLE_SIZE = 3
DEFAULT_ALERT_THRESHOLD = 0.75

DEFAULT_SEVERITY_WEIGHT = 0.30
DEFAULT_IMPACT_WEIGHT = 0.30
DEFAULT_SHARE_WEIGHT = 0.20
DEFAULT_URGENCY_WEIGHT = 0.15
DEFAULT_CONFIDENCE_WEIGHT = 0.05
DEFAULT_PRIORITY_MULTIPLIER = 1.0

DEFAULT_IMPACT_REFERENCE_ORDERS = 30
DEFAULT_SHARE_REFERENCE = 0.20


class OrdersDropDetector:
    name = EVENT_TYPE

    def __init__(self):
        self.rule: Optional[Dict[str, Any]] = None
        self.lookback_days = DEFAULT_LOOKBACK_DAYS
        self.cooldown_days = DEFAULT_COOLDOWN_DAYS
        self.warning_threshold = DEFAULT_WARNING_THRESHOLD
        self.critical_threshold = DEFAULT_CRITICAL_THRESHOLD
        self.min_sample_size = DEFAULT_MIN_SAMPLE_SIZE
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
        self.min_orders_share = 0.0
        self.exclude_new_products_days = 0
        self.allowed_product_statuses: List[str] = []
        self.current_date: Optional[str] = None
        self.user_id: Optional[Any] = None
        self.shop_id: Optional[Any] = None
        self.marketplace: Optional[str] = None

    def load_rule(self) -> Optional[Dict[str, Any]]:
        response = (
            supabase
            .table(RULES_TABLE)
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
        entity_scope = self.rule.get("entity_scope") or {}

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
        self.min_orders_share = float(rules.get("min_orders_share", 0.0))
        self.exclude_new_products_days = int(rules.get("exclude_new_products_days", 0))
        self.allowed_product_statuses = [str(status) for status in entity_scope.get("allowed_product_statuses", [])]
        return True

    def fetch_latest_date(self) -> Optional[str]:
        query = supabase.table(SOURCE_TABLE).select("snapshot_date").order("snapshot_date", desc=True).limit(1)
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
        query = supabase.table(SOURCE_TABLE).select("*")
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

    def fetch_allowed_product_keys(self) -> set[str]:
        if not self.allowed_product_statuses:
            return set()
        query = supabase.table(CATALOG_TABLE).select("product_key").in_("product_status", self.allowed_product_statuses)
        if self.user_id is not None:
            query = query.eq("user_id", self.user_id)
        if self.shop_id is not None:
            query = query.eq("shop_id", self.shop_id)
        if self.marketplace is not None:
            query = query.eq("marketplace", self.marketplace)
        response = query.execute()
        return {str(row.get("product_key")) for row in response.data or [] if row.get("product_key") is not None}

    @staticmethod
    def empty_period_orders_context() -> Dict[str, Any]:
        return {
            "previous_period_orders": 0,
            "current_period_orders": 0,
            "lost_orders": 0,
            "previous_total_orders": 0,
            "previous_total_revenue": 0.0,
            "previous_period_revenue": 0.0,
            "current_period_revenue": 0.0,
            "previous_period_aov": 0.0,
            "impact_money": 0.0,
            "orders_share_pct": 0.0,
            "revenue_share_pct": 0.0,
        }

    @staticmethod
    def safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    def fetch_period_orders_contexts(self, rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
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
        user_id = sample.get("user_id")
        shop_id = sample.get("shop_id")
        marketplace = sample.get("marketplace")
        metric_date = date.fromisoformat(str(sample.get("snapshot_date")))

        current_end = metric_date
        current_start = current_end - timedelta(days=self.lookback_days - 1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=self.lookback_days - 1)

        query = (
            supabase
            .table(SOURCE_TABLE)
            .select("product_key,orders_count,net_order_value,snapshot_date")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .gte("snapshot_date", previous_start.isoformat())
            .lte("snapshot_date", current_end.isoformat())
        )
        if product_keys:
            query = query.in_("product_key", list(product_keys))
        response = query.execute()

        contexts: Dict[str, Dict[str, Any]] = {
            product_key: self.empty_period_orders_context()
            for product_key in product_keys
        }

        previous_total_orders = 0.0
        previous_total_revenue = 0.0

        for item in response.data or []:
            item_product_key = str(item.get("product_key"))
            item_date_value = item.get("snapshot_date")
            if not item_date_value:
                continue

            item_date = date.fromisoformat(str(item_date_value))
            orders = self.safe_float(item.get("orders_count"))
            revenue = self.safe_float(item.get("net_order_value"))

            if previous_start <= item_date <= previous_end:
                previous_total_orders += orders
                previous_total_revenue += revenue
                if item_product_key in contexts:
                    contexts[item_product_key]["previous_period_orders"] += orders
                    contexts[item_product_key]["previous_period_revenue"] += revenue

            if current_start <= item_date <= current_end and item_product_key in contexts:
                contexts[item_product_key]["current_period_orders"] += orders
                contexts[item_product_key]["current_period_revenue"] += revenue

        for context in contexts.values():
            previous_orders = self.safe_float(context.get("previous_period_orders"))
            current_orders = self.safe_float(context.get("current_period_orders"))
            previous_revenue = self.safe_float(context.get("previous_period_revenue"))
            current_revenue = self.safe_float(context.get("current_period_revenue"))

            lost_orders = max(previous_orders - current_orders, 0.0)
            previous_period_aov = previous_revenue / previous_orders if previous_orders > 0 else 0.0
            impact_money = lost_orders * previous_period_aov
            orders_share = previous_orders / previous_total_orders if previous_total_orders > 0 else 0.0
            revenue_share = previous_revenue / previous_total_revenue if previous_total_revenue > 0 else 0.0

            context.update({
                "previous_period_orders": int(round(previous_orders)),
                "current_period_orders": int(round(current_orders)),
                "lost_orders": int(round(lost_orders)),
                "previous_total_orders": int(round(previous_total_orders)),
                "previous_total_revenue": round(previous_total_revenue, 2),
                "previous_period_revenue": round(previous_revenue, 2),
                "current_period_revenue": round(current_revenue, 2),
                "previous_period_aov": round(previous_period_aov, 2),
                "impact_money": round(impact_money, 2),
                "orders_share_pct": round(orders_share * 100, 2),
                "revenue_share_pct": round(revenue_share * 100, 2),
            })

        print(
            "Orders period windows:",
            f"previous={previous_start.isoformat()}..{previous_end.isoformat()}",
            f"current={current_start.isoformat()}..{current_end.isoformat()}",
        )
        print(f"Orders period contexts loaded: {len(contexts)}")
        return contexts

    def fetch_period_orders_context(self, row: Dict[str, Any]) -> Dict[str, Any]:
        product_key = row.get("product_key")
        user_id = row.get("user_id")
        shop_id = row.get("shop_id")
        marketplace = row.get("marketplace")
        metric_date = row.get("snapshot_date")

        empty_context = {
            "previous_period_orders": 0,
            "current_period_orders": 0,
            "lost_orders": 0,
            "previous_total_orders": 0,
            "previous_total_revenue": 0.0,
            "previous_period_revenue": 0.0,
            "current_period_revenue": 0.0,
            "previous_period_aov": 0.0,
            "impact_money": 0.0,
            "orders_share_pct": 0.0,
            "revenue_share_pct": 0.0,
        }

        if not product_key or not user_id or not shop_id or not marketplace or not metric_date:
            return empty_context

        current_date = date.fromisoformat(metric_date)
        previous_start = current_date - timedelta(days=self.lookback_days * 2)
        previous_end = current_date - timedelta(days=self.lookback_days + 1)
        current_start = current_date - timedelta(days=self.lookback_days - 1)
        current_end = current_date

        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("product_key,orders_count,net_order_value,snapshot_date")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .gte("snapshot_date", previous_start.isoformat())
            .lte("snapshot_date", current_end.isoformat())
            .execute()
        )

        previous_total_orders = 0
        previous_product_orders = 0
        current_product_orders = 0
        previous_total_revenue = 0.0
        previous_product_revenue = 0.0
        current_product_revenue = 0.0

        for item in response.data or []:
            item_date = date.fromisoformat(item.get("snapshot_date"))
            item_product_key = str(item.get("product_key"))
            orders = int(item.get("orders_count") or 0)
            revenue = float(item.get("net_order_value") or 0.0)

            if previous_start <= item_date <= previous_end:
                previous_total_orders += orders
                previous_total_revenue += revenue
                if item_product_key == str(product_key):
                    previous_product_orders += orders
                    previous_product_revenue += revenue

            if current_start <= item_date <= current_end and item_product_key == str(product_key):
                current_product_orders += orders
                current_product_revenue += revenue

        lost_orders = max(previous_product_orders - current_product_orders, 0)
        previous_period_aov = previous_product_revenue / previous_product_orders if previous_product_orders > 0 else 0.0
        impact_money = lost_orders * previous_period_aov
        orders_share = previous_product_orders / previous_total_orders if previous_total_orders > 0 else 0.0
        revenue_share = previous_product_revenue / previous_total_revenue if previous_total_revenue > 0 else 0.0

        return {
            "previous_period_orders": previous_product_orders,
            "current_period_orders": current_product_orders,
            "lost_orders": lost_orders,
            "previous_total_orders": previous_total_orders,
            "previous_total_revenue": round(previous_total_revenue, 2),
            "previous_period_revenue": round(previous_product_revenue, 2),
            "current_period_revenue": round(current_product_revenue, 2),
            "previous_period_aov": round(previous_period_aov, 2),
            "impact_money": round(impact_money, 2),
            "orders_share_pct": round(orders_share * 100, 2),
            "revenue_share_pct": round(revenue_share * 100, 2),
        }

    def fetch_first_seen_date(self, product_key: str, user_id: Any, shop_id: Any, marketplace: str) -> Optional[date]:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("snapshot_date")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", marketplace)
            .eq("product_key", product_key)
            .gt("orders_count", 0)
            .order("snapshot_date")
            .limit(1)
            .execute()
        )
        rows = response.data or []
        return date.fromisoformat(rows[0].get("snapshot_date")) if rows else None

    def is_new_product(self, row: Dict[str, Any]) -> bool:
        if self.exclude_new_products_days <= 0:
            return False
        product_key = row.get("product_key")
        user_id = row.get("user_id")
        shop_id = row.get("shop_id")
        marketplace = row.get("marketplace")
        metric_date = row.get("snapshot_date")
        if not product_key or not user_id or not shop_id or not marketplace or not metric_date:
            return False
        first_seen_date = self.fetch_first_seen_date(str(product_key), user_id, shop_id, marketplace)
        if not first_seen_date:
            return False
        current_date = date.fromisoformat(metric_date)
        return (current_date - first_seen_date).days < self.exclude_new_products_days

    def filter_rows_by_rule(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        allowed_product_keys = self.fetch_allowed_product_keys()
        result: List[Dict[str, Any]] = []
        contexts = self.fetch_period_orders_contexts(rows)

        for row in rows:
            product_key = row.get("product_key")
            if not product_key:
                continue
            if self.get_growth_value(row) >= self.warning_threshold:
                continue
            if allowed_product_keys and product_key not in allowed_product_keys:
                continue
            if self.exclude_new_products_days > 0 and self.is_new_product(row):
                continue

            context = contexts.get(str(product_key), self.empty_period_orders_context())

            if context["previous_period_orders"] < self.min_sample_size:
                continue
            if context["previous_period_revenue"] <= 0:
                continue
            if context["lost_orders"] <= 0:
                continue
            if context["impact_money"] <= 0:
                continue
            if (context["orders_share_pct"] / 100) < self.min_orders_share:
                continue

            row.update(context)
            result.append(row)

        return result

    @staticmethod
    def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
        return max(minimum, min(value, maximum))

    def get_growth_value(self, row: Dict[str, Any]) -> float:
        metric_column = f"orders_growth_{self.lookback_days}d_pct"
        raw_value = float(row.get(metric_column) or 0.0)
        if abs(raw_value) > 1:
            return raw_value / 100
        return raw_value

    def calculate_severity_score(self, row: Dict[str, Any]) -> float:
        growth = self.get_growth_value(row)
        if growth >= self.warning_threshold:
            return 0.0
        if self.critical_threshold == self.warning_threshold:
            return 1.0
        score = (abs(growth) - abs(self.warning_threshold)) / (abs(self.critical_threshold) - abs(self.warning_threshold))
        return round(self.clamp(score), 4)

    def calculate_impact_score(self, row: Dict[str, Any]) -> float:
        impact_money = float(row.get("impact_money") or 0.0)
        previous_period_aov = float(row.get("previous_period_aov") or 0.0)
        reference_money = self.impact_reference_orders * previous_period_aov
        if reference_money <= 0:
            return 0.0
        return round(self.clamp(impact_money / reference_money), 4)

    def calculate_share_score(self, row: Dict[str, Any]) -> float:
        share = float(row.get("revenue_share_pct") or 0.0) / 100
        if self.share_reference <= 0:
            return 0.0
        return round(self.clamp(share / self.share_reference), 4)

    def calculate_urgency_score(self, row: Dict[str, Any]) -> float:
        current_period_orders = int(row.get("current_period_orders") or 0)
        previous_period_orders = int(row.get("previous_period_orders") or 0)
        if current_period_orders == 0 and previous_period_orders >= self.min_sample_size:
            return 1.0
        growth = abs(self.get_growth_value(row))
        if growth >= 0.8:
            return 0.9
        if growth >= 0.6:
            return 0.7
        if growth >= 0.4:
            return 0.5
        return 0.3

    def calculate_confidence_score(self, row: Dict[str, Any]) -> float:
        previous_period_orders = int(row.get("previous_period_orders") or 0)
        if previous_period_orders >= 30:
            confidence = 0.95
        elif previous_period_orders >= 15:
            confidence = 0.9
        elif previous_period_orders >= 10:
            confidence = 0.85
        elif previous_period_orders >= 5:
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
        nm_id = row.get("marketplace_product_id")
        metric_date = row.get("snapshot_date")
        growth = self.get_growth_value(row)
        priority_parts = self.calculate_priority_parts(row)
        previous_orders = int(row.get("previous_period_orders") or 0)
        current_orders = int(row.get("current_period_orders") or 0)
        lost_orders = int(row.get("lost_orders") or 0)
        previous_total_orders = int(row.get("previous_total_orders") or 0)
        previous_total_revenue = round(float(row.get("previous_total_revenue") or 0.0), 2)
        orders_share_pct = round(float(row.get("orders_share_pct") or 0.0), 2)
        revenue_share_pct = round(float(row.get("revenue_share_pct") or 0.0), 2)
        previous_period_revenue = round(float(row.get("previous_period_revenue") or 0.0), 2)
        current_period_revenue = round(float(row.get("current_period_revenue") or 0.0), 2)
        previous_period_aov = round(float(row.get("previous_period_aov") or 0.0), 2)
        impact_money = round(float(row.get("impact_money") or 0.0), 2)
        drop_pct = round(abs(growth) * 100, 1)
        entity_id = str(nm_id or product_key)

        return DetectorEvent(
            user_id=row.get("user_id"),
            shop_id=row.get("shop_id"),
            marketplace=row.get("marketplace"),
            event_domain=EVENT_DOMAIN,
            event_type=EVENT_TYPE,
            event_group=EVENT_GROUP,
            entity_type="product",
            entity_id=entity_id,
            sub_entity_type=None,
            sub_entity_id=None,
            severity=priority_parts["severity_score"],
            confidence=priority_parts["confidence_score"],
            priority=priority_parts["priority_score"],
            is_alert=priority_parts["priority_score"] >= self.alert_threshold,
            event_date=date.fromisoformat(metric_date),
            title="Падение заказов",
            description=(
                f"Заказы товара снизились на {drop_pct}% за последние {self.lookback_days} дней. "
                f"Было {previous_orders}, стало {current_orders}, потеряно {lost_orders}. "
                f"Доля товара в выручке магазина за прошлый период: {revenue_share_pct}%. "
                f"Доля товара в заказах магазина за прошлый период: {orders_share_pct}%. "
                f"Оценка потерь: {impact_money}."
            ),
            source_table=SOURCE_TABLE,
            payload={
                "product_key": product_key,
                "nm_id": nm_id,
                "orders": row.get("orders_count"),
                "orders_growth": growth,
                "lookback_days": self.lookback_days,
                "previous_period_orders": previous_orders,
                "current_period_orders": current_orders,
                "lost_orders": lost_orders,
                "previous_total_orders": previous_total_orders,
                "previous_period_revenue": previous_period_revenue,
                "current_period_revenue": current_period_revenue,
                "previous_total_revenue": previous_total_revenue,
                "previous_period_aov": previous_period_aov,
                "impact_money": impact_money,
                "revenue_share_pct": revenue_share_pct,
                "orders_share_pct": orders_share_pct,
                "net_order_value": row.get("net_order_value"),
                "priority": {
                    "severity_score": priority_parts["severity_score"],
                    "impact_score": priority_parts["impact_score"],
                    "share_score": priority_parts["share_score"],
                    "urgency_score": priority_parts["urgency_score"],
                    "confidence_score": priority_parts["confidence_score"],
                    "priority_score": priority_parts["priority_score"],
                    "severity_label": self.severity_label(priority_parts["priority_score"]),
                },
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
                "exclude_new_products_days": self.exclude_new_products_days,
                "allowed_product_statuses": self.allowed_product_statuses,
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
        print(f"Min previous period orders share pct: {self.min_orders_share * 100}")
        print(f"Min sample size: {self.min_sample_size}")
        print(f"Exclude new products days: {self.exclude_new_products_days}")
        print(f"Allowed product statuses: {self.allowed_product_statuses or 'not set'}")
        return [self.build_event(row) for row in rows]


def run_detector_job(job, state, registry_entry):
    detector = OrdersDropDetector()
    detector.user_id = job.get("user_id")
    detector.shop_id = job.get("shop_id")
    detector.marketplace = job.get("marketplace")
    if not detector.apply_rule():
        print(f"Detector {detector.name} is disabled by rule")
        return {"rows_read": 0, "signals_created": 0, "last_processed_date": None}
    rows = detector.fetch_rows()
    rows_read = len(rows)
    print("Period context mode: batched")
    rows = detector.filter_rows_by_rule(rows)
    events = [detector.build_event(row) for row in rows]
    write_events(events)
    last_processed_date = detector.current_date
    if not last_processed_date and rows:
        last_processed_date = max(str(row.get("snapshot_date")) for row in rows if row.get("snapshot_date"))
    return {"rows_read": rows_read, "signals_created": len(events), "last_processed_date": last_processed_date}


def main() -> None:
    detector = OrdersDropDetector()
    events = detector.run()
    write_events(events)
    print(f"Events written: {len(events)}")


if __name__ == "__main__":
    main()