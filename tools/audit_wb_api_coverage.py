from pathlib import Path

EXPECTED_CONTOURS = {
    "cards": ["wb_api/endpoints/cards.py", "sync/sync_cards.py"],
    "prices": ["wb_api/endpoints/prices.py", "sync/sync_prices.py"],
    "stocks": ["wb_api/endpoints/stocks.py", "sync/sync_stocks.py"],
    "orders": ["wb_api/endpoints/orders.py", "sync/sync_orders.py"],
    "sales": ["wb_api/endpoints/sales.py", "sync/sync_sales.py"],
    "ads": ["wb_api/endpoints/ads.py", "sync/sync_ads.py"],
    "finance": ["wb_api/endpoints/finance.py", "sync/sync_finance.py"],
    "funnel": ["wb_api/endpoints/funnel.py", "sync/sync_funnel.py"],
    "search": ["sync/sync_search.py"],
    "feedbacks": ["wb_api/endpoints/feedbacks.py", "sync/sync_feedbacks.py"],
    "questions": ["wb_api/endpoints/questions.py", "sync/sync_questions.py"],
    "supplies": ["wb_api/endpoints/supplies.py", "sync/sync_supplies.py"],
    "tariffs": ["wb_api/endpoints/tariffs.py", "sync/sync_tariffs.py"],
    "statuses": ["sync/sync_statuses.py"],
    "realization": ["sync/sync_realization.py"],
}

def exists(path: str) -> str:
    return "✅" if Path(path).exists() else "❌"

for contour, files in EXPECTED_CONTOURS.items():
    print(f"\n{contour.upper()}")
    for file in files:
        print(f"  {exists(file)} {file}")