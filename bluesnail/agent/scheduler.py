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
from bluesnail.agent.tools import ToolManager
from bluesnail.agent.types import (
    AgentResult,
    AgentStep,
    LLMResponse,
    Message,
    Role,
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

        working_messages = self.memory.store.get_messages()
        window = self.context.build(
            system_prompt=system_prompt,
            messages=working_messages,
            recall_context=recall_context,
            extra_context=extra_context,
        )
        llm_messages = self.context.to_llm_messages(window)

        steps: list[AgentStep] = []
        final_answer = ""
        stopped_reason = "completed"
        run_context = {
            "system_prompt": system_prompt,
            "recall_context": recall_context,
            "extra_context": extra_context,
            "initial_input_count": len(llm_messages),
        }

        for iteration in range(1, self.config.max_iterations + 1):
            step_input = list(llm_messages)
            response = self.llm.chat(
                llm_messages,
                tools=self.tools.schemas() or None,
            )
            step = AgentStep(
                iteration=iteration,
                response=response,
                input_messages=step_input,
            )
            tool_results: list[ToolResult] = []

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

                tool_results = self.tools.run_many(response.tool_calls)
                step.tool_results = tool_results

                for result in tool_results:
                    tool_message = Message(
                        role=Role.TOOL,
                        content=result.content,
                        name=result.name,
                        tool_call_id=result.tool_call_id,
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

    def _fallback_answer(self, steps: list[AgentStep]) -> str:
        for step in reversed(steps):
            if step.response.content:
                return step.response.content.strip()
        return "Unable to produce a final answer."


def new_tool_call_id() -> str:
    return f"call_{uuid4().hex[:12]}"
