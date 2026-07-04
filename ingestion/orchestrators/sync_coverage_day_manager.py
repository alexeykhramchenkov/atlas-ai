

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from db.client import supabase


TABLE_NAME = "system_sync_coverage_days"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value[:10])

    raise ValueError(f"Unsupported date value: {value!r}")


def iter_days(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def chunked(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(items), size):
        yield items[index:index + size]


def build_coverage_day_row(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    coverage_date: date | str,
    job_id: int | None = None,
    status: str = "loaded",
    rows_fetched: int = 0,
    rows_upserted: int = 0,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = utc_now_iso()

    return {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "coverage_date": parse_date(coverage_date).isoformat(),
        "job_id": job_id,
        "status": status,
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "meta": meta or {},
        "updated_at": now,
    }


def mark_coverage_days(
    rows: list[dict[str, Any]],
    batch_size: int = 500,
) -> int:
    if not rows:
        return 0

    inserted_count = 0

    for batch in chunked(rows, batch_size):
        supabase.table(TABLE_NAME).upsert(
            batch,
            on_conflict="user_id,shop_id,marketplace,source_name,coverage_date",
        ).execute()
        inserted_count += len(batch)

    return inserted_count


def mark_coverage_day(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    coverage_date: date | str,
    job_id: int | None = None,
    status: str = "loaded",
    rows_fetched: int = 0,
    rows_upserted: int = 0,
    meta: dict[str, Any] | None = None,
) -> int:
    row = build_coverage_day_row(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=source_name,
        coverage_date=coverage_date,
        job_id=job_id,
        status=status,
        rows_fetched=rows_fetched,
        rows_upserted=rows_upserted,
        meta=meta,
    )

    return mark_coverage_days([row])


def mark_coverage_range(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    date_from: date | str,
    date_to: date | str,
    job_id: int | None = None,
    status: str = "loaded",
    rows_fetched: int = 0,
    rows_upserted: int = 0,
    meta: dict[str, Any] | None = None,
) -> int:
    start = parse_date(date_from)
    end = parse_date(date_to)

    rows = [
        build_coverage_day_row(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            source_name=source_name,
            coverage_date=day,
            job_id=job_id,
            status=status,
            rows_fetched=rows_fetched,
            rows_upserted=rows_upserted,
            meta=meta,
        )
        for day in iter_days(start, end)
    ]

    return mark_coverage_days(rows)