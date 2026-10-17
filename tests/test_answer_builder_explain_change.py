from ai_chat.answer_builder import explain_change


def _store_result() -> dict:
    return {
        "analysis": "explain_change",
        "metric": "orders",
        "scope": "store",
        "status": "success",
        "target": {
            "metric": "orders",
            "view": "compare",
            "change_pct": -21,
            "change_abs": -120,
        },
        "factors": {
            "views": {
                "metric": "views",
                "view": "compare",
                "change_pct": -2,
                "change_abs": -500,
            },
            "cart_rate": {
                "metric": "cart_rate",
                "view": "compare",
                "change_pct": -7,
                "change_abs": -1.2,
            },
            "conversion": {
                "metric": "conversion",
                "view": "compare",
                "change_pct": -19,
                "change_abs": -2.1,
            },
            "stock": {
                "metric": "stock",
                "view": "state",
                "value": 0,
            },
        },
        "main_cause": "conversion",
        "contributors": {
            "rows": [
                {
                    "title": "Товар 1",
                    "product_key": "wb_123",
                    "change_abs": -80,
                }
            ]
        },
    }


def _product_result() -> dict:
    result = _store_result()
    result["scope"] = "product"
    result["main_cause"] = "views"
    result["enriched_context"] = {
        "price": {
            "price_with_discount": 1000,
            "discount_percent": 20,
        },
        "stock": {
            "stock_qty": 5,
            "sizes_in_stock": ["42"],
        },
        "reviews": {
            "rating": 4.8,
        },
    }
    return result


def test_explain_change_answer_uses_deterministic_data_block(monkeypatch):
    monkeypatch.setattr(
        explain_change,
        "generate_text",
        lambda **kwargs: "Продажи снизились из-за падения конверсии. Трафик почти не изменился, поэтому проблема ниже по воронке.",
    )

    answer = explain_change.build_explain_change_answer(
        question="Почему упали заказы?",
        request={"language": "ru"},
        result=_store_result(),
        language="ru",
    )

    assert answer == "\n".join(
        [
            "Данные",
            "- Заказы: -21%",
            "- Просмотры: -2%",
            "- Cart rate: -7%",
            "- Конверсия: -19%",
            "- Остатки: 0 шт.",
            "",
            "AI Summary",
            "Продажи снизились из-за падения конверсии. Трафик почти не изменился, поэтому проблема ниже по воронке.",
        ]
    )


def test_explain_change_answer_rejects_metric_list_from_llm(monkeypatch):
    monkeypatch.setattr(
        explain_change,
        "generate_text",
        lambda **kwargs: "- Заказы: -21%\n- Конверсия: -19%",
    )

    answer = explain_change.build_explain_change_answer(
        question="Почему упали заказы?",
        request={"language": "ru"},
        result=_store_result(),
        language="ru",
    )

    assert "AI Summary\nЗаказы изменились в основном из-за падения конверсии." in answer
    assert "- Заказы: -21%\n- Конверсия: -19%" not in answer.split("AI Summary", 1)[1]


def test_product_explain_change_does_not_append_current_product_state(monkeypatch):
    monkeypatch.setattr(
        explain_change,
        "generate_text",
        lambda **kwargs: "Заказы по товару снизились из-за падения трафика. Конверсия не выглядит главной причиной.",
    )

    answer = explain_change.build_explain_change_answer(
        question="Почему упали заказы по товару?",
        request={"language": "ru", "product": {"title": "Тестовый товар"}},
        result=_product_result(),
        language="ru",
    )

    assert "Текущее состояние товара" not in answer
    assert "Цена со скидкой" not in answer
    assert answer.startswith("Данные\n- Заказы: -21%")
    assert "\n\nAI Summary\n" in answer
