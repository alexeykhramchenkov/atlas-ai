from __future__ import annotations

from typing import Any

from ai_chat.enrichers.product import enrich_products


RULES_TABLE = "system_metric_rules"
DEFAULT_LIMIT = 5
DEFAULT_PERIOD_DAYS = 30


class AnalysisRuleNotFoundError(Exception):
    pass


def run(request: dict, supabase) -> dict:
    metric = request.get("metric")
    analysis = request.get("analysis") or "ranked"
    entity = request.get("entity") or "product"

    if not metric:
        raise ValueError("metric is required for ranked analysis")

    rule = get_analysis_rule(
        supabase=supabase,
        metric=metric,
        analysis=analysis,
        entity=entity,
    )

    config = rule["config"] or {}
    fetched = fetch_rows(
        request=request,
        supabase=supabase,
        config=config,
    )
    rows = fetched["rows"]
    fetch_meta = fetched["meta"]

    grouped_rows = group_rows(rows=rows, config=config)
    sorted_rows = sort_rows(rows=grouped_rows, config=config)

    if should_enrich_products(request=request):
        try:
            sorted_rows = enrich_products(rows=sorted_rows, supabase=supabase)
        except Exception:
            pass

    limit = int(request.get("limit") or config.get("limit") or DEFAULT_LIMIT)
    limited_rows = sorted_rows[:limit]

    result = {
        "dataset": request.get("dataset"),
        "analysis": analysis,
        "metric": metric,
        "entity": entity,
        "period_days": request.get("period_days", DEFAULT_PERIOD_DAYS),
        "rows": limited_rows,
        "meta": {
            "limit": limit,
            "rows_count": len(limited_rows),
            "total_groups": len(sorted_rows),
            "raw_rows_count": len(rows),
            **fetch_meta,
        },
    }

    enriched_context = fetch_variant_product_context(
        request=request,
        supabase=supabase,
    )

    if enriched_context:
        result["enriched_context"] = enriched_context

    return result


def get_analysis_rule(supabase, metric: str, analysis: str, entity: str) -> dict:
    response = (
        supabase
        .table(RULES_TABLE)
        .select("metric,analysis,entity,config")
        .eq("metric", metric)
        .eq("analysis", analysis)
        .eq("entity", entity)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        builtin_rule = get_builtin_analysis_rule(
            metric=metric,
            analysis=analysis,
            entity=entity,
        )

        if builtin_rule:
            return builtin_rule

        raise AnalysisRuleNotFoundError(
            f"Rule not found: metric={metric}, analysis={analysis}, entity={entity}"
        )

    return rows[0]


def fetch_rows(request: dict, supabase, config: dict) -> dict:
    table = config["table"]
    date_field = config.get("date_field", "snapshot_date")
    select_fields = config.get("select", "*")
    period_days = int(request.get("period_days", DEFAULT_PERIOD_DAYS))
    latest_snapshot_only = bool(config.get("latest_snapshot_only"))
    latest_snapshot_date = None

    if latest_snapshot_only:
        latest_snapshot_date = get_latest_snapshot_date(
            request=request,
            supabase=supabase,
            table=table,
            date_field=date_field,
        )

        if not latest_snapshot_date:
            return {
                "rows": [],
                "meta": {
                    "table": table,
                    "date_field": date_field,
                    "latest_snapshot_only": latest_snapshot_only,
                    "latest_snapshot_date": None,
                    "date_filter_mode": "latest_snapshot",
                },
            }
    else:
        date_from = date_from_period(period_days)

    max_rows = int(config.get("limit_rows", config.get("max_rows", 10000)))
    page_size = int(config.get("page_size", 1000))
    group_by = config.get("group_by", "product_key")

    rows: list[dict] = []
    start = 0

    while start < max_rows:
        end = min(start + page_size - 1, max_rows - 1)

        query = (
            supabase
            .table(table)
            .select(select_fields)
            .eq("user_id", request["user_id"])
            .eq("shop_id", request["shop_id"])
            .eq("marketplace", request.get("marketplace", "wb"))
        )

        if latest_snapshot_only:
            query = query.eq(date_field, latest_snapshot_date)
        else:
            query = query.gte(date_field, date_from)

        for filter_field in ("product_key", "variant_key", "warehouse_key"):
            filter_value = request.get(filter_field)

            if filter_value:
                query = query.eq(filter_field, filter_value)

        query = (
            query
            .order(date_field, desc=False)
            .order(group_by, desc=False)
            .range(start, end)
        )

        response = query.execute()
        page_rows = response.data or []
        rows.extend(page_rows)

        if len(page_rows) < page_size:
            break

        start += page_size

    return {
        "rows": rows,
        "meta": {
            "table": table,
            "date_field": date_field,
            "latest_snapshot_only": latest_snapshot_only,
            "latest_snapshot_date": latest_snapshot_date,
            "date_filter_mode": "latest_snapshot" if latest_snapshot_only else "period",
        },
    }


def get_latest_snapshot_date(
    request: dict,
    supabase,
    table: str,
    date_field: str,
) -> str | None:
    response = (
        supabase
        .table(table)
        .select(date_field)
        .eq("user_id", request["user_id"])
        .eq("shop_id", request["shop_id"])
        .eq("marketplace", request.get("marketplace", "wb"))
        .order(date_field, desc=True)
        .limit(1)
        .execute()
    )

    rows = response.data or []

    if not rows:
        return None

    return rows[0].get(date_field)


def group_rows(rows: list[dict], config: dict) -> list[dict]:
    group_by = config.get("group_by", "product_key")
    value_field = config["value_field"]
    value_alias = config.get("value_alias")
    revenue_field = config.get("revenue_field")
    group_fields = config.get("group_fields") or [group_by]
    share_field = config.get("share_field")

    groups: dict[str, dict[str, Any]] = {}

    for row in rows:
        group_key = row.get(group_by)

        if not group_key:
            continue

        if group_key not in groups:
            groups[group_key] = {
                "value": 0.0,
            }

            for field in group_fields:
                groups[group_key][field] = row.get(field)

        groups[group_key]["value"] += safe_float(row.get(value_field))

        if value_field:
            groups[group_key][value_field] = groups[group_key]["value"]

        if value_alias:
            groups[group_key][value_alias] = groups[group_key]["value"]

        if revenue_field and revenue_field != value_field:
            groups[group_key].setdefault(revenue_field, 0.0)
            groups[group_key][revenue_field] += safe_float(row.get(revenue_field))

    grouped_rows = list(groups.values())

    if share_field:
        total_value = sum(safe_float(row.get("value")) for row in grouped_rows)

        for row in grouped_rows:
            row[share_field] = round(
                safe_float(row.get("value")) / total_value * 100,
                2,
            ) if total_value else 0.0

    return grouped_rows


def sort_rows(rows: list[dict], config: dict) -> list[dict]:
    sort_direction = config.get("sort_direction", "desc")
    reverse = sort_direction != "asc"
    sort_field = config.get("sort_field", "value")

    return sorted(
        rows,
        key=lambda row: safe_float(row.get(sort_field)),
        reverse=reverse,
    )


def date_from_period(period_days: int) -> str:
    from datetime import date, timedelta

    return (date.today() - timedelta(days=period_days)).isoformat()


def safe_float(value: Any) -> float:
    if value is None:
        return 0.0

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def get_builtin_analysis_rule(metric: str, analysis: str, entity: str) -> dict | None:
    if metric not in {"orders", "orders_count"}:
        return None

    if analysis not in {"best", "worst"} or entity != "variant":
        return None

    return {
        "metric": metric,
        "analysis": analysis,
        "entity": entity,
        "config": {
            "limit": 10,
            "table": "metrics_orders_variants_daily",
            "select": (
                "snapshot_date,product_key,size_name,"
                "orders_count,gross_order_value,net_order_value"
            ),
            "group_by": "size_name",
            "group_fields": [
                "product_key",
                "size_name",
            ],
            "page_size": 1000,
            "date_field": "snapshot_date",
            "aggregation": "sum",
            "value_field": "orders_count",
            "value_alias": "orders",
            "revenue_field": "gross_order_value",
            "share_field": "share_pct",
            "sort_direction": "asc" if analysis == "worst" else "desc",
        },
    }


def should_enrich_products(request: dict) -> bool:
    return bool(request.get("entity") != "variant")


def fetch_variant_product_context(request: dict, supabase) -> dict:
    if (
        request.get("dataset") != "orders"
        or request.get("entity") != "variant"
        or request.get("scope") != "product"
        or not request.get("product_key")
    ):
        return {}

    try:
        from ai_chat.metric_adapter import get_product_context

        return get_product_context(
            product_key=request["product_key"],
            user_id=request["user_id"],
            shop_id=request["shop_id"],
            marketplace=request.get("marketplace", "wb"),
            supabase=supabase,
        )
    except Exception:
        return {}
