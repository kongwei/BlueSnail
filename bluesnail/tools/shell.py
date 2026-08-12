"""Cross-platform shell command tool with an allowlist from ``.agent``."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from bluesnail.agent.tools import ToolManager
from bluesnail.tools.filesystem import resolve_path, resolve_workspace_root

DEFAULT_TIMEOUT_SECONDS = 60
MAX_TIMEOUT_SECONDS = 300
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
CONFIG_RELATIVE_PATH = Path(".agent") / "shell_commands.json"

# Windows cmd.exe builtins that cannot be launched as standalone executables.
WINDOWS_BUILTINS = frozenset(
    {
        "assoc",
        "break",
        "call",
        "cd",
        "chdir",
        "cls",
        "color",
        "copy",
        "date",
        "del",
        "dir",
        "echo",
        "endlocal",
        "erase",
        "exit",
        "for",
        "ftype",
        "goto",
        "if",
        "md",
        "mkdir",
        "mklink",
        "move",
        "path",
        "pause",
        "popd",
        "prompt",
        "pushd",
        "rd",
        "rem",
        "ren",
        "rename",
        "rmdir",
        "set",
        "setlocal",
        "shift",
        "start",
        "time",
        "title",
        "type",
        "ver",
        "verify",
        "vol",
    }
)

# Characters that enable chaining / redirection / injection across shells.
_UNSAFE_META_CHARS = frozenset("&|;<>`\n\r")

RUN_COMMAND_PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": (
                "Command line to run. The first token must be in the allowlist "
                "configured at .agent/shell_commands.json. Examples: "
                "'git status', 'python -V', 'dir' (Windows), 'ls -la' (Linux)."
            ),
        },
        "working_directory": {
            "type": "string",
            "description": (
                "Optional working directory relative to the workspace "
                "(default: workspace root)"
            ),
        },
        "timeout": {
            "type": "number",
            "description": (
                f"Optional timeout in seconds "
                f"(default from config or {DEFAULT_TIMEOUT_SECONDS}, "
                f"max {MAX_TIMEOUT_SECONDS})"
            ),
        },
    },
    "required": ["command"],
}


def _is_windows() -> bool:
    return sys.platform == "win32"


def config_path(workspace_root: Path | None = None) -> Path:
    """Return the absolute path to the shell allowlist config."""
    root = resolve_workspace_root(workspace_root)
    return root / CONFIG_RELATIVE_PATH


def _normalize_command_name(name: str) -> str:
    """Normalize an executable name for allowlist comparison."""
    base = Path(name.strip()).name
    if not base:
        return ""
    if _is_windows():
        lowered = base.lower()
        for suffix in (".exe", ".cmd", ".bat", ".com"):
            if lowered.endswith(suffix):
                return lowered[: -len(suffix)]
        return lowered
    return base


def load_shell_config(workspace_root: Path | None = None) -> dict[str, Any]:
    """Load ``.agent/shell_commands.json`` from the workspace."""
    path = config_path(workspace_root)
    if not path.is_file():
        raise ValueError(
            f"Shell command allowlist not found: {CONFIG_RELATIVE_PATH.as_posix()}. "
            "Create this file under the workspace to enable run_command."
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON in {CONFIG_RELATIVE_PATH.as_posix()}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise ValueError(
            f"{CONFIG_RELATIVE_PATH.as_posix()} must contain a JSON object"
        )
    return data


def allowed_commands(config: dict[str, Any]) -> set[str]:
    """Return the platform-specific allowlist from config."""
    section = config.get("commands", config)
    if not isinstance(section, dict):
        raise ValueError(
            f"{CONFIG_RELATIVE_PATH.as_posix()}: 'commands' must be an object"
        )

    names: set[str] = set()
    for key in ("common", "windows" if _is_windows() else "linux"):
        items = section.get(key, [])
        if items is None:
            continue
        if not isinstance(items, list):
            raise ValueError(
                f"{CONFIG_RELATIVE_PATH.as_posix()}: commands.{key} must be a list"
            )
        for item in items:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(
                    f"{CONFIG_RELATIVE_PATH.as_posix()}: commands.{key} "
                    "entries must be non-empty strings"
                )
            names.add(_normalize_command_name(item))
    return {name for name in names if name}


def parse_command_line(command: str) -> list[str]:
    """Split a command line into argv using platform-appropriate rules."""
    raw = command.strip()
    if not raw:
        raise ValueError("command is required")
    try:
        argv = shlex.split(raw, posix=not _is_windows())
    except ValueError as exc:
        raise ValueError(f"Failed to parse command: {exc}") from exc
    if not argv:
        raise ValueError("command is required")
    return argv


def _reject_unsafe_tokens(argv: list[str]) -> None:
    """Reject tokens that enable shell chaining or control-character injection."""
    for token in argv:
        if "\0" in token:
            raise ValueError(
                "Null bytes are not allowed in command arguments "
                f"(found in {token!r})"
            )
        if any(ch in _UNSAFE_META_CHARS for ch in token):
            raise ValueError(
                "Shell metacharacters are not allowed in command arguments "
                f"(found in {token!r})"
            )


def _normalize_timeout(
    timeout: float | None,
    *,
    default: float,
) -> float:
    if timeout is None:
        value = float(default)
    else:
        value = float(timeout)
    if value <= 0:
        raise ValueError("timeout must be positive")
    return min(value, float(MAX_TIMEOUT_SECONDS))


def _truncate(text: str, max_bytes: int) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text, False
    truncated = encoded[:max_bytes].decode("utf-8", errors="ignore")
    return truncated, True


def _build_popen_args(argv: list[str]) -> list[str]:
    """Build the real process argv, wrapping Windows builtins with cmd.exe."""
    executable = _normalize_command_name(argv[0])
    if _is_windows() and executable in WINDOWS_BUILTINS:
        # /d disables AutoRun; /s preserves quoting semantics for /c.
        return ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(argv)]
    return argv


def run_command(
    command: str,
    working_directory: str = ".",
    timeout: float | None = None,
    *,
    workspace_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run an allowlisted command and return a structured result."""
    root = resolve_workspace_root(workspace_root)
    cfg = config if config is not None else load_shell_config(root)
    allowlist = allowed_commands(cfg)
    if not allowlist:
        raise ValueError(
            f"No commands are allowlisted for this platform in "
            f"{CONFIG_RELATIVE_PATH.as_posix()}"
        )

    argv = parse_command_line(command)

    exe_name = _normalize_command_name(argv[0])
    if exe_name not in allowlist:
        allowed = ", ".join(sorted(allowlist))
        raise ValueError(
            f"Command not allowed: {exe_name!r}. "
            f"Allowed on this platform: {allowed}"
        )

    _reject_unsafe_tokens(argv)

    default_timeout = float(cfg.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    max_output = int(cfg.get("max_output_bytes", DEFAULT_MAX_OUTPUT_BYTES))
    if max_output <= 0:
        raise ValueError("max_output_bytes must be positive")
    timeout_seconds = _normalize_timeout(timeout, default=default_timeout)

    cwd = resolve_path(root, working_directory)
    if not cwd.is_dir():
        raise ValueError(f"Not a directory: {working_directory}")

    popen_args = _build_popen_args(argv)
    try:
        completed = subprocess.run(
            popen_args,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            shell=False,
            env=os.environ.copy(),
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executable not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Command timed out after {timeout_seconds} seconds"
        ) from exc

    stdout, stdout_truncated = _truncate(completed.stdout or "", max_output)
    stderr, stderr_truncated = _truncate(completed.stderr or "", max_output)
    return {
        "command": command.strip(),
        "argv": argv,
        "cwd": str(cwd),
        "exit_code": int(completed.returncode),
        "stdout": stdout,
        "stderr": stderr,
        "stdout_truncated": stdout_truncated,
        "stderr_truncated": stderr_truncated,
    }


def register_shell_tools(
    manager: ToolManager,
    *,
    workspace_root: Path | None = None,
) -> None:
    """Register the cross-platform ``run_command`` tool."""
    root = resolve_workspace_root(workspace_root)

    @manager.tool(
        name="run_command",
        description=(
            "Execute an allowlisted shell command on the host OS (Windows or Linux). "
            "Only commands listed in .agent/shell_commands.json may run. "
            "Shell operators such as pipes, redirects, and chaining are rejected. "
            "Returns exit code, stdout, and stderr as JSON."
        ),
        parameters=RUN_COMMAND_PARAMETERS,
    )
    def run_command_tool(
        command: str,
        working_directory: str = ".",
        timeout: float | None = None,
    ) -> str:
        result = run_command(
            command=command,
            working_directory=working_directory,
            timeout=timeout,
            workspace_root=root,
        )
        return json.dumps(result, ensure_ascii=False)
