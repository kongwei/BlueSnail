"""Tests for OpenAI-compatible provider helpers."""

import json

import httpx

from bluesnail.agent.providers.openai_compatible import (
    _parse_arguments,
    _to_api_message,
    extract_api_error,
)
from bluesnail.agent.types import Message, Role


def test_parse_arguments_from_json_string() -> None:
    assert _parse_arguments('{"city": "上海"}') == {"city": "上海"}


def test_parse_arguments_invalid_json_returns_raw_wrapper() -> None:
    assert _parse_arguments("{bad json") == {"_raw": "{bad json"}


def test_extract_api_error_from_openai_style_body() -> None:
    response = httpx.Response(
        500,
        json={"error": {"message": "内部错误"}},
    )
    assert extract_api_error(response) == "内部错误"


def test_extract_api_error_from_plain_message_field() -> None:
    response = httpx.Response(
        400,
        json={"message": "model not found"},
    )
    assert extract_api_error(response) == "model not found"


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
