"""Agent scheduling module — executes a user-defined workflow graph."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from bluesnail.context import ContextManager
from bluesnail.core.exceptions import ContextOverflowError, SchedulerError, WorkflowError
from bluesnail.llm import LLMProvider
from bluesnail.memory import MemoryProcessor
from bluesnail.skills import SkillManager
from bluesnail.tools import ToolManager
from bluesnail.core.types import (
    AgentResult,
    AgentStep,
    LLMResponse,
    Message,
    Role,
    SkillResult,
    ToolCall,
    ToolResult,
    WorkflowEvent,
)
from bluesnail.scheduler.hooks import (
    RunHook,
    RunHooks,
    RunStartHook,
    StepHook,
    WorkflowHook,
    compose_hooks,
)
from bluesnail.workflow import Workflow, WorkflowStep, default_react_workflow


@dataclass(slots=True)
class SchedulerConfig:
    max_iterations: int = 50
    auto_recall: bool = True
    recall_top_k: int = 3


@dataclass
class _RunState:
    user_input: str
    system_prompt: str
    session_id: str | None
    extra_context: str
    recall_context: str = ""
    skill_context: str = ""
    llm_messages: list[Message] = field(default_factory=list)
    steps: list[AgentStep] = field(default_factory=list)
    final_answer: str = ""
    stopped_reason: str = "completed"
    pending_step: AgentStep | None = None
    llm_calls: int = 0
    user_ingested: bool = False
    start_emitted: bool = False
    hop_index: int = 0
    run_context: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scheduler:
    """Orchestrates a user-defined workflow of think/act/observe steps."""

    llm: LLMProvider
    memory: MemoryProcessor
    tools: ToolManager
    context: ContextManager
    skills: SkillManager | None = None
    config: SchedulerConfig = field(default_factory=SchedulerConfig)
    workflow: Workflow | None = None
    on_step: StepHook | None = None
    on_complete: RunHook | None = None
    on_run_start: RunStartHook | None = None
    on_workflow: WorkflowHook | None = None

    def __post_init__(self) -> None:
        if self.workflow is None:
            self.workflow = default_react_workflow(
                max_iterations=self.config.max_iterations,
                auto_recall=self.config.auto_recall,
                recall_top_k=self.config.recall_top_k,
            )

    def run(
        self,
        user_input: str,
        *,
        system_prompt: str = "You are a helpful AI assistant.",
        session_id: str | None = None,
        extra_context: str = "",
        on_run_start: RunStartHook | None = None,
        on_step: StepHook | None = None,
        on_complete: RunHook | None = None,
        on_workflow: WorkflowHook | None = None,
        hooks: RunHooks | None = None,
    ) -> AgentResult:
        if not user_input.strip():
            raise SchedulerError("User input cannot be empty.")

        workflow = self.workflow or default_react_workflow(
            max_iterations=self.config.max_iterations,
            auto_recall=self.config.auto_recall,
            recall_top_k=self.config.recall_top_k,
        )

        resolved = RunHooks(
            on_run_start=compose_hooks(self.on_run_start, on_run_start),
            on_workflow=compose_hooks(self.on_workflow, on_workflow),
            on_step=compose_hooks(self.on_step, on_step),
            on_complete=compose_hooks(self.on_complete, on_complete),
        ).merge(hooks)
        step_hook = resolved.on_step
        complete_hook = resolved.on_complete
        run_start_hook = resolved.on_run_start
        workflow_hook = resolved.on_workflow

        state = _RunState(
            user_input=user_input.strip(),
            system_prompt=system_prompt,
            session_id=session_id,
            extra_context=extra_context,
            run_context={
                "system_prompt": system_prompt,
                "recall_context": "",
                "skill_context": "",
                "extra_context": extra_context,
                "workflow_id": workflow.id,
                "workflow_name": workflow.name,
                "initial_input_count": 0,
            },
        )

        current_id = workflow.entry
        visited = 0
        max_hops = max(workflow.max_iterations * 8, 32)

        while current_id:
            visited += 1
            if visited > max_hops:
                raise SchedulerError("Workflow exceeded the maximum number of hops.")
            step = workflow.get_step(current_id)
            if not step.enabled:
                current_id = step.next or step.on.get("next")
                continue
            current_id = self._run_step(
                step,
                state=state,
                workflow=workflow,
                step_hook=step_hook,
                run_start_hook=run_start_hook,
                workflow_hook=workflow_hook,
            )

        if not state.final_answer and state.stopped_reason != "completed":
            state.final_answer = self._fallback_answer(state.steps)

        self._refresh_run_context(state)

        result = AgentResult(
            answer=state.final_answer,
            steps=state.steps,
            messages=self.memory.store.get_messages(),
            iterations=len(state.steps),
            stopped_reason=state.stopped_reason,
            run_context=state.run_context,
        )

        if session_id:
            self.memory.store.remember(
                key=f"session:{session_id}",
                content=f"Q: {state.user_input}\nA: {state.final_answer}",
                metadata={"session_id": session_id},
            )

        if complete_hook:
            complete_hook(result)

        return result

    def _run_step(
        self,
        step: WorkflowStep,
        *,
        state: _RunState,
        workflow: Workflow,
        step_hook: StepHook | None,
        run_start_hook: RunStartHook | None,
        workflow_hook: WorkflowHook | None,
    ) -> str | None:
        handler = {
            "ingest_user": self._step_ingest_user,
            "recall_memory": self._step_recall_memory,
            "inject_skills": self._step_inject_skills,
            "inject_text": self._step_inject_text,
            "build_context": self._step_build_context,
            "llm": self._step_llm,
            "execute_calls": self._step_execute_calls,
            "finish": self._step_finish,
        }.get(step.type)
        if handler is None:
            raise WorkflowError(f"Unsupported step type: {step.type}")
        state.hop_index += 1
        sequence = state.hop_index
        if workflow_hook:
            workflow_hook(
                WorkflowEvent(
                    phase="before",
                    step_id=step.id,
                    step_type=step.type,
                    sequence=sequence,
                    payload=self._workflow_payload(step, state),
                )
            )
        outcome = handler(
            step,
            state=state,
            workflow=workflow,
            step_hook=step_hook,
            run_start_hook=run_start_hook,
        )
        if workflow_hook:
            workflow_hook(
                WorkflowEvent(
                    phase="after",
                    step_id=step.id,
                    step_type=step.type,
                    sequence=sequence,
                    outcome=outcome,
                    payload=self._workflow_payload(step, state, outcome=outcome),
                )
            )
        state.run_context.setdefault("workflow_trace", []).append(
            {"id": step.id, "type": step.type, "outcome": outcome}
        )
        if outcome is None:
            return None
        return self._route(step, outcome)

    def _route(self, step: WorkflowStep, outcome: str) -> str | None:
        if outcome == "__stop__":
            return None
        if outcome in step.on:
            return step.on[outcome]
        if step.next:
            return step.next
        if outcome == "next":
            return None
        raise WorkflowError(
            f"Step '{step.id}' has no route for outcome '{outcome}'."
        )

    def _step_ingest_user(self, step: WorkflowStep, *, state: _RunState, **_: Any) -> str:
        if not state.user_ingested:
            self.memory.store.add_message(Message(role=Role.USER, content=state.user_input))
            state.user_ingested = True
        return "next"

    def _step_recall_memory(self, step: WorkflowStep, *, state: _RunState, **_: Any) -> str:
        top_k = int(step.params.get("top_k", self.config.recall_top_k))
        state.recall_context = self.memory.build_recall_context(
            state.user_input,
            top_k=top_k,
        )
        return "next"

    def _step_inject_skills(self, step: WorkflowStep, *, state: _RunState, **_: Any) -> str:
        if self.skills:
            state.skill_context = self.skills.build_context()
        return "next"

    def _step_inject_text(self, step: WorkflowStep, *, state: _RunState, **_: Any) -> str:
        text = str(step.params.get("text") or "").strip()
        if text:
            state.extra_context = _join_context(state.extra_context, text)
        return "next"

    def _step_build_context(
        self,
        step: WorkflowStep,
        *,
        state: _RunState,
        run_start_hook: RunStartHook | None,
        **_: Any,
    ) -> str:
        self._build_llm_messages(state)
        self._maybe_emit_start(state, run_start_hook)
        return "next"

    def _step_llm(
        self,
        step: WorkflowStep,
        *,
        state: _RunState,
        workflow: Workflow,
        step_hook: StepHook | None,
        run_start_hook: RunStartHook | None,
        **_: Any,
    ) -> str:
        if not state.llm_messages:
            self._build_llm_messages(state)
        self._maybe_emit_start(state, run_start_hook)

        if state.llm_calls >= workflow.max_iterations:
            state.stopped_reason = "max_iterations"
            if not state.final_answer:
                state.final_answer = self._fallback_answer(state.steps)
            return "max_iterations"

        state.llm_calls += 1
        iteration = state.llm_calls
        step_input = list(state.llm_messages)
        use_tools = bool(step.params.get("use_tools", True))
        schemas = self._available_schemas() if use_tools else None

        response = None
        llm_error = None
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                response = self.llm.chat(state.llm_messages, tools=schemas)
                llm_error = None
                break
            except Exception as exc:
                llm_error = exc
                if attempt < max_attempts - 1:
                    time.sleep(attempt * 5 + 5)
        if llm_error is not None:
            state.stopped_reason = "llm_error"
            state.final_answer = f"LLM 调用失败：{llm_error}"
            error_step = AgentStep(
                iteration=iteration,
                response=LLMResponse(content=state.final_answer, finish_reason="error"),
                input_messages=step_input,
            )
            state.steps.append(error_step)
            if step_hook:
                step_hook(error_step)
            return "error"

        agent_step = AgentStep(
            iteration=iteration,
            response=response,
            input_messages=step_input,
        )
        state.pending_step = agent_step

        if response.tool_calls:
            if step_hook:
                step_hook(agent_step)
            return "tool_calls"

        if response.content:
            state.final_answer = response.content.strip()
            assistant_message = Message(role=Role.ASSISTANT, content=state.final_answer)
            self.memory.store.add_message(assistant_message)
            state.llm_messages.append(assistant_message)
            state.steps.append(agent_step)
            state.pending_step = None
            if step_hook:
                step_hook(agent_step)
            return "content"

        state.stopped_reason = "empty_response"
        state.pending_step = None
        return "empty"

    def _step_execute_calls(
        self,
        step: WorkflowStep,
        *,
        state: _RunState,
        step_hook: StepHook | None,
        **_: Any,
    ) -> str:
        agent_step = state.pending_step
        if agent_step is None or not agent_step.response.tool_calls:
            return "next"

        assistant_message = Message(
            role=Role.ASSISTANT,
            content=agent_step.response.content or "",
            metadata={
                "tool_calls": [
                    {
                        "id": call.id,
                        "name": call.name,
                        "arguments": call.arguments,
                    }
                    for call in agent_step.response.tool_calls
                ]
            },
        )
        self.memory.store.add_message(assistant_message)
        state.llm_messages.append(assistant_message)

        tool_results, skill_results = self._execute_calls(agent_step.response.tool_calls)
        agent_step.tool_results = tool_results
        agent_step.skill_results = skill_results

        for result in _merge_call_results(tool_results, skill_results):
            tool_message = Message(
                role=Role.TOOL,
                content=result.content,
                name=result.name,
                tool_call_id=result.call_id,
                metadata={"kind": result.kind},
            )
            self.memory.store.add_message(tool_message)
            state.llm_messages.append(tool_message)

        state.steps.append(agent_step)
        state.pending_step = None
        if step_hook:
            step_hook(agent_step)
        return "next"

    def _step_finish(
        self,
        step: WorkflowStep,
        *,
        state: _RunState,
        run_start_hook: RunStartHook | None = None,
        **_: Any,
    ) -> str:
        if (
            state.pending_step is not None
            and state.pending_step.response.tool_calls
            and state.pending_step not in state.steps
        ):
            state.steps.append(state.pending_step)
            state.pending_step = None
        if not state.final_answer and state.stopped_reason == "completed":
            state.final_answer = self._fallback_answer(state.steps)
        self._maybe_emit_start(state, run_start_hook)
        return "__stop__"

    def _build_llm_messages(self, state: _RunState) -> None:
        working_messages = self.memory.store.get_messages()
        try:
            window = self.context.build(
                system_prompt=state.system_prompt,
                messages=working_messages,
                recall_context=state.recall_context,
                extra_context=_join_context(state.extra_context, state.skill_context),
            )
        except ContextOverflowError as exc:
            raise SchedulerError(str(exc)) from exc
        state.llm_messages = self.context.to_llm_messages(window)
        self._refresh_run_context(state)

    def _workflow_payload(
        self,
        step: WorkflowStep,
        state: _RunState,
        *,
        outcome: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "params": dict(step.params),
            "user_input": state.user_input,
            "llm_calls": state.llm_calls,
            "message_count": len(state.llm_messages),
            "final_answer": state.final_answer,
            "stopped_reason": state.stopped_reason,
            "recall_context": state.recall_context,
            "skill_context": state.skill_context,
            "extra_context": state.extra_context,
        }
        if outcome is not None:
            payload["outcome"] = outcome
        view = self._latest_llm_view(state)
        if view:
            payload["llm"] = view
        return payload

    def _latest_llm_view(self, state: _RunState) -> dict[str, Any] | None:
        agent_step = state.pending_step
        if agent_step is None and state.steps:
            agent_step = state.steps[-1]
        if agent_step is None:
            return None
        return {
            "iteration": agent_step.iteration,
            "content": agent_step.response.content,
            "finish_reason": agent_step.response.finish_reason,
            "tool_calls": [
                {
                    "id": call.id,
                    "name": call.name,
                    "arguments": call.arguments,
                }
                for call in agent_step.response.tool_calls
            ],
            "tool_results": [
                {
                    "tool_call_id": item.tool_call_id,
                    "name": item.name,
                    "content": item.content,
                    "is_error": item.is_error,
                }
                for item in agent_step.tool_results
            ],
            "skill_results": [
                {
                    "skill_call_id": item.skill_call_id,
                    "name": item.name,
                    "content": item.content,
                    "is_error": item.is_error,
                }
                for item in agent_step.skill_results
            ],
        }

    def _maybe_emit_start(self, state: _RunState, run_start_hook: RunStartHook | None) -> None:
        if state.start_emitted:
            return
        self._refresh_run_context(state)
        if run_start_hook:
            run_start_hook(state.run_context)
        state.start_emitted = True

    def _refresh_run_context(self, state: _RunState) -> None:
        state.run_context.update(
            {
                "system_prompt": state.system_prompt,
                "recall_context": state.recall_context,
                "skill_context": state.skill_context,
                "extra_context": state.extra_context,
                "initial_input_count": len(state.llm_messages),
            }
        )

    def _available_schemas(self) -> list[dict[str, Any]] | None:
        schemas = self.tools.schemas()
        if self.skills:
            schemas.extend(self.skills.schemas())
        return schemas or None

    def _execute_calls(
        self,
        tool_calls: list[ToolCall],
    ) -> tuple[list[ToolResult], list[SkillResult]]:
        tool_results: list[ToolResult] = []
        skill_results: list[SkillResult] = []
        for call in tool_calls:
            if self.skills and self.skills.has(call.name):
                skill_results.append(self.skills.run(call))
            else:
                tool_results.append(self.tools.run(call))
        return tool_results, skill_results

    def _fallback_answer(self, steps: list[AgentStep]) -> str:
        for step in reversed(steps):
            if step.response.content:
                return step.response.content.strip()
        return "Unable to produce a final answer."


@dataclass(slots=True)
class _UnifiedCallResult:
    call_id: str
    name: str
    content: str
    kind: str


def _merge_call_results(
    tool_results: list[ToolResult],
    skill_results: list[SkillResult],
) -> list[_UnifiedCallResult]:
    merged: list[_UnifiedCallResult] = []
    for result in tool_results:
        merged.append(
            _UnifiedCallResult(
                call_id=result.tool_call_id,
                name=result.name,
                content=result.content,
                kind="tool",
            )
        )
    for result in skill_results:
        merged.append(
            _UnifiedCallResult(
                call_id=result.skill_call_id,
                name=result.name,
                content=result.content,
                kind="skill",
            )
        )
    return merged


def _join_context(*parts: str) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def new_tool_call_id() -> str:
    return f"call_{uuid4().hex[:12]}"
