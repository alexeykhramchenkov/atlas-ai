from ai_chat.analysis.executor import ANALYSIS_TYPE_HANDLERS


def test_orders_ranking_is_registered() -> None:
    assert "best" in ANALYSIS_TYPE_HANDLERS
    assert "worst" in ANALYSIS_TYPE_HANDLERS
