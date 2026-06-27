"""Tests for filesystem read/write tools."""

from pathlib import Path

import pytest

from bluesnail.agent.tools import ToolManager
from bluesnail.agent.types import ToolCall
from bluesnail.tools import create_default_tools
from bluesnail.tools.filesystem import register_filesystem_tools, resolve_path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    return root.resolve()


@pytest.fixture
def tools(workspace: Path) -> ToolManager:
    manager = ToolManager()
    register_filesystem_tools(manager, workspace_root=workspace)
    return manager


def test_create_default_tools_registers_filesystem_tools():
    manager = create_default_tools()
    names = {tool.name for tool in manager.registry.list_tools()}
    assert {"read_file", "write_file", "list_directory"}.issubset(names)


def test_write_and_read_file_round_trip(tools: ToolManager, workspace: Path):
    write_result = tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "notes/hello.txt", "content": "line 1\nline 2\nline 3"},
        )
    )
    assert not write_result.is_error
    assert "hello.txt" in write_result.content
    assert (workspace / "notes" / "hello.txt").is_file()

    read_result = tools.run(
        ToolCall(
            id="call_2",
            name="read_file",
            arguments={"path": "notes/hello.txt", "offset": 2, "limit": 1},
        )
    )
    assert not read_result.is_error
    assert read_result.content == "line 2"


def test_list_directory(tools: ToolManager):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "alpha.txt", "content": "a"},
        )
    )
    tools.run(
        ToolCall(
            id="call_2",
            name="write_file",
            arguments={"path": "nested/beta.txt", "content": "b"},
        )
    )

    result = tools.run(
        ToolCall(id="call_3", name="list_directory", arguments={"path": "."})
    )
    assert not result.is_error
    assert "[file] alpha.txt" in result.content
    assert "[dir] nested" in result.content


def test_path_traversal_is_rejected(workspace: Path):
    with pytest.raises(ValueError, match="escapes workspace"):
        resolve_path(workspace, "../outside.txt")


def test_read_missing_file_returns_error(tools: ToolManager):
    result = tools.run(
        ToolCall(id="call_1", name="read_file", arguments={"path": "missing.txt"})
    )
    assert result.is_error
    assert "Not a file" in result.content
