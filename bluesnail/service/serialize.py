"""Shared serialization for Agent results and stream events."""

from __future__ import annotations

from typing import Any

from bluesnail.core.types import AgentResult, AgentStep, Message, Role, WorkflowEvent


def serialize_message(message: Message) -> dict[str, Any]:
    return {
        "role": message.role.value,
        "content": message.content,
        "name": message.name,
        "tool_call_id": message.tool_call_id,
        "metadata": message.metadata,
        "timestamp": message.timestamp.isoformat(),
    }


def serialize_step(step: AgentStep) -> dict[str, Any]:
    return {
        "iteration": step.iteration,
        "content": step.response.content,
        "finish_reason": step.response.finish_reason,
        "tool_calls": [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in step.response.tool_calls
        ],
        "tool_results": [
            {
                "tool_call_id": item.tool_call_id,
                "name": item.name,
                "content": item.content,
                "is_error": item.is_error,
            }
            for item in step.tool_results
        ],
        "skill_results": [
            {
                "skill_call_id": item.skill_call_id,
                "name": item.name,
                "content": item.content,
                "is_error": item.is_error,
            }
            for item in step.skill_results
        ],
        "input_messages": [serialize_message(message) for message in step.input_messages],
    }


def serialize_result(result: AgentResult) -> dict[str, Any]:
    steps = [serialize_step(step) for step in result.steps]
    visible_messages = [
        serialize_message(message)
        for message in result.messages
        if message.role in {Role.USER, Role.ASSISTANT, Role.TOOL}
    ]
    return {
        "answer": result.answer,
        "iterations": result.iterations,
        "stopped_reason": result.stopped_reason,
        "steps": steps,
        "messages": visible_messages,
        "reasoning": {
            "run_context": result.run_context,
            "steps": steps,
            "iterations": result.iterations,
            "stopped_reason": result.stopped_reason,
        },
    }


def serialize_workflow_event(event: WorkflowEvent) -> dict[str, Any]:
    return event.to_dict()
