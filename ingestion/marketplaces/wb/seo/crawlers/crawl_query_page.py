

import hashlib
import json
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


BASE_URL = "https://u-search.wb.ru/exactmatch/ru/common/v18/search"
DEBUG_RESPONSE_PATH = PROJECT_ROOT / "seo" / "debug_query_page_response.json"

PAGE = 1
QUERY_LIMIT = 10
BATCH_SIZE = 100
SLEEP_SECONDS = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://www.wildberries.ru",
    "Referer": "https://www.wildberries.ru/",
}


def build_event_hash(query: str, nm_id: int, position: int, snapshot_date: str) -> str:
    raw_key = f"wb_query_rank|{query}|{nm_id}|{position}|{snapshot_date}"
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def fetch_active_queries(limit: int = QUERY_LIMIT) -> list[dict]:
    response = (
        supabase
        .table("seo_queries")
        .select("id, query, priority")
        .eq("active", True)
        .order("priority")
        .limit(limit)
        .execute()
    )

    return response.data or []


def fetch_search_page(query: str, page: int = PAGE) -> Optional[dict]:
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

        print(f"Query='{query}' page={page} attempt={attempt} status={response.status_code}")

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

        return data

    return None


def extract_products(data: dict) -> list[dict]:
    # 1. direct level
    products = data.get("products")
    if isinstance(products, list) and products:
        return products

    # 2. nested under data
    nested = data.get("data", {}).get("products")
    if isinstance(nested, list) and nested:
        return nested

    # 3. Wildberries search_result fallback (critical case)
    search_result = data.get("search_result")
    if isinstance(search_result, dict):
        sr_products = search_result.get("products")
        if isinstance(sr_products, list) and sr_products:
            return sr_products

    # 4. sometimes WB wraps inside state
    state_products = data.get("state", {}).get("products")
    if isinstance(state_products, list) and state_products:
        return state_products

    # 5. deep fallback: scan recursively (last resort)
    def deep_find(obj):
        if isinstance(obj, list):
            for item in obj:
                if isinstance(item, dict) and "id" in item:
                    return obj
        if isinstance(obj, dict):
            for v in obj.values():
                res = deep_find(v)
                if res:
                    return res
        return None

    fallback = deep_find(data)
    if isinstance(fallback, list):
        return fallback

    return []


def build_rank_rows(query: str, products: list[dict]) -> list[dict]:
    snapshot_date = datetime.utcnow().date().isoformat()
    rows = []

    for position, product in enumerate(products, start=1):
        nm_id = product.get("id")

        if not nm_id:
            continue

        rows.append({
            "query": query,
            "nm_id": int(nm_id),
            "found": True,
            "position": position,
            "page": PAGE,
            "sponsored": False,
            "product_name": product.get("name"),
            "brand": product.get("brand"),
            "event_hash": build_event_hash(
                query=query,
                nm_id=int(nm_id),
                position=position,
                snapshot_date=snapshot_date,
            ),
        })

    return rows


def chunked(items: list[dict], size: int) -> list[list[dict]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def save_rank_rows(rows: list[dict]) -> None:
    if not rows:
        print("No rows to save")
        return

    sent = 0

    for batch in chunked(rows, BATCH_SIZE):
        (
            supabase
            .table("query_rank_snapshots")
            .upsert(batch, on_conflict="event_hash")
            .execute()
        )

        sent += len(batch)
        print(f"Saved batch: {sent}/{len(rows)}")


def crawl_query(query: str) -> None:
    data = fetch_search_page(query=query, page=PAGE)

    if not data:
        print(f"No data for query: {query}")
        return

    products = extract_products(data)
    print(f"Products found for '{query}': {len(products)}")

    if not products:
        print(f"No products found for query: {query}")
        return

    rows = build_rank_rows(query=query, products=products)
    save_rank_rows(rows)


def crawl_queries() -> None:
    queries = fetch_active_queries()
    print(f"Active queries fetched: {len(queries)}")

    if not queries:
        print("No active queries in seo_queries")
        return

    for item in queries:
        query = item.get("query")

        if not query:
            continue

        print(f"\nCrawling query: {query}")
        crawl_query(query)
        time.sleep(SLEEP_SECONDS)

    print("Done")


if __name__ == "__main__":
    crawl_queries()