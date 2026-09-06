"""OpenAI-compatible API provider."""

from __future__ import annotations

import json
from typing import Any

import httpx

from bluesnail.llm.provider import BaseLLMProvider
from bluesnail.core.types import LLMResponse, Message, Role, ToolCall


class OpenAICompatibleProvider(BaseLLMProvider):
    """Provider for OpenAI-compatible chat completion APIs."""

    def __init__(
        self,
        *,
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout: float = 60.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("API Key is required for OpenAI-compatible provider.")

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [_to_api_message(message) for message in messages],
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(extract_api_error(exc.response)) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM returned invalid JSON.") from exc

        return _parse_chat_response(data)


def extract_api_error(response: httpx.Response) -> str:
    """Extract a readable error message from an API error response."""
    try:
        body = response.json()
    except json.JSONDecodeError:
        text = response.text.strip()
        if text:
            return text
        return f"LLM API HTTP {response.status_code}"

    if isinstance(body, dict):
        error = body.get("error", body)
        if isinstance(error, dict):
            message = error.get("message") or error.get("msg") or error.get("detail")
            if message:
                return str(message)
        message = body.get("message") or body.get("msg") or body.get("detail")
        if message:
            return str(message)
    return f"LLM API HTTP {response.status_code}"


def _parse_chat_response(data: dict[str, Any]) -> LLMResponse:
    choices = data.get("choices") or []
    if not choices:
        raise RuntimeError("LLM returned no choices.")

    choice = choices[0]
    message = choice.get("message") or {}
    tool_calls = [
        ToolCall(
            id=call.get("id") or "",
            name=(call.get("function") or {}).get("name") or "",
            arguments=_parse_arguments((call.get("function") or {}).get("arguments")),
        )
        for call in message.get("tool_calls") or []
        if (call.get("function") or {}).get("name")
    ]
    return LLMResponse(
        content=message.get("content"),
        tool_calls=tool_calls,
        finish_reason=choice.get("finish_reason"),
        raw=data,
    )


def _to_api_message(message: Message) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "role": message.role.value,
        "content": message.content or "",
    }
    if message.name:
        payload["name"] = message.name
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.role == Role.ASSISTANT:
        tool_calls = message.metadata.get("tool_calls")
        if tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call["id"],
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": json.dumps(
                            call["arguments"],
                            ensure_ascii=False,
                        ),
                    },
                }
                for call in tool_calls
            ]
    return payload


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}
