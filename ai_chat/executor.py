try:
    from ai_chat.datasets.orders import OrdersDataset
except ModuleNotFoundError:
    OrdersDataset = None
from copy import deepcopy
from typing import Any

from ai_chat.analysis.executor import analysis_executor
from db.client import supabase


class Executor:
    """
    Main coordinator.

    Router
      ↓
    Dataset
      ↓
    Analysis
      ↓
    Result
    """

    def __init__(self, supabase=None):
        self.supabase = supabase

        self.datasets = {}

        if OrdersDataset is not None:
            self.datasets["orders"] = OrdersDataset()

    def execute(self, request: dict):

        if request.get("question_type") == "lookup_chain" or request.get("plan"):
            return self.execute_plan(request)

        return self._execute_single_request(request)

    def _execute_single_request(self, request: dict):

        dataset_name = request["dataset"]
        analysis_name = request["analysis"]
        limit = request.get("limit", 10)

        dataset = self.datasets.get(dataset_name)

        if analysis_name in {"metric_value", "best", "worst", "explain_change", "overview"}:
            return analysis_executor.execute(
                dataset_name=dataset_name,
                analysis_name=analysis_name,
                rows=[],
                limit=limit,
                metric=request.get("metric"),
                request=request,
                supabase=self.supabase,
            )

        if dataset is None:
            raise ValueError(
                f"Dataset '{dataset_name}' is not available for analysis '{analysis_name}'"
            )

        dataset_result = dataset.get_data(
            supabase=self.supabase,
            user_id=request["user_id"],
            shop_id=request["shop_id"],
            marketplace=request["marketplace"],
            period_days=request.get("period_days", 30),
        )

        result = analysis_executor.execute(
            dataset_name=dataset_name,
            analysis_name=analysis_name,
            rows=dataset_result["rows"],
            limit=limit,
            metric=request.get("metric"),
            request=request,
            supabase=self.supabase,
        )

        return result

    def execute_plan(self, request: dict) -> dict:
        plan = request.get("plan") or []

        if not plan:
            raise ValueError("plan is required for lookup_chain")

        step_results: dict[str, dict] = {}
        executed_steps = []

        for index, step in enumerate(plan, start=1):
            step_id = step.get("id") or f"step{index}"
            step_request = self.build_step_request(
                parent_request=request,
                step=step,
                step_results=step_results,
            )

            step_result = self._execute_single_request(step_request)
            step_results[step_id] = step_result
            executed_steps.append(
                {
                    "id": step_id,
                    "request": step_request,
                    "result": step_result,
                }
            )

        final_step = executed_steps[-1]

        return {
            "question_type": "lookup_chain",
            "steps": executed_steps,
            "result": final_step["result"],
            "meta": {
                "steps_count": len(executed_steps),
                "final_step": final_step["id"],
            },
        }

    def build_step_request(
        self,
        parent_request: dict,
        step: dict,
        step_results: dict[str, dict],
    ) -> dict:
        step_request = {
            "is_valid_question": True,
            "question_type": "plan_step",
            "dataset": step["dataset"],
            "analysis": step["analysis"],
            "metric": step["metric"],
            "entity": step.get("entity") or "store",
            "period_days": step.get("period_days", parent_request.get("period_days", 30)),
            "answer_scope": step.get("answer_scope", parent_request.get("answer_scope", "single")),
            "limit": step.get("limit", parent_request.get("limit", 1)),
            "user_id": parent_request["user_id"],
            "shop_id": parent_request["shop_id"],
            "marketplace": parent_request.get("marketplace", "wb"),
        }

        if parent_request.get("language"):
            step_request["language"] = parent_request["language"]

        for key, value in step.items():
            if key not in {"id", "inputs"} and key not in step_request:
                step_request[key] = deepcopy(value)

        for key, reference in (step.get("inputs") or {}).items():
            step_request[key] = self.resolve_plan_reference(
                reference=reference,
                step_results=step_results,
            )

        return step_request

    def resolve_plan_reference(
        self,
        reference: Any,
        step_results: dict[str, dict],
    ) -> Any:
        if not isinstance(reference, dict):
            return reference

        from_step = reference.get("from_step")
        path = reference.get("path")

        if not from_step or not path:
            return reference

        if from_step not in step_results:
            raise ValueError(f"Plan step result not found: {from_step}")

        return self.extract_path(
            data=step_results[from_step],
            path=path,
        )

    def extract_path(self, data: Any, path: str) -> Any:
        current = data

        for part in path.split("."):
            if isinstance(current, list):
                if not current:
                    raise ValueError(
                        f"Cannot extract path '{path}': step returned empty rows"
                    )

                index = int(part)

                if index < 0 or index >= len(current):
                    raise ValueError(
                        f"Cannot extract path '{path}': index {part} out of range"
                    )

                current = current[index]
                continue

            if isinstance(current, dict):
                if part not in current:
                    raise ValueError(
                        f"Cannot extract path '{path}': key '{part}' not found"
                    )

                current = current[part]
                continue

            raise ValueError(f"Cannot extract path '{path}'")

        return current


executor = Executor(supabase=supabase)
