from ai_chat.analysis.engine import run_analysis
from ai_chat.analysis.analysis_type import explain_change, metric_value, overview, ranked
from ai_chat.timing import timing


ANALYSIS_TYPE_HANDLERS = {
    "metric_value": metric_value.run,
    "best": ranked.run,
    "worst": ranked.run,
    "explain_change": explain_change.run,
    "overview": overview.run,
}


class AnalysisExecutor:
    """
    Executes analysis over dataset rows.
    """

    def execute(
        self,
        dataset_name: str,
        analysis_name: str,
        rows: list,
        limit: int = 10,
        metric: str | None = None,
        request: dict | None = None,
        supabase=None,
    ):

        if analysis_name in ANALYSIS_TYPE_HANDLERS:
            if request is None:
                raise ValueError("request is required for analysis_type dispatch")
            if supabase is None:
                raise ValueError("supabase is required for analysis_type dispatch")

            handler = ANALYSIS_TYPE_HANDLERS[analysis_name]
            with timing(
                "analysis",
                analysis=analysis_name,
                dataset=dataset_name,
                metric=metric,
                scope=request.get("scope") if request else None,
            ):
                return handler(
                    request={**request, "analysis": analysis_name},
                    supabase=supabase,
                )

        with timing("analysis", analysis=analysis_name, dataset=dataset_name, metric=metric):
            result = run_analysis(
                dataset=dataset_name,
                analysis=analysis_name,
                rows=rows,
                limit=limit,
                metric=metric,
            )

        return result


analysis_executor = AnalysisExecutor()
