

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from db.client import supabase


RULES_TABLE = "system_ai_analysis_rules"
DEFAULT_ANALYSIS = "metric_value"


@dataclass(frozen=True)
class AnalysisMatch:
    analysis: str
    matched_alias: str | None = None
    score: int = 0
    priority: int = 100


def resolve_analysis(question: str) -> str:
    match = resolve_analysis_from_rules(question)

    if match is not None:
        return match.analysis

    return DEFAULT_ANALYSIS


def resolve_analysis_from_rules(question: str) -> AnalysisMatch | None:
    text = normalize_text(question)
    rules = load_analysis_rules()
    best_match: AnalysisMatch | None = None

    for rule in rules:
        aliases = collect_aliases(rule)

        for alias in aliases:
            alias_text = normalize_text(alias)

            if not alias_text:
                continue

            if alias_text in text:
                candidate = AnalysisMatch(
                    analysis=rule["analysis"],
                    matched_alias=alias,
                    score=len(alias_text),
                    priority=int(rule.get("priority") or 100),
                )

                if is_better_match(candidate, best_match):
                    best_match = candidate

    return best_match


def load_analysis_rules() -> list[dict[str, Any]]:
    try:
        response = (
            supabase
            .table(RULES_TABLE)
            .select("analysis,aliases_ru,aliases_en,priority")
            .eq("is_active", True)
            .execute()
        )

        return response.data or []
    except Exception:
        return []


def collect_aliases(rule: dict[str, Any]) -> list[str]:
    aliases: list[str] = []

    aliases.extend(rule.get("aliases_ru") or [])
    aliases.extend(rule.get("aliases_en") or [])

    analysis = rule.get("analysis")
    if analysis:
        aliases.append(analysis)

    return aliases


def is_better_match(candidate: AnalysisMatch, current: AnalysisMatch | None) -> bool:
    if current is None:
        return True

    if candidate.priority != current.priority:
        return candidate.priority < current.priority

    return candidate.score > current.score


def normalize_text(value: str) -> str:
    return " ".join(str(value).lower().replace("_", " ").split())