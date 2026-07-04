

DEFAULT_RULES = {
    "orders": {
        "best": [
            {"metric": "orders", "direction": "desc", "priority": 1, "weight": 1.0},
            {"metric": "revenue", "direction": "desc", "priority": 2, "weight": 0.8},
            {"metric": "profit", "direction": "desc", "priority": 3, "weight": 0.7},
        ],
        "worst": [
            {"metric": "orders", "direction": "asc", "priority": 1, "weight": 1.0},
            {"metric": "revenue", "direction": "asc", "priority": 2, "weight": 0.8},
            {"metric": "profit", "direction": "asc", "priority": 3, "weight": 0.7},
        ],
        "scale": [
            {"metric": "orders", "direction": "desc", "priority": 1, "weight": 1.0},
            {"metric": "profit", "direction": "desc", "priority": 2, "weight": 1.0},
            {"metric": "buyout_rate", "direction": "desc", "priority": 3, "weight": 0.7},
            {"metric": "stock_qty", "direction": "desc", "priority": 4, "weight": 0.5},
            {"metric": "ads_roas", "direction": "desc", "priority": 5, "weight": 0.4},
        ],
        "stop": [
            {"metric": "profit", "direction": "asc", "priority": 1, "weight": 1.0},
            {"metric": "orders", "direction": "asc", "priority": 2, "weight": 0.8},
            {"metric": "cancel_rate", "direction": "desc", "priority": 3, "weight": 0.7},
            {"metric": "ads_spend", "direction": "desc", "priority": 4, "weight": 0.5},
        ],
        "risk": [
            {"metric": "stock_qty", "direction": "asc", "priority": 1, "weight": 1.0},
            {"metric": "orders", "direction": "desc", "priority": 2, "weight": 0.8},
            {"metric": "revenue", "direction": "desc", "priority": 3, "weight": 0.6},
        ],
    }
}


def load_rules(dataset: str, analysis: str) -> list[dict]:
    """
    Load analysis rules.

    For MVP rules are stored in code.
    Later this function can be replaced with Supabase table analysis_rules.
    """

    dataset_rules = DEFAULT_RULES.get(dataset)
    if not dataset_rules:
        raise ValueError(f"No rules for dataset: {dataset}")

    rules = dataset_rules.get(analysis)
    if not rules:
        raise ValueError(f"No rules for dataset={dataset}, analysis={analysis}")

    return sorted(rules, key=lambda rule: rule.get("priority", 999))


if __name__ == "__main__":
    print("rules loader")
    print("Ready")