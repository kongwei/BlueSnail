"""Basic usage demo for BlueSnail agent framework."""

from __future__ import annotations

from bluesnail.agent import (
    Agent,
    AgentConfig,
    ContextConfig,
    MockLLMProvider,
    SchedulerConfig,
    ToolManager,
)


def main() -> None:
    tools = ToolManager()

    @tools.tool(description="Return current weather for a city")
    def get_weather(city: str) -> dict[str, str]:
        return {"city": city, "weather": "sunny", "temperature": "26C"}

    llm = MockLLMProvider(default_content="Hello from BlueSnail!")
    llm.queue_tool_call(
        "call_demo_1",
        "get_weather",
        {"city": "Shanghai"},
        then_content="Shanghai is sunny today, 26C.",
    )

    agent = Agent(
        llm=llm,
        tools=tools,
        config=AgentConfig(
            system_prompt="You are BlueSnail, a helpful assistant.",
            scheduler=SchedulerConfig(max_iterations=5, auto_recall=True),
            context=ContextConfig(max_tokens=4096),
        ),
    )

    agent.remember("user_pref", "User prefers concise answers in Chinese.")

    result = agent.run("上海今天天气怎么样？", session_id="demo")
    print("Answer:", result.answer)
    print("Iterations:", result.iterations)
    print("Stopped:", result.stopped_reason)
    print("Tool steps:", sum(1 for step in result.steps if step.tool_results))


if __name__ == "__main__":
    main()
