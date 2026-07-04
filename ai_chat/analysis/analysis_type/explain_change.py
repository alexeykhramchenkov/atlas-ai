from concurrent.futures import ThreadPoolExecutor

from ai_chat.metric_adapter import (
    compare_funnel_metrics,
    compare_metric,
    find_contributors,
    get_product_context,
    get_metric_state,
)

ANALYSIS = "explain_change"
SUPPORTED_METRIC = "orders"
SUPPORTED_SCOPES = {"store", "product"}
DEFAULT_PERIOD_DAYS = 30

ORDER_CHANGE_FACTORS = [
    "views",
    "cart_rate",
    "conversion",
    "stock",
]


def run(request: dict, supabase) -> dict:
    metric = request.get("metric")
    scope = request.get("scope") or "store"

    if metric != SUPPORTED_METRIC:
        raise ValueError(f"Unsupported explain_change metric: {metric}")

    if scope not in SUPPORTED_SCOPES:
        raise ValueError(f"Unsupported explain_change scope: {scope}")

    if scope == "product" and not request.get("product_key"):
        raise ValueError("product_key is required for product explain_change")

    user_id = request.get("user_id")
    shop_id = request.get("shop_id")
    marketplace = request.get("marketplace", "wb")
    period_days = request.get("period_days", DEFAULT_PERIOD_DAYS)
    product_key = request.get("product_key") if scope == "product" else None

    with ThreadPoolExecutor(max_workers=4) as executor:
        target_future = executor.submit(
            compare_metric,
            metric="orders",
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            period_days=period_days,
            product_key=product_key,
        )
        funnel_future = executor.submit(
            compare_funnel_metrics,
            metrics=["views", "cart_rate", "conversion"],
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            period_days=period_days,
            product_key=product_key,
        )
        stock_future = executor.submit(
            get_metric_state,
            metric="stock",
            supabase=supabase,
            user_id=user_id,
            shop_id=shop_id,
            marketplace=marketplace,
            product_key=product_key,
        )
        contributors_future = None
        product_context_future = None

        if scope == "store":
            contributors_future = executor.submit(
                find_contributors,
                metric="orders",
                supabase=supabase,
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
                period_days=period_days,
                scope="product",
                direction="negative",
                limit=3,
            )
        elif product_key:
            product_context_future = executor.submit(
                get_product_context,
                supabase=supabase,
                product_key=product_key,
                user_id=user_id,
                shop_id=shop_id,
                marketplace=marketplace,
            )

        target = target_future.result()
        funnel_factors = funnel_future.result()
        stock = stock_future.result()
        contributors = contributors_future.result() if contributors_future else None
        product_context = (
            product_context_future.result()
            if product_context_future
            else None
        )

    factors = {
        "views": funnel_factors["views"],
        "cart_rate": funnel_factors["cart_rate"],
        "conversion": funnel_factors["conversion"],
        "stock": stock,
    }

    main_cause = _select_main_cause(factors)

    result = {
        "analysis": ANALYSIS,
        "metric": metric,
        "scope": scope,
        "status": "success",
        "target": target,
        "factors": factors,
        "main_cause": main_cause,
        "evidence": _build_evidence(target=target, factors=factors),
    }

    if contributors:
        result["contributors"] = contributors

    if product_context:
        result["enriched_context"] = product_context

    return result


def _select_main_cause(factors: dict) -> str | None:
    compare_factors = [
        factor
        for factor in factors.values()
        if factor.get("view") == "compare"
        and factor.get("change_pct") is not None
        and factor.get("change_pct") < 0
    ]

    if not compare_factors:
        return None

    worst_factor = min(compare_factors, key=lambda factor: factor["change_pct"])
    return worst_factor.get("metric")


def _build_evidence(target: dict, factors: dict) -> list[dict]:
    evidence = [
        {
            "metric": target.get("metric"),
            "view": target.get("view"),
            "change_pct": target.get("change_pct"),
            "change_abs": target.get("change_abs"),
        }
    ]

    for factor in factors.values():
        item = {
            "metric": factor.get("metric"),
            "view": factor.get("view"),
            "status": factor.get("status"),
        }
        if factor.get("view") == "compare":
            item["change_pct"] = factor.get("change_pct")
            item["change_abs"] = factor.get("change_abs")
        else:
            item["value"] = factor.get("value")
        evidence.append(item)

    return evidence
