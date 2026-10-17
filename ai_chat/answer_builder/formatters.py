from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


def format_value(
    *,
    value: Any,
    formatter: str,
    language: str,
    options: dict | None = None,
) -> str:
    if formatter == "signed_percent":
        if value is None:
            return (options or {}).get("zero_baseline", "—")
        return ("+" if value > 0 else "−" if value < 0 else "") + _format_number(value=abs(value), language=language) + "%"
    if value is None:
        return (options or {}).get("missing_text", "—")

    if formatter == "plural":
        forms = (options or {}).get("forms")
        if not isinstance(forms, list) or len(forms) != 3:
            raise ValueError("Plural formatter requires three forms")
        number = abs(Decimal(str(value)))
        if number != number.to_integral_value():return forms[1]
        number = int(number)
        return forms[0] if number % 10 == 1 and number % 100 != 11 else forms[1] if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14) else forms[2]

    if formatter == "text":
        return str(value)
    if formatter == "html_text":
        from html import escape
        return escape(str(value), quote=False)
    if formatter == "date":
        from datetime import datetime
        from zoneinfo import ZoneInfo
        parsed = datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(ZoneInfo('Europe/Moscow'))
        if (options or {}).get('style') == 'day_month':
            months = ('января','февраля','марта','апреля','мая','июня',
                      'июля','августа','сентября','октября','ноября','декабря')
            return f'{parsed.day} {months[parsed.month-1]}'
        return parsed.strftime('%d.%m.%Y')
    if formatter == "change":
        options = options or {}
        pct = value.get("change_pct")
        if pct is None:
            return options["zero_baseline"]
        if pct == 0:
            return options["unchanged"]
        return ("+" if pct > 0 else "−") + _format_number(value=abs(pct), language=language) + "%"
    if formatter == "number":
        return _format_number(value=_round_display(value, options), language=language)
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
        rounded = _round_display(value, options)
        days = _format_number(value=rounded, language=language)
        if language == "ru":
            if (options or {}).get('decimals') == 0:
                count = abs(int(rounded))
                word = 'дней' if 11 <= count % 100 <= 14 else 'день' if count % 10 == 1 else 'дня' if count % 10 in (2,3,4) else 'дней'
                return f"{days} {word}"
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


def _round_display(value, options):
    places = (options or {}).get('decimals')
    if places is None:
        return value
    if type(places) is not int or not 0 <= places <= 6:
        raise ValueError('decimals must be an integer from 0 to 6')
    return _to_decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
