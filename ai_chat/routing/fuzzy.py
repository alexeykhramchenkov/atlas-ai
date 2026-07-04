

from difflib import SequenceMatcher


THRESHOLD = 0.82


def similarity(a: str, b: str) -> float:
    a = (a or "").lower().strip()
    b = (b or "").lower().strip()

    if not a or not b:
        return 0.0

    return SequenceMatcher(None, a, b).ratio()



def fuzzy_match(text: str, aliases: list[str], threshold: float = THRESHOLD):
    text = (text or "").lower()

    best_alias = None
    best_score = 0.0

    words = text.split()

    for alias in aliases:
        alias = alias.lower().strip()

        if alias in text:
            return alias, 1.0

        score = similarity(text, alias)

        if score > best_score:
            best_alias = alias
            best_score = score

        for word in words:
            score = similarity(word, alias)

            if score > best_score:
                best_alias = alias
                best_score = score

    if best_score >= threshold:
        return best_alias, best_score

    return None, 0.0