"""Basic tests for BlueSnail agent framework."""

from bluesnail.agent import (
    ACTIVATE_SKILL_NAME,
    RUN_SKILL_SCRIPT_NAME,
    Agent,
    ContextManager,
    MemoryProcessor,
    MockLLMProvider,
    Role,
    SkillManager,
    ToolManager,
)
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


def test_skill_activation():
    skills = create_default_skills()
    result = skills.run(
        ToolCall(
            id="call_1",
            name=ACTIVATE_SKILL_NAME,
            arguments={"name": "get-weather"},
        )
    )
    assert not result.is_error
    assert "scripts/get_weather.py" in result.content
    assert "run_skill_script" in result.content


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


def test_agent_run_with_skill(monkeypatch):
    skills = create_default_skills()

    class FakeCompleted:
        returncode = 0
        stdout = '{"city":"上海","temperature":"26C","weather":"clear sky"}'
        stderr = ""

    monkeypatch.setattr(
        "bluesnail.agent.skills.subprocess.run",
        lambda *args, **kwargs: FakeCompleted(),
    )

    llm = MockLLMProvider()
    llm.queue_tool_call(
        "call_1",
        ACTIVATE_SKILL_NAME,
        {"name": "get-weather"},
    )
    llm.queue_tool_call(
        "call_2",
        RUN_SKILL_SCRIPT_NAME,
        {
            "skill": "get-weather",
            "script": "scripts/get_weather.py",
            "arguments": ["--city", "上海"],
        },
        then_content="上海今天 26C。",
    )

    agent = Agent(llm=llm, skills=skills)
    result = agent.run("上海天气怎么样？")
    assert "26" in result.answer or "上海" in result.answer
    assert any(step.skill_results for step in result.steps)
    assert any(
        skill_result.name == RUN_SKILL_SCRIPT_NAME
        for step in result.steps
        for skill_result in step.skill_results
    )


def test_agent_unknown_tool_returns_error_to_llm():
    tools = ToolManager()

    @tools.tool(description="Echo input")
    def echo(text: str) -> str:
        return text

    llm = MockLLMProvider()
    llm.queue_tool_call("call_1", "missing_tool", {"text": "x"}, then_content="已处理。")

    agent = Agent(llm=llm, tools=tools)
    result = agent.run("test")
    assert result.answer == "已处理。"
    assert result.steps[0].tool_results
    assert result.steps[0].tool_results[0].is_error
    assert "Tool not found" in result.steps[0].tool_results[0].content


def test_agent_llm_failure_returns_message_instead_of_crashing():
    class FailingLLM:
        def chat(self, messages, tools=None):
            raise RuntimeError("内部错误")

    agent = Agent(llm=FailingLLM())
    result = agent.run("hello")
    assert "LLM 调用失败" in result.answer
    assert "内部错误" in result.answer
    assert result.stopped_reason == "llm_error"


def test_agent_direct_response():
    llm = MockLLMProvider(responses=[LLMResponse(content="done", finish_reason="stop")])
    agent = Agent(llm=llm)
    result = agent.run("hello")
    assert result.answer == "done"
    assert result.iterations == 1


def test_programmatic_callable_skill():
    skills = SkillManager()

    @skills.skill(description="Double a number")
    def double(value: int) -> int:
        return value * 2

    result = skills.run(ToolCall(id="c1", name="double", arguments={"value": 4}))
    assert result.content == "8"
