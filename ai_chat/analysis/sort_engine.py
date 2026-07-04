

def _to_number(value) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0



def _normalize_metric(rows: list[dict], metric: str) -> dict:
    values = [_to_number(row.get(metric)) for row in rows]

    if not values:
        return {}

    min_value = min(values)
    max_value = max(values)

    if min_value == max_value:
        return {index: 0.0 for index in range(len(rows))}

    return {
        index: (value - min_value) / (max_value - min_value)
        for index, value in enumerate(values)
    }



def _calculate_score(row_index: int, normalized_metrics: dict, rules: list[dict]) -> float:
    score = 0.0

    for rule in rules:
        metric = rule["metric"]
        direction = rule.get("direction", "desc")
        weight = _to_number(rule.get("weight", 1.0))

        metric_score = normalized_metrics.get(metric, {}).get(row_index, 0.0)

        if direction == "asc":
            metric_score = 1.0 - metric_score

        score += metric_score * weight

    return score



def sort_rows(
    rows: list[dict],
    rules: list[dict],
    limit: int = 10,
) -> list[dict]:
    """
    Sort dataset rows using weighted normalized ranking rules.

    Each rule has:
        metric
        direction: asc | desc
        weight
        priority
    """

    if not rows:
        return []

    if not rules:
        return rows[:limit]

    normalized_metrics = {
        rule["metric"]: _normalize_metric(rows, rule["metric"])
        for rule in rules
    }

    scored_rows = []

    for index, row in enumerate(rows):
        row_score = _calculate_score(
            row_index=index,
            normalized_metrics=normalized_metrics,
            rules=rules,
        )

        enriched_row = dict(row)
        enriched_row["analysis_score"] = round(row_score, 4)
        scored_rows.append(enriched_row)

    scored_rows.sort(
        key=lambda row: row.get("analysis_score", 0),
        reverse=True,
    )

    return scored_rows[:limit]


if __name__ == "__main__":
    print("sort engine")
    print("Ready")