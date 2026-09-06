"""Scheduler unit tests."""

import pytest

from bluesnail.context import ContextManager
from bluesnail.core.exceptions import SchedulerError
from bluesnail.core.types import LLMResponse
from bluesnail.llm import MockLLMProvider
from bluesnail.memory import MemoryProcessor
from bluesnail.scheduler import Scheduler
from bluesnail.tools import ToolManager


def _scheduler(llm=None) -> Scheduler:
    return Scheduler(
        llm=llm or MockLLMProvider(responses=[LLMResponse(content="ok", finish_reason="stop")]),
        memory=MemoryProcessor(),
        tools=ToolManager(),
        context=ContextManager(),
    )


def test_empty_input_raises() -> None:
    with pytest.raises(SchedulerError):
        _scheduler().run("   ")


def test_scheduler_direct_answer() -> None:
    result = _scheduler().run("hello")
    assert result.answer == "ok"
    assert result.stopped_reason == "completed"


def test_workflow_and_step_hooks_fire() -> None:
    events: list[tuple[str, str, str | None]] = []
    steps: list[int] = []

    def on_workflow(event) -> None:
        events.append((event.phase, event.step_type, event.outcome))

    result = _scheduler().run("hello", on_workflow=on_workflow, on_step=lambda step: steps.append(step.iteration))
    assert result.answer == "ok"
    assert steps == [1]
    after_types = [step_type for phase, step_type, _ in events if phase == "after"]
    assert after_types[0] == "ingest_user"
    assert "llm" in after_types
    assert "finish" in after_types
    assert all(phase in {"before", "after"} for phase, _, _ in events)
    llm_after = next(item for item in events if item[0] == "after" and item[1] == "llm")
    assert llm_after[2] == "content"
