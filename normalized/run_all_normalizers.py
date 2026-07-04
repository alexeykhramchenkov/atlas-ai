

from __future__ import annotations

import importlib
import runpy
import sys
import traceback
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable


@dataclass(frozen=True)
class NormalizerSpec:
    name: str
    module_path: str


NORMALIZERS: list[NormalizerSpec] = [
    NormalizerSpec("products", "normalized.normalized_wb_products"),
    NormalizerSpec("orders", "normalized.normalized_wb_orders"),
    NormalizerSpec("sales", "normalized.normalized_wb_sales"),
    NormalizerSpec("stocks", "normalized.normalized_wb_stocks"),
    NormalizerSpec("prices", "normalized.normalized_wb_prices"),
    NormalizerSpec("funnel", "normalized.normalized_wb_funnel"),
    NormalizerSpec("ads", "normalized.normalized_wb_ads"),
    NormalizerSpec("ads_stats", "normalized.normalized_wb_ads_stats"),
    NormalizerSpec("feedbacks", "normalized.normalized_wb_feedbacks"),
    NormalizerSpec("questions", "normalized.normalized_wb_questions"),
    NormalizerSpec("realization_reports", "normalized.normalized_wb_realization_reports"),
    NormalizerSpec("realization", "normalized.normalized_wb_realization"),
]


CANDIDATE_ENTRYPOINTS = (
    "run",
    "main",
    "normalize",
    "run_normalizer",
    "run_all",
)


def find_entrypoint(module: Any) -> Callable[[], Any] | None:
    for entrypoint_name in CANDIDATE_ENTRYPOINTS:
        entrypoint = getattr(module, entrypoint_name, None)
        if callable(entrypoint):
            return entrypoint

    return None


def run_normalizer(spec: NormalizerSpec) -> dict[str, Any]:
    started_at = perf_counter()
    print(f"\n=== Normalizer started | {spec.name} | {spec.module_path} ===")

    module = importlib.import_module(spec.module_path)
    entrypoint = find_entrypoint(module)

    if entrypoint:
        result = entrypoint()
    else:
        print(
            f"No callable entrypoint found for {spec.name}. "
            f"Running module as script: {spec.module_path}"
        )
        result = runpy.run_module(spec.module_path, run_name="__main__")

    duration_sec = round(perf_counter() - started_at, 2)
    print(f"=== Normalizer success | {spec.name} | duration={duration_sec}s | result={result} ===")

    return {
        "name": spec.name,
        "module_path": spec.module_path,
        "status": "success",
        "duration_sec": duration_sec,
        "result": result,
    }


def run_all_normalizers() -> dict[str, Any]:
    started_at = perf_counter()
    results: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    print("Starting all WB normalizers")

    for spec in NORMALIZERS:
        try:
            result = run_normalizer(spec)
            results.append(result)
        except Exception as exc:
            duration_sec = round(perf_counter() - started_at, 2)
            error = {
                "name": spec.name,
                "module_path": spec.module_path,
                "status": "failed",
                "duration_sec": duration_sec,
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            failed.append(error)
            results.append(error)

            print(f"=== Normalizer failed | {spec.name} | {type(exc).__name__}: {exc} ===")
            traceback.print_exc()
            break

    total_duration_sec = round(perf_counter() - started_at, 2)
    summary = {
        "status": "success" if not failed else "failed",
        "total": len(NORMALIZERS),
        "success": len([item for item in results if item["status"] == "success"]),
        "failed": len(failed),
        "duration_sec": total_duration_sec,
        "results": results,
    }

    print(f"\nAll normalizers finished | summary={summary}")
    return summary


def main() -> None:
    summary = run_all_normalizers()
    if summary["status"] != "success":
        sys.exit(1)


if __name__ == "__main__":
    main()