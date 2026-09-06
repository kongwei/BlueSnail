"""HTTP client for the BlueSnail Agent server."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from bluesnail.core.exceptions import AgentError


@dataclass(slots=True)
class StreamEvent:
    event_type: str
    data: dict[str, Any]


class AgentClientError(AgentError):
    """Raised when the Agent HTTP API returns an error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AgentClient:
    """Call Agent server endpoints, including SSE inference streams."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:7860",
        *,
        timeout: float = 120.0,
        client: Any | None = None,
    ) -> None:
        httpx = _require_httpx()
        self.base_url = base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> AgentClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def health(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/health")

    def tools(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/tools")

    def skills(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/skills")

    def history(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/history")

    def active_workflow(self) -> dict[str, Any]:
        return self._request_json("GET", "/api/workflow/active")

    def clear(self) -> dict[str, Any]:
        return self._request_json("POST", "/api/clear")

    def chat(
        self,
        message: str,
        *,
        session_id: str | None = None,
        extra_context: str = "",
    ) -> dict[str, Any]:
        return self._request_json(
            "POST",
            "/api/chat",
            json={
                "message": message,
                "session_id": session_id,
                "extra_context": extra_context,
            },
        )

    def chat_stream(
        self,
        message: str,
        *,
        session_id: str | None = None,
        extra_context: str = "",
    ) -> Iterator[StreamEvent]:
        with self._client.stream(
            "POST",
            "/api/chat/stream",
            json={
                "message": message,
                "session_id": session_id,
                "extra_context": extra_context,
            },
        ) as response:
            if response.status_code >= 400:
                detail = _error_detail(response.read().decode("utf-8", errors="replace"))
                raise AgentClientError(detail, status_code=response.status_code)
            buffer = ""
            for chunk in response.iter_text():
                buffer += chunk
                events, buffer = parse_sse_buffer(buffer)
                for event in events:
                    if event.event_type == "error":
                        raise AgentClientError(
                            str(event.data.get("detail") or "Agent 运行失败"),
                            status_code=event.data.get("status_code"),
                        )
                    yield event

    def _request_json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        response = self._client.request(method, path, **kwargs)
        if response.status_code >= 400:
            raise AgentClientError(
                _error_detail(response.text),
                status_code=response.status_code,
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise AgentClientError("Expected a JSON object from the Agent server.")
        return payload


def parse_sse_buffer(buffer: str) -> tuple[list[StreamEvent], str]:
    """Split complete SSE frames out of *buffer*; return leftover text."""
    parts = buffer.split("\n\n")
    remaining = parts.pop() if parts else ""
    events: list[StreamEvent] = []
    for part in parts:
        event = parse_sse_frame(part)
        if event is not None:
            events.append(event)
    return events, remaining


def parse_sse_frame(frame: str) -> StreamEvent | None:
    if not frame.strip():
        return None
    event_type = "message"
    data_line = ""
    for line in frame.split("\n"):
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_line = line[5:].strip()
    if not data_line:
        return None
    payload = json.loads(data_line)
    if not isinstance(payload, dict):
        payload = {"value": payload}
    return StreamEvent(event_type=event_type, data=payload)


def _require_httpx():
    try:
        import httpx
    except ImportError as exc:
        raise ImportError(
            "AgentClient requires httpx. Install with: pip install 'bluesnail[web]' "
            "or pip install 'bluesnail[tui]'"
        ) from exc
    return httpx


def _error_detail(text: str) -> str:
    text = text.strip()
    if not text:
        return "Agent server request failed."
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(payload, dict) and payload.get("detail"):
        return str(payload["detail"])
    return text
