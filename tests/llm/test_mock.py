"""Mock LLM provider tests."""

from bluesnail.core.types import LLMResponse, Message, Role
from bluesnail.llm import MockLLMProvider


def test_mock_provider_returns_queued_then_default() -> None:
    llm = MockLLMProvider(
        responses=[LLMResponse(content="first", finish_reason="stop")],
        default_content="fallback",
    )
    first = llm.chat([Message(role=Role.USER, content="a")])
    second = llm.chat([Message(role=Role.USER, content="b")])
    assert first.content == "first"
    assert second.content == "fallback"
