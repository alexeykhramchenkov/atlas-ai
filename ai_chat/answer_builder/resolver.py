from typing import Any


RULES_TABLE = "system_ai_answer_rules"
DEFAULT_LANGUAGE = "en"


def resolve_answer_rule(
    *,
    supabase: Any,
    question_type: str,
    language: str,
    request: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    rule = _fetch_rule(
        supabase=supabase,
        question_type=question_type,
        language=language,
        request=request,
        result=result,
    )
    if rule or language == DEFAULT_LANGUAGE:
        return rule

    return _fetch_rule(
        supabase=supabase,
        question_type=question_type,
        language=DEFAULT_LANGUAGE,
        request=request,
        result=result,
    )


def _fetch_rule(
    *,
    supabase: Any,
    question_type: str,
    language: str,
    request: dict[str, Any] | None,
    result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    response = (
        supabase.table(RULES_TABLE)
        .select(
            """
            id,
            question_type,
            template_name,
            language,
            title_template,
            fields,
            priority
            """
        )
        .eq("question_type", question_type)
        .eq("language", language)
        .eq("is_active", True)
        .order("priority", desc=False)
        .execute()
    )

    rows = response.data or []
    for row in rows:
        if _matches_context(rule=row, request=request or {}, result=result or {}):
            return row

    return None


def _matches_context(
    *,
    rule: dict[str, Any],
    request: dict[str, Any],
    result: dict[str, Any],
) -> bool:
    match = _extract_match(rule)

    if not match:
        return True

    for key, expected in match.items():
        if expected in [None, ""]:
            continue

        actual = request.get(key)
        if actual is None:
            actual = result.get(key)

        if str(actual) != str(expected):
            return False

    return True


def _extract_match(rule: dict[str, Any]) -> dict[str, Any]:
    for field in rule.get("fields") or []:
        if not isinstance(field, dict):
            continue

        match = field.get("match")
        if isinstance(match, dict):
            return match

    return {}
