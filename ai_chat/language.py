

SUPPORTED_LANGUAGES = {"ru", "en"}
DEFAULT_LANGUAGE = "ru"
ENGLISH_ANALYTICS_PREFIXES = (
    "why did",
    "why has",
    "why have",
    "what caused",
    "which",
    "show",
    "find",
)


def detect_language(text: str, default: str = DEFAULT_LANGUAGE) -> str:
    """
    Detect answer language without LLM.

    MVP logic:
    - Count Cyrillic Russian letters.
    - Count Latin English letters.
    - Return the language with more letters.
    - If equal or unclear, return default language.
    """
    if not text:
        return default

    text_lower = text.lower()
    normalized_text = " ".join(text_lower.split())

    if normalized_text.startswith(ENGLISH_ANALYTICS_PREFIXES):
        return "en"

    ru_chars = sum(
        1
        for char in text_lower
        if ("а" <= char <= "я") or char == "ё"
    )

    en_chars = sum(
        1
        for char in text_lower
        if "a" <= char <= "z"
    )

    if ru_chars > en_chars:
        return "ru"

    if en_chars > ru_chars:
        return "en"

    return default if default in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
