import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db.client import supabase
from snapshots.snapshot_coverage import get_dates_to_build, print_dates_to_build


SOURCE_TABLE = "normalized_realization"
TARGET_TABLE = "snapshots_realization_daily"
MARKETPLACE = "wb"
BATCH_SIZE = 100
REPAIR_DAYS = 7


def to_float(value: Any, default: float = 0) -> float:
    if value in [None, ""]:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_date(value: Any) -> Optional[date]:
    if value in [None, ""]:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def fetch_realization_for_dates(dates_to_build: List[date], *, user_id: int, shop_id: int, marketplace: str = MARKETPLACE) -> List[Dict[str, Any]]:
    if not dates_to_build:
        return []

    rows: List[Dict[str, Any]] = []
    offset = 0
    batch_size = 1000

    start_date = min(dates_to_build)
    end_date_exclusive = max(dates_to_build) + timedelta(days=1)
    allowed_dates = set(dates_to_build)

    while True:
        response = (
            supabase
            .table(SOURCE_TABLE)
            .select("*")
            .eq("marketplace", marketplace).eq("user_id", user_id).eq("shop_id", shop_id)
            .gte("event_time", start_date.isoformat())
            .lt("event_time", end_date_exclusive.isoformat())
            .order("event_time", desc=False)
            .order("id", desc=False)
            .range(offset, offset + batch_size - 1)
            .execute()
        )

        batch = response.data or []

        for row in batch:
            row_date = parse_date(row.get("event_time"))
            if row_date in allowed_dates:
                rows.append(row)

        if len(batch) < batch_size:
            break

        offset += batch_size

    return rows


def build_group_key(row: Dict[str, Any]) -> Optional[Tuple[Any, Any, str, str, date]]:
    event_date = parse_date(row.get("event_time"))
    product_key = row.get("product_key")

    if not event_date:
        return None

    if not product_key:
        product_key = "__account__"

    return (
        row.get("user_id"),
        row.get("shop_id"),
        row.get("marketplace") or MARKETPLACE,
        product_key,
        event_date,
    )


def build_empty_group(row: Dict[str, Any], key: Tuple[Any, Any, str, str, date]) -> Dict[str, Any]:
    user_id, shop_id, marketplace, product_key, snapshot_date = key

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "snapshot_date": snapshot_date.isoformat(),
        "product_key": product_key,
        "marketplace_product_id": row.get("marketplace_product_id") or "__account__",
        "seller_sku": row.get("seller_sku") or "__account__",

        "sales_count": 0,
        "returns_count": 0,
        "sales_amount": 0,
        "returns_amount": 0,

        "wb_commission_amount": 0,
        "logistics_amount": 0,
        "storage_amount": 0,
        "acquiring_amount": 0,
        "penalty_amount": 0,
        "deduction_amount": 0,
        "acceptance_amount": 0,

        "compensation_amount": 0,
        "reimbursement_amount": 0,
        "other_income_amount": 0,
        "other_expense_amount": 0,

        "seller_payout": 0,
        "realization_events_count": 0,
    }


def is_sale(row: Dict[str, Any]) -> bool:
    payload = row.get("raw_payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    supplier_oper_name = str(payload.get("supplier_oper_name") or "").strip().lower()
    operation_type = str(row.get("operation_type") or "").strip().lower()

    return supplier_oper_name in {"продажа", "sale"} and operation_type in {"продажа", "sale"}


def is_return(row: Dict[str, Any]) -> bool:
    payload = row.get("raw_payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    supplier_oper_name = str(payload.get("supplier_oper_name") or "").strip().lower()
    operation_type = str(row.get("operation_type") or "").strip().lower()

    return supplier_oper_name in {"возврат", "return"} and operation_type in {"возврат", "return"}


def supplier_operation(row: Dict[str, Any]) -> str:
    payload = row.get("raw_payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    return str(payload.get("supplier_oper_name") or row.get("operation_type") or "").strip().lower()


def has_word(row: Dict[str, Any], *words: str) -> bool:
    text = f"{row.get('event_type') or ''} {row.get('operation_type') or ''}".lower()
    return any(word.lower() in text for word in words)


def payload_value(payload: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in [None, ""]:
            return value
    return None


def amount_abs(value: Any) -> float:
    return abs(to_float(value))


def add_other_amount(item: Dict[str, Any], amount: float) -> None:
    if amount > 0:
        item["other_income_amount"] += amount
    elif amount < 0:
        item["other_expense_amount"] += abs(amount)


def apply_realization_row(item: Dict[str, Any], row: Dict[str, Any]) -> None:
    payload = row.get("raw_payload") or {}
    if not isinstance(payload, dict):
        payload = {}

    supplier_oper_name = supplier_operation(row)

    quantity = amount_abs(row.get("quantity"))
    row_amount = to_float(row.get("amount"))

    retail_amount = amount_abs(payload_value(payload, "retail_amount", "retail_amount_withdisc_rub"))
    return_amount = amount_abs(payload_value(payload, "return_amount"))
    ppvz_for_pay = to_float(payload_value(payload, "ppvz_for_pay"))
    ppvz_vw = to_float(payload_value(payload, "ppvz_vw"))
    commission_value = payload_value(payload, "ppvz_sales_commission")
    commission_amount = to_float(commission_value) if commission_value is not None else ppvz_vw
    acquiring_fee = amount_abs(payload_value(payload, "acquiring_fee"))
    delivery_rub = to_float(payload_value(payload, "delivery_rub", "deliveryService"))
    storage_fee = to_float(payload_value(payload, "storage_fee", "paidStorage"))
    penalty = amount_abs(payload_value(payload, "penalty"))
    deduction = amount_abs(payload_value(payload, "deduction"))
    acceptance = amount_abs(payload_value(payload, "acceptance"))
    additional_payment = to_float(payload_value(payload, "additional_payment"))
    rebill_logistic_cost = amount_abs(payload_value(payload, "rebill_logistic_cost"))
    row_amount_abs = amount_abs(row_amount)

    item["realization_events_count"] += 1

    if is_sale(row):
        item["sales_count"] += quantity or 1
        item["sales_amount"] += retail_amount or max(row_amount, 0)
        item["seller_payout"] += abs(ppvz_for_pay)
    elif is_return(row):
        item["returns_count"] += quantity or 1
        item["returns_amount"] += retail_amount or return_amount or abs(row_amount)
        item["seller_payout"] -= abs(ppvz_for_pay)

    if supplier_oper_name in {"продажа", "возврат", "sale", "return"}:
        if commission_amount:
            item["wb_commission_amount"] += -commission_amount if is_return(row) else commission_amount
        if acquiring_fee:
            item["acquiring_amount"] += acquiring_fee

    if supplier_oper_name in {"логистика", "доставка", "коррекция логистики"}:
        if delivery_rub:
            item["logistics_amount"] += delivery_rub

    if supplier_oper_name == "хранение":
        if storage_fee:
            item["storage_amount"] += storage_fee

    if supplier_oper_name == "штраф":
        if penalty:
            item["penalty_amount"] += penalty

    if supplier_oper_name == "удержание":
        if deduction:
            item["deduction_amount"] += deduction

    if supplier_oper_name in {"приемка", "приёмка"}:
        if acceptance:
            item["acceptance_amount"] += acceptance

    if supplier_oper_name == "возмещение издержек по перевозке/по складским операциям с товаром":
        if rebill_logistic_cost:
            item["reimbursement_amount"] += rebill_logistic_cost

    if supplier_oper_name == "компенсация скидки по программе лояльности":
        compensation_amount = row_amount_abs or additional_payment
        if compensation_amount:
            item["compensation_amount"] += compensation_amount

    known_amount = any([
        retail_amount,
        return_amount,
        commission_amount if supplier_oper_name in {"продажа", "возврат", "sale", "return"} else 0,
        acquiring_fee if supplier_oper_name in {"продажа", "возврат", "sale", "return"} else 0,
        delivery_rub if supplier_oper_name in {"логистика", "коррекция логистики"} else 0,
        rebill_logistic_cost if supplier_oper_name == "возмещение издержек по перевозке/по складским операциям с товаром" else 0,
        row_amount_abs if supplier_oper_name == "компенсация скидки по программе лояльности" else 0,
        storage_fee if supplier_oper_name == "хранение" else 0,
        penalty if supplier_oper_name == "штраф" else 0,
        deduction if supplier_oper_name == "удержание" else 0,
        acceptance if supplier_oper_name in {"приемка", "приёмка"} else 0,
        ppvz_for_pay,
    ])

    if additional_payment:
        add_other_amount(item, additional_payment)
    elif not known_amount and row_amount:
        add_other_amount(item, row_amount)


def build_snapshots(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[Any, Any, str, str, date], Dict[str, Any]] = {}

    for row in rows:
        key = build_group_key(row)
        if key is None:
            continue

        if key not in groups:
            groups[key] = build_empty_group(row, key)

        apply_realization_row(groups[key], row)

    result = []
    money_fields = [
        "sales_count",
        "returns_count",
        "sales_amount",
        "returns_amount",
        "wb_commission_amount",
        "logistics_amount",
        "storage_amount",
        "acquiring_amount",
        "penalty_amount",
        "deduction_amount",
        "acceptance_amount",
        "compensation_amount",
        "reimbursement_amount",
        "other_income_amount",
        "other_expense_amount",
        "seller_payout",
    ]

    for item in groups.values():
        for field in money_fields:
            item[field] = round(to_float(item.get(field)), 2)
        result.append(item)

    return result


def chunked(items: List[Dict[str, Any]], size: int) -> List[List[Dict[str, Any]]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def upsert_snapshots(rows: List[Dict[str, Any]]) -> int:
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
                on_conflict="user_id,shop_id,marketplace,product_key,snapshot_date",
            )
            .execute()
        )

        sent += len(batch)
        print(f"Sent batch: {sent}/{len(rows)}")

    return sent



def run_snapshot_job(
    job: Dict[str, Any],
    state: Optional[Dict[str, Any]],
    registry_entry: Dict[str, Any],
) -> Dict[str, Any]:
    user_id, shop_id = int(job["user_id"]), int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    print("Resolving realization daily snapshot coverage...")
    dates_to_build = get_dates_to_build(
        normalized_table=SOURCE_TABLE,
        normalized_date_column="event_time",
        snapshot_table=TARGET_TABLE,
        snapshot_date_column="snapshot_date",
        marketplace=MARKETPLACE,
        repair_days=REPAIR_DAYS, user_id=user_id, shop_id=shop_id,
    )
    print_dates_to_build(dates_to_build)

    if not dates_to_build:
        print("No realization snapshots to build")
        return {
            "rows_read": 0,
            "rows_upserted": 0,
            "last_processed_date": state.get("last_processed_date") if state else None,
        }

    print("Fetching normalized realization for selected dates...")
    realization_rows = fetch_realization_for_dates(dates_to_build, user_id=user_id, shop_id=shop_id, marketplace=marketplace)
    print(f"Normalized realization rows fetched: {len(realization_rows)}")

    snapshots = build_snapshots(realization_rows)
    print(f"Realization snapshots prepared: {len(snapshots)}")

    if not snapshots:
        print("No realization snapshots to upsert")
        return {
            "rows_read": len(realization_rows),
            "rows_upserted": 0,
            "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
        }

    sent = upsert_snapshots(snapshots)

    print("Done")
    print(f"Rows sent to {TARGET_TABLE}: {sent}")

    return {
        "rows_read": len(realization_rows),
        "rows_upserted": sent,
        "last_processed_date": max(dates_to_build).isoformat() if dates_to_build else None,
    }


def build_snapshots_realization_daily() -> None:
    result = run_snapshot_job(
        job={},
        state=None,
        registry_entry={},
    )
    print(result)


if __name__ == "__main__":
    build_snapshots_realization_daily()
