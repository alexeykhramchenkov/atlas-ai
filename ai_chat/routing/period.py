

from __future__ import annotations

import re


DEFAULT_PERIOD_DAYS = 30
MAX_PERIOD_DAYS = 365


def resolve_period_days(question: str, default_period_days: int = DEFAULT_PERIOD_DAYS) -> int:
    text = question.lower()

    explicit = extract_period_days(text)
    if explicit is not None:
        return normalize_period_days(explicit)

    if contains_any(text, ["сегодня", "today"]):
        return 1

    if contains_any(text, ["вчера", "yesterday"]):
        return 1

    if contains_any(text, ["недел", "week"]):
        return 7

    if contains_any(text, ["месяц", "month"]):
        return 30

    if contains_any(text, ["квартал", "quarter"]):
        return 90

    if contains_any(text, ["год", "year"]):
        return 365

    return default_period_days


def extract_period_days(text: str) -> int | None:
    patterns = [
        r"последние\s+(\d{1,3})\s+д",
        r"последних\s+(\d{1,3})\s+д",
        r"за\s+(\d{1,3})\s+д",
        r"за\s+последние\s+(\d{1,3})\s+д",
        r"last\s+(\d{1,3})\s+day",
        r"for\s+(\d{1,3})\s+day",
        r"past\s+(\d{1,3})\s+day",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))

    return None


def normalize_period_days(value: int) -> int:
    if value <= 0:
        return DEFAULT_PERIOD_DAYS

    if value > MAX_PERIOD_DAYS:
        return MAX_PERIOD_DAYS

    return value


def contains_any(text: str, markers: list[str]) -> bool:
    return any(marker in text for marker in markers)
