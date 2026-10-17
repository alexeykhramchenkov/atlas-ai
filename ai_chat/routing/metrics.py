

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_chat.routing.resolver import resolve_from_rules


RULES_TABLE = "system_metric_ai_bot_rules"


@dataclass(frozen=True)
class MetricMatch:
    dataset: str
    metric: str
    default_entity: str
    matched_alias: str | None = None
    score: int = 0


def resolve_metric(question: str, supabase) -> MetricMatch | None:
    matches = resolve_metrics(question=question, supabase=supabase)
    return matches[0] if matches else None


def resolve_metrics(question: str, supabase) -> list[MetricMatch]:
    """
    Resolve one or many dataset + metric matches from user question.

    Source table:
    system_metric_ai_bot_rules

    Example:
    "Покажи общие заказы и выручку"
    ->
    [
        MetricMatch(dataset="orders", metric="orders_count", ...),
        MetricMatch(dataset="orders", metric="orders_revenue", ...),
    ]
    """
    question_lower = normalize_text(question)
    rules = load_metric_rules(supabase)
    best_by_metric: dict[tuple[str, str], MetricMatch] = {}

    for rule in rules:
        for alias in collect_aliases(rule):
            alias_lower = normalize_text(alias)

            if not alias_lower:
                continue

            if alias_lower in question_lower:
                candidate = MetricMatch(
                    dataset=rule["dataset"],
                    metric=rule["metric"],
                    default_entity=rule.get("default_entity") or "store",
                    matched_alias=alias,
                    score=len(alias_lower),
                )

                key = (candidate.dataset, candidate.metric)
                current = best_by_metric.get(key)

                if current is None or candidate.score > current.score:
                    best_by_metric[key] = candidate

    matches = list(best_by_metric.values())
    matches.sort(key=lambda match: match.score, reverse=True)

    if matches:
        return matches

    fuzzy_match = resolve_from_rules(
        text=question,
        rules=rules,
        value_field="metric",
        aliases_fields=("aliases_ru", "aliases_en"),
        fuzzy_threshold=0.75,
    )

    if fuzzy_match is None or fuzzy_match.rule is None:
        return []

    rule = fuzzy_match.rule

    return [
        MetricMatch(
            dataset=rule["dataset"],
            metric=rule["metric"],
            default_entity=rule.get("default_entity") or "store",
            matched_alias=fuzzy_match.matched_alias,
            score=fuzzy_match.score,
        )
    ]


def load_metric_rules(supabase) -> list[dict[str, Any]]:
    response = (
        supabase
        .table(RULES_TABLE)
        .select("dataset,metric,aliases_ru,aliases_en,default_entity")
        .eq("is_active", True)
        .execute()
    )

    return response.data or []


def collect_aliases(rule: dict[str, Any]) -> list[str]:
    aliases: list[str] = []

    aliases.extend(rule.get("aliases_ru") or [])
    aliases.extend(rule.get("aliases_en") or [])

    metric = rule.get("metric")
    if metric:
        aliases.append(metric)

    return aliases


def normalize_text(value: str) -> str:
    return " ".join(str(value).lower().replace("ё", "е").replace("_", " ").split())


def metric_match_to_dict(match: MetricMatch | None) -> dict[str, Any]:
    if match is None:
        return {}

    return {
        "dataset": match.dataset,
        "metric": match.metric,
        "entity": match.default_entity,
        "matched_alias": match.matched_alias,
        "metric_match_score": match.score,
    }
