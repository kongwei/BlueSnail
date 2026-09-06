"""End-to-end Agent evaluation against SWE-bench-style instances."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from bluesnail.core.exceptions import AgentError
from bluesnail.eval.dataset import BenchInstance
from bluesnail.eval.harness import EVAL_SYSTEM_PROMPT, build_issue_prompt, dump_json
from bluesnail.eval.predictions import make_prediction, resolve_model_patch, write_predictions_jsonl
from bluesnail.service import AgentService, serialize_result

AgentFactory = Callable[[Path | None], AgentService]


def run_evaluation(
    instances: list[BenchInstance],
    *,
    run_id: str,
    report_dir: Path,
    predictions_path: Path,
    model_name_or_path: str,
    agent_factory: AgentFactory,
    gold: bool = False,
    timeout: int = 1800,
    max_workers: int = 1,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    """Run Agent inference (or gold patches) and write SWE-bench predictions JSONL."""
    run_dir = report_dir / "logs" / "evaluation" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    if gold:
        predictions = [
            make_prediction(item.instance_id, model_name_or_path, item.patch)
            for item in instances
        ]
        write_predictions_jsonl(predictions_path, predictions)
        summary = _summary(
            run_id=run_id,
            predictions_path=predictions_path,
            instances=instances,
            predictions=predictions,
            errors=[],
        )
        dump_json(run_dir / "results.json", summary)
        return summary

    workers = max(1, max_workers)
    errors: list[dict[str, str]] = []
    predictions: list[dict[str, str]] = []

    def evaluate_one(instance: BenchInstance) -> dict[str, str]:
        instance_dir = run_dir / instance.instance_id
        instance_dir.mkdir(parents=True, exist_ok=True)
        workspace = _instance_workspace(workspace_root, instance.instance_id)
        events: list[dict[str, Any]] = []
        service = agent_factory(workspace)
        try:
            result = service.run_with_emitter(
                build_issue_prompt(instance),
                lambda kind, data: events.append({"event": kind, "data": data}),
                session_id=f"{run_id}:{instance.instance_id}",
            )
        except AgentError as exc:
            dump_json(
                instance_dir / "report.json",
                {"instance_id": instance.instance_id, "error": str(exc)},
            )
            raise
        patch = resolve_model_patch(workspace, result.answer)
        prediction = make_prediction(instance.instance_id, model_name_or_path, patch)
        (instance_dir / "trace.jsonl").write_text(
            "\n".join(json.dumps(item, ensure_ascii=False) for item in events) + "\n",
            encoding="utf-8",
        )
        dump_json(
            instance_dir / "report.json",
            {
                "instance_id": instance.instance_id,
                "stopped_reason": result.stopped_reason,
                "iterations": result.iterations,
                "empty_patch": not bool(patch.strip()),
                "result": serialize_result(result),
            },
        )
        (instance_dir / "patch.diff").write_text(patch + ("\n" if patch else ""), encoding="utf-8")
        return prediction

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(evaluate_one, item): item for item in instances}
        for future, instance in futures.items():
            try:
                predictions.append(future.result(timeout=timeout))
            except Exception as exc:
                errors.append({"instance_id": instance.instance_id, "error": str(exc)})
                predictions.append(make_prediction(instance.instance_id, model_name_or_path, ""))

    predictions.sort(key=lambda item: item["instance_id"])
    write_predictions_jsonl(predictions_path, predictions)
    summary = _summary(
        run_id=run_id,
        predictions_path=predictions_path,
        instances=instances,
        predictions=predictions,
        errors=errors,
    )
    dump_json(run_dir / "results.json", summary)
    return summary


def _instance_workspace(root: Path | None, instance_id: str) -> Path | None:
    if root is None:
        return None
    candidate = root / instance_id
    if candidate.is_dir():
        return candidate
    return root


def _summary(
    *,
    run_id: str,
    predictions_path: Path,
    instances: list[BenchInstance],
    predictions: list[dict[str, str]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    empty = [item["instance_id"] for item in predictions if not item.get("model_patch", "").strip()]
    return {
        "run_id": run_id,
        "predictions_path": str(predictions_path),
        "total_instances": len(instances),
        "instances_submitted": len(predictions),
        "instances_completed": len(predictions) - len(errors),
        "instances_with_empty_patches": empty,
        "instances_with_errors": errors,
    }


def default_agent_factory(workspace: Path | None) -> AgentService:
    from bluesnail.integration import Agent, AgentConfig
    from bluesnail.skills import create_default_skills
    from bluesnail.tools import create_default_tools
    from bluesnail.web.llm_config import create_llm_provider, load_config

    config = load_config()
    agent = Agent(
        llm=create_llm_provider(config),
        tools=create_default_tools(workspace_root=workspace),
        skills=create_default_skills(),
        config=AgentConfig(system_prompt=EVAL_SYSTEM_PROMPT),
    )
    return AgentService(agent)
