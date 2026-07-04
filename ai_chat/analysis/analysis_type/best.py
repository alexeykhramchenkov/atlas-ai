from __future__ import annotations

from ai_chat.analysis.analysis_type.ranked import run as run_ranked


ANALYSIS_NAME = "best"



def run(request: dict, supabase) -> dict:
    return run_ranked(
        request={**request, "analysis": ANALYSIS_NAME},
        supabase=supabase,
    )
