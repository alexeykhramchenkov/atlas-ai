from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_chat.routing.fuzzy import fuzzy_match


DEFAULT_EXACT_SCORE = 100
DEFAULT_FUZZY_THRESHOLD = 0.75
DEFAULT_PRIORITY = 100


@dataclass(frozen=True)
class ResolveMatch:
    value: str
    matched_alias: str | None = None
    score: int = 0
    priority: int = DEFAULT_PRIORITY
    source: str = "unknown"
    rule: dict[str, Any] | None = None


def resolve_from_rules(
    *,
    text: str,
    rules: list[dict[str, Any]],
    value_field: str,
    aliases_fields: tuple[str, ...] = ("aliases_ru", "aliases_en"),
    priority_field: str = "priority",
    fuzzy_threshold: float = DEFAULT_FUZZY_THRESHOLD,
    prefer_score_over_priority: bool | None = None,
) -> ResolveMatch | None:
    normalized_text = normalize_text(text)

    exact_match = find_exact_match(
        text=normalized_text,
        rules=rules,
        value_field=value_field,
        aliases_fields=aliases_fields,
        priority_field=priority_field,
    )

    if exact_match is not None:
        return exact_match

    return find_fuzzy_match(
        text=normalized_text,
        rules=rules,
        value_field=value_field,
        aliases_fields=aliases_fields,
        priority_field=priority_field,
        fuzzy_threshold=fuzzy_threshold,
    )


def find_exact_match(
    *,
    text: str,
    rules: list[dict[str, Any]],
    value_field: str,
    aliases_fields: tuple[str, ...],
    priority_field: str,
) -> ResolveMatch | None:
    best_match: ResolveMatch | None = None

    for rule in rules:
        value = rule.get(value_field)
        if not value:
            continue

        for alias in collect_aliases(rule, value_field, aliases_fields):
            alias_text = normalize_text(alias)

            if not alias_text:
                continue

            if alias_text in text:
                candidate = ResolveMatch(
                    value=str(value),
                    matched_alias=alias,
                    score=max(DEFAULT_EXACT_SCORE, len(alias_text)),
                    priority=get_priority(rule, priority_field),
                    source="exact",
                    rule=rule,
                )

                if is_better_match(candidate, best_match):
                    best_match = candidate

    return best_match


def find_fuzzy_match(
    *,
    text: str,
    rules: list[dict[str, Any]],
    value_field: str,
    aliases_fields: tuple[str, ...],
    priority_field: str,
    fuzzy_threshold: float,
) -> ResolveMatch | None:
    best_match: ResolveMatch | None = None

    for rule in rules:
        value = rule.get(value_field)
        if not value:
            continue

        aliases = collect_aliases(rule, value_field, aliases_fields)
        matched_alias, score = fuzzy_match(
            text=text,
            aliases=aliases,
            threshold=fuzzy_threshold,
        )

        if not matched_alias:
            continue

        candidate = ResolveMatch(
            value=str(value),
            matched_alias=matched_alias,
            score=int(score * 100),
            priority=get_priority(rule, priority_field),
            source="fuzzy",
            rule=rule,
        )

        if is_better_match(candidate, best_match):
            best_match = candidate

    return best_match


def collect_aliases(
    rule: dict[str, Any],
    value_field: str,
    aliases_fields: tuple[str, ...],
) -> list[str]:
    aliases: list[str] = []

    for field in aliases_fields:
        values = rule.get(field) or []

        if isinstance(values, list):
            aliases.extend(str(value) for value in values if value)
        elif isinstance(values, str):
            aliases.append(values)

    value = rule.get(value_field)
    if value:
        aliases.append(str(value))

    return aliases


def is_better_match(candidate: ResolveMatch, current: ResolveMatch | None) -> bool:
    if current is None:
        return True

    if candidate.score != current.score:
        return candidate.score > current.score

    if candidate.priority != current.priority:
        return candidate.priority < current.priority

    if candidate.source != current.source:
        return candidate.source == "exact"

    return False


def get_priority(rule: dict[str, Any], priority_field: str) -> int:
    try:
        return int(rule.get(priority_field) or DEFAULT_PRIORITY)
    except (TypeError, ValueError):
        return DEFAULT_PRIORITY


def normalize_text(value: str) -> str:
    return " ".join(str(value).lower().replace("_", " ").split())
