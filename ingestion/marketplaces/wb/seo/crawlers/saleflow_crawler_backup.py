import os
import sys
import json
from pathlib import Path
from statistics import mean
from playwright.sync_api import sync_playwright

sys.path.append("/Users/macbook/Projects/wb_profit_bot")

SALEFLOW_BASE_URL = "https://saleflow.pro"
STORAGE_STATE_PATH = "seo/saleflow_storage_state.json"
USER_DATA_DIR = "seo/saleflow_chrome_profile"
TEST_SKU = "439996132"
D1 = "2026-03-23"
D2 = "2026-04-21"
RAW_DIR = "seo/saleflow_api_raw"


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
        "position",
        "organic_position",
        "organicPosition",
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

    for row in rows:
        pos = get_position(row)
        if pos is None or pos <= 0:
            continue

        positions.append(pos)

        if pos <= 100:
            top_100_positions.append(pos)

    return {
        "total_keywords": len(rows),
        "keywords_with_position": len(positions),
        "avg_position": round(mean(positions), 2) if positions else None,
        "top_100_count": len(top_100_positions),
        "avg_top_100_position": round(mean(top_100_positions), 2) if top_100_positions else None,
    }


# --- Browser fetch helpers and warmup for SaleFlow APIs ---

def browser_fetch_json(page, url: str, method: str = "GET", body=None):
    result = page.evaluate(
        """
        async ({url, method, body}) => {
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
                status: response.status,
                text: text
            };
        }
        """,
        {"url": url, "method": method, "body": body},
    )

    print(f"FETCH {method} {url}")
    print("Status:", result.get("status"))

    try:
        data = json.loads(result.get("text") or "null")
    except Exception:
        data = None

    return result, data


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
        result, _ = browser_fetch_json(page, url)
        preview = (result.get("text") or "")[:200]
        if preview:
            print("Preview:", preview)
        page.wait_for_timeout(700)


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


def fetch_keywords_direct(sku: str = TEST_SKU, d1: str = "2026-04-25", d2: str = "2026-05-24"):
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

        item_url = f"{SALEFLOW_BASE_URL}/wb/item/{sku}"
        print(f"Opening item page: {item_url}")
        page.goto(item_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(7000)

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

        print("Raw response preview:")
        print((result.get("text") or "")[:1000])

        save_json(f"keywords_{sku}_organic_position.json", data)

        rows = extract_keyword_rows(data)
        print(f"Rows loaded: {len(rows)}")

        if len(rows) == 0:
            print("JSON structure preview:")
            print_json_structure(data)

        metrics = calc_metrics(rows)
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

        context.close()


if __name__ == "__main__":
    fetch_keywords_direct()