"""LLM provider abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable

from bluesnail.agent.types import LLMResponse, Message, ToolCall


@runtime_checkable
class LLMProvider(Protocol):
    """Protocol for language model backends."""

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        """Send messages to the model and return a structured response."""
        ...


class BaseLLMProvider(ABC):
    """Optional base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        raise NotImplementedError


class MockLLMProvider(BaseLLMProvider):
    """Deterministic LLM for testing and demos."""

    def __init__(
        self,
        responses: list[LLMResponse] | None = None,
        default_content: str = "Mock response.",
    ) -> None:
        self._responses = list(responses or [])
        self._default_content = default_content
        self._call_count = 0
        self.last_messages: list[Message] = []
        self.last_tools: list[dict[str, Any]] | None = None

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.last_messages = list(messages)
        self.last_tools = tools
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
        else:
            response = LLMResponse(content=self._default_content, finish_reason="stop")
        self._call_count += 1
        return response

    def queue_tool_call(
        self,
        tool_call_id: str,
        name: str,
        arguments: dict[str, Any],
        *,
        then_content: str | None = None,
    ) -> None:
        """Helper to enqueue a tool-call response followed by a final answer."""
        self._responses.append(
            LLMResponse(
                tool_calls=[ToolCall(id=tool_call_id, name=name, arguments=arguments)],
                finish_reason="tool_calls",
            )
        )
        if then_content is not None:
            self._responses.append(
                LLMResponse(content=then_content, finish_reason="stop")
            )
