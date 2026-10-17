from ai_chat.routing import llm_fallback


def test_llm_router_keeps_tenant_context_outside_model(monkeypatch):
    monkeypatch.setattr(
        llm_fallback,
        "generate_openai_json",
        lambda **kwargs: {
            "is_valid_question": True,
            "analysis": "best",
            "metric": "revenue",
            "scope": "product",
            "period_days": 30,
            "answer_scope": "top",
            "limit": 5,
        },
    )
    context = {"user_id": 17, "shop_id": 42, "marketplace": "ozon"}

    request = llm_fallback.route_with_openai(
        "покажи лидеров по деньгам за месяц",
        request_context=context,
    )

    assert request["dataset"] == "orders"
    assert request["metric"] == "orders_revenue"
    assert request["user_id"] == 17
    assert request["shop_id"] == 42
    assert request["marketplace"] == "ozon"


def test_llm_router_fails_closed(monkeypatch):
    def fail(**kwargs):
        raise TimeoutError("model timeout")

    monkeypatch.setattr(llm_fallback, "generate_openai_json", fail)
    assert llm_fallback.route_with_openai("question", request_context={}) is None
