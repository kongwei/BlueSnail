"""Basic tests for BlueSnail agent framework."""

import importlib.util
from pathlib import Path

from bluesnail.agent import (
    Agent,
    ContextManager,
    MemoryProcessor,
    MockLLMProvider,
    Role,
    SkillManager,
    ToolManager,
)
from bluesnail.agent.skill_loader import load_skill_package
from bluesnail.agent.types import LLMResponse, Message, ToolCall
from bluesnail.skills import create_default_skills


def test_memory_recall():
    memory = MemoryProcessor()
    memory.store.remember("python", "Python 3.12 supports better typing.")
    hits = memory.store.recall("python typing")
    assert hits
    assert hits[0].key == "python"


def test_context_trimming():
    context = ContextManager()
    messages = [
        Message(role=Role.USER, content="hello"),
        Message(role=Role.ASSISTANT, content="hi"),
    ]
    window = context.build(system_prompt="system", messages=messages)
    llm_messages = context.to_llm_messages(window)
    assert llm_messages[0].role == Role.SYSTEM
    assert len(llm_messages) >= 2


def test_tool_execution():
    tools = ToolManager()

    @tools.tool(description="Add two numbers")
    def add(a: int, b: int) -> int:
        return a + b

    result = tools.run(
        ToolCall(id="call_1", name="add", arguments={"a": 2, "b": 3})
    )
    assert result.content == "5"
    assert not result.is_error


def test_skill_execution(monkeypatch):
    handler_path = (
        Path(__file__).resolve().parents[1]
        / "bluesnail"
        / "skills"
        / "get-weather"
        / "scripts"
        / "handler.py"
    )
    spec = importlib.util.spec_from_file_location("get_weather_handler_agent_test", handler_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "fetch_weather",
        lambda city: {
            "city": city,
            "country": "中国",
            "weather": "clear sky",
            "weather_code": 0,
            "temperature": "26C",
            "humidity": "60%",
            "wind_speed": "10 km/h",
            "source": "open-meteo.com",
        },
    )

    skills = SkillManager()
    package = load_skill_package(handler_path.parents[1])
    skills.register_package(package)
    skills.registry.get("get-weather").handler = module.run

    result = skills.run(
        ToolCall(id="call_1", name="get-weather", arguments={"city": "上海"})
    )
    assert "上海" in result.content
    assert not result.is_error


def test_agent_run_with_tool():
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


def test_agent_run_with_skill():
    skills = create_default_skills()
    llm = MockLLMProvider()
    llm.queue_tool_call(
        "call_1",
        "get-weather",
        {"city": "上海"},
        then_content="上海今天 26C。",
    )

    agent = Agent(llm=llm, skills=skills)
    result = agent.run("上海天气怎么样？")
    assert "26" in result.answer or "上海" in result.answer
    assert any(step.skill_results for step in result.steps)


def test_agent_direct_response():
    llm = MockLLMProvider(responses=[LLMResponse(content="done", finish_reason="stop")])
    agent = Agent(llm=llm)
    result = agent.run("hello")
    assert result.answer == "done"
    assert result.iterations == 1
