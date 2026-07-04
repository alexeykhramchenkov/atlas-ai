from decimal import Decimal, InvalidOperation
from typing import Any


def format_value(
    *,
    value: Any,
    formatter: str,
    language: str,
) -> str:
    if value is None:
        return "—"

    if formatter == "text":
        return str(value)
    if formatter == "number":
        return _format_number(value=value, language=language)
    if formatter == "money":
        amount = _format_number(value=value, language=language)
        if language == "ru":
            return f"{amount} ₽"
        return f"${amount}"
    if formatter == "qty":
        quantity = _format_number(value=value, language=language)
        if language == "ru":
            return f"{quantity} шт"
        return f"{quantity} pcs"
    if formatter == "percent":
        return f"{_format_number(value=value, language=language)}%"
    if formatter == "days":
        days = _format_number(value=value, language=language)
        if language == "ru":
            return f"{days} дней"
        return f"{days} days"

    raise ValueError(f"Unknown formatter: {formatter}")


def _format_number(*, value: Any, language: str) -> str:
    number = _to_decimal(value)

    if number == number.to_integral_value():
        formatted = f"{int(number):,}"
    else:
        formatted = f"{number:,.2f}".rstrip("0").rstrip(".")

    if language == "ru":
        return formatted.replace(",", " ")

    return formatted


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Cannot format numeric value: {value}") from error
