from ai_chat.answer_builder.answer import build_answer
from ai_chat.routing.route import resolve_explicit_limit


def test_worst_products_use_compact_five_item_format():
    rows = [
        {
            "title": f"Товар {index}",
            "product_key": f"wb_{index}",
            "orders_count": index,
            "seller_sku": f"sku-{index}",
            "brand": "Brand",
        }
        for index in range(1, 8)
    ]
    answer = build_answer(
        question="Какие товары продаются хуже всего?",
        request={"entity": "product", "limit": 5, "language": "ru"},
        result={
            "analysis": "worst",
            "dataset": "orders",
            "metric": "orders_count",
            "entity": "product",
            "rows": rows,
        },
        language="ru",
    )

    assert answer.splitlines() == [
        "Товар 1_wb_1 - 1 заказов",
        "Товар 2_wb_2 - 2 заказов",
        "Товар 3_wb_3 - 3 заказов",
        "Товар 4_wb_4 - 4 заказов",
        "Товар 5_wb_5 - 5 заказов",
    ]
    assert "seller_sku" not in answer
    assert "Brand" not in answer


def test_stock_products_are_sorted_and_compact():
    answer = build_answer(
        question="У каких товаров заканчиваются остатки?",
        request={"entity": "product", "limit": 2, "language": "ru"},
        result={
            "analysis": "metric_value",
            "dataset": "stocks",
            "metric": "stock_qty",
            "entity": "product",
            "rows": [
                {"title": "Много", "product_key": "wb_2", "stock_qty": 10},
                {"title": "Нет", "product_key": "wb_1", "stock_qty": 0},
                {"title": "Мало", "product_key": "wb_3", "stock_qty": 1},
            ],
        },
        language="ru",
    )

    assert answer.splitlines() == [
        "Нет_wb_1 - 0 шт.",
        "Мало_wb_3 - 1 шт.",
    ]


def test_explicit_numeric_limit_is_bounded():
    assert resolve_explicit_limit("покажи топ 7 товаров") == 7
    assert resolve_explicit_limit("покажи 99 товаров") == 50
    assert resolve_explicit_limit("покажи товары") is None


def test_product_warehouse_answer_names_scope_and_total():
    answer = build_answer(
        question="На каком складе больше всего лежит?",
        request={
            "entity": "warehouse",
            "scope": "product",
            "product_key": "wb_236348866",
            "product": {
                "title": "Платье с крыльями ангела",
                "stock_qty": 123,
            },
            "language": "ru",
        },
        result={
            "analysis": "best",
            "dataset": "stocks",
            "metric": "stock_qty",
            "entity": "warehouse",
            "rows": [{"warehouse_key": "wb_коледино", "quantity": 20}],
        },
        language="ru",
    )
    assert answer.splitlines() == [
        "Платье с крыльями ангела_wb_236348866",
        "Больше всего на складе Коледино — 20 шт.",
        "Всего остаток товара — 123 шт.",
    ]
