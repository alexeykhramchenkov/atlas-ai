from ai_chat.memory import _single_product_from_result
from ai_chat.routing.route import resolve_product_from_memory


def test_memory_extracts_single_ranked_product():
    product = _single_product_from_result(
        request={"entity": "product", "answer_scope": "single", "limit": 1},
        result={
            "rows": [
                {
                    "product_key": "wb_236348866",
                    "title": "Платье с крыльями ангела",
                }
            ]
        },
    )
    assert product["product_key"] == "wb_236348866"


def test_result_product_fields_can_refresh_request_product():
    request_product = {
        "product_key": "wb_236348866",
        "title": "Платье с крыльями ангела",
    }
    result_product = _single_product_from_result(
        request={
            "entity": "product",
            "answer_scope": "single",
            "limit": 1,
            "product": request_product,
        },
        result={
            "rows": [
                {
                    "product_key": "wb_236348866",
                    "stock_qty": 123,
                }
            ]
        },
    )
    merged = {**request_product, **result_product}
    assert merged["stock_qty"] == 123


def test_memory_does_not_choose_from_product_list():
    product = _single_product_from_result(
        request={"entity": "product", "answer_scope": "top", "limit": 5},
        result={"rows": [{"product_key": "wb_1"}]},
    )
    assert product == {}


def test_pronoun_resolves_previous_product():
    product = resolve_product_from_memory(
        question="Какой у него остаток?",
        memory={
            "last_product_key": "wb_236348866",
            "last_product": {"title": "Платье с крыльями ангела"},
        },
    )
    assert product["product_key"] == "wb_236348866"
    assert product["match_type"] == "memory"


def test_warehouse_dimension_keeps_previous_product():
    product = resolve_product_from_memory(
        question="На каком складе его больше всего лежит?",
        memory={"last_product_key": "wb_236348866"},
    )
    assert product["product_key"] == "wb_236348866"


def test_region_dimension_keeps_previous_product():
    product = resolve_product_from_memory(
        question="В каких регионах его чаще всего заказывают?",
        memory={"last_product_key": "wb_236348866"},
    )
    assert product["product_key"] == "wb_236348866"


def test_explicit_store_scope_does_not_keep_previous_product():
    product = resolve_product_from_memory(
        question="На каком складе больше всего по всем товарам?",
        memory={"last_product_key": "wb_236348866"},
    )
    assert product is None


def test_unrelated_question_does_not_use_memory():
    assert resolve_product_from_memory(
        question="Сколько заказов за месяц?",
        memory={"last_product_key": "wb_236348866"},
    ) is None
