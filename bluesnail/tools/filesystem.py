"""Filesystem read/write tools scoped to a workspace root."""

from __future__ import annotations

import os
from pathlib import Path

from bluesnail.agent.tools import ToolManager

MAX_READ_BYTES = 1_048_576
MAX_WRITE_BYTES = 1_048_576

READ_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path to the file within the workspace",
        },
        "offset": {
            "type": "integer",
            "description": "1-based line number to start reading from",
        },
        "limit": {
            "type": "integer",
            "description": "Maximum number of lines to read (0 means read to end)",
        },
    },
    "required": ["path"],
}

WRITE_FILE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path to the file within the workspace",
        },
        "content": {
            "type": "string",
            "description": "UTF-8 text content to write",
        },
    },
    "required": ["path", "content"],
}

LIST_DIRECTORY_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Relative path to the directory within the workspace",
        },
    },
    "required": [],
}


def resolve_workspace_root(workspace_root: Path | None = None) -> Path:
    if workspace_root is not None:
        return workspace_root.resolve()
    env_root = os.getenv("BLUESNAIL_WORKSPACE", "").strip()
    if env_root:
        return Path(env_root).resolve()
    return Path.cwd().resolve()


def resolve_path(root: Path, user_path: str) -> Path:
    normalized = user_path.strip().replace("\\", "/")
    if not normalized or normalized == ".":
        return root

    candidate = Path(normalized)
    if candidate.is_absolute():
        resolved = candidate.resolve()
    else:
        resolved = (root / candidate).resolve()

    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path escapes workspace: {user_path}") from exc
    return resolved


def register_filesystem_tools(
    manager: ToolManager,
    *,
    workspace_root: Path | None = None,
) -> None:
    """Register read/write/list tools constrained to a workspace root."""
    root = resolve_workspace_root(workspace_root)

    @manager.tool(
        name="read_file",
        description="Read a UTF-8 text file from the workspace.",
        parameters=READ_FILE_PARAMETERS,
    )
    def read_file(path: str, offset: int = 1, limit: int = 0) -> str:
        resolved = resolve_path(root, path)
        if not resolved.is_file():
            raise ValueError(f"Not a file: {path}")

        size = resolved.stat().st_size
        if size > MAX_READ_BYTES:
            raise ValueError(
                f"File too large ({size} bytes, max {MAX_READ_BYTES})"
            )

        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"File is not valid UTF-8 text: {path}") from exc

        lines = text.splitlines()
        start = max(offset - 1, 0)
        if limit > 0:
            selected = lines[start : start + limit]
        else:
            selected = lines[start:]
        return "\n".join(selected)

    @manager.tool(
        name="write_file",
        description="Write UTF-8 text to a file in the workspace. Creates parent directories if needed.",
        parameters=WRITE_FILE_PARAMETERS,
    )
    def write_file(path: str, content: str) -> str:
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_WRITE_BYTES:
            raise ValueError(
                f"Content too large ({len(encoded)} bytes, max {MAX_WRITE_BYTES})"
            )

        resolved = resolve_path(root, path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {path}"

    @manager.tool(
        name="list_directory",
        description="List files and directories in a workspace directory.",
        parameters=LIST_DIRECTORY_PARAMETERS,
    )
    def list_directory(path: str = ".") -> str:
        resolved = resolve_path(root, path)
        if not resolved.is_dir():
            raise ValueError(f"Not a directory: {path}")

        entries = sorted(resolved.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        lines = []
        for entry in entries:
            kind = "dir" if entry.is_dir() else "file"
            lines.append(f"[{kind}] {entry.name}")
        return "\n".join(lines) if lines else "(empty directory)"
