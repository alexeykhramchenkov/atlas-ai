import os
import sys
import json
from pathlib import Path
from statistics import mean
from playwright.sync_api import sync_playwright
 
sys.path.append("/Users/macbook/Projects/wb_profit_bot")
from db.client import supabase

SALEFLOW_BASE_URL = "https://saleflow.pro"
STORAGE_STATE_PATH = "seo/saleflow_storage_state.json"
USER_DATA_DIR = "seo/saleflow_chrome_profile"
TEST_SKU = "439996132"
D1 = "2026-03-23"
D2 = "2026-04-21"
RAW_DIR = "seo/saleflow_api_raw"
HEADLESS = True
# If SaleFlow session expires, temporarily set HEADLESS = False, log in once, then return it to True.


SALEFLOW_LOGIN = os.getenv("SALEFLOW_LOGIN")
SALEFLOW_PASSWORD = os.getenv("SALEFLOW_PASSWORD")


class NonRetryableSeoError(Exception):
    pass


def ensure_dirs():
    Path("seo").mkdir(exist_ok=True)
    Path(RAW_DIR).mkdir(exist_ok=True)


def save_json(name: str, data):
    ensure_dirs()
    path = Path(RAW_DIR) / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {path}")



# Save raw text to file in RAW_DIR
def save_text(name: str, text: str):
    ensure_dirs()
    path = Path(RAW_DIR) / name
    path.write_text(text or "", encoding="utf-8")
    print(f"Saved: {path}")


# --- Supabase integration helpers ---

def load_active_products(limit: int = 1000) -> list[dict]:
    rows = (
        supabase
        .table("normalized_products")
        .select("user_id,shop_id,nm_id,title,brand,vendor_code,subject_name,is_active")
        .eq("is_active", True)
        .not_.is_("nm_id", "null")
        .order("id")
        .limit(limit)
        .execute()
        .data
    )

    products = []
    seen = set()

    for row in rows:
        nm_id = row.get("nm_id")

        if not nm_id:
            continue

        user_id = row.get("user_id") or 1
        shop_id = row.get("shop_id") or str(user_id)

        key = (user_id, shop_id, nm_id)
        if key in seen:
            continue

        products.append({
            "user_id": user_id,
            "shop_id": int(shop_id) if str(shop_id).isdigit() else shop_id,
            "nm_id": str(nm_id),
            "title": row.get("title"),
            "brand": row.get("brand"),
            "vendor_code": row.get("vendor_code"),
            "subject_name": row.get("subject_name"),
            "source": "normalized_products",
        })
        seen.add(key)

    print("Products source: normalized_products")
    return products


def safe_number(value):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


# Helper: split a list into chunks of given size (default 500)
def chunks(items, size=500):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def save_summary_to_supabase(product: dict, summary: dict):
    row = {
        "user_id": product["user_id"],
        "shop_id": product["shop_id"],
        "nm_id": int(product["nm_id"]),
        "period_start": summary["period_start"],
        "period_end": summary["period_end"],
        "total_keywords": summary.get("total_keywords"),
        "keywords_with_position": summary.get("keywords_with_position"),
        "avg_position": summary.get("avg_position"),
        "top_10_count": summary.get("top_10_count"),
        "avg_top_10_position": summary.get("avg_top_10_position"),
        "top_30_count": summary.get("top_30_count"),
        "avg_top_30_position": summary.get("avg_top_30_position"),
        "top_100_count": summary.get("top_100_count"),
        "avg_top_100_position": summary.get("avg_top_100_position"),
        "visibility_score": summary.get("visibility_score"),
        "raw": summary,
    }

    supabase.table("seo_product_summary_snapshots").insert(row).execute()
    print(f"Saved summary to Supabase: user_id={product['user_id']}, shop_id={product['shop_id']}, nm_id={product['nm_id']}")




# --- New keyword helpers and save_keywords_to_supabase implementation ---

def get_top_zone(position):
    pos = safe_number(position)
    if pos is None or pos <= 0:
        return None
    if pos <= 10:
        return "top_10"
    if pos <= 30:
        return "top_30"
    if pos <= 100:
        return "top_100"
    return "outside_top_100"


def get_frequency(row: dict):
    for key in ["frequency", "freq", "wb_count", "total_found"]:
        value = row.get(key)
        if value is not None:
            return safe_number(value)
    return None




def detect_keyword_event(old_position, new_position, old_zone, new_zone):
    old_pos = safe_number(old_position)
    new_pos = safe_number(new_position)

    if old_pos is None and new_pos is not None:
        return "new_keyword"

    if old_pos is not None and new_pos is None:
        return "lost_keyword"

    if old_zone != new_zone:
        if new_zone == "top_10":
            return "entered_top_10"
        if old_zone == "top_10":
            return "left_top_10"
        if new_zone == "top_30":
            return "entered_top_30"
        if old_zone == "top_30":
            return "left_top_30"
        if new_zone == "top_100":
            return "entered_top_100"
        if old_zone == "top_100":
            return "left_top_100"

    if old_pos is not None and new_pos is not None:
        diff = new_pos - old_pos
        if diff >= 20:
            return "position_drop"
        if diff <= -20:
            return "position_growth"

    return None


def save_keywords_to_supabase(product: dict, rows: list[dict], period_start: str, period_end: str):
    now = __import__("datetime").datetime.utcnow().isoformat()

    prepared = []
    keyword_texts = []

    for row in rows:
        keyword = get_keyword(row)
        if not keyword:
            continue

        keyword = keyword.strip().lower()
        if not keyword:
            continue

        position = get_position(row)
        frequency = get_frequency(row)

        prepared.append({
            "keyword": keyword,
            "position": safe_number(position),
            "top_zone": get_top_zone(position),
            "frequency": frequency,
            "visibility": safe_number(row.get("visibility")),
            "traffic": safe_number(row.get("traffic")),
            "sales": safe_number(row.get("sales")),
            "revenue": safe_number(row.get("revenue")),
            "raw": row,
        })
        keyword_texts.append(keyword)

    keyword_texts = sorted(set(keyword_texts))

    if not prepared:
        print(f"No keyword rows to save for nm_id={product['nm_id']}")
        return 0

    # 1) Load existing global keywords in batches
    keyword_map = {}
    frequency_history_rows = []

    for part in chunks(keyword_texts, 500):
        existing = (
            supabase
            .table("seo_keywords")
            .select("id,keyword,current_frequency")
            .in_("keyword", part)
            .execute()
            .data
        )

        for item in existing:
            keyword_map[item["keyword"]] = item

    # 2) Insert missing global keywords in one batch
    missing_keywords = [kw for kw in keyword_texts if kw not in keyword_map]

    if missing_keywords:
        insert_rows = []
        frequency_by_keyword = {item["keyword"]: item["frequency"] for item in prepared}

        for kw in missing_keywords:
            insert_rows.append({
                "keyword": kw,
                "current_frequency": frequency_by_keyword.get(kw),
                "source": "saleflow",
            })

        for part in chunks(insert_rows, 500):
            supabase.table("seo_keywords").insert(part).execute()

        # reload created keywords
        for part in chunks(missing_keywords, 500):
            created = (
                supabase
                .table("seo_keywords")
                .select("id,keyword,current_frequency")
                .in_("keyword", part)
                .execute()
                .data
            )
            for item in created:
                keyword_map[item["keyword"]] = item

    # 3) Update keyword frequency only when changed
    for item in prepared:
        kw = item["keyword"]
        frequency = item["frequency"]
        keyword_record = keyword_map.get(kw)
        if not keyword_record or frequency is None:
            continue

        old_frequency = safe_number(keyword_record.get("current_frequency"))
        if old_frequency != frequency:
            supabase.table("seo_keywords").update({
                "current_frequency": frequency,
                "updated_at": now,
            }).eq("id", keyword_record["id"]).execute()

            frequency_history_rows.append({
                "keyword_id": keyword_record["id"],
                "frequency": frequency,
                "source": "saleflow",
            })

    if frequency_history_rows:
        for part in chunks(frequency_history_rows, 500):
            supabase.table("seo_keyword_frequency_history").insert(part).execute()

    keyword_ids = [keyword_map[item["keyword"]]["id"] for item in prepared if item["keyword"] in keyword_map]
    keyword_ids = sorted(set(keyword_ids))
    seen_keyword_ids = set(keyword_ids)

    # 4) Load current product-keyword links once
    current_map = {}

    for part in chunks(keyword_ids, 500):
        existing_links = (
            supabase
            .table("product_keywords")
            .select("id,keyword_id,current_position,current_top_zone,active")
            .eq("user_id", product["user_id"])
            .eq("shop_id", product["shop_id"])
            .eq("nm_id", int(product["nm_id"]))
            .in_("keyword_id", part)
            .execute()
            .data
        )

        for link in existing_links:
            current_map[link["keyword_id"]] = link

    insert_links = []
    event_rows = []
    updated = 0

    # 5) Insert new links in batch; update existing links only when needed
    for item in prepared:
        keyword_record = keyword_map.get(item["keyword"])
        if not keyword_record:
            continue

        keyword_id = keyword_record["id"]
        current = current_map.get(keyword_id)

        if current:
            old_position = current.get("current_position")
            old_zone = current.get("current_top_zone")
            event_type = detect_keyword_event(old_position, item["position"], old_zone, item["top_zone"])

            supabase.table("product_keywords").update({
                "current_position": item["position"],
                "current_top_zone": item["top_zone"],
                "current_visibility": item["visibility"],
                "current_traffic": item["traffic"],
                "current_sales": item["sales"],
                "current_revenue": item["revenue"],
                "current_frequency": item["frequency"],
                "active": True,
                "last_seen_at": now,
                "updated_at": now,
                "raw": item["raw"],
            }).eq("id", current["id"]).execute()

            updated += 1

            if event_type:
                event_rows.append({
                    "user_id": product["user_id"],
                    "shop_id": product["shop_id"],
                    "nm_id": int(product["nm_id"]),
                    "keyword_id": keyword_id,
                    "event_type": event_type,
                    "old_position": safe_number(old_position),
                    "new_position": item["position"],
                })

        else:
            insert_links.append({
                "user_id": product["user_id"],
                "shop_id": product["shop_id"],
                "nm_id": int(product["nm_id"]),
                "keyword_id": keyword_id,
                "current_position": item["position"],
                "current_top_zone": item["top_zone"],
                "current_visibility": item["visibility"],
                "current_traffic": item["traffic"],
                "current_sales": item["sales"],
                "current_revenue": item["revenue"],
                "current_frequency": item["frequency"],
                "active": True,
                "raw": item["raw"],
            })

            event_rows.append({
                "user_id": product["user_id"],
                "shop_id": product["shop_id"],
                "nm_id": int(product["nm_id"]),
                "keyword_id": keyword_id,
                "event_type": "new_keyword",
                "old_position": None,
                "new_position": item["position"],
            })

    for part in chunks(insert_links, 500):
        supabase.table("product_keywords").insert(part).execute()

    # 6) Mark lost keywords in one query + per-row updates/events only for lost
    all_active_links = (
        supabase
        .table("product_keywords")
        .select("id,keyword_id,current_position,current_top_zone,active")
        .eq("user_id", product["user_id"])
        .eq("shop_id", product["shop_id"])
        .eq("nm_id", int(product["nm_id"]))
        .eq("active", True)
        .execute()
        .data
    )

    lost_count = 0

    for link in all_active_links:
        if link["keyword_id"] in seen_keyword_ids:
            continue

        supabase.table("product_keywords").update({
            "active": False,
            "current_position": None,
            "current_top_zone": None,
            "updated_at": now,
        }).eq("id", link["id"]).execute()

        event_rows.append({
            "user_id": product["user_id"],
            "shop_id": product["shop_id"],
            "nm_id": int(product["nm_id"]),
            "keyword_id": link["keyword_id"],
            "event_type": "lost_keyword",
            "old_position": safe_number(link.get("current_position")),
            "new_position": None,
        })

        lost_count += 1

    if event_rows:
        for part in chunks(event_rows, 500):
            supabase.table("product_keyword_events").insert(part).execute()

    print(
        f"Saved/updated product keywords: nm_id={product['nm_id']}, "
        f"inserted={len(insert_links)}, updated={updated}, lost={lost_count}, events={len(event_rows)}"
    )

    return len(prepared)


def request_json(api, url: str):
    print(f"GET {url}")
    response = api.get(url)
    print("Status:", response.status)

    if response.status != 200:
        print(response.text()[:1000])
        return None

    try:
        return response.json()
    except Exception:
        text = response.text()
        print(text[:1000])
        return None


def extract_keyword_rows(data):
    if not data:
        return []

    if isinstance(data, list):
        return data

    if not isinstance(data, dict):
        return []

    direct_keys = [
        "data", "items", "keywords", "rows", "result", "results",
        "table", "records", "content", "list"
    ]

    for key in direct_keys:
        value = data.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = extract_keyword_rows(value)
            if nested:
                return nested

    # fallback: find the biggest list of dicts anywhere in JSON
    best = []

    def walk(value):
        nonlocal best

        if isinstance(value, list):
            dict_items = [x for x in value if isinstance(x, dict)]
            if len(dict_items) > len(best):
                best = dict_items
            for item in value:
                walk(item)

        elif isinstance(value, dict):
            for item in value.values():
                walk(item)

    walk(data)
    return best


def get_position(row):
    for key in [
        "avg_organic_position",
        "organic_position",
        "organicPosition",
        "position",
        "avg_position",
        "avgPosition",
        "pos",
    ]:
        value = row.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except Exception:
            pass
    return None


def get_keyword(row):
    for key in ["keyword", "query", "word", "text", "name"]:
        value = row.get(key)
        if value:
            return str(value)
    return None


def print_json_structure(data, prefix="root", depth=0, max_depth=4):
    if depth > max_depth:
        return

    if isinstance(data, dict):
        print(f"{prefix}: dict keys={list(data.keys())[:30]}")
        for key, value in list(data.items())[:10]:
            print_json_structure(value, f"{prefix}.{key}", depth + 1, max_depth)

    elif isinstance(data, list):
        print(f"{prefix}: list len={len(data)}")
        if data:
            print_json_structure(data[0], f"{prefix}[0]", depth + 1, max_depth)

    else:
        print(f"{prefix}: {type(data).__name__}")


# Attach a logger to capture "/keywords" API responses and save them
def attach_keywords_response_logger(page):
    def handle_response(response):
        try:
            url = response.url
            if "/keywords" not in url:
                return

            status = response.status
            text = response.text()

            print("KEYWORDS API DETECTED")
            print("Status:", status)
            print("URL:", url)
            print("Body preview:", text[:500])

            safe_name = (
                url.replace("https://", "")
                .replace("http://", "")
                .replace("/", "_")
                .replace("?", "__")
                .replace("&", "_")
                .replace("=", "-")
            )[:180]

            save_text(f"captured_keywords_{status}_{safe_name}.txt", text)

            try:
                data = json.loads(text)
                rows = extract_keyword_rows(data)
                print(f"Captured rows parsed: {len(rows)}")
                if rows:
                    print("Captured first row:", rows[0])
                    save_json("captured_keywords_best.json", rows)
                    save_json("captured_keywords_metrics.json", calc_metrics(rows))
            except Exception as e:
                print(f"Could not parse captured keywords json: {e}")

        except Exception as e:
            print(f"Keywords response logger error: {e}")

    page.on("response", handle_response)


def attach_keywords_request_logger(page):
    def handle_request(request):
        try:
            url = request.url
            if "/keywords" not in url:
                return

            print("KEYWORDS REQUEST DETECTED")
            print("Method:", request.method)
            print("URL:", url)

            headers = request.all_headers()
            print("Headers:")
            print(json.dumps(headers, ensure_ascii=False, indent=2))

            safe_name = (
                url.replace("https://", "")
                .replace("http://", "")
                .replace("/", "_")
                .replace("?", "__")
                .replace("&", "_")
                .replace("=", "-")
            )[:180]

            post_data = request.post_data or ""
            print("Post data:", post_data[:1000])

            save_json(f"captured_keywords_request_{safe_name}.json", {
                "method": request.method,
                "url": url,
                "headers": headers,
                "post_data": post_data,
            })

        except Exception as e:
            print(f"Keywords request logger error: {e}")

    page.on("request", handle_request)


def calc_metrics(rows):
    positions = []
    top_100_positions = []
    top_10_positions = []
    top_30_positions = []

    for row in rows:
        pos = get_position(row)
        if pos is None or pos <= 0:
            continue

        positions.append(pos)

        if pos <= 100:
            top_100_positions.append(pos)

        if pos <= 10:
            top_10_positions.append(pos)

        if pos <= 30:
            top_30_positions.append(pos)

    visibility_score = (
        len(top_10_positions) * 10 +
        len(top_30_positions) * 5 +
        len(top_100_positions) * 1
    )

    return {
        "total_keywords": len(rows),
        "keywords_with_position": len(positions),
        "avg_position": round(mean(positions), 2) if positions else None,
        "top_100_count": len(top_100_positions),
        "avg_top_100_position": round(mean(top_100_positions), 2) if top_100_positions else None,
        "top_10_count": len(top_10_positions),
        "avg_top_10_position": round(mean(top_10_positions), 2) if top_10_positions else None,
        "top_30_count": len(top_30_positions),
        "avg_top_30_position": round(mean(top_30_positions), 2) if top_30_positions else None,
        "visibility_score": visibility_score,
    }


# --- Browser fetch helpers and warmup for SaleFlow APIs ---

def browser_fetch_json(page, url: str, method: str = "GET", body=None, retries: int = 3):
    full_url = url if url.startswith("http") else f"{SALEFLOW_BASE_URL}{url}"

    last_result = None

    for attempt in range(1, retries + 1):
        try:
            result = page.evaluate(
                """
                async ({url, method, body}) => {
                    try {
                        const options = {
                            method: method,
                            credentials: 'include',
                            headers: {
                                'Accept': 'application/json, text/plain, */*',
                                'Content-Type': 'application/json'
                            }
                        };

                        if (body !== null && body !== undefined) {
                            options.body = JSON.stringify(body);
                        }

                        const response = await fetch(url, options);
                        const text = await response.text();
                        return {
                            ok: true,
                            status: response.status,
                            text: text
                        };
                    } catch (error) {
                        return {
                            ok: false,
                            status: 0,
                            text: String(error)
                        };
                    }
                }
                """,
                {"url": full_url, "method": method, "body": body},
            )

            last_result = result
            print(f"FETCH {method} {full_url} | attempt {attempt}")
            print("Status:", result.get("status"))

            if result.get("ok") and result.get("status") != 0:
                try:
                    data = json.loads(result.get("text") or "null")
                except Exception:
                    data = None

                return result, data

            print("Fetch failed:", (result.get("text") or "")[:300])
            page.wait_for_timeout(1500 * attempt)

        except Exception as e:
            print(f"browser_fetch_json error attempt={attempt}: {e}")
            page.wait_for_timeout(1500 * attempt)

    return last_result or {"status": 0, "text": "fetch failed"}, None


def warmup_saleflow_item(page, sku: str, d1: str, d2: str):
    warmup_urls = [
        f"/api/cabinet/wb/get/product/{sku}/access",
        f"/api/public/data/user?resource=%2Fwb%2Fitem%2F{sku}",
        f"/api/analytics/v1/wb/items/{sku}/by_period?d1={d1}&d2={d2}",
        f"/api/wb/get/item/{sku}/full_page/versions",
        f"/api/analytics/v1/wb/groups?sku={sku}",
        f"/api/annotations?target_id={sku}&mp=wb&addPhoto=1&addVersion=1",
    ]

    print("Warming up SaleFlow item APIs...")

    for url in warmup_urls:
        try:
            result, _ = browser_fetch_json(page, url, retries=2)
            preview = (result.get("text") or "")[:200]
            if preview:
                print("Preview:", preview)
        except Exception as e:
            print(f"Warmup skipped for {url}: {e}")
        page.wait_for_timeout(700)


# --- Auto login helper ---

def auto_login_if_needed(page, context):
    if "/login" not in page.url:
        return True

    if not SALEFLOW_LOGIN or not SALEFLOW_PASSWORD:
        print("SaleFlow session is not active.")
        print("Set env vars first:")
        print("export SALEFLOW_LOGIN='your_login'")
        print("export SALEFLOW_PASSWORD='your_password'")
        return False

    print("SaleFlow session is not active. Trying auto-login...")

    page.wait_for_timeout(3000)

    inputs = page.locator("input")
    count = inputs.count()
    print(f"Login page inputs found: {count}")

    if count < 2:
        print("Could not find login/password inputs")
        return False

    inputs.nth(0).fill(SALEFLOW_LOGIN)
    inputs.nth(1).fill(SALEFLOW_PASSWORD)
    page.keyboard.press("Enter")

    page.wait_for_timeout(8000)

    if "/login" in page.url:
        buttons = page.locator("button")
        if buttons.count() > 0:
            try:
                buttons.first.click(timeout=3000)
                page.wait_for_timeout(8000)
            except Exception:
                pass

    if "/login" in page.url:
        print("Auto-login failed. Need manual check.")
        return False

    context.storage_state(path=STORAGE_STATE_PATH)
    print(f"Session saved: {STORAGE_STATE_PATH}")
    return True


# Manual UI capture for /keywords API
def capture_keywords_from_ui(sku: str = TEST_SKU):
    ensure_dirs()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=False,
            viewport={"width": 1500, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        page = context.pages[0] if context.pages else context.new_page()
        attach_keywords_response_logger(page)
        attach_keywords_request_logger(page)

        item_url = f"{SALEFLOW_BASE_URL}/wb/item/{sku}?d1=23.03.2026&d2=21.04.2026&tab=visibility"
        print(f"Opening item page: {item_url}")
        page.goto(item_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(8000)

        print("Now manually scroll to 'Видимость на Wildberries' and select 'Органическая'.")
        print("The script will capture the exact keywords API URL and response.")
        input("After table loads, press ENTER to close browser: ")

        context.close()


def fetch_keywords_direct(product=None, sku: str = TEST_SKU, d1: str = D1, d2: str = D2, save_to_db: bool = True):
    if product is None:
        product = {
            "user_id": None,
            "shop_id": None,
            "nm_id": str(sku),
            "title": None,
        }
    else:
        sku = str(product["nm_id"])
    ensure_dirs()

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            channel="chrome",
            headless=HEADLESS,
            viewport={"width": 1500, "height": 900},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--no-default-browser-check",
            ],
        )

        page = context.pages[0] if context.pages else context.new_page()

        page.set_extra_http_headers({
            "x-page-url": f"https://saleflow.pro/wb/item/{sku}?d1=25.04.2026&d2=24.05.2026&tab=visibility#pageModel=%7B%22page%22%3A1%7D"
        })

        item_url = f"{SALEFLOW_BASE_URL}/wb/item/{sku}"
        print(f"Opening item page: {item_url}")
        page.goto(item_url, wait_until="domcontentloaded", timeout=60000)
        print("Current page URL:", page.url)

        if "/login" in page.url:
            logged_in = auto_login_if_needed(page, context)
            if not logged_in:
                context.close()
                return

            page.goto(item_url, wait_until="domcontentloaded", timeout=60000)
            print("Current page URL after login:", page.url)

        page.wait_for_timeout(3000)

        warmup_saleflow_item(page, sku, d1, d2)
        page.wait_for_timeout(3000)

        request_body = {
            "startRow": 0,
            "endRow": 500,
            "rowGroupCols": [],
            "valueCols": [],
            "pivotCols": [],
            "pivotMode": False,
            "groupKeys": [],
            "filterModel": {},
            "sortModel": []
        }

        # UI sends POST, not GET.
        position_url = f"/api/analytics/v1/wb/items/{sku}/keywords?positionType=position&d1={d1}&d2={d2}"
        position_result, position_data = browser_fetch_json(page, position_url, method="POST", body=request_body)
        save_json(f"keywords_{sku}_position_warmup.json", position_data)
        page.wait_for_timeout(1500)

        api_url = f"/api/analytics/v1/wb/items/{sku}/keywords?positionType=organic_position&d1={d1}&d2={d2}"
        print(f"FETCH ORGANIC KEYWORDS {api_url}")
        result, data = browser_fetch_json(page, api_url, method="POST", body=request_body)

        if result.get("status") != 200:
            print((result.get("text") or "")[:1000])
            save_json(f"keywords_{sku}_organic_position_error.json", result)
            context.close()
            return

        raw_text = result.get("text") or ""

        print("Raw response preview:")
        print(raw_text[:1000])

        save_json(f"keywords_{sku}_organic_position.json", data)

        if "твой план провалился" in raw_text.lower():
            raise NonRetryableSeoError(f"SaleFlow has no available SEO data for nm_id={sku}")

        if isinstance(data, dict):
            message = str(data.get("message") or "")
            if "твой план провалился" in message.lower():
                raise NonRetryableSeoError(f"SaleFlow has no available SEO data for nm_id={sku}: {message}")

        rows = extract_keyword_rows(data)
        if not rows:
            raise RuntimeError(f"No SEO rows returned for nm_id={sku}")

        summary = {
                "user_id": product.get("user_id"),
                "shop_id": product.get("shop_id"),
                "nm_id": sku,
                "title": product.get("title"),
                "period_start": d1,
                "period_end": d2,
                "created_at": __import__("datetime").datetime.utcnow().isoformat(),
        }
        print(f"Rows loaded: {len(rows)}")

        if len(rows) == 0:
                print("JSON structure preview:")
                print_json_structure(data)

        metrics = calc_metrics(rows)
        summary.update(metrics)
        print("Metrics:")
        print(json.dumps(metrics, ensure_ascii=False, indent=2))

        print("Sample rows:")
        for row in rows[:10]:
                print({
                    "keyword": get_keyword(row),
                    "avg_position": row.get("avg_position"),
                    "avg_organic_position": row.get("avg_organic_position"),
                    "position": get_position(row),
                })

        save_json(f"keywords_{sku}_best.json", rows)
        save_json(f"keywords_{sku}_metrics.json", metrics)
        save_json(f"keywords_{sku}_summary.json", summary)

        if save_to_db and product.get("user_id") and product.get("shop_id"):
                save_summary_to_supabase(product, summary)
                save_keywords_to_supabase(product, rows, d1, d2)

        print("Background fetch completed successfully")
        context.close()

# Retry wrapper for fetch_keywords_direct
def fetch_keywords_with_retry(product: dict, d1: str, d2: str, attempts: int = 3) -> bool:
    for attempt in range(1, attempts + 1):
        try:
            print(f"Attempt {attempt}/{attempts} for nm_id={product['nm_id']}")
            fetch_keywords_direct(product=product, d1=d1, d2=d2, save_to_db=True)
            return True
        except NonRetryableSeoError as e:
            print(f"Skip without retry nm_id={product['nm_id']}: {e}")
            return False

        except Exception as e:
            print(f"Attempt {attempt}/{attempts} failed for nm_id={product['nm_id']}: {e}")

            if attempt < attempts:
                wait_ms = 3000 * attempt
                print(f"Retry after {wait_ms / 1000:.0f}s...")
                try:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_page()
                        page.wait_for_timeout(wait_ms)
                        browser.close()
                except Exception:
                    pass

    print(f"Failed after {attempts} attempts: nm_id={product['nm_id']}")
    return False


# Fetch all active products from DB and fetch keywords for each
def fetch_all_active_products(d1: str = D1, d2: str = D2):
    products = load_active_products()
    print(f"Active products loaded: {len(products)}")

    if not products:
        print("No active products found in normalized_products")
        return

    success = 0
    failed = 0

    for index, product in enumerate(products, start=1):
        print("=" * 70)
        print(f"[{index}/{len(products)}] user_id={product['user_id']} shop_id={product['shop_id']} nm_id={product['nm_id']}")

        ok = fetch_keywords_with_retry(product=product, d1=d1, d2=d2, attempts=3)

        if ok:
            success += 1
        else:
            failed += 1

    print("=" * 70)
    print(f"Done. success={success}, failed={failed}")


if __name__ == "__main__":
    fetch_all_active_products()