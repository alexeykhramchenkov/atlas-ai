

import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase



SOURCE_TABLE = "raw_wb_realization"
TARGET_TABLE = "normalized_realization_reports"
MARKETPLACE = "wb"
BATCH_SIZE = 100


def get_watermark(state: Optional[Dict[str, Any]]) -> tuple[Any, int]:
    if not state:
        return None, 0

    return (
        state.get("last_raw_updated_at"),
        int(state.get("last_raw_id") or 0),
    )


def to_number(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    if value in [None, ""]:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_date(value: Any) -> Optional[str]:
    if value in [None, ""]:
        return None
    if isinstance(value, str):
        return value[:10]
    try:
        return value.isoformat()[:10]
    except AttributeError:
        return str(value)[:10]


def payload_number(payload: Dict[str, Any], *keys: str) -> float:
    for key in keys:
        if key in payload:
            return to_number(payload.get(key))
    return 0


def fetch_raw_rows(
    user_id: int,
    shop_id: int,
    last_raw_updated_at: Any = None,
    last_raw_id: int = 0,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .eq("shop_id", shop_id)
            .eq("marketplace", MARKETPLACE)
            .order("updated_at")
            .order("id")
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < batch_size:
            break

        offset += batch_size

    if last_raw_updated_at is None:
        return rows

    filtered_rows: List[Dict[str, Any]] = []

    for row in rows:
        updated_at = row.get("updated_at")
        row_id = int(row.get("id") or 0)

        if updated_at is None:
            continue

        if updated_at > last_raw_updated_at:
            filtered_rows.append(row)
            continue

        if updated_at == last_raw_updated_at and row_id > last_raw_id:
            filtered_rows.append(row)

    return filtered_rows


def build_report_rows(raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    reports: Dict[Tuple[Any, Any, str, int], Dict[str, Any]] = {}

    for raw_row in raw_rows:
        payload = raw_row.get("payload") or {}
        if not isinstance(payload, dict):
            continue

        user_id = raw_row.get("user_id")
        shop_id = raw_row.get("shop_id")
        marketplace = raw_row.get("marketplace") or MARKETPLACE
        report_id = to_int(raw_row.get("report_id"))

        if not user_id or not shop_id or not report_id:
            continue

        key = (user_id, shop_id, marketplace, report_id)

        if key not in reports:
            reports[key] = {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "report_id": report_id,
                "report_from": parse_date(raw_row.get("report_from")),
                "report_to": parse_date(raw_row.get("report_to")),

                "sales_amount": 0,
                "returns_amount": 0,
                "goods_to_pay": 0,
                "logistics_amount": 0,
                "storage_amount": 0,
                "acceptance_amount": 0,
                "penalty_amount": 0,
                "deduction_amount": 0,
                "other_expense_amount": 0,
                "other_income_amount": 0,
                "total_to_pay": 0,

                "rows_count": 0,
                "raw_report_ids": [report_id],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

        report = reports[key]
        supplier_oper_name = str(payload.get("supplier_oper_name") or "")
        doc_type_name = str(payload.get("doc_type_name") or "")

        retail_amount = payload_number(payload, "retail_amount")
        return_amount = payload_number(payload, "return_amount")
        ppvz_for_pay = payload_number(payload, "ppvz_for_pay")
        delivery_rub = payload_number(payload, "delivery_rub")
        storage_fee = payload_number(payload, "storage_fee")
        penalty = payload_number(payload, "penalty")
        deduction = payload_number(payload, "deduction")
        acceptance = payload_number(payload, "acceptance")
        acquiring_fee = payload_number(payload, "acquiring_fee")
        ppvz_sales_commission = payload_number(payload, "ppvz_sales_commission")

        if supplier_oper_name == "Продажа":
            report["sales_amount"] += retail_amount
            report["goods_to_pay"] += ppvz_for_pay
            report["total_to_pay"] += ppvz_for_pay
        elif supplier_oper_name == "Возврат":
            report["returns_amount"] += retail_amount
            report["goods_to_pay"] -= ppvz_for_pay
            report["total_to_pay"] -= ppvz_for_pay
        elif supplier_oper_name == "Логистика":
            report["logistics_amount"] += delivery_rub
            report["total_to_pay"] -= delivery_rub
        elif supplier_oper_name == "Хранение":
            report["storage_amount"] += storage_fee
            report["total_to_pay"] -= storage_fee
        elif supplier_oper_name == "Штраф":
            report["penalty_amount"] += penalty
            report["total_to_pay"] -= penalty
        elif supplier_oper_name == "Удержание":
            report["deduction_amount"] += deduction
            report["total_to_pay"] -= deduction
        elif supplier_oper_name == "Возмещение издержек по перевозке/по складским операциям с товаром":
            report["other_income_amount"] += delivery_rub
            report["total_to_pay"] += delivery_rub
        elif supplier_oper_name == "Возмещение за выдачу и возврат товаров на ПВЗ":
            report["other_income_amount"] += ppvz_for_pay
            report["total_to_pay"] += ppvz_for_pay
        else:
            # Keep unknown rows visible in row counts, but do not force them into finances.
            pass

        report["acceptance_amount"] += acceptance
        report["other_expense_amount"] += acquiring_fee + ppvz_sales_commission
        report["rows_count"] += 1

    normalized_reports: List[Dict[str, Any]] = []

    for report in reports.values():
        for field in [
            "sales_amount",
            "returns_amount",
            "goods_to_pay",
            "logistics_amount",
            "storage_amount",
            "acceptance_amount",
            "penalty_amount",
            "deduction_amount",
            "other_expense_amount",
            "other_income_amount",
            "total_to_pay",
        ]:
            report[field] = round(to_number(report.get(field)), 2)

        normalized_reports.append(report)

    return normalized_reports


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_rows(rows: List[Dict[str, Any]]) -> int:
    if not rows:
        print("Nothing to upsert")
        return 0

    sent = 0

    for batch in chunked(rows, BATCH_SIZE):
        (
            supabase
            .table(TARGET_TABLE)
            .upsert(
                batch,
                on_conflict="user_id,shop_id,marketplace,report_id",
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(rows)}")

    return sent


def run_normalization_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]] = None,
    registry_entry: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])

    last_raw_updated_at, last_raw_id = get_watermark(state)

    raw_rows = fetch_raw_rows(
        user_id=user_id,
        shop_id=shop_id,
        last_raw_updated_at=last_raw_updated_at,
        last_raw_id=last_raw_id,
    )

    if not raw_rows:
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_raw_updated_at": last_raw_updated_at,
            "last_raw_id": last_raw_id,
        }

    report_rows = build_report_rows(raw_rows)

    rows_upserted = 0
    if report_rows:
        rows_upserted = upsert_rows(report_rows)

    newest_row = raw_rows[-1]

    return {
        "rows_read": len(raw_rows),
        "rows_upserted": rows_upserted,
        "last_raw_updated_at": newest_row.get("updated_at"),
        "last_raw_id": newest_row.get("id"),
    }


if __name__ == "__main__":
    result = run_normalization_job(
        job={"user_id": 1, "shop_id": 1},
        state=None,
        registry_entry=None,
    )

    print(result)