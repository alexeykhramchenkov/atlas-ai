from __future__ import annotations

from typing import Any

from ai_chat.enrichers.product import enrich_products


RULES_TABLE = "system_metric_rules"
DEFAULT_LIMIT = 5
DEFAULT_PERIOD_DAYS = 30


class AnalysisRuleNotFoundError(Exception):
    pass


def run(request: dict, supabase) -> dict:
    from ai_chat.metric import seller_questions
    if seller_questions.handles(request):
        return seller_questions.run(request, supabase)
    if (request.get("metric") == "orders_count" and request.get("question_type") == "simple"
            and request.get("entity") == "region" and request.get("answer_scope") == "top"):
        from collections import Counter
        from ai_chat.internal_tools.get_orders import get_orders, IncompleteOrdersError
        from ai_chat.internal_tools.get_seller_facts import get_seller_facts
        from ai_chat.analysis.analysis_type.rank import run as rank
        product_key = request.get("product_key")
        context = {"dataset":"orders","analysis":request.get("analysis","best"),
                   "metric":"orders_count","entity":"region","rows":[]}
        if not product_key:
            return {**context,"status":"no_product"}
        dates = {"start_date":request.get("date_from"),"end_date":request.get("date_to")}
        if not any(dates.values()):
            dates = {"period_days":request.get("period_days",7)}
        try:
            facts = get_orders(user_id=request["user_id"],shop_id=request["shop_id"],
                marketplace=request.get("marketplace","wb"),product_key=product_key,supabase=supabase,**dates)
        except IncompleteOrdersError as error:
            return {**context,"status":"incomplete","date_from":error.start_date,"date_to":error.end_date}
        start,end = facts["start_date"],facts["end_date"]
        events = get_seller_facts(supabase,request,"order_events",start,end)
        counts,cancellations,seen = Counter(),Counter(),set()
        for row in events:
            if row.get("product_key") != product_key or row["srid"] in seen:
                continue
            seen.add(row["srid"])
            region=(row.get("country_name") or "Страна не указана",row.get("region_name") or "Регион не указан")
            counts[region]+=1
            if row.get("is_cancel"):cancellations[region]+=1
        rows=[{"country_name":country,"region_name":region,"value":n,
               "cancelled_orders_count":cancellations[(country,region)]}
              for (country,region),n in sorted(counts.items())]
        ranked=rank(rows=rows,metric="value",direction="desc",limit=int(request.get("limit",5)))
        product=next(iter(facts["products"]),request.get("product") or {"product_key":product_key})
        from datetime import date
        return {**context,"status":"ok","date_from":start,"date_to":end,
                "period_days":(date.fromisoformat(end)-date.fromisoformat(start)).days+1,
                "product":product,"rows":ranked["rows"],"orders_count":sum(counts.values()),
                "cancelled_orders_count":sum(cancellations.values())}
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
            sorted_rows = enrich_products(rows=sorted_rows,supabase=supabase,user_id=request['user_id'],shop_id=request['shop_id'],marketplace=request.get('marketplace','wb'))
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
    if table in {"metrics_stocks_daily","metrics_stocks_variants_daily"}:
        from ai_chat.internal_tools.get_stocks import get_stocks, StockDataUnavailableError
        try:
            facts=get_stocks(user_id=request["user_id"],shop_id=request["shop_id"],marketplace=request.get("marketplace","wb"),
                product_key=request.get("product_key"),variant_key=request.get("variant_key"),warehouse_key=request.get("warehouse_key"),
                as_of=request.get("as_of") or request.get("snapshot_date"),level="variant" if table.endswith("variants_daily") else "product",supabase=supabase)
        except StockDataUnavailableError as error:
            return {"rows":[],"meta":{"latest_snapshot_date":error.as_of}}
        return {"rows":[{**row,"snapshot_date":facts["as_of"],"quantity":row["total_quantity"]} for row in facts["products"]],
                "meta":{"latest_snapshot_date":facts["as_of"],"latest_snapshot_only":True,"date_filter_mode":"latest_snapshot"}}
    if table == "metrics_funnel_daily":
        from ai_chat.internal_tools.get_funnel import get_funnel
        dates={"start_date":request.get("date_from"),"end_date":request.get("date_to")}
        if not any(dates.values()):dates={"period_days":request.get("period_days",30)}
        facts=get_funnel(user_id=request["user_id"],shop_id=request["shop_id"],
            marketplace=request.get("marketplace","wb"),product_key=request.get("product_key"),
            supabase=supabase,**dates)
        return {"rows":facts["products"],"meta":{"date_from":facts["start_date"],"date_to":facts["end_date"]}}
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
    if group_by == []:
        from decimal import Decimal
        field = config.get("value_field")
        if not rows: return []
        total = len(rows) if config.get("aggregation") == "count" else sum((Decimal(str(row[field])) for row in rows), Decimal(0))
        value = int(total) if total == int(total) else float(total)
        return [{"value":value, **({field:value} if field else {})}]
    aggregation = config.get("aggregation") or "sum"
    value_field = config.get("value_field")
    value_alias = config.get("value_alias")
    revenue_field = config.get("revenue_field")
    group_fields = config.get("group_fields") or [group_by]
    share_field = config.get("share_field")

    groups: dict[str, dict[str, Any]] = {}

    for row in rows:
        group_key = tuple(row.get(field) for field in group_by) if isinstance(group_by,list) else row.get(group_by)

        if not group_key:
            continue

        if group_key not in groups:
            groups[group_key] = {
                "value": 0.0,
            }

            for field in group_fields:
                groups[group_key][field] = row.get(field)

        if aggregation == "count":
            groups[group_key]["value"] += 1.0
        else:
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
