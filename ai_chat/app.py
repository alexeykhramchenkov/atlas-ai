import sys
from typing import Any, Dict, List

PROJECT_ROOT = "/Users/macbook/Projects/wb_profit_bot"
sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from ai_chat.chat import chat as run_chat
from ai_chat.tools.get_actions import get_actions
from ai_chat.tools.rank_products import rank_products


st.set_page_config(page_title="AI Analytics OS", layout="wide")


# --------------------
# PAGE STYLE
# --------------------
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.8rem;
        }
        [data-testid="stMetricLabel"] {
            font-size: 0.9rem;
        }
        .dashboard-subtitle {
            color: #777;
            font-size: 1rem;
            margin-top: -0.5rem;
            margin-bottom: 1.5rem;
        }
        .section-title {
            font-size: 1.15rem;
            font-weight: 700;
            margin-top: 0.5rem;
            margin-bottom: 0.5rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------
# HELPERS
# --------------------
def safe_number(value: Any, default: float = 0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def format_money(value: Any) -> str:
    number = safe_number(value)
    return f"${number:,.0f}"


def format_number(value: Any) -> str:
    number = safe_number(value)
    return f"{number:,.0f}"


def format_pct(value: Any) -> str:
    number = safe_number(value)
    return f"{number:.1f}%"


def pick_first(row: Dict[str, Any], keys: List[str], default: Any = 0) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return default


def get_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ["rows", "products", "items", "data", "result"]:
        value = result.get(key)
        if isinstance(value, list):
            return value
    return []


def normalize_product_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    normalized = []
    for index, row in enumerate(rows, start=1):
        revenue = pick_first(row, ["revenue", "total_revenue", "net_revenue"], 0)
        orders = pick_first(row, ["orders", "total_orders", "net_orders"], 0)
        profit = pick_first(row, ["profit", "net_profit", "seller_payout"], 0)
        views = pick_first(row, ["views", "open_card_count", "opens"], 0)
        stock = pick_first(row, ["stock", "stock_qty", "quantity"], 0)
        product_key = pick_first(row, ["product_key", "entity_key", "nm_id"], "—")

        normalized.append(
            {
                "rank": pick_first(row, ["rank"], index),
                "product_key": product_key,
                "orders": safe_number(orders),
                "revenue": safe_number(revenue),
                "profit": safe_number(profit),
                "views": safe_number(views),
                "stock": safe_number(stock),
            }
        )
    return normalized


def normalize_action_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_rows = []
    for key in ["actions", "items", "rows", "data", "result"]:
        value = result.get(key)
        if isinstance(value, list):
            raw_rows = value
            break

    rows = []
    for index, row in enumerate(raw_rows, start=1):
        rows.append(
            {
                "rank": pick_first(row, ["rank"], index),
                "priority": pick_first(row, ["priority", "priority_label", "severity"], "—"),
                "product_key": pick_first(row, ["product_key", "entity_key", "nm_id"], "—"),
                "action": pick_first(row, ["title", "action", "action_type"], "—"),
                "reason": pick_first(row, ["reason", "description", "why"], "—"),
            }
        )
    return rows


def calculate_summary(top_rows: List[Dict[str, Any]], worst_rows: List[Dict[str, Any]], action_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    revenue = sum(row["revenue"] for row in top_rows)
    orders = sum(row["orders"] for row in top_rows)
    profit = sum(row["profit"] for row in top_rows)
    views = sum(row["views"] for row in top_rows)
    stock = sum(row["stock"] for row in top_rows)
    aov = revenue / orders if orders else 0
    conversion = orders / views * 100 if views else 0

    losing_products = [row for row in worst_rows if row["profit"] < 0]
    low_stock_products = [row for row in top_rows + worst_rows if row["stock"] <= 5 and row["stock"] > 0]

    return {
        "revenue": revenue,
        "orders": orders,
        "profit": profit,
        "aov": aov,
        "conversion": conversion,
        "stock": stock,
        "active_problems": len(action_rows),
        "losing_products": len(losing_products),
        "stock_risks": len(low_stock_products),
    }


def render_ai_chat() -> None:
    st.markdown('<div class="section-title">AI Chat</div>', unsafe_allow_html=True)
    st.caption("Ask your AI analyst about products, revenue, profit, stock or actions.")

    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    for message in st.session_state.chat_messages[-6:]:
        with st.chat_message(message["role"]):
            st.write(message["content"])

    user_question = st.chat_input("Ask your ecommerce analyst...")

    if user_question:
        st.session_state.chat_messages.append({"role": "user", "content": user_question})

        with st.chat_message("user"):
            st.write(user_question)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing store data..."):
                try:
                    output = run_chat(user_question)
                    answer = output.get("answer", "No answer returned.")
                except Exception as exc:
                    answer = f"Error: {exc}"

            st.write(answer)

        st.session_state.chat_messages.append({"role": "assistant", "content": answer})

    if st.button("Clear chat"):
        st.session_state.chat_messages = []
        st.rerun()


# --------------------
# SIDEBAR
# --------------------
with st.sidebar:
    st.header("Dashboard controls")
    period_days = st.slider("Period days", min_value=7, max_value=60, value=14)
    st.caption("Current version uses real WB data as ecommerce demo data.")

    st.divider()
    st.markdown("**Data source**")
    st.write("Marketplace: WB")
    st.write("Store: Beberry")
    st.write("Mode: MVP")


# --------------------
# MAIN DASHBOARD
# --------------------
st.title("AI Analytics OS")
st.markdown(
    '<div class="dashboard-subtitle">Shopify-style executive dashboard powered by real WB store data.</div>',
    unsafe_allow_html=True,
)

with st.spinner("Loading dashboard data..."):
    top_products_raw = rank_products(metric="revenue", direction="desc", period_days=period_days, limit=10)
    worst_products_raw = rank_products(metric="profit", direction="asc", period_days=period_days, limit=10)
    actions_raw = get_actions(limit=10)


top_products = normalize_product_rows(get_rows(top_products_raw))
worst_products = normalize_product_rows(get_rows(worst_products_raw))
actions = normalize_action_rows(actions_raw)
summary = calculate_summary(top_products, worst_products, actions)


# KPI ROW
kpi_1, kpi_2, kpi_3, kpi_4, kpi_5, kpi_6 = st.columns(6)

with kpi_1:
    st.metric("Revenue", format_money(summary["revenue"]))
with kpi_2:
    st.metric("Orders", format_number(summary["orders"]))
with kpi_3:
    st.metric("Profit", format_money(summary["profit"]))
with kpi_4:
    st.metric("AOV", format_money(summary["aov"]))
with kpi_5:
    st.metric("Conversion", format_pct(summary["conversion"]))
with kpi_6:
    st.metric("Active problems", format_number(summary["active_problems"]))

st.divider()


# TOP AREA
left_col, right_col = st.columns([1.25, 0.75])

with left_col:
    st.markdown('<div class="section-title">Top products by revenue</div>', unsafe_allow_html=True)
    if top_products:
        st.dataframe(top_products, use_container_width=True, hide_index=True)
    else:
        st.info("No top product data returned yet.")

with right_col:
    st.markdown('<div class="section-title">AI Summary</div>', unsafe_allow_html=True)
    if worst_products:
        worst_product = worst_products[0]
        st.write(
            f"The first product to inspect is `{worst_product['product_key']}`. "
            f"It generated {format_money(worst_product['revenue'])} revenue, "
            f"{format_money(worst_product['profit'])} profit and "
            f"{format_number(worst_product['orders'])} orders in the selected period."
        )
    else:
        st.write("Not enough product data to build an AI summary yet.")

    st.write(
        f"There are **{format_number(summary['active_problems'])}** active action items, "
        f"**{format_number(summary['losing_products'])}** losing products and "
        f"**{format_number(summary['stock_risks'])}** stock risks in the current view."
    )

st.divider()


# SECOND AREA
problems_col, worst_col = st.columns(2)

with problems_col:
    st.markdown('<div class="section-title">Problems / actions</div>', unsafe_allow_html=True)
    if actions:
        st.dataframe(actions, use_container_width=True, hide_index=True)
    else:
        st.info("No action items returned yet.")

with worst_col:
    st.markdown('<div class="section-title">Worst products by profit</div>', unsafe_allow_html=True)
    if worst_products:
        st.dataframe(worst_products, use_container_width=True, hide_index=True)
    else:
        st.info("No worst product data returned yet.")

st.divider()

render_ai_chat()

with st.expander("Raw JSON"):
    st.json(
        {
            "top_products_raw": top_products_raw,
            "worst_products_raw": worst_products_raw,
            "actions_raw": actions_raw,
        }
    )