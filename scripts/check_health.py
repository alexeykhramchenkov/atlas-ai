"""Health check for WB Profit Bot.

Run from project root:
    PYTHONPATH=. python3 scripts/check_health.py
"""

from __future__ import annotations

import importlib
import sys
from dataclasses import dataclass
from datetime import date
from typing import Callable


REQUIRED_PACKAGES = [
    "dotenv",
    "requests",
    "supabase",
    "aiohttp",
    "pandas",
]

REQUIRED_TABLES = [
    "action_log",
    "ad_bid_snapshots",
    "ad_campaigns",
    "ad_daily",
    "business_plans",
    "card_stats",
    "commission_rates",
    "external_ads",
    "external_costs",
    "feedbacks",
    "hypotheses",
    "logistics_tariffs",
    "nm_daily_metrics",
    "nm_metrics_snapshot",
    "order_status_history",
    "orders_daily",
    "questions",
    "realization_report_lines",
    "realization_reports",
    "region_daily_metrics",
    "sales_daily",
    "search_queries_daily",
    "search_query_nm_daily",
    "sku_catalog",
    "stock_snapshots",
    "subscriptions",
    "supplies",
    "supply_items",
    "sync_log",
    "users",
    "wb_ads_raw",
    "wb_cards_raw",
    "wb_events_raw",
    "wb_feedbacks_raw",
    "wb_funnel_raw",
    "wb_orders_raw",
    "wb_prices_raw",
    "wb_questions_raw",
    "wb_realization_raw",
    "wb_sales_raw",
    "wb_stocks_raw",
    "wb_supplies_raw",
    "wb_tariffs_raw",
]


@dataclass
class CheckResult:
    name: str
    ok: bool
    message: str


def print_result(result: CheckResult) -> None:
    icon = "✅" if result.ok else "❌"
    print(f"{icon} {result.name}: {result.message}")


def check_packages() -> CheckResult:
    missing = []

    for package in REQUIRED_PACKAGES:
        try:
            importlib.import_module(package)
        except ModuleNotFoundError:
            missing.append(package)

    if missing:
        return CheckResult(
            name="packages",
            ok=False,
            message=f"missing: {', '.join(missing)}. Install: python3 -m pip install python-dotenv requests supabase aiohttp pandas",
        )

    return CheckResult(name="packages", ok=True, message="all required packages installed")


def check_config() -> CheckResult:
    try:
        from core.config import settings
    except Exception as exc:
        return CheckResult(name="config", ok=False, message=str(exc))

    missing_optional = []
    if not settings.wb_api_key:
        missing_optional.append("WB_API_KEY")
    if not settings.telegram_bot_token:
        missing_optional.append("TELEGRAM_BOT_TOKEN")

    if missing_optional:
        return CheckResult(
            name="config",
            ok=True,
            message=f"required env ok; optional missing: {', '.join(missing_optional)}",
        )

    return CheckResult(name="config", ok=True, message="env loaded")


def check_supabase_connection() -> CheckResult:
    try:
        from db.client import supabase

        supabase.table("users").select("id").limit(1).execute()
    except Exception as exc:
        return CheckResult(name="supabase", ok=False, message=str(exc))

    return CheckResult(name="supabase", ok=True, message="connection ok")


def check_tables() -> CheckResult:
    try:
        from db.client import supabase
    except Exception as exc:
        return CheckResult(name="tables", ok=False, message=f"cannot import supabase client: {exc}")

    failed = []

    for table in REQUIRED_TABLES:
        try:
            supabase.table(table).select("id").limit(1).execute()
        except Exception as exc:
            failed.append(f"{table} ({str(exc)[:80]})")

    if failed:
        return CheckResult(name="tables", ok=False, message=f"missing or inaccessible: {', '.join(failed)}")

    return CheckResult(name="tables", ok=True, message=f"{len(REQUIRED_TABLES)} tables accessible")


def check_wb_token_present() -> CheckResult:
    try:
        from core.config import settings
    except Exception as exc:
        return CheckResult(name="wb token", ok=False, message=f"cannot load config: {exc}")

    token = settings.wb_api_key

    if not token:
        return CheckResult(name="wb token", ok=False, message="WB_API_KEY is missing in .env")

    if len(token) < 20:
        return CheckResult(name="wb token", ok=False, message="WB_API_KEY looks too short")

    try:
        import requests
        response = requests.get(
            "https://statistics-api.wildberries.ru/api/v1/supplier/orders",
            headers={
                "Authorization": token,
            },
            params={
                "dateFrom": date.today().isoformat(),
                "flag": 1,
            },
            timeout=20,
        )

        if response.status_code == 200:
            return CheckResult(name="wb token", ok=True, message="token valid and API reachable")

        if response.status_code == 401:
            return CheckResult(name="wb token", ok=False, message="WB API token unauthorized")

        if response.status_code == 402:
            return CheckResult(name="wb token", ok=False, message="WB API requires payment or access for Statistics category")

        if response.status_code == 403:
            return CheckResult(name="wb token", ok=False, message="WB API token has no access to Statistics category")

        if response.status_code == 429:
            return CheckResult(name="wb token", ok=False, message="WB API rate limit reached")

        return CheckResult(
            name="wb token",
            ok=False,
            message=f"WB API error: {response.status_code} | {response.text[:120]}",
        )

    except Exception as exc:
        return CheckResult(name="wb token", ok=False, message=f"WB API request failed: {exc}")


def run_checks() -> int:
    checks: list[Callable[[], CheckResult]] = [
        check_packages,
        check_config,
        check_supabase_connection,
        check_tables,
        check_wb_token_present,
    ]

    print("\nWB Profit Bot health check\n")

    results = []
    for check in checks:
        result = check()
        results.append(result)
        print_result(result)

    failed = [result for result in results if not result.ok]

    print()
    if failed:
        print(f"Health check failed: {len(failed)} problem(s).")
        return 1

    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(run_checks())