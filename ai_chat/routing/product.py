from __future__ import annotations

import re
from typing import Any


PRODUCTS_TABLE = "normalized_products"
FUZZY_TITLE_MIN_SCORE = 8
STOP_TOKENS = {
    "why",
    "did",
    "drop",
    "decline",
    "declined",
    "почему",
    "упало",
    "упали",
    "упала",
    "снизилось",
    "снизилась",
    "снизились",
}


def resolve_product(
    *,
    question: str,
    supabase,
    user_id: int = 1,
    shop_id: int = 1,
    marketplace: str = "wb",
) -> dict[str, Any] | None:
    products = load_products(
        supabase=supabase,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
    )
    normalized_question = normalize_text(question)
    best_match = None

    for product in products:
        for candidate in collect_product_aliases(product):
            normalized_candidate = normalize_text(candidate)

            if not normalized_candidate:
                continue

            score = 0

            if normalized_candidate in normalized_question:
                score = len(normalized_candidate)
            elif normalized_question in normalized_candidate:
                score = len(normalized_question)
            elif (
                candidate != product.get("title")
                and token_overlap_score(normalized_question, normalized_candidate) > 0
            ):
                score = token_overlap_score(normalized_question, normalized_candidate)

            if score <= 0:
                continue

            match = {
                **product,
                "matched_text": candidate,
                "score": score,
                "match_type": "exact",
                "matched_tokens": [],
            }

            if best_match is None or match["score"] > best_match["score"]:
                best_match = match

        fuzzy_match = fuzzy_title_match(
            question=normalized_question,
            product=product,
        )

        if fuzzy_match and (
            best_match is None
            or fuzzy_match["score"] > best_match["score"]
        ):
            best_match = fuzzy_match

    return best_match


def load_products(
    *,
    supabase,
    user_id: int,
    shop_id: int,
    marketplace: str,
) -> list[dict[str, Any]]:
    response = (
        supabase
        .table(PRODUCTS_TABLE)
        .select(
            """
            product_key,
            title,
            brand,
            seller_sku,
            subject_name,
            main_photo_url,
            marketplace_product_id
            """
        )
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .execute()
    )

    return response.data or []


def collect_product_aliases(product: dict[str, Any]) -> list[Any]:
    return [
        product.get("title"),
        product.get("seller_sku"),
        product.get("product_key"),
        product.get("marketplace_product_id"),
    ]


def token_overlap_score(question: str, candidate: str) -> int:
    question_tokens = token_stems(question)
    candidate_tokens = token_stems(candidate)
    overlap = question_tokens & candidate_tokens
    return sum(len(token) for token in overlap)


def fuzzy_title_match(
    *,
    question: str,
    product: dict[str, Any],
) -> dict[str, Any] | None:
    title = product.get("title")
    normalized_title = normalize_text(title)

    if not normalized_title:
        return None

    question_tokens = content_tokens(question)
    title_tokens = content_tokens(normalized_title)

    if not question_tokens or not title_tokens:
        return None

    title_stems = {simple_stem(token): token for token in title_tokens}
    matched_tokens = []

    for token in question_tokens:
        token_stem = simple_stem(token)

        if token in title_tokens:
            matched_tokens.append(token)
        elif token_stem in title_stems:
            matched_tokens.append(title_stems[token_stem])

    matched_tokens = sorted(set(matched_tokens))

    if len(matched_tokens) < 2:
        return None

    score = sum(len(token) for token in matched_tokens)

    if score < FUZZY_TITLE_MIN_SCORE:
        return None

    return {
        **product,
        "matched_text": title,
        "score": score,
        "match_type": "fuzzy_title",
        "matched_tokens": matched_tokens,
    }


def content_tokens(value: str) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) >= 3 and token not in STOP_TOKENS
    }


def simple_stem(token: str) -> str:
    for suffix in ("ами", "ями", "ого", "его", "ыми", "ими", "ая", "яя", "ое", "ее", "ые", "ие", "ой", "ей", "ом", "ем", "ах", "ях", "ам", "ям", "а", "я", "ы", "и", "е", "у", "ю"):
        if len(token) >= len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]

    return token


def token_stems(value: str) -> set[str]:
    tokens = normalize_text(value).split()
    return {token[:5] for token in tokens if len(token) >= 5}


def normalize_text(value: Any) -> str:
    text = str(value or "").lower().replace("_", " ")
    text = re.sub(r"[^\w\s]+", " ", text)
    return " ".join(text.split())
