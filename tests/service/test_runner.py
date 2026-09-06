"""AgentService hook injection tests."""

from bluesnail.core.types import LLMResponse
from bluesnail.integration import Agent, MockLLMProvider
from bluesnail.scheduler.hooks import RunHooks
from bluesnail.service import AgentService, serialize_result


def test_service_run_injects_workflow_hooks() -> None:
    agent = Agent(llm=MockLLMProvider(responses=[LLMResponse(content="ok", finish_reason="stop")]))
    service = AgentService(agent)
    seen: list[str] = []

    def on_workflow(event) -> None:
        if event.phase == "after":
            seen.append(event.step_type)

    result = service.run("hello", on_workflow=on_workflow)
    assert result.answer == "ok"
    assert "llm" in seen
    assert "finish" in seen


def test_persistent_and_per_run_hooks_both_fire() -> None:
    agent = Agent(llm=MockLLMProvider(responses=[LLMResponse(content="ok", finish_reason="stop")]))
    service = AgentService(agent)
    persistent: list[str] = []
    per_run: list[str] = []
    service.add_hook(on_workflow=lambda event: persistent.append(event.phase))
    service.run("hello", hooks=RunHooks(on_workflow=lambda event: per_run.append(event.step_type)))
    assert persistent
    assert "llm" in per_run


def test_run_with_emitter_emits_stream_events() -> None:
    agent = Agent(llm=MockLLMProvider(responses=[LLMResponse(content="ok", finish_reason="stop")]))
    service = AgentService(agent)
    events: list[tuple[str, dict]] = []
    result = service.run_with_emitter("hello", lambda kind, data: events.append((kind, data)))
    kinds = [kind for kind, _ in events]
    assert kinds[0] == "workflow"
    assert "start" in kinds
    assert "step" in kinds
    assert kinds[-1] == "done"
    assert kinds.index("start") < kinds.index("step")
    assert events[-1][1]["answer"] == "ok"
    assert serialize_result(result)["answer"] == "ok"
