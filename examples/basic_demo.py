"""Basic usage demo for BlueSnail agent framework."""

from __future__ import annotations

from bluesnail.agent import (
    Agent,
    AgentConfig,
    ContextConfig,
    MockLLMProvider,
    SchedulerConfig,
)
from bluesnail.skills import create_default_skills


def main() -> None:
    skills = create_default_skills()

    llm = MockLLMProvider(default_content="Hello from BlueSnail!")
    llm.queue_tool_call(
        "call_demo_1",
        "get-weather",
        {"city": "Shanghai"},
        then_content="Shanghai is sunny today, 26C.",
    )

    agent = Agent(
        llm=llm,
        skills=skills,
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
    print("Skill steps:", sum(1 for step in result.steps if step.skill_results))


if __name__ == "__main__":
    main()
