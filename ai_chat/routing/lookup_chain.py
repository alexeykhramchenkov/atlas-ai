from __future__ import annotations

from typing import Any


RULES_TABLE = "system_question_type_rules"
QUESTION_TYPE = "lookup_chain"


def resolve_lookup_chain(question: str, supabase) -> dict[str, Any] | None:
    normalized_question = normalize_text(question)

    for rule in load_lookup_chain_rules(supabase):
        aliases = rule.get("aliases") or []

        for alias in aliases:
            alias_text = alias.get("text") if isinstance(alias, dict) else alias
            normalized_alias = normalize_text(alias_text)

            if not normalized_alias:
                continue

            if normalized_alias in normalized_question:
                plan = rule.get("plan") or []

                if plan:
                    return {
                        "question_type": rule.get("question_type") or QUESTION_TYPE,
                        "plan": plan,
                    }

    return None


def load_lookup_chain_rules(supabase) -> list[dict[str, Any]]:
    try:
        response = (
            supabase
            .table(RULES_TABLE)
            .select("question_type,aliases,plan,priority")
            .eq("question_type", QUESTION_TYPE)
            .eq("is_active", True)
            .order("priority", desc=False)
            .execute()
        )

        return response.data or []
    except Exception:
        return []


def normalize_text(value: str) -> str:
    return " ".join(str(value).lower().replace("_", " ").replace("?", "").split())
