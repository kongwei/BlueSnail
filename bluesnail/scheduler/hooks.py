"""Composable run hooks for observing every inference step."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from bluesnail.core.types import AgentResult, AgentStep, WorkflowEvent

StepHook = Callable[[AgentStep], None]
RunHook = Callable[[AgentResult], None]
RunStartHook = Callable[[dict[str, Any]], None]
WorkflowHook = Callable[[WorkflowEvent], None]


def compose_hooks(*hooks: Callable | None) -> Callable | None:
    """Call hooks in order. ``None`` entries are skipped."""
    active = [hook for hook in hooks if hook is not None]
    if not active:
        return None
    if len(active) == 1:
        return active[0]

    def _combined(argument: Any) -> None:
        for hook in active:
            hook(argument)

    return _combined


@dataclass
class RunHooks:
    """Inject observers for run start, workflow nodes, LLM steps, and completion."""

    on_run_start: RunStartHook | None = None
    on_workflow: WorkflowHook | None = None
    on_step: StepHook | None = None
    on_complete: RunHook | None = None

    def merge(self, other: RunHooks | None) -> RunHooks:
        if other is None:
            return self
        return RunHooks(
            on_run_start=compose_hooks(self.on_run_start, other.on_run_start),
            on_workflow=compose_hooks(self.on_workflow, other.on_workflow),
            on_step=compose_hooks(self.on_step, other.on_step),
            on_complete=compose_hooks(self.on_complete, other.on_complete),
        )
