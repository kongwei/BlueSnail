"""Basic tests for BlueSnail agent framework."""

from bluesnail.agent import (
    Agent,
    ContextManager,
    MemoryProcessor,
    MockLLMProvider,
    Role,
    ToolManager,
)
from bluesnail.agent.types import LLMResponse, Message, ToolCall


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


def test_agent_direct_response():
    llm = MockLLMProvider(responses=[LLMResponse(content="done", finish_reason="stop")])
    agent = Agent(llm=llm)
    result = agent.run("hello")
    assert result.answer == "done"
    assert result.iterations == 1
