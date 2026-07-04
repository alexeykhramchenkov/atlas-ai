from __future__ import annotations

from ai_chat.analysis.analysis_type.best import run as run_ranked_analysis


ANALYSIS_NAME = "worst"


def run(request: dict, supabase) -> dict:
    return run_ranked_analysis(
        request={**request, "analysis": ANALYSIS_NAME},
        supabase=supabase,
    )
