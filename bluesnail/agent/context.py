"""Context management module."""

from __future__ import annotations

from dataclasses import dataclass, field

from bluesnail.agent.exceptions import ContextOverflowError
from bluesnail.agent.types import Message, Role


@dataclass(slots=True)
class ContextConfig:
    max_tokens: int = 8192
    reserve_tokens: int = 1024
    chars_per_token: float = 4.0
    keep_system: bool = True


@dataclass(slots=True)
class ContextWindow:
    system_prompt: str = ""
    messages: list[Message] = field(default_factory=list)
    injected_context: str = ""


class ContextManager:
    """Build and trim prompt context within a token budget."""

    def __init__(self, config: ContextConfig | None = None) -> None:
        self.config = config or ContextConfig()

    def estimate_tokens(self, text: str) -> int:
        if not text:
            return 0
        return max(1, int(len(text) / self.config.chars_per_token))

    def estimate_messages_tokens(self, messages: list[Message]) -> int:
        return sum(self.estimate_tokens(message.content) for message in messages)

    def available_budget(self) -> int:
        return max(0, self.config.max_tokens - self.config.reserve_tokens)

    def build(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        recall_context: str = "",
        extra_context: str = "",
    ) -> ContextWindow:
        injected = _join_non_empty([recall_context, extra_context])
        trimmed = self.trim_messages(
            system_prompt=system_prompt,
            messages=messages,
            injected_context=injected,
        )
        return ContextWindow(
            system_prompt=system_prompt,
            messages=trimmed,
            injected_context=injected,
        )

    def trim_messages(
        self,
        *,
        system_prompt: str,
        messages: list[Message],
        injected_context: str = "",
    ) -> list[Message]:
        budget = self.available_budget()
        fixed_cost = (
            self.estimate_tokens(system_prompt)
            + self.estimate_tokens(injected_context)
        )
        remaining = budget - fixed_cost
        if remaining <= 0:
            raise ContextOverflowError(
                "System prompt and injected context exceed token budget."
            )

        system_messages = [m for m in messages if m.role == Role.SYSTEM]
        other_messages = [m for m in messages if m.role != Role.SYSTEM]

        if self.config.keep_system:
            remaining -= self.estimate_messages_tokens(system_messages)

        kept: list[Message] = []
        running = 0
        for message in reversed(other_messages):
            cost = self.estimate_tokens(message.content)
            if running + cost > remaining:
                break
            kept.append(message)
            running += cost

        kept.reverse()
        if self.config.keep_system:
            return system_messages + kept
        return kept

    def to_llm_messages(self, window: ContextWindow) -> list[Message]:
        output: list[Message] = []
        if window.system_prompt:
            system_content = window.system_prompt
            if window.injected_context:
                system_content = f"{system_content}\n\n{window.injected_context}"
            output.append(Message(role=Role.SYSTEM, content=system_content))

        output.extend(window.messages)
        return output


def _join_non_empty(parts: list[str]) -> str:
    return "\n\n".join(part.strip() for part in parts if part and part.strip())
