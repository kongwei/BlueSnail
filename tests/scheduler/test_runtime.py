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
