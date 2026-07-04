from db.client import supabase

from ai_chat.datasets.orders import get_orders_dataset
from ai_chat.analysis.engine import run_analysis


request = {
    "dataset": "orders",
    "analysis": "best",
    "period_days": 30,
    "limit": 10,
}


print("=" * 80)
print("REQUEST")
print(request)
print("=" * 80)


dataset = get_orders_dataset(
    supabase=supabase,
    user_id=1,
    shop_id=1,
    marketplace="wb",
    period_days=request["period_days"],
)


print()
print("DATASET")
print(dataset["dataset"])
print("ROWS:", dataset["meta"]["rows_count"])
print("=" * 80)


result = run_analysis(
    dataset=request["dataset"],
    analysis=request["analysis"],
    rows=dataset["rows"],
    limit=request["limit"],
)


print()
print("RESULT")
print(result["analysis"])
print("ROWS:", len(result["rows"]))
print("=" * 80)


for row in result["rows"]:
    print()
    print("product_key:", row.get("product_key"))
    print("orders:", row.get("orders"))
    print("revenue:", row.get("revenue"))
    print("profit:", row.get("profit"))
    print("analysis_score:", row.get("analysis_score"))