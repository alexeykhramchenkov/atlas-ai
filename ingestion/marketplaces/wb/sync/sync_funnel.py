from __future__ import annotations

from datetime import date, datetime, timedelta
import time
from typing import Any, Callable

from db.client import supabase
from ingestion.marketplaces.wb.api.endpoints.funnel import get_sales_funnel_products


MARKETPLACE = "wb"
SOURCE_NAME = "funnel"
RAW_TABLE = "raw_wb_funnel"
PRODUCTS_TABLE = "normalized_products"
NM_IDS_LIMIT = 100
API_LIMIT = 100


ProgressCallback = Callable[[dict[str, Any]], None]


# --- AdaptiveRateLimiter class for adaptive API rate limiting ---
class AdaptiveRateLimiter:
    def __init__(
        self,
        base_sleep_sec: int = 5,
        max_sleep_sec: int = 300,
        success_decay: float = 0.9,
        error_multiplier: float = 2.0,
        max_attempts: int = 3,
    ):
        self.base_sleep_sec = base_sleep_sec
        self.current_sleep_sec = base_sleep_sec
        self.max_sleep_sec = max_sleep_sec
        self.success_decay = success_decay
        self.error_multiplier = error_multiplier
        self.max_attempts = max_attempts

    def record_success(self) -> None:
        self.current_sleep_sec = max(
            self.base_sleep_sec,
            int(self.current_sleep_sec * self.success_decay),
        )

    def record_error(self) -> None:
        self.current_sleep_sec = min(
            self.max_sleep_sec,
            max(self.base_sleep_sec, int(self.current_sleep_sec * self.error_multiplier)),
        )

    def sleep(self) -> None:
        if self.current_sleep_sec > 0:
            print(f"WB funnel adaptive sleep | {self.current_sleep_sec} sec")
            time.sleep(self.current_sleep_sec)

    def call(self, func: Callable[[], Any]) -> Any:
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                result = func()
                self.record_success()
                return result
            except Exception as exc:
                last_error = exc
                self.record_error()
                print(
                    "WB funnel API error | "
                    f"attempt={attempt}/{self.max_attempts} | "
                    f"next_sleep={self.current_sleep_sec} sec | "
                    f"error={exc}"
                )

                if attempt < self.max_attempts:
                    self.sleep()

        raise last_error


def parse_job_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        return date.fromisoformat(value[:10])

    raise ValueError(f"Unsupported job date value: {value!r}")


def iter_days(date_from: date, date_to: date):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def get_marketplace_product_ids(user_id: int, shop_id: int, limit: int = NM_IDS_LIMIT) -> list[int]:
    response = (
        supabase
        .table(PRODUCTS_TABLE)
        .select("marketplace_product_id")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", MARKETPLACE)
        .not_.is_("marketplace_product_id", "null")
        .limit(limit)
        .execute()
    )

    marketplace_product_ids: list[int] = []
    for row in response.data or []:
        value = row.get("marketplace_product_id")
        if value in [None, ""]:
            continue
        marketplace_product_ids.append(int(value))

    return sorted(set(marketplace_product_ids))


def is_raw_funnel_day_loaded(user_id: int, shop_id: int, marketplace: str, day: str) -> bool:
    response = (
        supabase
        .table(RAW_TABLE)
        .select("id")
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("period_start", day)
        .eq("period_end", day)
        .limit(1)
        .execute()
    )

    return bool(response.data)


def extract_funnel_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    data = payload.get("data")

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("products", "items", "list", "cards"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    for key in ("products", "items", "list", "cards"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []



def upsert_sync_state(
    user_id: int,
    shop_id: int,
    marketplace: str,
    source_name: str,
    date_from: date,
    date_to: date,
    rows_fetched: int,
    rows_upserted: int,
    days_checked: int,
    days_loaded: int,
    days_skipped: int,
    status: str = "success",
    error_message: str | None = None,
) -> None:
    now_iso = datetime.utcnow().isoformat()
    coverage_days_required = max((date_to - date_from).days + 1, 0)
    coverage_days_actual = days_skipped + days_loaded
    coverage_percent = (
        round((coverage_days_actual / coverage_days_required) * 100, 2)
        if coverage_days_required > 0
        else 100
    )
    missing_days_count = max(coverage_days_required - coverage_days_actual, 0)

    row = {
        "user_id": user_id,
        "shop_id": shop_id,
        "marketplace": marketplace,
        "source_name": source_name,
        "last_attempt_at": now_iso,
        "updated_at": now_iso,
        "last_rows_fetched": rows_fetched,
        "last_rows_upserted": rows_upserted,
        "coverage_days_required": coverage_days_required,
        "coverage_days_actual": coverage_days_actual,
        "coverage_percent": coverage_percent,
        "coverage_from": date_from.isoformat(),
        "coverage_to": date_to.isoformat(),
        "last_loaded_date_from": date_from.isoformat(),
        "last_loaded_date_to": date_to.isoformat(),
        "missing_days_count": missing_days_count,
        "repair_required": missing_days_count > 0,
        "status": status,
        "error_message": error_message,
    }

    if status == "success":
        row["last_success_at"] = now_iso
        row["error_code"] = None

    supabase.table("system_sync_state").upsert(
        row,
        on_conflict="user_id,shop_id,marketplace,source_name",
    ).execute()


def delete_raw_funnel_day(user_id: int, shop_id: int, marketplace: str, day: str) -> None:
    (
        supabase
        .table(RAW_TABLE)
        .delete()
        .eq("user_id", user_id)
        .eq("shop_id", shop_id)
        .eq("marketplace", marketplace)
        .eq("period_start", day)
        .eq("period_end", day)
        .execute()
    )


def extract_marketplace_product_id(item: dict[str, Any]) -> int | None:
    value = (
        item.get("nmID")
        or item.get("nmId")
        or item.get("nm_id")
        or item.get("marketplace_product_id")
    )

    if value is None and isinstance(item.get("product"), dict):
        product = item["product"]
        value = (
            product.get("nmID")
            or product.get("nmId")
            or product.get("nm_id")
            or product.get("marketplace_product_id")
        )

    if value in [None, ""]:
        return None

    return int(value)


def insert_raw_funnel_items(
    user_id: int,
    shop_id: int,
    marketplace: str,
    day: str,
    items: list[dict[str, Any]],
    raw_payload: Any,
) -> int:
    rows: list[dict[str, Any]] = []

    if items:
        for item in items:
            marketplace_product_id = extract_marketplace_product_id(item)
            rows.append(
                {
                    "user_id": user_id,
                    "shop_id": shop_id,
                    "marketplace": marketplace,
                    "nm_id": marketplace_product_id,
                    "marketplace_product_id": marketplace_product_id,
                    "period_start": day,
                    "period_end": day,
                    "payload": item,
                }
            )
    else:
        rows.append(
            {
                "user_id": user_id,
                "shop_id": shop_id,
                "marketplace": marketplace,
                "nm_id": None,
                "marketplace_product_id": None,
                "period_start": day,
                "period_end": day,
                "payload": raw_payload,
            }
        )

    supabase.table(RAW_TABLE).insert(rows).execute()
    return len(rows)


def run_sync_job(
    job: dict[str, Any],
    connection: dict[str, Any],
    rule: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    user_id = int(job["user_id"])
    shop_id = int(job["shop_id"])
    marketplace = job.get("marketplace") or MARKETPLACE
    api_token = connection.get("api_token")

    date_from = parse_job_date(job["date_from"])
    date_to = parse_job_date(job["date_to"])

    request_sleep_sec = int((rule or {}).get("request_sleep_sec") or 5)
    max_sleep_sec = int((rule or {}).get("max_sleep_sec") or 300)
    max_attempts = int((rule or {}).get("max_attempts") or 3)

    rate_limiter = AdaptiveRateLimiter(
        base_sleep_sec=request_sleep_sec,
        max_sleep_sec=max_sleep_sec,
        max_attempts=max_attempts,
    )

    rows_fetched = 0
    rows_upserted = 0

    days_checked = 0
    days_loaded = 0
    days_skipped = 0

    marketplace_product_ids = get_marketplace_product_ids(user_id=user_id, shop_id=shop_id)
    print(f"WB funnel job | found marketplace_product_ids={len(marketplace_product_ids)}")

    if not marketplace_product_ids:
        upsert_sync_state(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            source_name=SOURCE_NAME,
            date_from=date_from,
            date_to=date_to,
            rows_fetched=0,
            rows_upserted=0,
            days_checked=0,
            days_loaded=0,
            days_skipped=0,
            status="success",
        )
        return {
            "rows_fetched": 0,
            "rows_upserted": 0,
            "days_checked": 0,
            "days_loaded": 0,
            "days_skipped": 0,
        }

    for day in iter_days(date_from, date_to):
        day_str = day.isoformat()

        days_checked += 1

        if is_raw_funnel_day_loaded(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            day=day_str,
        ):
            days_skipped += 1
            print(f"WB funnel job | day={day_str} | already loaded | skipped")

            if progress_callback:
                progress_callback(
                    {
                        "day": day,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "day_skipped_already_loaded",
                        "days_checked": days_checked,
                        "days_loaded": days_loaded,
                        "days_skipped": days_skipped,
                    }
                )

            continue

        delete_raw_funnel_day(
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            day=day_str,
        )

        offset = 0

        while True:
            payload = rate_limiter.call(
                lambda: get_sales_funnel_products(
                    nm_ids=marketplace_product_ids,
                    date_from=day_str,
                    date_to=day_str,
                    limit=API_LIMIT,
                    offset=offset,
                    api_token=api_token,
                )
            )

            items = extract_funnel_items(payload)
            rows_fetched += len(items)
            rows_upserted += insert_raw_funnel_items(
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                day=day_str,
                items=items,
                raw_payload=payload,
            )

            print(f"WB funnel job | day={day_str} | offset={offset} | items={len(items)}")

            if not items or len(items) < API_LIMIT:
                break

            offset += API_LIMIT

            if progress_callback:
                progress_callback(
                    {
                        "day": day,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "before_request_sleep",
                        "next_offset": offset,
                    }
                )

            rate_limiter.sleep()

        days_loaded += 1

        if progress_callback:
            progress_callback(
                {
                    "day": day,
                    "rows_fetched": rows_fetched,
                    "rows_upserted": rows_upserted,
                    "phase": "day_completed",
                    "days_checked": days_checked,
                    "days_loaded": days_loaded,
                    "days_skipped": days_skipped,
                }
            )

        if day < date_to:
            if progress_callback:
                progress_callback(
                    {
                        "day": day,
                        "rows_fetched": rows_fetched,
                        "rows_upserted": rows_upserted,
                        "phase": "before_day_sleep",
                        "sleep_sec": rate_limiter.current_sleep_sec,
                    }
                )
            rate_limiter.sleep()

    upsert_sync_state(
        user_id=user_id,
        shop_id=shop_id,
        marketplace=marketplace,
        source_name=SOURCE_NAME,
        date_from=date_from,
        date_to=date_to,
        rows_fetched=rows_fetched,
        rows_upserted=rows_upserted,
        days_checked=days_checked,
        days_loaded=days_loaded,
        days_skipped=days_skipped,
        status="success",
    )

    print(
        "WB funnel job finished | "
        f"checked_days={days_checked} | "
        f"loaded_days={days_loaded} | "
        f"skipped_days={days_skipped} | "
        f"rows_fetched={rows_fetched} | "
        f"rows_upserted={rows_upserted}"
    )

    return {
        "rows_fetched": rows_fetched,
        "rows_upserted": rows_upserted,
        "days_checked": days_checked,
        "days_loaded": days_loaded,
        "days_skipped": days_skipped,
        "final_sleep_sec": rate_limiter.current_sleep_sec,
    }


def sync_wb_funnel_job(
    job: dict[str, Any],
    connection: dict[str, Any],
    rule: dict[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    return run_sync_job(
        job=job,
        connection=connection,
        rule=rule,
        progress_callback=progress_callback,
    )