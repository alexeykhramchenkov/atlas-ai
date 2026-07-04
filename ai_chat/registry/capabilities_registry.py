

"""
Capability registry for AI Analytics OS.

This file describes what the bot can do.
Router should use this registry to choose the right analytical capability,
instead of hardcoding every possible question directly in router.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


Capability = Dict[str, Any]


CAPABILITIES: Dict[str, Capability] = {
    "store_overview": {
        "title": "Store overview",
        "description": "Explain what is happening in the store at the business level.",
        "status": "planned",
        "questions": [
            "what happened",
            "store overview",
            "how is the store doing",
            "что происходит в магазине",
            "как дела в магазине",
            "дай обзор магазина",
        ],
        "metrics": ["revenue", "orders", "profit", "aov", "conversion", "stock"],
        "tools": ["get_store_overview", "rank_products", "get_actions"],
        "output_format": "summary_with_kpis",
    },

    "product_ranking": {
        "title": "Product ranking",
        "description": "Find best, worst, growing, declining, profitable or problematic products.",
        "status": "active",
        "questions": [
            "best products",
            "worst products",
            "top products",
            "products by profit",
            "products by revenue",
            "products by turnover",
            "лучшие товары",
            "худшие товары",
            "товары по прибыли",
            "товары по выручке",
            "товары по оборачиваемости",
            "лучшие товары по прибыли и оборачиваемости",
        ],
        "metrics": [
            "orders",
            "revenue",
            "profit",
            "views",
            "turnover",
            "stock",
            "conversion",
        ],
        "tools": ["rank_products", "get_product_card"],
        "output_format": "numbered_product_list",
    },

    "product_health": {
        "title": "Product health",
        "description": "Explain the current condition of one product using sales, funnel, stock and profit data.",
        "status": "planned",
        "questions": [
            "show product",
            "product card",
            "product health",
            "what is happening with product",
            "покажи товар",
            "карточка товара",
            "что с товаром",
            "состояние товара",
        ],
        "metrics": ["orders", "revenue", "profit", "views", "conversion", "buyout_rate", "stock"],
        "tools": ["get_product_card", "get_orders", "get_profit", "get_views", "get_funnel", "get_stocks"],
        "output_format": "product_diagnostic_summary",
    },

    "root_cause": {
        "title": "Root cause",
        "description": "Explain why a metric changed for a product or store.",
        "status": "active",
        "questions": [
            "why did orders drop",
            "why did revenue drop",
            "why did profit drop",
            "why did views drop",
            "what happened to product",
            "почему упали заказы",
            "почему упала выручка",
            "почему упала прибыль",
            "почему упали просмотры",
            "что случилось с товаром",
        ],
        "metrics": ["orders", "revenue", "profit", "views", "conversion", "buyout_rate", "stock"],
        "tools": ["find_root_cause", "get_product_card"],
        "output_format": "root_cause_explanation",
    },

    "detector_explainer": {
        "title": "Detector explainer",
        "description": "Explain detector events, business context, impact, share and priority.",
        "status": "planned",
        "questions": [
            "explain detector",
            "explain event",
            "why did detector fire",
            "why is priority high",
            "why is priority medium",
            "what does this event mean",
            "объясни детектор",
            "объясни событие",
            "почему сработал детектор",
            "что означает проблема",
            "почему такой приоритет",
        ],
        "metrics": ["severity", "impact", "share", "urgency", "confidence", "priority"],
        "tools": ["get_detector_events", "get_product_card"],
        "output_format": "detector_event_explanation",
    },

    "daily_actions": {
        "title": "Daily actions",
        "description": "Choose the most important actions for today based on events, priorities and business impact.",
        "status": "active",
        "questions": [
            "what should i do",
            "what should i do today",
            "top actions",
            "recommended actions",
            "main actions today",
            "что делать",
            "что делать сегодня",
            "главные действия",
            "какие действия рекомендуешь",
            "на чем сфокусироваться сегодня",
        ],
        "metrics": ["priority", "impact", "revenue", "orders", "profit", "stock", "ads"],
        "tools": ["get_actions", "get_product_card"],
        "output_format": "prioritized_action_list",
    },

    "inventory_risk": {
        "title": "Inventory risk",
        "description": "Analyze stock, low inventory, out-of-stock risks and frozen inventory.",
        "status": "planned",
        "questions": [
            "stock risk",
            "inventory risk",
            "out of stock",
            "low stock",
            "frozen stock",
            "остатки",
            "риски по остаткам",
            "что заканчивается",
            "какие товары заморозили деньги",
            "какие товары зависли на складе",
        ],
        "metrics": ["stock", "orders", "turnover", "days_left", "frozen_stock_value"],
        "tools": ["get_stocks", "get_orders", "get_profit"],
        "output_format": "inventory_risk_summary",
    },

    "ads_efficiency": {
        "title": "Ads efficiency",
        "description": "Analyze advertising spend, CTR, CPC, orders and revenue from ads.",
        "status": "planned",
        "questions": [
            "ads performance",
            "advertising efficiency",
            "ad spend",
            "ads without orders",
            "реклама",
            "эффективность рекламы",
            "рекламные расходы",
            "реклама без заказов",
        ],
        "metrics": ["ad_spend", "views", "clicks", "ctr", "cpc", "orders", "revenue", "acos", "roas"],
        "tools": ["get_ads", "get_orders", "get_profit"],
        "output_format": "ads_efficiency_summary",
    },

    "funnel_analysis": {
        "title": "Funnel analysis",
        "description": "Analyze product funnel from views to cart, orders and buyouts.",
        "status": "planned",
        "questions": [
            "funnel",
            "conversion",
            "cart rate",
            "buyout rate",
            "why conversion dropped",
            "воронка",
            "конверсия",
            "добавления в корзину",
            "процент выкупа",
            "почему упала конверсия",
        ],
        "metrics": ["views", "add_to_cart", "orders", "buyouts", "cart_rate", "conversion", "buyout_rate"],
        "tools": ["get_funnel", "get_views", "get_orders"],
        "output_format": "funnel_diagnostic_summary",
    },

    "feedback_analysis": {
        "title": "Feedback analysis",
        "description": "Analyze customer feedback, rating, review dynamics and possible product quality problems.",
        "status": "planned",
        "questions": [
            "feedback",
            "reviews",
            "rating",
            "negative reviews",
            "отзывы",
            "рейтинг",
            "негативные отзывы",
            "что пишут покупатели",
        ],
        "metrics": ["rating", "reviews_count", "negative_reviews", "feedback_sentiment"],
        "tools": ["get_feedbacks", "get_product_card"],
        "output_format": "feedback_summary",
    },

    "questions_analysis": {
        "title": "Questions analysis",
        "description": "Analyze customer questions and find missing information on product cards.",
        "status": "planned",
        "questions": [
            "questions",
            "customer questions",
            "faq",
            "buyer questions",
            "вопросы",
            "вопросы покупателей",
            "что спрашивают покупатели",
            "чего не хватает в карточке",
        ],
        "metrics": ["questions_count", "unanswered_questions", "question_topics"],
        "tools": ["get_questions", "get_product_card"],
        "output_format": "questions_summary",
    },

    "seo_analysis": {
        "title": "SEO analysis",
        "description": "Analyze organic visibility, search ranking and SEO opportunities. Planned for external data layer.",
        "status": "future",
        "questions": [
            "seo",
            "organic traffic",
            "search ranking",
            "keywords",
            "сео",
            "органика",
            "позиции в поиске",
            "ключевые слова",
        ],
        "metrics": ["organic_views", "search_position", "keywords", "impressions"],
        "tools": ["get_seo", "get_external_market"],
        "output_format": "seo_summary",
    },

    "external_market": {
        "title": "External market analysis",
        "description": "Analyze competitor and market data from external sources. Planned for parser layer.",
        "status": "future",
        "questions": [
            "competitors",
            "market",
            "external data",
            "market benchmark",
            "конкуренты",
            "рынок",
            "внешние данные",
            "сравни с рынком",
        ],
        "metrics": ["competitor_price", "market_position", "benchmark", "external_demand"],
        "tools": ["get_external_market"],
        "output_format": "external_market_summary",
    },
}


def get_capabilities() -> Dict[str, Capability]:
    """Return all capabilities."""
    return CAPABILITIES


def get_capability(name: str) -> Optional[Capability]:
    """Return one capability by name."""
    return CAPABILITIES.get(name)


def list_capability_names() -> List[str]:
    """Return all capability names."""
    return list(CAPABILITIES.keys())


def get_active_capabilities() -> Dict[str, Capability]:
    """Return capabilities that can already be used in the current MVP."""
    return {
        name: capability
        for name, capability in CAPABILITIES.items()
        if capability.get("status") == "active"
    }


def build_router_context(include_planned: bool = True) -> str:
    """
    Build a compact text description for router prompt.

    Router can receive this text and select the best capability
    instead of relying on hardcoded if/else rules.
    """
    allowed_statuses = {"active", "planned"} if include_planned else {"active"}
    blocks = []

    for name, capability in CAPABILITIES.items():
        if capability.get("status") not in allowed_statuses:
            continue

        questions = "; ".join(capability.get("questions", [])[:8])
        metrics = ", ".join(capability.get("metrics", []))
        tools = ", ".join(capability.get("tools", []))

        blocks.append(
            f"Capability: {name}\n"
            f"Title: {capability.get('title')}\n"
            f"Description: {capability.get('description')}\n"
            f"Example questions: {questions}\n"
            f"Metrics: {metrics}\n"
            f"Tools: {tools}\n"
            f"Output format: {capability.get('output_format')}"
        )

    return "\n\n".join(blocks)