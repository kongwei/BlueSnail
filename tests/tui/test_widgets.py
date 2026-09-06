"""TUI component tests for Agent server stream rendering."""

from bluesnail.service.http import StreamEvent
from bluesnail.tui.render import format_stream_event, format_workflow_event
from bluesnail.tui.widgets import InferenceTrace, SessionView


def test_format_workflow_event_includes_step_identity() -> None:
    line = format_workflow_event(
        {
            "phase": "after",
            "step_id": "think",
            "step_type": "llm",
            "sequence": 5,
            "outcome": "content",
            "payload": {"llm": {"content": "hello from the model", "tool_calls": []}},
        }
    )
    assert "[5]" in line
    assert "think" in line
    assert "llm" in line
    assert "hello" in line


def test_session_view_applies_stream_events() -> None:
    view = SessionView("tui-test")
    view.begin_user_turn("hi")
    view.apply_stream_event(
        StreamEvent("start", {"run_context": {"workflow_name": "react"}, "user_input": "hi"})
    )
    view.apply_stream_event(
        StreamEvent(
            "workflow",
            {
                "phase": "after",
                "step_id": "llm",
                "step_type": "llm",
                "sequence": 1,
                "outcome": "content",
                "payload": {},
            },
        )
    )
    chat_line, _ = view.apply_stream_event(
        StreamEvent("done", {"answer": "ok", "iterations": 1, "stopped_reason": "completed"})
    )
    assert chat_line is not None
    assert "ok" in chat_line
    assert view.busy is False
    assert "llm" in view.trace.workflow_after_types()
    assert format_stream_event("done", {"iterations": 1, "stopped_reason": "completed"})


def test_inference_trace_records_hook_events() -> None:
    trace = InferenceTrace()
    trace.add_event("workflow", {"phase": "before", "step_type": "ingest_user", "step_id": "user", "sequence": 1})
    trace.add_event("workflow", {"phase": "after", "step_type": "ingest_user", "step_id": "user", "sequence": 1, "outcome": "next"})
    assert trace.workflow_after_types() == ["ingest_user"]
    assert len(trace.lines) == 2
