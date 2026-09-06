"""Core contract tests."""

from bluesnail.core.schema import build_parameters_schema, stringify_result
from bluesnail.core.types import Message, Role


def test_message_to_dict_includes_optional_fields() -> None:
    message = Message(role=Role.TOOL, content="ok", name="echo", tool_call_id="c1")
    payload = message.to_dict()
    assert payload["role"] == "tool"
    assert payload["name"] == "echo"
    assert payload["tool_call_id"] == "c1"


def test_stringify_result_json() -> None:
    assert stringify_result({"a": 1}) == '{"a": 1}'
    assert stringify_result("plain") == "plain"


def test_build_parameters_schema_marks_required() -> None:
    def add(a: int, b: int = 0) -> int:
        return a + b

    schema = build_parameters_schema(add)
    assert schema["required"] == ["a"]
    assert schema["properties"]["a"]["type"] == "integer"
