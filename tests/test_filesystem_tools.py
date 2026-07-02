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
    assert {
        "read_file",
        "write_file",
        "list_directory",
        "delete_file",
        "delete_lines",
    }.issubset(names)


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


def test_delete_file_removes_file(tools: ToolManager, workspace: Path):
    target = workspace / "temp.txt"
    target.write_text("remove me", encoding="utf-8")

    result = tools.run(
        ToolCall(id="call_1", name="delete_file", arguments={"path": "temp.txt"})
    )
    assert not result.is_error
    assert "Deleted file" in result.content
    assert not target.exists()


def test_delete_file_missing_path_returns_error(tools: ToolManager):
    result = tools.run(
        ToolCall(id="call_1", name="delete_file", arguments={"path": "missing.txt"})
    )
    assert result.is_error
    assert "Path not found" in result.content


def test_delete_file_rejects_directory(tools: ToolManager, workspace: Path):
    (workspace / "folder").mkdir()

    result = tools.run(
        ToolCall(id="call_1", name="delete_file", arguments={"path": "folder"})
    )
    assert result.is_error
    assert "Not a file" in result.content


def test_delete_file_rejects_path_traversal(tools: ToolManager):
    result = tools.run(
        ToolCall(
            id="call_1",
            name="delete_file",
            arguments={"path": "../outside.txt"},
        )
    )
    assert result.is_error
    assert "escapes workspace" in result.content


def test_delete_lines_removes_single_line(tools: ToolManager, workspace: Path):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "doc.txt", "content": "keep\nremove\nkeep too"},
        )
    )

    result = tools.run(
        ToolCall(
            id="call_2",
            name="delete_lines",
            arguments={"path": "doc.txt", "start": 2},
        )
    )
    assert not result.is_error
    assert result.content == "Deleted line 2 from doc.txt"
    assert (workspace / "doc.txt").read_text(encoding="utf-8") == "keep\nkeep too"


def test_delete_lines_removes_inclusive_range(tools: ToolManager, workspace: Path):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "doc.txt", "content": "a\nb\nc\nd\ne"},
        )
    )

    result = tools.run(
        ToolCall(
            id="call_2",
            name="delete_lines",
            arguments={"path": "doc.txt", "start": 2, "end": 4},
        )
    )
    assert not result.is_error
    assert result.content == "Deleted lines 2-4 from doc.txt"
    assert (workspace / "doc.txt").read_text(encoding="utf-8") == "a\ne"


def test_delete_lines_all_lines_leaves_empty_file(tools: ToolManager, workspace: Path):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "doc.txt", "content": "only line"},
        )
    )

    result = tools.run(
        ToolCall(
            id="call_2",
            name="delete_lines",
            arguments={"path": "doc.txt", "start": 1, "end": 1},
        )
    )
    assert not result.is_error
    assert (workspace / "doc.txt").read_text(encoding="utf-8") == ""


def test_delete_lines_start_out_of_range_returns_error(tools: ToolManager):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "doc.txt", "content": "one\ntwo"},
        )
    )

    result = tools.run(
        ToolCall(
            id="call_2",
            name="delete_lines",
            arguments={"path": "doc.txt", "start": 3},
        )
    )
    assert result.is_error
    assert "out of range" in result.content


def test_delete_lines_end_less_than_start_returns_error(tools: ToolManager):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "doc.txt", "content": "one\ntwo\nthree"},
        )
    )

    result = tools.run(
        ToolCall(
            id="call_2",
            name="delete_lines",
            arguments={"path": "doc.txt", "start": 3, "end": 2},
        )
    )
    assert result.is_error
    assert "end must be >= start" in result.content


def test_delete_lines_clamps_end_beyond_file_length(tools: ToolManager, workspace: Path):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "doc.txt", "content": "a\nb\nc"},
        )
    )

    result = tools.run(
        ToolCall(
            id="call_2",
            name="delete_lines",
            arguments={"path": "doc.txt", "start": 2, "end": 99},
        )
    )
    assert not result.is_error
    assert result.content == "Deleted lines 2-3 from doc.txt"
    assert (workspace / "doc.txt").read_text(encoding="utf-8") == "a"


def test_delete_lines_empty_file_returns_error(tools: ToolManager):
    tools.run(
        ToolCall(
            id="call_1",
            name="write_file",
            arguments={"path": "empty.txt", "content": ""},
        )
    )

    result = tools.run(
        ToolCall(
            id="call_2",
            name="delete_lines",
            arguments={"path": "empty.txt", "start": 1},
        )
    )
    assert result.is_error
    assert "out of range" in result.content
