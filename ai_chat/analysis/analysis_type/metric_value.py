from importlib import import_module
from typing import Any

from ai_chat.enrichers.product import enrich_products


RULES_TABLE = "system_metric_rules"
ANALYSIS_NAME = "metric_value"
DEFAULT_ENTITY = "store"


class MetricRuleNotFoundError(Exception):
    pass


class MetricHandlerNotFoundError(Exception):
    pass


def run(request: dict, supabase) -> dict:
    from ai_chat.metric import seller_questions
    if seller_questions.handles(request):
        return seller_questions.run(request, supabase)
    metric = request.get("metric")
    dataset = request.get("dataset")

    if not metric:
        raise ValueError("metric is required for metric_value analysis")

    if not dataset:
        raise ValueError("dataset is required for metric_value analysis")

    entity = request.get("entity") or DEFAULT_ENTITY

    request = apply_default_metrics(request)

    rule = get_metric_rule(
        supabase=supabase,
        metric=metric,
        analysis=ANALYSIS_NAME,
        entity=entity,
    )

    metric_module = import_metric_module(dataset)

    if not hasattr(metric_module, ANALYSIS_NAME):
        raise MetricHandlerNotFoundError(
            f"Metric module ai_chat.metric.{dataset} does not support {ANALYSIS_NAME}"
        )

    handler = getattr(metric_module, ANALYSIS_NAME)

    result = handler(
        request={**request, "entity": entity},
        supabase=supabase,
        config=rule["config"],
    )
    if entity == "product" and result.get("rows"):
        result["rows"] = enrich_products(rows=result['rows'],supabase=supabase,user_id=request['user_id'],shop_id=request['shop_id'],marketplace=request.get('marketplace','wb'))
    return result


# Applies default metrics for certain datasets and metrics if not provided in request.
def apply_default_metrics(request: dict) -> dict:
    """
    Ensures that for specific datasets and metrics, a default list of metrics is set in the request
    if not already present.

    Args:
        request (dict): The request dictionary for metric_value analysis.

    Returns:
        dict: The request dictionary, possibly updated with default metrics.
    """
    dataset = request.get("dataset")
    metric = request.get("metric")

    if request.get("metrics"):
        return request

    if dataset == "orders" and metric in {"orders_count", "orders_revenue"}:
        return {
            **request,
            "metrics": ["orders_count", "orders_revenue"],
        }

    return request


def get_metric_rule(
    supabase,
    metric: str,
    analysis: str,
    entity: str,
) -> dict:
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
        raise MetricRuleNotFoundError(
            f"Rule not found: metric={metric}, analysis={analysis}, entity={entity}"
        )

    return rows[0]


def import_metric_module(dataset: str) -> Any:
    safe_dataset = dataset.strip().lower()
    return import_module(f"ai_chat.metric.{safe_dataset}")
