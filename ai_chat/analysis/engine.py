from ai_chat.analysis.rules_loader import load_rules
from ai_chat.analysis.sort_engine import sort_rows


SUPPORTED_RANKING_ANALYSES = {
    "best",
    "worst",
    "scale",
    "stop",
    "risk",
}


def run_analysis(
    dataset: str,
    analysis: str,
    rows: list[dict],
    limit: int = 10,
    metric: str | None = None,
    rules: list[dict] | None = None,
):
    """
    Main analysis entry point.

    It does not know how dataset was created.
    It only receives rows and applies selected analysis logic.
    """

    if not rows:
        return {
            "dataset": dataset,
            "analysis": analysis,
            "rows": [],
            "meta": {
                "limit": limit,
                "rows_count": 0,
                "message": "No rows to analyze",
            },
        }

    if analysis in {"best", "worst"} and metric:
        direction = "desc" if analysis == "best" else "asc"

        analysis_rules = [
            {
                "metric": metric,
                "direction": direction,
                "priority": 1,
                "weight": 1.0,
            }
        ]

        result_rows = sort_rows(
            rows=rows,
            rules=analysis_rules,
            limit=limit,
        )

        return {
            "dataset": dataset,
            "analysis": analysis,
            "metric": metric,
            "rows": result_rows,
            "meta": {
                "limit": limit,
                "rows_count": len(result_rows),
                "rules": analysis_rules,
            },
        }

    if analysis in SUPPORTED_RANKING_ANALYSES:
        analysis_rules = rules or load_rules(
            dataset=dataset,
            analysis=analysis,
        )

        result_rows = sort_rows(
            rows=rows,
            rules=analysis_rules,
            limit=limit,
        )

        return {
            "dataset": dataset,
            "analysis": analysis,
            "metric": metric,
            "rows": result_rows,
            "meta": {
                "limit": limit,
                "rows_count": len(result_rows),
                "rules": analysis_rules,
            },
        }

    raise ValueError(f"Unsupported analysis: {analysis}")


if __name__ == "__main__":
    print("analysis engine")
    print("Ready")