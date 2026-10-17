from ai_chat.analysis.analysis_type.ranked import group_rows
from ai_chat.answer_builder.answer import build_answer


def test_ranked_count_uses_one_value_per_order_row():
    rows = [
        {"region_name": "Москва"},
        {"region_name": "Москва"},
        {"region_name": "Казань"},
        {"region_name": None},
    ]
    grouped = group_rows(
        rows=rows,
        config={
            "group_by": "region_name",
            "group_fields": ["region_name"],
            "aggregation": "count",
            "value_alias": "orders_count",
        },
    )
    by_region = {row["region_name"]: row for row in grouped}
    assert by_region["Москва"]["orders_count"] == 2
    assert by_region["Казань"]["orders_count"] == 1


def test_region_answer_uses_compact_existing_result_contract():
    answer = build_answer(
        question="В какой регион чаще всего заказывают?",
        request={"limit": 1, "language": "ru"},
        result={
            "dataset": "orders",
            "analysis": "best",
            "metric": "orders_count",
            "entity": "region",
            "rows": [
                {"region_name": "Москва", "orders_count": 24, "value": 24}
            ],
        },
        language="ru",
    )
    assert answer == "\n".join(
        [
            "За последние 30 дней больше всего заказывали в следующих регионах:",
            "Москва - 24 заказа",
        ]
    )


def test_product_region_answer_has_product_context_and_skips_zeroes():
    answer = build_answer(
        question="В каких регионах чаще всего заказывают?",
        request={
            "limit": 5,
            "period_days": 30,
            "scope": "product",
            "product_key": "wb_236348866",
            "product": {"title": "Платье с крыльями ангела"},
            "language": "ru",
        },
        result={
            "dataset": "orders",
            "analysis": "best",
            "metric": "orders_count",
            "entity": "region",
            "rows": [
                {"region_name": "Москва", "orders_count": 5},
                {"region_name": "Краснодарский край", "orders_count": 2},
                {"region_name": "Неизвестно", "orders_count": 0},
            ],
        },
        language="ru",
    )
    assert answer.splitlines() == [
        "Платье с крыльями ангела_wb_236348866",
        "",
        "За последние 30 дней больше всего заказывали в следующих регионах:",
        "Москва - 5 заказов",
        "Краснодарский край - 2 заказа",
    ]
