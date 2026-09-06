"""Windows IME / CJK input helpers for the TUI."""

import sys

import pytest

from bluesnail.tui.ime import (
    apply_textual_ime_patches,
    collect_win32_keydown_chars,
    keep_win32_key_event,
)


NUMLOCK_ON = 0x0020
SHIFT_PRESSED = 0x0010


def test_keep_cjk_ime_commit_with_numlock() -> None:
    # Typical Microsoft Pinyin commit: VK=0, NumLock on, Unicode present.
    assert keep_win32_key_event(0, NUMLOCK_ON, "你")
    assert keep_win32_key_event(0, NUMLOCK_ON | SHIFT_PRESSED, "好")


def test_keep_fullwidth_punctuation_with_shift() -> None:
    assert keep_win32_key_event(0, SHIFT_PRESSED, "？")


def test_drop_bare_modifier_noise() -> None:
    assert keep_win32_key_event(0, NUMLOCK_ON, "\x00") is False
    assert keep_win32_key_event(0, SHIFT_PRESSED, "") is False


def test_keep_normal_ascii_keydown() -> None:
    assert keep_win32_key_event(65, NUMLOCK_ON, "a")


def test_collect_ime_commit_sequence() -> None:
    chars = collect_win32_keydown_chars(
        [
            (True, 0, NUMLOCK_ON, "你"),
            (True, 0, NUMLOCK_ON, "好"),
            (False, 0, NUMLOCK_ON, "好"),
            (True, 0, NUMLOCK_ON, "\x00"),
        ]
    )
    assert chars == ["你", "好"]


def test_apply_patches_is_idempotent() -> None:
    apply_textual_ime_patches()
    apply_textual_ime_patches()
    if sys.platform != "win32":
        return
    pytest.importorskip("textual")
    from textual.drivers.win32 import EventMonitor
    from textual.drivers.windows_driver import WindowsDriver

    assert getattr(EventMonitor.run, "_bluesnail_ime", False)
    assert getattr(WindowsDriver.start_application_mode, "_bluesnail_ime", False)
