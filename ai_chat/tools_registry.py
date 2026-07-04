from typing import Callable, Dict

from ai_chat.tools.rank_products import rank_products
from ai_chat.tools.get_product_card import get_product_card
from ai_chat.tools.find_root_cause import find_root_cause
from ai_chat.tools.get_actions import get_actions


TOOLS: Dict[str, Callable] = {
    "rank_products": rank_products,
    "get_product_card": get_product_card,
    "find_root_cause": find_root_cause,
    "get_actions": get_actions,
}


def get_tool(tool_name: str) -> Callable:
    """
    Return a registered AI chat tool by name.
    Raises ValueError if the tool is not allowed.
    """
    if tool_name not in TOOLS:
        allowed = ", ".join(sorted(TOOLS.keys()))
        raise ValueError(f"Unknown tool: {tool_name}. Allowed tools: {allowed}")

    return TOOLS[tool_name]


if __name__ == "__main__":
    print("Registered tools:")
    for name in sorted(TOOLS.keys()):
        print(f"- {name}")
