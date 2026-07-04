from pathlib import Path

SYNC_DIR = Path("sync")

RAW_TABLES = [
    "wb_orders_raw",
    "wb_sales_raw",
    "wb_stocks_raw",
    "wb_prices_raw",
    "wb_ads_raw",
    "wb_cards_raw",
    "wb_funnel_raw",
    "wb_realization_raw",
    "wb_feedbacks_raw",
    "wb_questions_raw",
    "wb_supplies_raw",
    "wb_tariffs_raw",
    "wb_search_raw",
    "wb_finance_raw",
    "wb_statuses_raw",
]

METRIC_BUILDERS = {
    "sync_nm_daily_metrics.py",
    "sync_region_daily_metrics.py",
    "sync_unified_events.py",
    "sync_wb_events.py",
}


def scan_file(path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")

    found_raw = [table for table in RAW_TABLES if table in text]

    has_direct_insert = ".insert" in text.lower() or "insert(" in text.lower()
    has_raw_helper = "save_raw_payload" in text
    has_upsert = "upsert" in text.lower()
    is_metric_builder = path.name in METRIC_BUILDERS

    return found_raw, has_direct_insert, has_raw_helper, has_upsert, is_metric_builder


for file in sorted(SYNC_DIR.glob("sync_*.py")):
    found_raw, has_direct_insert, has_raw_helper, has_upsert, is_metric_builder = scan_file(file)

    write_status = "✅" if has_direct_insert or has_raw_helper else "❌"
    raw_helper_status = "✅" if has_raw_helper else "❌"
    upsert_status = "✅" if has_upsert else "❌"

    print(f"\n{file}")
    print(f"  type: {'METRIC BUILDER' if is_metric_builder else 'API / RAW SYNC'}")
    print(f"  RAW tables: {found_raw if found_raw else '❌ нет RAW таблицы'}")
    print(f"  RAW write: {write_status}")
    print(f"  save_raw_payload: {raw_helper_status}")
    print(f"  upsert normalized/analytics: {upsert_status}")

    if not found_raw and not is_metric_builder:
        print("  ⚠️  Нужно проверить: API sync без RAW таблицы")

    if is_metric_builder:
        print("  ℹ️  Это builder метрик/событий. RAW может быть не нужен.")