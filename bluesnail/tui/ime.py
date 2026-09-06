"""Workarounds so Windows IME can type CJK in the Textual TUI."""

from __future__ import annotations

import os
import sys
from typing import Any


def keep_win32_key_event(
    virtual_key_code: int,
    control_key_state: int,
    unicode_char: str | None,
) -> bool:
    """Keep KEY_EVENT records that carry real Unicode, including CJK IME commits.

    Textual drops every key-down with ``VK=0`` when *any* control-key state bit is
    set. NumLock/CapsLock count, so Microsoft Pinyin commits (VK=0 + Unicode)
    never reach the Input widget.
    """
    char = unicode_char or ""
    has_char = bool(char) and char != "\x00"
    if virtual_key_code == 0 and control_key_state and not has_char:
        return False
    return True


def collect_win32_keydown_chars(
    events: list[tuple[bool, int, int, str]],
) -> list[str]:
    """Return Unicode chars that should be fed to the parser from key-down events."""
    keys: list[str] = []
    for key_down, virtual_key, control_state, char in events:
        if not key_down:
            continue
        if not keep_win32_key_event(virtual_key, control_state, char):
            continue
        keys.append(char)
    return keys


def configure_tui_environment() -> None:
    """Disable Kitty key protocol before Textual reads environment constants."""
    os.environ.setdefault("TEXTUAL_DISABLE_KITTY_KEY", "1")


def apply_textual_ime_patches() -> None:
    """Patch Textual's Windows driver so IME characters are not discarded."""
    configure_tui_environment()
    if sys.platform != "win32":
        return
    try:
        from textual.drivers import win32
        from textual.drivers.windows_driver import WindowsDriver
    except ImportError:
        return
    _patch_event_monitor(win32)
    _patch_windows_driver(WindowsDriver)


def _patch_event_monitor(win32: Any) -> None:
    monitor = win32.EventMonitor
    if getattr(monitor.run, "_bluesnail_ime", False):
        return

    def run(self) -> None:
        from ctypes import byref, wintypes

        from textual import constants
        from textual._xterm_parser import XTermParser

        exit_requested = self.exit_event.is_set
        parser = XTermParser(debug=constants.DEBUG)

        try:
            read_count = wintypes.DWORD(0)
            h_in = win32.GetStdHandle(win32.STD_INPUT_HANDLE)
            max_events = 1024
            key_event_type = 0x0001
            window_event_type = 0x0004
            input_records = (win32.INPUT_RECORD * max_events)()
            read_console_input_w = win32.KERNEL32.ReadConsoleInputW
            keys: list[str] = []

            while not exit_requested():
                for event in parser.tick():
                    self.process_event(event)
                if win32.wait_for_handles([h_in], 100) is None:
                    continue
                read_console_input_w(
                    h_in, byref(input_records), max_events, byref(read_count)
                )
                new_size: tuple[int, int] | None = None
                del keys[:]
                for input_record in input_records[: read_count.value]:
                    event_type = input_record.EventType
                    if event_type == key_event_type:
                        key_event = input_record.Event.KeyEvent
                        key = key_event.uChar.UnicodeChar
                        if key_event.bKeyDown and keep_win32_key_event(
                            key_event.wVirtualKeyCode,
                            key_event.dwControlKeyState,
                            key,
                        ):
                            keys.append(key)
                    elif event_type == window_event_type:
                        size = input_record.Event.WindowBufferSizeEvent.dwSize
                        new_size = (size.X, size.Y)
                if keys:
                    payload = (
                        "".join(keys)
                        .encode("utf-16", "surrogatepass")
                        .decode("utf-16")
                    )
                    for event in parser.feed(payload):
                        self.process_event(event)
                if new_size is not None:
                    self.on_size_change(*new_size)
        except Exception as error:
            self.app.log.error("EVENT MONITOR ERROR", error)

    run._bluesnail_ime = True  # type: ignore[attr-defined]
    monitor.run = run


def _patch_windows_driver(windows_driver_cls: Any) -> None:
    original = windows_driver_cls.start_application_mode
    if getattr(original, "_bluesnail_ime", False):
        return

    def start_application_mode(self) -> None:
        real_write = self.write

        def write(data: str) -> None:
            # Kitty keyboard protocol mangles multi-codepoint IME commits.
            if data == "\x1b[>1u":
                return
            return real_write(data)

        self.write = write
        try:
            return original(self)
        finally:
            if getattr(self, "write", None) is write:
                del self.write

    start_application_mode._bluesnail_ime = True  # type: ignore[attr-defined]
    windows_driver_cls.start_application_mode = start_application_mode
