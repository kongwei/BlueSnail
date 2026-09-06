"""Shared JSON-schema helpers used by tools and skills."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from typing import Any, get_type_hints


def stringify_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except TypeError:
        return str(result)


def build_parameters_schema(func: Callable[..., Any]) -> dict[str, Any]:
    signature = inspect.signature(func)
    hints = get_type_hints(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    for param_name, param in signature.parameters.items():
        if param_name in {"self", "cls"}:
            continue
        param_type = hints.get(param_name, Any)
        properties[param_name] = {
            "type": _python_type_to_json(param_type),
            "description": param_name,
        }
        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    return {"type": "object", "properties": properties, "required": required}


def _python_type_to_json(type_hint: Any) -> str:
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    origin = getattr(type_hint, "__origin__", None)
    if origin is list:
        return "array"
    if origin is dict:
        return "object"
    return mapping.get(type_hint, "string")
