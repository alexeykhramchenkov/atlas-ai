"""
Tool registry for AI Analytics OS.

This file describes:

- what tools exist
- what they do
- what metrics they support
- what arguments they accept
- what they return

Router and capabilities should use this registry
instead of hardcoded logic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


Tool = Dict[str, Any]


TOOLS: Dict[str, Tool] = {

    "rank_products": {

        "title":
        "Rank products",

        "description":
        "Rank products by one or several business metrics.",

        "status":
        "active",

        "metrics": [

            "orders",
            "revenue",
            "profit",

            "views",

            "turnover",

            "conversion",

            "stock"
        ],

        "args": {

            "metric":
            "str",

            "secondary_metric":
            "str | None",

            "direction":
            "asc | desc",

            "period_days":
            "int",

            "limit":
            "int"
        },

        "returns": [

            "rank",

            "product_key",

            "product_name",

            "orders",

            "revenue",

            "profit",

            "views",

            "turnover",

            "stock"

        ]

    },



    "get_product_card": {

        "title":
        "Get product card",

        "description":
        "Return full product facts.",

        "status":
        "active",

        "metrics": [

            "orders",

            "revenue",

            "profit",

            "views",

            "conversion",

            "buyout_rate",

            "stock",

            "turnover"

        ],

        "args": {

            "product_key":
            "str",

            "period_days":
            "int"

        },

        "returns": [

            "product_key",

            "product_name",

            "orders",

            "revenue",

            "profit",

            "views",

            "conversion",

            "buyout_rate",

            "stock",

            "turnover"

        ]

    },



    "find_root_cause": {

        "title":
        "Find root cause",

        "description":
        "Explain why metric changed.",

        "status":
        "active",

        "metrics": [

            "orders",

            "revenue",

            "profit",

            "views",

            "conversion",

            "buyout_rate",

            "stock"

        ],

        "args": {

            "product_key":
            "str",

            "metric":
            "str",

            "period_days":
            "int"

        },

        "returns": [

            "main_cause",

            "secondary_causes",

            "confidence",

            "priority",

            "impact"

        ]

    },



    "get_actions": {

        "title":
        "Get actions",

        "description":
        "Return recommended actions based on events and priorities.",

        "status":
        "active",

        "metrics": [

            "priority",

            "severity",

            "impact",

            "share"

        ],

        "args": {

            "limit":
            "int"

        },

        "returns": [

            "rank",

            "priority",

            "product_key",

            "title",

            "reason",

            "evidence"

        ]

    },



    "get_store_overview": {

        "title":
        "Get store overview",

        "description":
        "Return store level KPIs.",

        "status":
        "planned",

        "metrics": [

            "orders",

            "revenue",

            "profit",

            "aov",

            "conversion"

        ],

        "args": {

            "period_days":
            "int"

        },

        "returns": [

            "orders",

            "revenue",

            "profit",

            "aov",

            "conversion"

        ]

    },



    "get_detector_events": {

        "title":
        "Get detector events",

        "description":
        "Return detector events with business context.",

        "status":
        "planned",

        "metrics": [

            "severity",

            "impact",

            "share",

            "urgency",

            "confidence",

            "priority"

        ],

        "args": {

            "period_days":
            "int",

            "limit":
            "int"

        },

        "returns": [

            "event_type",

            "product_key",

            "severity",

            "impact",

            "share",

            "priority",

            "payload"

        ]

    }

}


def get_tools() -> Dict[str, Tool]:

    return TOOLS



def get_tool(name: str) -> Optional[Tool]:

    return TOOLS.get(name)



def list_tool_names() -> List[str]:

    return list(TOOLS.keys())



def get_active_tools() -> Dict[str, Tool]:

    return {

        name: tool

        for name, tool in TOOLS.items()

        if tool.get("status") == "active"

    }



def build_tools_context() -> str:

    blocks = []

    for name, tool in TOOLS.items():

        metrics = ", ".join(tool.get("metrics", []))

        args = ", ".join(tool.get("args", {}).keys())

        returns = ", ".join(tool.get("returns", []))

        blocks.append(

            f"Tool: {name}\n"

            f"Description: {tool['description']}\n"

            f"Metrics: {metrics}\n"

            f"Args: {args}\n"

            f"Returns: {returns}"

        )

    return "\n\n".join(blocks)