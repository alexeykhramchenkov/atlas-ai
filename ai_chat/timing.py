from __future__ import annotations

import os
from contextlib import contextmanager
from time import perf_counter
from typing import Any

from core.logger import logger


def timing_enabled() -> bool:
    return os.getenv("AI_TIMING") == "1"


@contextmanager
def timing(stage: str, **context: Any):
    started_at = perf_counter()
    try:
        yield
    finally:
        log_timing(stage=stage, started_at=started_at, **context)


def log_timing(stage: str, started_at: float, **context: Any) -> None:
    if not timing_enabled():
        return

    duration_ms = (perf_counter() - started_at) * 1000
    context_text = " ".join(
        f"{key}={value}"
        for key, value in context.items()
        if value is not None
    )
    logger.info(
        "timing stage=%s duration_ms=%.2f %s",
        stage,
        duration_ms,
        context_text,
    )
