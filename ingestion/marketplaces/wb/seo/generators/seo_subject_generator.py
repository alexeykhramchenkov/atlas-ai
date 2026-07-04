import sys
import os
sys.path.append("/Users/macbook/Projects/wb_profit_bot")
import requests
import re
from collections import Counter
import time
from db.client import supabase


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.wildberries.ru/",
    "Origin": "https://www.wildberries.ru"
}


# --- WB competitor search ---
WB_SEARCH_URLS = [
    "https://u-search.wb.ru/exactmatch/ru/common/v18/search",
    "https://search.wb.ru/exactmatch/ru/common/v18/search",
    "https://search.wb.ru/exactmatch/ru/common/v9/search",
    "https://search.wb.ru/exactmatch/ru/common/v5/search",
    "https://search.wb.ru/exactmatch/ru/common/v4/search",
]

def parse_products_from_text(text: str):
    products = []

    names = re.findall(r'"name"\s*:\s*"([^"]+)"', text)
    brands = re.findall(r'"brand"\s*:\s*"([^"]*)"', text)

    for i, name in enumerate(names):
        brand = brands[i] if i < len(brands) else None
        products.append({"name": name, "brand": brand})

    return products


def fetch_wb_products(query: str, pages: int = 5):
    products = []
    seen_names = set()

    for page in range(1, pages + 1):
        params = {
            "ab_testid": "new_sorting_algorithm",
            "ab_testing": "false",
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
            "suppressSpellcheck": "false"
        }

        page_products = []

        for url in WB_SEARCH_URLS:
            try:
                response = requests.get(url, params=params, headers=HEADERS, timeout=20)

                if response.status_code == 429:
                    print(f"429 Too Many Requests: page={page}, url={url}")
                    time.sleep(5)
                    continue

                if response.status_code != 200:
                    print(f"WB status {response.status_code}: page={page}, url={url}")
                    continue

                try:
                    data = response.json()
                    page_products = data.get("data", {}).get("products", [])
                except Exception:
                    page_products = parse_products_from_text(response.text)

                if not page_products:
                    text_products = parse_products_from_text(response.text)
                    if text_products:
                        page_products = text_products

                if page_products:
                    break

            except Exception as e:
                print(f"WB fetch error: query={query}, page={page}, url={url}, error={e}")

        if not page_products:
            print(f"No products parsed for query={query}, page={page}")

        clean_page_products = []

        for product in page_products:
            name = product.get("name")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            clean_page_products.append(product)

        print(f"Searching: {query} | page {page}: {len(clean_page_products)} products")
        products.extend(clean_page_products)
        time.sleep(3)

    return products


def clean(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-zA-Zа-яА-Я0-9 ]", " ", text)
    return " ".join(text.split())


def extract_keywords(titles):
    stop_words = {
        "для", "или", "при", "под", "над", "без", "это", "как", "и", "в", "на", "с", "по", "от", "до",
        "the", "and", "with", "from",
        "beberry", "jolly", "jingle", "shop", "kids", "wow", "hello", "meow", "live", "style", "dress"
    }

    required_words = {
        "эльза", "эльзы", "холодное", "сердце", "принцесса", "принцессы", "платье", "костюм", "карнавальный", "карнавальное", "новогодний", "новогоднее"
    }

    bad_words = {
        "110", "116", "120", "122", "128", "134", "140", "146", "152",
        "садик", "одежда", "белое", "голубое", "пайетками", "длинным", "шлейфом", "год", "новый"
    }

    bad_phrases = {
        "платье девочки",
        "платье нарядное",
        "нарядное платье",
        "нарядное праздничное",
        "платье праздничное",
        "платье пышное",
        "детское платье",
        "платье детское",
        "новый год",
        "девочки нарядное",
        "костюм платье",
    }

    phrases = []

    for t in titles:
        words = [
            w for w in clean(t).split()
            if len(w) > 2
            and w not in stop_words
            and not w.isdigit()
            and not re.fullmatch(r"[a-z]+", w)
        ]

        for n in [2, 3, 4]:
            for i in range(len(words) - n + 1):
                phrase_words = words[i:i+n]
                phrase = " ".join(phrase_words)

                if phrase in bad_phrases:
                    continue

                if any(w in bad_words for w in phrase_words):
                    continue

                if not any(w in required_words for w in phrase_words):
                    continue

                phrases.append(phrase)

    freq = Counter(phrases)

    keywords = [
        phrase for phrase, count in freq.items()
        if len(phrase.split()) >= 2
    ]

    return sorted(keywords, key=lambda x: (-freq[x], x))[:100]


def save_to_db(query: str, keywords: list[str]):
    rows = []

    if not keywords:
        print(f"No keywords to save for query: {query}")
        return 0

    for i, kw in enumerate(keywords):
        rows.append({
            "nm_id": None,
            "query": kw,
            "source": "competitor_miner",
            "priority": 1 if i < 10 else 2,
            "active": True
        })

    new_rows = [
        row for row in rows
        if is_actual_keyword(row.get("query"))
        and not keyword_exists(row.get("nm_id"), row.get("query"))
    ]

    if not new_rows:
        print(f"All keywords already exist for query: {query}")
        return 0

    supabase.table("seo_queries").insert(new_rows).execute()
    return len(new_rows)


# New function to get title by nm_id from query_rank_snapshots
def get_title_by_nm_id(nm_id):
    if not nm_id:
        return None

    try:
        rows = supabase.table("query_rank_snapshots") \
            .select("product_name,brand") \
            .eq("nm_id", nm_id) \
            .not_.is_("product_name", "null") \
            .limit(1) \
            .execute().data

        if not rows:
            return None

        product_name = rows[0].get("product_name")
        brand = rows[0].get("brand")

        if product_name and brand:
            return f"{product_name} {brand}"

        return product_name or brand

    except Exception as e:
        print(f"Could not load title for nm_id={nm_id}: {e}")
        return None


# Check if keyword exists for nm_id and query
def keyword_exists(nm_id, query):
    try:
        q = supabase.table("seo_queries") \
            .select("id") \
            .eq("query", query) \
            .limit(1)

        if nm_id is None:
            q = q.is_("nm_id", "null")
        else:
            q = q.eq("nm_id", nm_id)

        rows = q.execute().data
        return bool(rows)

    except Exception as e:
        print(f"Could not check keyword exists: nm_id={nm_id}, query={query}, error={e}")
        return False


# --- New: is_actual_keyword ---
def is_actual_keyword(query: str):
    if not query:
        return False

    query = clean(query)
    words = query.split()

    required_words = {
        "эльза", "эльзы", "холодное", "сердце", "принцесса", "принцессы", "платье", "костюм", "карнавальный", "карнавальное", "новогодний", "новогоднее"
    }

    bad_words = {
        "110", "116", "120", "122", "128", "134", "140", "146", "152",
        "садик", "одежда", "белое", "голубое", "пайетками", "длинным", "шлейфом", "год", "новый",
        "jolly", "jingle", "shop", "kids", "wow", "hello", "meow", "live", "style", "dress", "beberry"
    }

    bad_phrases = {
        "платье девочки",
        "платье нарядное",
        "нарядное платье",
        "нарядное праздничное",
        "платье праздничное",
        "платье пышное",
        "детское платье",
        "платье детское",
        "новый год",
        "девочки нарядное",
        "костюм платье",
    }

    if len(words) < 2:
        return False

    if query in bad_phrases:
        return False

    if any(w in bad_words for w in words):
        return False

    if not any(w in required_words for w in words):
        return False

    return True


# --- New: cleanup_bad_competitor_keywords ---
def cleanup_bad_competitor_keywords():
    try:
        rows = supabase.table("seo_queries") \
            .select("id,query,source") \
            .eq("source", "competitor_miner") \
            .execute().data

        bad_ids = []

        for row in rows:
            query = row.get("query") or ""
            if not is_actual_keyword(query):
                bad_ids.append(row.get("id"))

        if not bad_ids:
            print("Bad competitor_miner keywords: 0")
            return 0

        for keyword_id in bad_ids:
            supabase.table("seo_queries") \
                .delete() \
                .eq("id", keyword_id) \
                .execute()

        print(f"Bad competitor_miner keywords deleted: {len(bad_ids)}")
        return len(bad_ids)

    except Exception as e:
        print(f"Could not cleanup competitor keywords: {e}")
        return 0


def cleanup_bad_db_miner_keywords():
    try:
        rows = supabase.table("seo_queries") \
            .select("id,query,source") \
            .eq("source", "db_miner") \
            .execute().data

        bad_ids = []

        for row in rows:
            query = row.get("query") or ""
            words = query.split()

            if len(words) < 2 or query == "beberry":
                bad_ids.append(row.get("id"))

        if not bad_ids:
            print("Bad db_miner keywords: 0")
            return 0

        for keyword_id in bad_ids:
            supabase.table("seo_queries") \
                .delete() \
                .eq("id", keyword_id) \
                .execute()

        print(f"Bad db_miner keywords deleted: {len(bad_ids)}")
        return len(bad_ids)

    except Exception as e:
        print(f"Could not cleanup bad db_miner keywords: {e}")
        return 0


# --- Competitor miner ---
def load_seed_queries(limit=10):
    rows = supabase.table("seo_queries") \
        .select("query,priority,active") \
        .eq("active", True) \
        .in_("source", ["manual", "seed"]) \
        .order("priority") \
        .limit(limit) \
        .execute().data

    queries = []
    seen = set()

    for row in rows:
        query = row.get("query")
        if query and query not in seen:
            queries.append(query)
            seen.add(query)

    return queries


# --- Load competitor titles from DB for seed queries ---
def load_competitor_titles_from_db(seed_queries, limit=1000):
    titles = []
    seen = set()

    for query in seed_queries:
        try:
            rows = supabase.table("query_rank_snapshots") \
                .select("product_name,brand,query") \
                .eq("query", query) \
                .limit(limit) \
                .execute().data

            print(f"DB competitors: {query} -> {len(rows)} rows")

            for row in rows:
                product_name = row.get("product_name")
                brand = row.get("brand")

                if product_name and brand:
                    title = f"{product_name} {brand}"
                else:
                    title = product_name or brand

                if title and title not in seen:
                    titles.append(title)
                    seen.add(title)

        except Exception as e:
            print(f"Could not load DB competitors for query={query}: {e}")

    return titles


def run_competitor_miner():
    seed_query = "платье эльзы"
    cleanup_bad_competitor_keywords()
    print(f"Seed query: {seed_query}")

    products = fetch_wb_products(seed_query, pages=5)
    print(f"Competitor products loaded: {len(products)}")

    titles = []

    for product in products:
        name = product.get("name")
        brand = product.get("brand")

        if name and brand:
            titles.append(f"{name} {brand}")
        elif name:
            titles.append(name)

    print(f"Competitor titles loaded: {len(titles)}")

    keywords = extract_keywords(titles)
    print(f"Keywords found: {len(keywords)}")

    for kw in keywords[:100]:
        print(kw)

    saved = save_to_db(seed_query, keywords)
    print(f"Done. Competitor keywords saved: {saved}")


def run():
    print("Loading products from DB...")
    cleanup_bad_db_miner_keywords()

    products = supabase.table("funnel_snapshots") \
        .select("nm_id,title") \
        .limit(50) \
        .execute().data

    if not products:
        print("No products found")
        return

    print(f"Products loaded: {len(products)}")

    total_saved = 0

    for p in products:
        nm_id = p.get("nm_id")
        title = p.get("title") or get_title_by_nm_id(nm_id)

        if not title:
            print(f"Skip nm_id={nm_id} — empty title and no product_name in query_rank_snapshots")
            continue

        keywords = extract_keywords([title])

        if not keywords:
            print(f"Skip nm_id={nm_id} — no keywords from title: {title}")
            continue

        rows = [
            {
                "nm_id": nm_id,
                "query": kw,
                "source": "db_miner",
                "priority": 2,
                "active": True
            }
            for kw in keywords
        ]

        if not rows:
            continue

        new_rows = [row for row in rows if not keyword_exists(row.get("nm_id"), row.get("query"))]

        if not new_rows:
            print(f"{title} -> all keys already exist")
            continue

        supabase.table("seo_queries").insert(new_rows).execute()
        total_saved += len(new_rows)

        print(f"{title} -> {len(new_rows)} new keys")

    print(f"Done. Total saved: {total_saved}")


if __name__ == "__main__":
    run_competitor_miner()