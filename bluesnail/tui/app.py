"""Textual TUI that connects to the BlueSnail Agent server."""

from __future__ import annotations

import argparse
import threading
from uuid import uuid4

from bluesnail.service.http import AgentClient, AgentClientError, StreamEvent
from bluesnail.tui.ime import apply_textual_ime_patches, configure_tui_environment
from bluesnail.tui.widgets import SessionView


def build_app(base_url: str = "http://127.0.0.1:7860"):
    configure_tui_environment()
    apply_textual_ime_patches()
    textual = _require_textual()
    App = textual["App"]
    ComposeResult = textual["ComposeResult"]
    Horizontal = textual["Horizontal"]
    Vertical = textual["Vertical"]
    Footer = textual["Footer"]
    Header = textual["Header"]
    Input = textual["Input"]
    RichLog = textual["RichLog"]
    Static = textual["Static"]

    class BlueSnailTUI(App):
        """Terminal UI for chatting with a running Agent server."""

        CSS = """
        Screen {
            layout: vertical;
        }
        #body {
            height: 1fr;
        }
        #chat-pane, #trace-pane {
            height: 1fr;
            border: solid $accent;
        }
        #chat-pane {
            width: 3fr;
        }
        #trace-pane {
            width: 2fr;
        }
        #status {
            height: 1;
            padding: 0 1;
        }
        Input {
            dock: bottom;
        }
        """
        BINDINGS = [
            ("ctrl+c", "quit", "Quit"),
            ("ctrl+l", "clear_chat", "Clear"),
        ]

        def __init__(self, base_url: str) -> None:
            super().__init__()
            self.base_url = base_url.rstrip("/")
            self.client = AgentClient(self.base_url)
            self.view_state = SessionView(session_id=f"tui-{uuid4().hex[:10]}")

        def compose(self) -> ComposeResult:
            yield Header()
            yield Static("Connecting…", id="status")
            with Horizontal(id="body"):
                with Vertical(id="chat-pane"):
                    yield Static("Chat")
                    yield RichLog(id="chat", highlight=True, markup=False, wrap=True)
                with Vertical(id="trace-pane"):
                    yield Static("Inference trace")
                    yield RichLog(id="trace", highlight=True, markup=False, wrap=True)
            yield Input(placeholder="输入消息后回车发送（支持中文）")
            yield Footer()

        def on_mount(self) -> None:
            self.title = "BlueSnail TUI"
            self.sub_title = self.base_url
            self._refresh_connection()
            self.query_one(Input).focus()

        def on_unmount(self) -> None:
            self.client.close()

        def on_input_submitted(self, event) -> None:
            text = event.value.strip()
            event.input.value = ""
            if not text or self.view_state.busy:
                return
            chat_log = self.query_one("#chat", RichLog)
            chat_log.write(self.view_state.begin_user_turn(text))
            self.query_one("#trace", RichLog).clear()
            self._set_status("Running…")
            thread = threading.Thread(target=self._stream_chat, args=(text,), daemon=True)
            thread.start()

        def action_clear_chat(self) -> None:
            if self.view_state.busy:
                return
            try:
                self.client.clear()
            except AgentClientError as exc:
                self.view_state.fail(str(exc))
                self.query_one("#chat", RichLog).write(format_error(str(exc)))
                return
            self.view_state.chat.clear()
            self.view_state.trace.clear()
            self.query_one("#chat", RichLog).clear()
            self.query_one("#trace", RichLog).clear()
            self._set_status("Conversation cleared")

        def _stream_chat(self, text: str) -> None:
            try:
                for event in self.client.chat_stream(
                    text,
                    session_id=self.view_state.session_id,
                ):
                    self.call_from_thread(self._apply_event, event)
            except Exception as exc:
                self.call_from_thread(self._fail, str(exc))

        def _apply_event(self, event: StreamEvent) -> None:
            chat_line, trace_line = self.view_state.apply_stream_event(event)
            if chat_line:
                self.query_one("#chat", RichLog).write(chat_line)
            if trace_line:
                self.query_one("#trace", RichLog).write(trace_line)
            if event.event_type == "done":
                reason = event.data.get("stopped_reason", "completed")
                self._set_status(f"Idle · {reason}")

        def _fail(self, message: str) -> None:
            line = self.view_state.fail(message)
            self.query_one("#chat", RichLog).write(line)
            self._set_status("Error")

        def _refresh_connection(self) -> None:
            try:
                health = self.client.health()
                workflow = self.client.active_workflow()
            except Exception as exc:
                self.view_state.status = "disconnected"
                self._set_status(f"Disconnected · {exc}")
                return
            self.view_state.status = "connected"
            name = workflow.get("name") or workflow.get("id") or "workflow"
            workspace = health.get("filesystem_workspace", "")
            self._set_status(f"Connected · {name} · {workspace}")

        def _set_status(self, text: str) -> None:
            self.query_one("#status", Static).update(text)

    def format_error(message: str) -> str:
        return f"Error: {message}"

    return BlueSnailTUI(base_url)


def _require_textual() -> dict:
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.widgets import Footer, Header, Input, RichLog, Static
    except ImportError as exc:
        raise ImportError(
            "TUI requires textual. Install with: pip install 'bluesnail[tui]'"
        ) from exc
    return {
        "App": App,
        "ComposeResult": ComposeResult,
        "Horizontal": Horizontal,
        "Vertical": Vertical,
        "Footer": Footer,
        "Header": Header,
        "Input": Input,
        "RichLog": RichLog,
        "Static": Static,
    }


def main() -> None:
    configure_tui_environment()
    parser = argparse.ArgumentParser(description="Run BlueSnail TUI against an Agent server")
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:7860",
        help="Agent server base URL (default: http://127.0.0.1:7860)",
    )
    args = parser.parse_args()
    app = build_app(args.url)
    app.run()


if __name__ == "__main__":
    main()
