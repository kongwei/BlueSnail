"""TUI widgets that consume Agent server stream events."""

from __future__ import annotations

from typing import Any

from bluesnail.service.http import StreamEvent
from bluesnail.tui.render import (
    assistant_content_from_done,
    format_chat_line,
    format_stream_event,
)


class ChatTranscript:
    """In-memory chat log used by the TUI chat panel."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def add_user(self, text: str) -> str:
        line = format_chat_line("user", text)
        self.lines.append(line)
        return line

    def add_assistant(self, text: str) -> str:
        line = format_chat_line("assistant", text)
        self.lines.append(line)
        return line

    def add_status(self, text: str) -> str:
        line = format_chat_line("status", text)
        self.lines.append(line)
        return line

    def add_error(self, text: str) -> str:
        line = format_chat_line("error", text)
        self.lines.append(line)
        return line

    def clear(self) -> None:
        self.lines.clear()


class InferenceTrace:
    """Collects workflow/LLM hook events for the eval/trace panel."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.lines: list[str] = []

    def add_event(self, event_type: str, data: dict[str, Any]) -> str | None:
        self.events.append((event_type, data))
        line = format_stream_event(event_type, data)
        if line:
            self.lines.append(line)
        return line

    def add_stream_event(self, event: StreamEvent) -> str | None:
        return self.add_event(event.event_type, event.data)

    def clear(self) -> None:
        self.events.clear()
        self.lines.clear()

    def workflow_after_types(self) -> list[str]:
        types: list[str] = []
        for event_type, data in self.events:
            if event_type == "workflow" and data.get("phase") == "after":
                types.append(str(data.get("step_type") or ""))
        return types


class SessionView:
    """Coordinates chat transcript and inference trace for one TUI session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.chat = ChatTranscript()
        self.trace = InferenceTrace()
        self.busy = False
        self.status = "disconnected"

    def begin_user_turn(self, text: str) -> str:
        self.busy = True
        self.trace.clear()
        return self.chat.add_user(text)

    def apply_stream_event(self, event: StreamEvent) -> tuple[str | None, str | None]:
        trace_line = self.trace.add_stream_event(event)
        chat_line = None
        if event.event_type == "done":
            answer = assistant_content_from_done(event.data)
            if answer:
                chat_line = self.chat.add_assistant(answer)
            self.busy = False
        return chat_line, trace_line

    def fail(self, message: str) -> str:
        self.busy = False
        return self.chat.add_error(message)
