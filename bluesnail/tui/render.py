"""Format Agent stream events for TUI panels."""

from __future__ import annotations

from typing import Any


def format_chat_line(role: str, content: str) -> str:
    label = {
        "user": "You",
        "assistant": "Agent",
        "tool": "Tool",
        "system": "System",
        "status": "Status",
        "error": "Error",
    }.get(role, role)
    text = content.strip() or "(empty)"
    return f"{label}: {text}"


def format_workflow_event(data: dict[str, Any]) -> str:
    phase = data.get("phase", "?")
    step_id = data.get("step_id", "?")
    step_type = data.get("step_type", "?")
    sequence = data.get("sequence", "?")
    outcome = data.get("outcome")
    line = f"[{sequence}] {phase} {step_id} ({step_type})"
    if outcome:
        line += f" -> {outcome}"
    payload = data.get("payload") or {}
    llm = payload.get("llm") or {}
    if phase == "after" and step_type == "llm":
        tool_names = [call.get("name") for call in llm.get("tool_calls") or []]
        content = (llm.get("content") or "").strip()
        if tool_names:
            line += f" tools={','.join(tool_names)}"
        elif content:
            line += f" {_clip(content, 80)}"
    if phase == "after" and step_type == "execute_calls":
        tools = [item.get("name") for item in llm.get("tool_results") or []]
        skills = [item.get("name") for item in llm.get("skill_results") or []]
        names = tools + skills
        if names:
            line += f" ran={','.join(names)}"
    if phase == "after" and step_type == "recall_memory":
        recall = (payload.get("recall_context") or "").strip()
        if recall:
            line += f" {_clip(recall, 60)}"
    return line


def format_step_event(data: dict[str, Any]) -> str:
    iteration = data.get("iteration", "?")
    tool_calls = data.get("tool_calls") or []
    tool_results = data.get("tool_results") or []
    skill_results = data.get("skill_results") or []
    content = (data.get("content") or "").strip()
    parts = [f"LLM step #{iteration}"]
    if tool_calls and not tool_results and not skill_results:
        names = ", ".join(call.get("name", "?") for call in tool_calls)
        parts.append(f"call {names}")
    if tool_results or skill_results:
        names = [item.get("name", "?") for item in tool_results + skill_results]
        parts.append(f"results {', '.join(names)}")
    if content:
        parts.append(_clip(content, 80))
    return " · ".join(parts)


def format_start_event(data: dict[str, Any]) -> str:
    ctx = data.get("run_context") or {}
    name = ctx.get("workflow_name") or ctx.get("workflow_id") or "workflow"
    return f"Run start · {name}"


def format_done_event(data: dict[str, Any]) -> str:
    iterations = data.get("iterations", "?")
    reason = data.get("stopped_reason", "?")
    return f"Done · {iterations} iterations · {reason}"


def format_stream_event(event_type: str, data: dict[str, Any]) -> str | None:
    if event_type == "start":
        return format_start_event(data)
    if event_type == "workflow":
        return format_workflow_event(data)
    if event_type == "step":
        return format_step_event(data)
    if event_type == "done":
        return format_done_event(data)
    if event_type == "error":
        return f"Error: {data.get('detail') or data}"
    return None


def assistant_content_from_done(data: dict[str, Any]) -> str:
    return str(data.get("answer") or "").strip()


def _clip(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"
