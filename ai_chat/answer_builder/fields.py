from typing import Any

from ai_chat.answer_builder.formatters import format_value


def extract_fields(
    *,
    data: dict[str, Any],
    field_rules: list[dict[str, Any]],
    language: str,
) -> list[dict[str, Any]]:
    fields = []

    for field_rule in field_rules:
        path = field_rule.get("path")
        if not path:
            continue

        hide_if_missing = bool(field_rule.get("hide_if_missing"))

        try:
            value = extract_path(data, path)
        except (KeyError, IndexError, TypeError, ValueError):
            if hide_if_missing:
                continue
            value = None

        formatter = field_rule.get("formatter") or "text"
        fields.append(
            {
                "label": field_rule.get("label") or path,
                "path": path,
                "formatter": formatter,
                "value": value,
                "formatted": format_value(
                    value=value,
                    formatter=formatter,
                    language=language,
                ),
            }
        )

    return fields


def extract_path(data: Any, path: str) -> Any:
    current = data

    for part in path.split("."):
        if part.endswith("[]"):
            key = part[:-2]
            if not isinstance(current, dict):
                raise ValueError(
                    f"Cannot extract path '{path}': cannot access list '{key}'"
                )

            current = current[key]
            if not isinstance(current, list):
                raise ValueError(
                    f"Cannot extract path '{path}': '{key}' is not a list"
                )
            continue

        if isinstance(current, list):
            if not current:
                raise ValueError(
                    f"Cannot extract path '{path}': step returned empty rows"
                )

            try:
                index = int(part)
            except ValueError as error:
                raise ValueError(
                    f"Cannot extract path '{path}': index '{part}' is not an integer"
                ) from error

            if index < 0 or index >= len(current):
                raise ValueError(
                    f"Cannot extract path '{path}': index {part} out of range"
                )

            current = current[index]
            continue

        if isinstance(current, dict):
            if part not in current:
                raise ValueError(
                    f"Cannot extract path '{path}': key '{part}' not found"
                )

            current = current[part]
            continue

        raise ValueError(
            f"Cannot extract path '{path}': cannot access '{part}'"
        )

    return current
