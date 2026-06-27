"""Built-in Agent tools for BlueSnail."""

from __future__ import annotations

from pathlib import Path

from bluesnail.agent.tools import ToolManager
from bluesnail.tools.filesystem import register_filesystem_tools

__all__ = ["create_default_tools"]


def create_default_tools(workspace_root: Path | None = None) -> ToolManager:
    """Create the default built-in tool set."""
    manager = ToolManager()
    register_filesystem_tools(manager, workspace_root=workspace_root)
    return manager
