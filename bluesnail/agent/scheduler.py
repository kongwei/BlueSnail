"""Agent scheduling module."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from bluesnail.agent.context import ContextManager
from bluesnail.agent.exceptions import SchedulerError
from bluesnail.agent.llm import LLMProvider
from bluesnail.agent.memory import MemoryProcessor
from bluesnail.agent.skills import SkillManager
from bluesnail.agent.tools import ToolManager
from bluesnail.agent.types import (
    AgentResult,
    AgentStep,
    LLMResponse,
    Message,
    Role,
    SkillResult,
    ToolCall,
    ToolResult,
)


@dataclass(slots=True)
class SchedulerConfig:
    max_iterations: int = 10
    auto_recall: bool = True
    recall_top_k: int = 3


StepHook = Callable[[AgentStep], None]
RunHook = Callable[[AgentResult], None]


@dataclass
class Scheduler:
    """Orchestrates the think-act-observe loop for an agent."""

    llm: LLMProvider
    memory: MemoryProcessor
    tools: ToolManager
    context: ContextManager
    skills: SkillManager | None = None
    config: SchedulerConfig = field(default_factory=SchedulerConfig)
    on_step: StepHook | None = None
    on_complete: RunHook | None = None

    def run(
        self,
        user_input: str,
        *,
        system_prompt: str = "You are a helpful AI assistant.",
        session_id: str | None = None,
        extra_context: str = "",
    ) -> AgentResult:
        if not user_input.strip():
            raise SchedulerError("User input cannot be empty.")

        user_message = Message(role=Role.USER, content=user_input.strip())
        self.memory.store.add_message(user_message)

        recall_context = ""
        if self.config.auto_recall:
            recall_context = self.memory.build_recall_context(
                user_input,
                top_k=self.config.recall_top_k,
            )

        skill_context = ""
        if self.skills:
            skill_context = self.skills.build_context()

        working_messages = self.memory.store.get_messages()
        window = self.context.build(
            system_prompt=system_prompt,
            messages=working_messages,
            recall_context=recall_context,
            extra_context=_join_context(extra_context, skill_context),
        )
        llm_messages = self.context.to_llm_messages(window)

        steps: list[AgentStep] = []
        final_answer = ""
        stopped_reason = "completed"
        run_context = {
            "system_prompt": system_prompt,
            "recall_context": recall_context,
            "skill_context": skill_context,
            "extra_context": extra_context,
            "initial_input_count": len(llm_messages),
        }

        for iteration in range(1, self.config.max_iterations + 1):
            step_input = list(llm_messages)
            response = self.llm.chat(
                llm_messages,
                tools=self._available_schemas(),
            )
            step = AgentStep(
                iteration=iteration,
                response=response,
                input_messages=step_input,
            )
            tool_results: list[ToolResult] = []
            skill_results: list[SkillResult] = []

            if response.tool_calls:
                assistant_message = Message(
                    role=Role.ASSISTANT,
                    content=response.content or "",
                    metadata={
                        "tool_calls": [
                            {
                                "id": call.id,
                                "name": call.name,
                                "arguments": call.arguments,
                            }
                            for call in response.tool_calls
                        ]
                    },
                )
                self.memory.store.add_message(assistant_message)
                llm_messages.append(assistant_message)

                tool_results, skill_results = self._execute_calls(response.tool_calls)
                step.tool_results = tool_results
                step.skill_results = skill_results

                for result in _merge_call_results(tool_results, skill_results):
                    tool_message = Message(
                        role=Role.TOOL,
                        content=result.content,
                        name=result.name,
                        tool_call_id=result.call_id,
                        metadata={"kind": result.kind},
                    )
                    self.memory.store.add_message(tool_message)
                    llm_messages.append(tool_message)

                steps.append(step)
                if self.on_step:
                    self.on_step(step)
                continue

            if response.content:
                final_answer = response.content.strip()
                assistant_message = Message(role=Role.ASSISTANT, content=final_answer)
                self.memory.store.add_message(assistant_message)
                steps.append(step)
                if self.on_step:
                    self.on_step(step)
                break

            stopped_reason = "empty_response"
            break
        else:
            stopped_reason = "max_iterations"

        if not final_answer and stopped_reason != "completed":
            final_answer = self._fallback_answer(steps)

        result = AgentResult(
            answer=final_answer,
            steps=steps,
            messages=self.memory.store.get_messages(),
            iterations=len(steps),
            stopped_reason=stopped_reason,
            run_context=run_context,
        )

        if session_id:
            self.memory.store.remember(
                key=f"session:{session_id}",
                content=f"Q: {user_input}\nA: {final_answer}",
                metadata={"session_id": session_id},
            )

        if self.on_complete:
            self.on_complete(result)

        return result

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
