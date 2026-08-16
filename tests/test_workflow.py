"""Tests for user-defined agent workflows."""

from bluesnail.agent import (
    Agent,
    AgentConfig,
    MockLLMProvider,
    ToolManager,
    Workflow,
    WorkflowBundle,
    WorkflowStep,
    default_direct_workflow,
    default_react_workflow,
)
from bluesnail.agent.exceptions import WorkflowError
from bluesnail.agent.types import LLMResponse
from bluesnail.agent.workflow import validate_workflow


def test_default_react_workflow_is_valid() -> None:
    workflow = default_react_workflow()
    validate_workflow(workflow)
    assert workflow.entry == "ingest"
    assert any(step.type == "execute_calls" for step in workflow.steps)


def test_invalid_workflow_unknown_step_type() -> None:
    workflow = Workflow(
        id="bad",
        name="bad",
        entry="start",
        steps=[
            WorkflowStep(id="start", type="not_a_type", next="finish"),
            WorkflowStep(id="finish", type="finish"),
        ],
    )
    try:
        validate_workflow(workflow)
    except WorkflowError as exc:
        assert "Unknown step type" in str(exc)
    else:
        raise AssertionError("expected WorkflowError")


def test_direct_workflow_skips_tools() -> None:
    tools = ToolManager()

    @tools.tool(description="Echo input")
    def echo(text: str) -> str:
        return text

    llm = MockLLMProvider()
    llm.queue_tool_call("call_1", "echo", {"text": "blue"}, then_content="should not run")
    agent = Agent(
        llm=llm,
        tools=tools,
        config=AgentConfig(workflow=default_direct_workflow()),
    )
    result = agent.run("say blue")
    assert result.run_context["workflow_id"] == "direct"
    assert not any(step.tool_results for step in result.steps)


def test_custom_workflow_injects_text() -> None:
    llm = MockLLMProvider(responses=[LLMResponse(content="ok", finish_reason="stop")])
    workflow = Workflow.from_dict(
        {
            "id": "custom",
            "name": "custom",
            "entry": "ingest",
            "max_iterations": 3,
            "steps": [
                {"id": "ingest", "type": "ingest_user", "next": "note"},
                {
                    "id": "note",
                    "type": "inject_text",
                    "next": "think",
                    "params": {"text": "Always mention snails."},
                },
                {
                    "id": "think",
                    "type": "llm",
                    "params": {"use_tools": False},
                    "on": {"content": "finish", "empty": "finish", "error": "finish"},
                },
                {"id": "finish", "type": "finish"},
            ],
        }
    )
    agent = Agent(llm=llm, config=AgentConfig(workflow=workflow))
    result = agent.run("hello")
    assert result.answer == "ok"
    assert "Always mention snails." in result.run_context["extra_context"]
    trace_ids = [item["id"] for item in result.run_context["workflow_trace"]]
    assert trace_ids == ["ingest", "note", "think", "finish"]


def test_disabled_step_is_skipped() -> None:
    llm = MockLLMProvider(responses=[LLMResponse(content="done", finish_reason="stop")])
    workflow = default_react_workflow()
    for step in workflow.steps:
        if step.type == "inject_skills":
            step.enabled = False
    agent = Agent(llm=llm, config=AgentConfig(workflow=workflow))
    result = agent.run("hello")
    assert result.answer == "done"
    assert result.run_context["skill_context"] == ""


def test_bundle_rejects_missing_active() -> None:
    try:
        WorkflowBundle.from_dict(
            {
                "active_id": "missing",
                "workflows": [default_direct_workflow().to_dict()],
            }
        )
    except WorkflowError as exc:
        assert "Active workflow not found" in str(exc)
    else:
        raise AssertionError("expected WorkflowError")


def test_bundle_resolve_by_name() -> None:
    bundle = WorkflowBundle.from_dict(
        {
            "active_id": "react",
            "workflows": [
                default_react_workflow().to_dict(),
                default_direct_workflow().to_dict(),
            ],
        }
    )
    assert bundle.resolve("直接回答").id == "direct"
    assert bundle.resolve("react").id == "react"


def test_agent_still_runs_tools_on_default_workflow() -> None:
    tools = ToolManager()

    @tools.tool(description="Echo input")
    def echo(text: str) -> str:
        return text

    llm = MockLLMProvider()
    llm.queue_tool_call("call_1", "echo", {"text": "blue"}, then_content="blue")
    agent = Agent(llm=llm, tools=tools)
    result = agent.run("say blue")
    assert result.answer == "blue"
    assert result.iterations == 2
    assert result.run_context["workflow_id"] == "react"
