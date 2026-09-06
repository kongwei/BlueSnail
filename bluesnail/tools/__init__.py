"""Tools module: registry, executor, and built-in tool pack."""

from __future__ import annotations

from pathlib import Path

from bluesnail.tools.bench import register_bench_tools
from bluesnail.tools.filesystem import register_filesystem_tools
from bluesnail.tools.http import register_http_tools
from bluesnail.tools.manager import ToolDefinition, ToolManager, ToolRegistry
from bluesnail.tools.shell import register_shell_tools

__all__ = [
    "ToolDefinition",
    "ToolManager",
    "ToolRegistry",
    "create_default_tools",
]


def create_default_tools(workspace_root: Path | None = None) -> ToolManager:
    """Create the default built-in tool set."""
    manager = ToolManager()
    register_filesystem_tools(manager, workspace_root=workspace_root)
    register_http_tools(manager)
    register_shell_tools(manager, workspace_root=workspace_root)
    register_bench_tools(manager)
    return manager
