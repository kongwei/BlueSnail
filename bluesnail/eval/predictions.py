"""SWE-bench prediction records and unified-diff extraction."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

PREDICTION_FIELDS = ("instance_id", "model_name_or_path", "model_patch")

_DIFF_BLOCK = re.compile(
    r"```(?:diff|patch)?\s*\n(.*?)```",
    re.DOTALL | re.IGNORECASE,
)
_UNIFIED_DIFF = re.compile(
    r"(?:^|\n)(diff --git .*|.+\n--- .+\n\+\+\+ .+)",
    re.DOTALL,
)


def make_prediction(
    instance_id: str,
    model_name_or_path: str,
    model_patch: str,
) -> dict[str, str]:
    return {
        "instance_id": instance_id,
        "model_name_or_path": model_name_or_path,
        "model_patch": model_patch or "",
    }


def write_predictions_jsonl(path: Path, predictions: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False) for item in predictions]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def read_predictions_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def extract_unified_diff(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""
    if stripped.startswith("diff --git ") or stripped.startswith("--- "):
        return _normalize_diff(stripped)
    blocks = _DIFF_BLOCK.findall(stripped)
    for block in blocks:
        candidate = block.strip()
        if candidate.startswith("diff --git ") or "\n--- " in candidate:
            return _normalize_diff(candidate)
    match = _UNIFIED_DIFF.search("\n" + stripped)
    if match:
        start = match.start(1)
        return _normalize_diff(stripped[start:].strip())
    return ""


def workspace_git_diff(workspace: Path) -> str:
    if not (workspace / ".git").exists():
        return ""
    staged = _git(workspace, ["diff", "--cached", "--no-color"])
    unstaged = _git(workspace, ["diff", "--no-color"])
    return _normalize_diff("\n".join(part for part in (staged, unstaged) if part))


def resolve_model_patch(workspace: Path | None, agent_answer: str) -> str:
    if workspace is not None:
        from_git = workspace_git_diff(workspace)
        if from_git:
            return from_git
    return extract_unified_diff(agent_answer)


def _git(workspace: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def _normalize_diff(text: str) -> str:
    return text.replace("\r\n", "\n").strip()
