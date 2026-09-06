"""Tool manager unit tests."""

from bluesnail.core.types import ToolCall
from bluesnail.tools import ToolManager


def test_tool_execution() -> None:
    tools = ToolManager()

    @tools.tool(description="Add two numbers")
    def add(a: int, b: int) -> int:
        return a + b

    result = tools.run(ToolCall(id="call_1", name="add", arguments={"a": 2, "b": 3}))
    assert result.content == "5"
    assert not result.is_error


def test_missing_tool_is_error() -> None:
    tools = ToolManager()
    result = tools.run(ToolCall(id="call_1", name="missing", arguments={}))
    assert result.is_error
    assert "Tool not found" in result.content
