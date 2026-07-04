

from __future__ import annotations

import re


GREETINGS = {
    "hi",
    "hello",
    "hey",
    "привет",
    "здравствуй",
    "здравствуйте",
}


def is_valid_analytics_question(question: str) -> bool:
    text = question.strip().lower()

    if not text:
        return False

    if len(text) < 3:
        return False

    if text in GREETINGS:
        return False

    if re.fullmatch(r"[\d\W_]+", text):
        return False

    return True