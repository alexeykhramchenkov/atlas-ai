from typing import Any

from ai_chat.answer_builder.fields import extract_path
from ai_chat.answer_builder.formatters import format_value


def apply_template(
    *,
    rule: dict[str, Any],
    fields: list[dict[str, Any]],
    language: str,
    data: dict[str, Any] | None = None,
    request: dict[str, Any] | None = None,
) -> str:
    template_name = rule.get("template_name")

    if template_name == "top_product_stock":
        return _render_key_value(
            title=rule.get("title_template") or template_name,
            fields=fields,
        )

    if template_name == "ranking_list":
        return _render_ranking_list(
            rule=rule,
            data=data or {},
            request=request or {},
            language=language,
        )

    raise ValueError(f"Unknown answer template: {template_name}")


def _render_key_value(
    *,
    title: str,
    fields: list[dict[str, Any]],
) -> str:
    lines = [title]

    for field in fields:
        lines.extend(
            [
                "",
                f"{field['label']}:",
                field["formatted"],
            ]
        )

    return "\n".join(lines)


def _render_ranking_list(
    *,
    rule: dict[str, Any],
    data: dict[str, Any],
    request: dict[str, Any],
    language: str,
) -> str:
    config = _extract_template_config(rule)
    rows_path = config.get("rows_path") or "rows"
    rows = _extract_optional_path(data, rows_path) or []

    if not rows:
        return config.get("empty_text") or "Данных не найдено."

    limit = int(request.get("limit") or data.get("meta", {}).get("limit") or len(rows))
    title = _render_text_template(
        rule.get("title_template") or config.get("title_template") or "Рейтинг:",
        data=data,
        request=request,
        top_row=rows[0],
    )
    item_fields = _extract_item_fields(rule)

    lines = [title, ""]

    for index, row in enumerate(rows[:limit], start=1):
        lines.append(_render_ranking_item(index=index, row=row, fields=item_fields, language=language))

    summary_template = config.get("summary_template")
    if summary_template:
        lines.extend(
            [
                "",
                "AI Summary:",
                _render_text_template(
                    summary_template,
                    data=data,
                    request=request,
                    top_row=rows[0],
                ),
            ]
        )

    return "\n".join(lines)


def _render_ranking_item(
    *,
    index: int,
    row: dict[str, Any],
    fields: list[dict[str, Any]],
    language: str,
) -> str:
    label_parts = []
    value = ""

    for field in fields:
        role = field.get("role")
        formatted = _format_row_field(row=row, field=field, language=language)

        if not formatted or formatted == "—":
            continue

        if role == "item_value":
            unit = field.get("unit")
            value = f"{formatted} {unit}".strip() if unit else formatted
            continue

        label_parts.append(formatted)

    label = " / ".join(label_parts) if label_parts else "—"
    if value:
        return f"{index}. {label} — {value}"

    return f"{index}. {label}"


def _format_row_field(
    *,
    row: dict[str, Any],
    field: dict[str, Any],
    language: str,
) -> str:
    value = _extract_first_row_value(row=row, field=field)

    if value is None:
        return ""

    formatter = field.get("formatter") or "text"
    return format_value(value=value, formatter=formatter, language=language)


def _extract_first_row_value(row: dict[str, Any], field: dict[str, Any]) -> Any:
    paths = []
    path = field.get("path")
    if path:
        paths.append(path)
    paths.extend(field.get("fallback_paths") or [])

    for candidate in paths:
        value = _extract_optional_path(row, candidate)
        if value not in [None, ""]:
            return value

    return None


def _extract_template_config(rule: dict[str, Any]) -> dict[str, Any]:
    for field in rule.get("fields") or []:
        if not isinstance(field, dict):
            continue

        config = field.get("template")
        if isinstance(config, dict):
            return config

    return {}


def _extract_item_fields(rule: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []

    for field in rule.get("fields") or []:
        if not isinstance(field, dict):
            continue

        if field.get("path") and field.get("role"):
            fields.append(field)

    return fields


def _render_text_template(
    template: str,
    *,
    data: dict[str, Any],
    request: dict[str, Any],
    top_row: dict[str, Any],
) -> str:
    values = {
        "period_days": request.get("period_days") or data.get("period_days"),
        "top_product": top_row.get("product_key") or top_row.get("title") or top_row.get("product_name"),
    }

    try:
        return str(template).format(**values)
    except (KeyError, ValueError):
        return str(template)


def _extract_optional_path(data: Any, path: str) -> Any:
    try:
        return extract_path(data, path)
    except (KeyError, IndexError, TypeError, ValueError):
        return None
