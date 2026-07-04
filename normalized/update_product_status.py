

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from dotenv import load_dotenv
from supabase import create_client


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY / SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


STOCK_TABLE = "snapshots_stocks_daily"
CATALOG_TABLE = "sku_catalog"
BATCH_SIZE = 100


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def to_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def fetch_latest_snapshot_date() -> Optional[str]:
    response = (
        supabase
        .table(STOCK_TABLE)
        .select("snapshot_date")
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )

    rows = response.data or []
    if not rows:
        return None

    return rows[0].get("snapshot_date")


def fetch_stock_rows(snapshot_date: str) -> List[Dict[str, Any]]:
    response = (
        supabase
        .table(STOCK_TABLE)
        .select("nm_id, quantity")
        .eq("snapshot_date", snapshot_date)
        .execute()
    )
    return response.data or []


def build_stock_by_nm(rows: List[Dict[str, Any]]) -> Dict[int, int]:
    stock_by_nm: Dict[int, int] = {}

    for row in rows:
        nm_id = to_int(row.get("nm_id"))
        if nm_id is None:
            continue

        quantity = to_int(row.get("quantity")) or 0
        stock_by_nm[nm_id] = stock_by_nm.get(nm_id, 0) + quantity

    return stock_by_nm


def fetch_catalog_rows() -> List[Dict[str, Any]]:
    response = (
        supabase
        .table(CATALOG_TABLE)
        .select("product_key, nm_id, product_status")
        .execute()
    )
    return response.data or []


def build_updates(
    catalog_rows: List[Dict[str, Any]],
    stock_by_nm: Dict[int, int],
) -> List[Dict[str, Any]]:
    updates: List[Dict[str, Any]] = []
    now = utc_now_iso()

    for row in catalog_rows:
        product_key = row.get("product_key")
        nm_id = to_int(row.get("nm_id"))
        current_status = row.get("product_status") or "active"

        if not product_key or nm_id is None:
            continue

        if current_status == "archived":
            continue

        total_stock = stock_by_nm.get(nm_id, 0)
        new_status = current_status

        if total_stock <= 0 and current_status == "active":
            new_status = "paused"
        elif total_stock > 0 and current_status == "paused":
            new_status = "active"

        if new_status != current_status:
            updates.append(
                {
                    "product_key": product_key,
                    "product_status": new_status,
                    "updated_at": now,
                    "last_sync_at": now,
                }
            )

    return updates


def upsert_updates(rows: List[Dict[str, Any]]) -> None:
    for start in range(0, len(rows), BATCH_SIZE):
        batch = rows[start:start + BATCH_SIZE]

        for row in batch:
            (
                supabase
                .table(CATALOG_TABLE)
                .update(
                    {
                        "product_status": row["product_status"],
                        "updated_at": row["updated_at"],
                        "last_sync_at": row["last_sync_at"],
                    }
                )
                .eq("product_key", row["product_key"])
                .execute()
            )

        print(f"Updated batch: {start + len(batch)}/{len(rows)}")


def print_summary(
    catalog_rows: List[Dict[str, Any]],
    stock_by_nm: Dict[int, int],
    updates: List[Dict[str, Any]],
) -> None:
    active_to_paused: Set[str] = set()
    paused_to_active: Set[str] = set()

    for row in updates:
        if row.get("product_status") == "paused":
            active_to_paused.add(row.get("product_key"))
        elif row.get("product_status") == "active":
            paused_to_active.add(row.get("product_key"))

    total_stock_products = sum(1 for value in stock_by_nm.values() if value > 0)

    print(f"Products in sku_catalog: {len(catalog_rows)}")
    print(f"Products with stock > 0: {total_stock_products}")
    print(f"Products changed active -> paused: {len(active_to_paused)}")
    print(f"Products changed paused -> active: {len(paused_to_active)}")
    print(f"Total updates: {len(updates)}")


def main() -> None:
    latest_date = fetch_latest_snapshot_date()
    if not latest_date:
        print("No stock snapshots found")
        return

    print(f"Latest stock snapshot date: {latest_date}")

    stock_rows = fetch_stock_rows(latest_date)
    print(f"Stock rows fetched: {len(stock_rows)}")

    stock_by_nm = build_stock_by_nm(stock_rows)
    print(f"Products in stock snapshot: {len(stock_by_nm)}")

    catalog_rows = fetch_catalog_rows()
    updates = build_updates(catalog_rows, stock_by_nm)

    print_summary(catalog_rows, stock_by_nm, updates)

    if not updates:
        print("No status updates needed")
        return

    upsert_updates(updates)
    print("Done")


if __name__ == "__main__":
    main()