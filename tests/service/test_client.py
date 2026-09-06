"""Agent HTTP client and SSE parser tests."""

import pytest

httpx = pytest.importorskip("httpx")

from bluesnail.service.http import AgentClient, AgentClientError, parse_sse_buffer, parse_sse_frame


def test_parse_sse_buffer_splits_complete_frames() -> None:
    buffer = (
        'event: start\ndata: {"user_input": "hi"}\n\n'
        'event: workflow\ndata: {"phase": "after", "step_type": "llm"}\n\n'
        "event: done\ndata: "
    )
    events, remaining = parse_sse_buffer(buffer)
    assert [event.event_type for event in events] == ["start", "workflow"]
    assert remaining.startswith("event: done")


def test_parse_sse_frame_roundtrip() -> None:
    event = parse_sse_frame('event: step\ndata: {"iteration": 1}')
    assert event is not None
    assert event.event_type == "step"
    assert event.data["iteration"] == 1


def test_agent_client_health_and_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/health":
            return httpx.Response(200, json={"status": "ok", "service": "bluesnail-web"})
        if request.url.path == "/api/chat/stream":
            body = (
                'event: start\ndata: {"run_context": {"workflow_name": "react"}, "user_input": "hi"}\n\n'
                'event: workflow\ndata: {"phase": "after", "step_id": "llm", "step_type": "llm", "sequence": 1, "outcome": "content", "payload": {}}\n\n'
                'event: done\ndata: {"answer": "ok", "iterations": 1, "stopped_reason": "completed"}\n\n'
            )
            return httpx.Response(
                200,
                content=body.encode("utf-8"),
                headers={"content-type": "text/event-stream"},
            )
        if request.url.path == "/api/clear":
            return httpx.Response(400, json={"detail": "nope"})
        return httpx.Response(404, json={"detail": "missing"})

    transport = httpx.MockTransport(handler)
    raw = httpx.Client(transport=transport, base_url="http://test")
    client = AgentClient("http://test", client=raw)
    assert client.health()["status"] == "ok"
    events = list(client.chat_stream("hi", session_id="s1"))
    assert [event.event_type for event in events] == ["start", "workflow", "done"]
    assert events[-1].data["answer"] == "ok"
    with pytest.raises(AgentClientError):
        client.clear()
