from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from db.client import supabase

from ai_chat.routing.resolver import resolve_from_rules


RULES_TABLE = "system_ai_entity_rules"
DEFAULT_ENTITY = "store"


@dataclass(frozen=True)
class EntityMatch:
    entity: str
    matched_alias: str | None = None
    score: int = 0
    priority: int = 100


def resolve_entity(question: str, default_entity: str = DEFAULT_ENTITY) -> str:
    match = resolve_entity_from_rules(question)

    if match is not None:
        return match.entity

    return default_entity or DEFAULT_ENTITY


def resolve_entity_from_rules(question: str) -> EntityMatch | None:
    rules = load_entity_rules()

    match = resolve_from_rules(
        text=question,
        rules=rules,
        value_field="entity",
        aliases_fields=("aliases_ru", "aliases_en"),
        priority_field="priority",
        fuzzy_threshold=0.75,
        prefer_score_over_priority=True,
    )

    if match is None:
        return None

    return EntityMatch(
        entity=match.value,
        matched_alias=match.matched_alias,
        score=match.score,
        priority=match.priority,
    )


def load_entity_rules() -> list[dict[str, Any]]:
    try:
        response = (
            supabase
            .table(RULES_TABLE)
            .select("entity,aliases_ru,aliases_en,priority")
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

    entity = rule.get("entity")
    if entity:
        aliases.append(entity)

    return aliases


def is_better_match(candidate: EntityMatch, current: EntityMatch | None) -> bool:
    if current is None:
        return True

    if candidate.priority != current.priority:
        return candidate.priority < current.priority

    return candidate.score > current.score


def normalize_text(value: str) -> str:
    return " ".join(str(value).lower().replace("_", " ").split())
