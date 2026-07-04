import hashlib
import json
import re
from collections import Counter
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase


QUERY = "платье эльзы"
TARGET_NM_ID = 809244672
MAX_PAGES = 5

BASE_URL = "https://u-search.wb.ru/exactmatch/ru/common/v18/search"
DEBUG_RESPONSE_PATH = PROJECT_ROOT / "seo" / "debug_wb_search_response.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}


def build_event_hash(query: str, nm_id: int, date: str) -> str:
    raw_key = f"wb_search_rank|{query}|{nm_id}|{date}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def fetch_search_page(query: str, page: int) -> Optional[dict]:
    params = {
        "ab_testid": "new_benefit_sort",
        "appType": "1",
        "curr": "rub",
        "dest": "-1257786",
        "inheritFilters": "false",
        "lang": "ru",
        "page": page,
        "query": query,
        "resultset": "catalog",
        "sort": "popular",
        "spp": "30",
        "suppressSpellcheck": "false",
    }

    for attempt in range(1, 4):
        response = requests.get(
            BASE_URL,
            params=params,
            headers=HEADERS,
            timeout=30,
        )

        print(f"Page {page} attempt {attempt} status: {response.status_code}")

        if response.status_code == 429:
            sleep_seconds = attempt * 5
            print(f"Rate limited. Sleeping {sleep_seconds}s...")
            time.sleep(sleep_seconds)
            continue

        if response.status_code != 200:
            print(response.text[:500])
            return None

        try:
            data = response.json()
        except ValueError:
            DEBUG_RESPONSE_PATH.write_text(response.text, encoding="utf-8")
            print(f"Invalid JSON. Saved raw response to {DEBUG_RESPONSE_PATH}")
            return None

        DEBUG_RESPONSE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("Response keys:", list(data.keys()))
        return data

    return None


def extract_products(data: dict) -> list[dict]:
    if isinstance(data.get("products"), list):
        return data["products"]

    nested_products = data.get("data", {}).get("products")
    if isinstance(nested_products, list):
        return nested_products

    return []


# --- Keyword mining functions ---

def clean(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-zA-Zа-яА-Я0-9 ]", " ", text)
    return " ".join(text.split())


def is_good_keyword(query: str) -> bool:
    query = clean(query)
    words = query.split()

    if len(words) < 2:
        return False

    bad_words = {
        "beberry", "jolly", "jingle", "shop", "kids", "wow", "hello", "meow", "live", "style", "dress",
        "110", "116", "120", "122", "128", "134", "140", "146", "152",
        "анна", "анны", "футболка", "повседневное", "бальное", "корсетное",
        "садик", "одежда", "белое", "голубое", "пайетками", "длинным", "шлейфом"
    }

    core_words = {"эльза", "эльзы", "холодное", "сердце", "принцесса", "принцессы"}
    product_words = {"платье", "костюм", "карнавальный", "карнавальное", "новогодний", "новогоднее"}

    if any(w in bad_words for w in words):
        return False

    has_core = any(w in core_words for w in words)
    has_product = any(w in product_words for w in words)

    if not has_core:
        return False

    if not has_product and not {"холодное", "сердце"}.issubset(set(words)):
        return False

    return True


def extract_keywords_from_titles(titles: list[str], limit: int = 100) -> list[str]:
    stop_words = {
        "для", "или", "при", "под", "над", "без", "это", "как", "и", "в", "на", "с", "по", "от", "до",
        "the", "and", "with", "from"
    }

    phrases = []

    for title in titles:
        words = [
            word for word in clean(title).split()
            if len(word) > 2 and word not in stop_words and not word.isdigit()
        ]

        for n in [2, 3, 4]:
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i+n])
                if is_good_keyword(phrase):
                    phrases.append(phrase)

    freq = Counter(phrases)
    return sorted(freq.keys(), key=lambda x: (-freq[x], x))[:limit]


def keyword_exists(query: str) -> bool:
    rows = (
        supabase
        .table("seo_queries")
        .select("id")
        .eq("query", query)
        .limit(1)
        .execute()
        .data
    )
    return bool(rows)


def save_keywords(keywords: list[str]) -> int:
    rows = []

    for i, keyword in enumerate(keywords):
        if keyword_exists(keyword):
            continue

        rows.append({
            "nm_id": None,
            "query": keyword,
            "source": "crawl_wb_search",
            "priority": 1 if i < 10 else 2,
            "active": True,
        })

    if not rows:
        print("No new keywords to save")
        return 0

    supabase.table("seo_queries").insert(rows).execute()
    return len(rows)


def crawl_keywords(query: str = QUERY, max_pages: int = MAX_PAGES) -> None:
    titles = []
    seen_nm_ids = set()

    print(f"Keyword crawl query: {query}")

    for page in range(1, max_pages + 1):
        time.sleep(2)
        data = fetch_search_page(query, page)

        if not data:
            continue

        products = extract_products(data)
        print(f"Page {page} products: {len(products)}")

        for product in products:
            nm_id = product.get("id")
            if nm_id in seen_nm_ids:
                continue
            seen_nm_ids.add(nm_id)

            name = product.get("name")
            brand = product.get("brand")

            if name and brand:
                titles.append(f"{name} {brand}")
            elif name:
                titles.append(name)

    print(f"Titles collected: {len(titles)}")

    keywords = extract_keywords_from_titles(titles, limit=100)
    print(f"Keywords found: {len(keywords)}")

    for keyword in keywords:
        print(keyword)

    saved = save_keywords(keywords)
    print(f"Done. Keywords saved: {saved}")


def find_nm_position(query: str, target_nm_id: int, max_pages: int = MAX_PAGES) -> dict:
    global_position = 0
    pages_loaded = 0

    for page in range(1, max_pages + 1):
        time.sleep(2)

        data = fetch_search_page(query, page)
        if not data:
            continue

        products = extract_products(data)
        pages_loaded += 1

        print(f"Page {page} products: {len(products)}")

        if not products:
            continue

        for product in products:
            global_position += 1
            nm_id = product.get("id")

            if not nm_id:
                continue

            if int(nm_id) == int(target_nm_id):
                return {
                    "found": True,
                    "position": global_position,
                    "page": page,
                    "product_name": product.get("name"),
                    "brand": product.get("brand"),
                    "pages_loaded": pages_loaded,
                }

    return {
        "found": False,
        "position": None,
        "page": 1 if pages_loaded > 0 else None,
        "product_name": None,
        "brand": None,
        "pages_loaded": pages_loaded,
    }


def save_rank_snapshot(query: str, nm_id: int, result: dict) -> None:
    today = datetime.utcnow().date().isoformat()

    row = {
        "query": query,
        "nm_id": nm_id,
        "found": result.get("found"),
        "position": result.get("position"),
        "page": result.get("page"),
        "sponsored": False,
        "product_name": result.get("product_name"),
        "brand": result.get("brand"),
        "event_hash": build_event_hash(query, nm_id, today),
    }

    (
        supabase
        .table("query_rank_snapshots")
        .upsert(row, on_conflict="event_hash")
        .execute()
    )

    print("Saved to query_rank_snapshots")


def load_keywords_for_rank_check(limit: int = 100) -> list[str]:
    rows = (
        supabase
        .table("seo_queries")
        .select("query,active,priority")
        .eq("active", True)
        .order("priority")
        .limit(limit)
        .execute()
        .data
    )

    keywords = []
    seen = set()

    for row in rows:
        query = row.get("query")
        if query and query not in seen:
            keywords.append(query)
            seen.add(query)

    return keywords


def crawl_rank_for_keywords(target_nm_id: int = TARGET_NM_ID, max_pages: int = MAX_PAGES) -> None:
    keywords = load_keywords_for_rank_check(limit=100)

    print(f"Target nm_id: {target_nm_id}")
    print(f"Keywords loaded: {len(keywords)}")

    if not keywords:
        print("No keywords found in seo_queries")
        return

    for index, query in enumerate(keywords, start=1):
        print("-" * 50)
        print(f"[{index}/{len(keywords)}] Checking: {query}")

        result = find_nm_position(
            query=query,
            target_nm_id=target_nm_id,
            max_pages=max_pages,
        )

        print("Result:", result)

        if result.get("pages_loaded", 0) == 0:
            print("No valid pages loaded. Skip save.")
            continue

        save_rank_snapshot(
            query=query,
            nm_id=target_nm_id,
            result=result,
        )

        time.sleep(2)

    print("Done. Rank check completed.")


def crawl_one_query() -> None:
    print(f"Query: {QUERY}")
    print(f"Target nm_id: {TARGET_NM_ID}")

    result = find_nm_position(
        query=QUERY,
        target_nm_id=TARGET_NM_ID,
        max_pages=MAX_PAGES,
    )

    print("Result:", result)

    if result.get("pages_loaded", 0) == 0:
        print("No valid pages loaded. Snapshot not saved.")
        return

    save_rank_snapshot(
        query=QUERY,
        nm_id=TARGET_NM_ID,
        result=result,
    )


if __name__ == "__main__":
    crawl_rank_for_keywords()