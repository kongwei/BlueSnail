"""Server-side Agent run API with injectable inference hooks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from bluesnail.core.types import AgentResult, AgentStep, WorkflowEvent
from bluesnail.integration import Agent
from bluesnail.scheduler.hooks import RunHooks, compose_hooks
from bluesnail.service.serialize import serialize_result, serialize_step, serialize_workflow_event

EmitFn = Callable[[str, Any], None]


class AgentService:
    """Run an Agent and fan out start / workflow / step / done events.

    Persistent hooks (``add_hook``) are invoked on every run. Extra hooks passed
    to ``run`` / ``run_with_emitter`` are composed for that call only, which is
    the injection point used by evals and the streaming server.
    """

    def __init__(self, agent: Agent) -> None:
        self.agent = agent
        self._hooks = RunHooks()

    def add_hook(
        self,
        *,
        on_run_start=None,
        on_workflow=None,
        on_step=None,
        on_complete=None,
    ) -> None:
        self._hooks = self._hooks.merge(
            RunHooks(
                on_run_start=on_run_start,
                on_workflow=on_workflow,
                on_step=on_step,
                on_complete=on_complete,
            )
        )

    def run(
        self,
        user_input: str,
        *,
        session_id: str | None = None,
        extra_context: str = "",
        hooks: RunHooks | None = None,
        on_run_start=None,
        on_workflow=None,
        on_step=None,
        on_complete=None,
    ) -> AgentResult:
        merged = self._merge_call_hooks(
            hooks,
            on_run_start=on_run_start,
            on_workflow=on_workflow,
            on_step=on_step,
            on_complete=on_complete,
        )
        return self.agent.run(
            user_input,
            session_id=session_id,
            extra_context=extra_context,
            on_run_start=merged.on_run_start,
            on_workflow=merged.on_workflow,
            on_step=merged.on_step,
            on_complete=merged.on_complete,
        )

    def run_with_emitter(
        self,
        user_input: str,
        emit: EmitFn,
        *,
        session_id: str | None = None,
        extra_context: str = "",
        hooks: RunHooks | None = None,
    ) -> AgentResult:
        """Run the agent and emit serialized stream events for each hook."""
        stripped = user_input.strip()

        def on_run_start(ctx: dict[str, Any]) -> None:
            emit(
                "start",
                {
                    "run_context": ctx,
                    "user_input": stripped,
                },
            )

        def on_workflow(event: WorkflowEvent) -> None:
            emit("workflow", serialize_workflow_event(event))

        def on_step(step: AgentStep) -> None:
            emit("step", serialize_step(step))

        def on_complete(result: AgentResult) -> None:
            emit("done", serialize_result(result))

        return self.run(
            stripped,
            session_id=session_id,
            extra_context=extra_context,
            hooks=hooks,
            on_run_start=on_run_start,
            on_workflow=on_workflow,
            on_step=on_step,
            on_complete=on_complete,
        )

    def _merge_call_hooks(
        self,
        hooks: RunHooks | None,
        *,
        on_run_start=None,
        on_workflow=None,
        on_step=None,
        on_complete=None,
    ) -> RunHooks:
        call_hooks = RunHooks(
            on_run_start=on_run_start,
            on_workflow=on_workflow,
            on_step=on_step,
            on_complete=on_complete,
        )
        if hooks is not None:
            call_hooks = call_hooks.merge(hooks)
        return self._hooks.merge(call_hooks)


def fanout(*hooks: Callable | None) -> Callable | None:
    return compose_hooks(*hooks)
