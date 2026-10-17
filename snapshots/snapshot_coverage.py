

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, List, Optional, Set

from db.client import supabase


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    value_str = str(value)
    if not value_str:
        return None

    try:
        return datetime.fromisoformat(value_str.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.strptime(value_str[:10], "%Y-%m-%d").date()
        except ValueError:
            return None


def date_range(start_date: date, end_date: date) -> List[date]:
    if start_date > end_date:
        return []

    days_count = (end_date - start_date).days + 1
    return [start_date + timedelta(days=i) for i in range(days_count)]


def normalize_dates(values: Iterable[Any]) -> Set[date]:
    result: Set[date] = set()

    for value in values:
        parsed = parse_date(value)
        if parsed:
            result.add(parsed)

    return result


def fetch_distinct_dates(
    table_name: str,
    date_column: str,
    *,
    user_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    marketplace: Optional[str] = None,
    batch_size: int = 1000,
) -> Set[date]:
    result: Set[date] = set()
    offset = 0

    while True:
        query = (
            supabase
            .table(table_name)
            .select(date_column)
            .order(date_column)
            .range(offset, offset + batch_size - 1)
        )

        if user_id is not None:
            query = query.eq("user_id", user_id)
        if shop_id is not None:
            query = query.eq("shop_id", shop_id)
        if marketplace is not None:
            query = query.eq("marketplace", marketplace)

        response = query.execute()
        rows = response.data or []

        if table_name == "normalized_orders" and date_column == "order_date":
            from core.dates import moscow_date
            result.update(day for row in rows if (day := moscow_date(row.get(date_column))) is not None)
        else:
            result.update(normalize_dates(row.get(date_column) for row in rows))

        if len(rows) < batch_size:
            break

        offset += batch_size

    return result


def get_dates_to_build(
    normalized_table: str,
    normalized_date_column: str,
    snapshot_table: str,
    snapshot_date_column: str = "snapshot_date",
    *,
    user_id: Optional[int] = None,
    shop_id: Optional[int] = None,
    marketplace: Optional[str] = None,
    repair_days: int = 7,
    include_all_when_empty: bool = True,
) -> List[date]:
    normalized_dates = fetch_distinct_dates(
        normalized_table,
        normalized_date_column,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
    )

    if not normalized_dates:
        return []

    snapshot_dates = fetch_distinct_dates(
        snapshot_table,
        snapshot_date_column,
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
    )

    min_normalized_date = min(normalized_dates)
    max_normalized_date = max(normalized_dates)
    full_normalized_range = set(date_range(min_normalized_date, max_normalized_date))

    if include_all_when_empty and not snapshot_dates:
        return sorted(full_normalized_range)

    missing_dates = full_normalized_range - snapshot_dates

    repair_start_date = max_normalized_date - timedelta(days=max(repair_days - 1, 0))
    repair_dates = {
        current_date
        for current_date in full_normalized_range
        if repair_start_date <= current_date <= max_normalized_date
    }

    return sorted(missing_dates | repair_dates)


def print_dates_to_build(dates_to_build: List[date]) -> None:
    if not dates_to_build:
        print("Dates to build: 0")
        return

    print(f"Dates to build: {len(dates_to_build)}")
    print(f"Build range: {min(dates_to_build)} \u2192 {max(dates_to_build)}")