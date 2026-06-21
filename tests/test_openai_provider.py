"""Tests for OpenAI-compatible provider helpers."""

from bluesnail.agent.providers.openai_compatible import _parse_arguments, _to_api_message
from bluesnail.agent.types import Message, Role


def test_parse_arguments_from_json_string() -> None:
    assert _parse_arguments('{"city": "上海"}') == {"city": "上海"}


def test_to_api_message_with_tool_calls() -> None:
    message = Message(
        role=Role.ASSISTANT,
        content="",
        metadata={
            "tool_calls": [
                {"id": "call_1", "name": "get_weather", "arguments": {"city": "上海"}}
            ]
        },
    )
    payload = _to_api_message(message)
    assert payload["tool_calls"][0]["function"]["name"] == "get_weather"
