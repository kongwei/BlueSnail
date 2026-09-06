"""Tool management module."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bluesnail.core.exceptions import ToolNotFoundError
from bluesnail.core.schema import build_parameters_schema, stringify_result
from bluesnail.core.types import ToolCall, ToolResult


@dataclass(slots=True)
class ToolDefinition:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
                or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }


class ToolRegistry:
    """Register and lookup tools by name."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> ToolDefinition:
        try:
            return self._tools[name]
        except KeyError as exc:
            raise ToolNotFoundError(f"Tool not found: {name}") from exc

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]


class ToolExecutor:
    """Execute tool calls with validation and error handling."""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, tool_call: ToolCall) -> ToolResult:
        try:
            tool = self.registry.get(tool_call.name)
            result = tool.handler(**tool_call.arguments)
            content = stringify_result(result)
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=content,
            )
        except ToolNotFoundError as exc:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=str(exc),
                is_error=True,
            )
        except TypeError as exc:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Invalid tool arguments: {exc}",
                is_error=True,
            )
        except Exception as exc:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=str(exc),
                is_error=True,
            )

    def execute_batch(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        return [self.execute(call) for call in tool_calls]


class ToolManager:
    """Facade combining registry and executor."""

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self.executor = ToolExecutor(self.registry)

    def tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for registering a function as a tool."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            tool_name = name or func.__name__
            tool_description = description or (func.__doc__ or "").strip() or tool_name
            tool_parameters = parameters or build_parameters_schema(func)
            self.registry.register(
                ToolDefinition(
                    name=tool_name,
                    description=tool_description,
                    handler=func,
                    parameters=tool_parameters,
                )
            )
            return func

        return decorator

    def register(self, tool: ToolDefinition) -> None:
        self.registry.register(tool)

    def run(self, tool_call: ToolCall) -> ToolResult:
        return self.executor.execute(tool_call)

    def run_many(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        return self.executor.execute_batch(tool_calls)

    def schemas(self) -> list[dict[str, Any]]:
        return self.registry.schemas()
