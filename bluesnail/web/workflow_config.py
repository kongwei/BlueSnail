"""Persist user-defined agent workflows."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from bluesnail.core.exceptions import WorkflowError
from bluesnail.workflow import Workflow, WorkflowBundle, default_bundle


def config_path() -> Path:
    custom = os.getenv("BLUESNAIL_CONFIG_DIR")
    if custom:
        return Path(custom) / "workflow.json"
    return Path.home() / ".bluesnail" / "workflow.json"


def load_bundle() -> WorkflowBundle:
    path = config_path()
    if not path.exists():
        return default_bundle()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"Invalid workflow.json: {exc}") from exc
    return WorkflowBundle.from_dict(data)


def save_bundle(bundle: WorkflowBundle) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_active_workflow() -> Workflow:
    return load_bundle().active()


def apply_bundle(agent: Any, bundle: WorkflowBundle) -> None:
    agent.scheduler.workflow = bundle.active()
    agent.scheduler.config.max_iterations = bundle.active().max_iterations
