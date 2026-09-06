"""Prompt construction and SWE-bench harness forwarding."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from bluesnail.eval.dataset import BenchInstance

EVAL_SYSTEM_PROMPT = (
    "You are a software engineering agent. Fix the GitHub issue by editing files "
    "in the workspace. Prefer small, correct patches. When finished, produce a "
    "unified git diff (diff --git) that can be applied with `git apply`."
)


def build_issue_prompt(instance: BenchInstance) -> str:
    parts = [
        "Solve the following GitHub issue. Edit files under the workspace root "
        "and return a unified git diff that applies cleanly.",
        "",
        f"instance_id: {instance.instance_id}",
    ]
    if instance.repo:
        parts.append(f"repo: {instance.repo}")
    if instance.base_commit:
        parts.append(f"base_commit: {instance.base_commit}")
    parts.extend(["", "ISSUE:", instance.problem_statement.strip()])
    if instance.hints_text.strip():
        parts.extend(["", "HINTS:", instance.hints_text.strip()])
    return "\n".join(parts)


def harness_command(
    *,
    dataset_name: str,
    split: str,
    predictions_path: str,
    run_id: str,
    max_workers: int,
    timeout: int,
    report_dir: str,
    instance_ids: list[str] | None = None,
    rewrite_reports: bool = False,
    modal: bool = False,
    open_file_limit: int = 4096,
    extra_args: list[str] | None = None,
) -> list[str]:
    """Build `python -m swebench.harness.run_evaluation` argv, same flags as SWE-bench."""
    command = [
        sys.executable,
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--split",
        split,
        "--predictions_path",
        predictions_path,
        "--run_id",
        run_id,
        "--max_workers",
        str(max_workers),
        "--timeout",
        str(timeout),
        "--report_dir",
        report_dir,
        "--open_file_limit",
        str(open_file_limit),
        "--rewrite_reports",
        str(rewrite_reports),
        "--modal",
        str(modal),
    ]
    if instance_ids:
        command.extend(["--instance_ids", *instance_ids])
    if extra_args:
        command.extend(extra_args)
    return command


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
