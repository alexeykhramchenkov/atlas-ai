

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


RULES_TABLE = "system_detector_rules"


def _normalize_rule(rule: Dict[str, Any]) -> Dict[str, Any]:
    rule = dict(rule or {})

    rule["rules"] = rule.get("rules") or {}
    rule["settings"] = rule.get("settings") or {}
    rule["entity_scope"] = rule.get("entity_scope") or {}
    rule["required_tables"] = rule.get("required_tables") or []
    rule["required_columns"] = rule.get("required_columns") or []
    rule["optional_columns"] = rule.get("optional_columns") or []
    rule["payload_schema"] = rule.get("payload_schema") or {}

    rule["lookback_days"] = rule.get("lookback_days") or 7
    rule["compare_days"] = rule.get("compare_days")
    rule["cooldown_days"] = rule.get("cooldown_days") or 3
    rule["min_sample_size"] = rule.get("min_sample_size") or 0
    rule["min_confidence"] = rule.get("min_confidence") or 0.5
    rule["severity_weight"] = rule.get("severity_weight") or 1
    rule["confidence_weight"] = rule.get("confidence_weight") or 1
    rule["version"] = rule.get("version") or 1

    return rule


def get_active_rules(
    detector_domain: Optional[str] = None,
    detector_group: Optional[str] = None,
    marketplace: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query = (
        supabase
        .table(RULES_TABLE)
        .select("*")
        .eq("is_enabled", True)
        .order("detector_domain")
        .order("detector_group")
        .order("detector_name")
    )

    if detector_domain:
        query = query.eq("detector_domain", detector_domain)

    if detector_group:
        query = query.eq("detector_group", detector_group)

    response = query.execute()
    rules = response.data or []

    normalized_rules = [_normalize_rule(rule) for rule in rules]

    if marketplace:
        normalized_rules = [
            rule for rule in normalized_rules
            if _rule_allows_marketplace(rule, marketplace)
        ]

    return normalized_rules


def get_rule(detector_name: str) -> Optional[Dict[str, Any]]:
    response = (
        supabase
        .table(RULES_TABLE)
        .select("*")
        .eq("detector_name", detector_name)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    if not rows:
        return None

    return _normalize_rule(rows[0])


def get_rules_by_domain(detector_domain: str) -> List[Dict[str, Any]]:
    return get_active_rules(detector_domain=detector_domain)


def get_rules_by_group(detector_group: str) -> List[Dict[str, Any]]:
    return get_active_rules(detector_group=detector_group)


def _rule_allows_marketplace(rule: Dict[str, Any], marketplace: str) -> bool:
    entity_scope = rule.get("entity_scope") or {}
    settings = rule.get("settings") or {}

    allowed_marketplaces = (
        entity_scope.get("allowed_marketplaces")
        or settings.get("allowed_marketplaces")
    )

    if not allowed_marketplaces:
        return True

    return marketplace in allowed_marketplaces


def is_rule_enabled(detector_name: str) -> bool:
    rule = get_rule(detector_name)
    return bool(rule and rule.get("is_enabled"))


if __name__ == "__main__":
    rules = get_active_rules()
    print(f"Active detector rules: {len(rules)}")
    for rule in rules:
        print(f"- {rule.get('detector_name')} [{rule.get('detector_domain')}]")