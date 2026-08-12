"""Tests for the cross-platform shell command tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bluesnail.agent.tools import ToolManager
from bluesnail.agent.types import ToolCall
from bluesnail.tools import create_default_tools
from bluesnail.tools.shell import (
    allowed_commands,
    load_shell_config,
    parse_command_line,
    register_shell_tools,
    run_command,
)


def _write_config(workspace: Path, data: dict) -> Path:
    config_dir = workspace / ".agent"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "shell_commands.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root.resolve()


@pytest.fixture
def shell_config(workspace: Path) -> dict:
    data = {
        "timeout_seconds": 30,
        "max_output_bytes": 65536,
        "commands": {
            "common": ["echo", "python", "python3"],
            "windows": ["dir", "cd", "ver"],
            "linux": ["ls", "pwd", "uname"],
        },
    }
    _write_config(workspace, data)
    return data


@pytest.fixture
def tools(workspace: Path, shell_config: dict) -> ToolManager:
    manager = ToolManager()
    register_shell_tools(manager, workspace_root=workspace)
    return manager


def test_create_default_tools_registers_run_command():
    manager = create_default_tools()
    names = {tool.name for tool in manager.registry.list_tools()}
    assert "run_command" in names


def test_load_shell_config(workspace: Path, shell_config: dict):
    loaded = load_shell_config(workspace)
    assert loaded["timeout_seconds"] == 30
    allowlist = allowed_commands(loaded)
    assert "echo" in allowlist
    if sys.platform == "win32":
        assert "dir" in allowlist
        assert "ls" not in allowlist
    else:
        assert "ls" in allowlist
        assert "dir" not in allowlist


def test_missing_config_raises(workspace: Path):
    with pytest.raises(ValueError, match="allowlist not found"):
        load_shell_config(workspace)


def test_reject_disallowed_command(workspace: Path, shell_config: dict):
    with pytest.raises(ValueError, match="Command not allowed"):
        run_command("rm -rf /", workspace_root=workspace)


def test_reject_shell_metacharacters(workspace: Path, shell_config: dict):
    with pytest.raises(ValueError, match="metacharacters"):
        run_command("echo hello && echo world", workspace_root=workspace)


def test_parse_command_line_basic():
    argv = parse_command_line('echo "hello world"')
    assert argv[0] == "echo"
    # Windows shlex (posix=False) keeps surrounding quotes on tokens.
    assert any(token.strip('"') == "hello world" for token in argv)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only command")
def test_run_echo_windows(workspace: Path, shell_config: dict):
    result = run_command("echo hello-shell", workspace_root=workspace)
    assert result["exit_code"] == 0
    assert "hello-shell" in result["stdout"]


@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only command")
def test_run_echo_linux(workspace: Path, shell_config: dict):
    result = run_command("echo hello-shell", workspace_root=workspace)
    assert result["exit_code"] == 0
    assert "hello-shell" in result["stdout"]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only command")
def test_run_dir_windows(tools: ToolManager, workspace: Path, shell_config: dict):
    (workspace / "marker.txt").write_text("x", encoding="utf-8")
    result = tools.run(
        ToolCall(
            id="call_1",
            name="run_command",
            arguments={"command": "dir"},
        )
    )
    assert not result.is_error
    payload = json.loads(result.content)
    assert payload["exit_code"] == 0
    assert "marker.txt" in payload["stdout"]


@pytest.mark.skipif(sys.platform == "win32", reason="Unix-only command")
def test_run_ls_linux(tools: ToolManager, workspace: Path, shell_config: dict):
    (workspace / "marker.txt").write_text("x", encoding="utf-8")
    result = tools.run(
        ToolCall(
            id="call_1",
            name="run_command",
            arguments={"command": "ls"},
        )
    )
    assert not result.is_error
    payload = json.loads(result.content)
    assert payload["exit_code"] == 0
    assert "marker.txt" in payload["stdout"]


def test_working_directory_must_stay_in_workspace(
    workspace: Path, shell_config: dict
):
    with pytest.raises(ValueError, match="escapes workspace"):
        run_command(
            "echo hi",
            working_directory="../outside",
            workspace_root=workspace,
        )


def test_python_version_when_available(workspace: Path, shell_config: dict):
    import shlex
    import subprocess

    code = "print('ok-shell')"
    candidates = ["python", "python3"] if sys.platform == "win32" else ["python3", "python"]
    last_error: Exception | None = None
    result = None
    for exe in candidates:
        if sys.platform == "win32":
            command = subprocess.list2cmdline([exe, "-c", code])
        else:
            command = f"{exe} -c {shlex.quote(code)}"
        try:
            result = run_command(command, workspace_root=workspace)
            break
        except (RuntimeError, ValueError) as exc:
            last_error = exc
    if result is None:
        raise AssertionError(f"python interpreter not available: {last_error}")
    assert result["exit_code"] == 0
    assert "ok-shell" in result["stdout"]
