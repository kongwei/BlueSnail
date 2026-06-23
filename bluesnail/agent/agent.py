"""High-level Agent facade."""

from __future__ import annotations

from dataclasses import dataclass, field

from bluesnail.agent.context import ContextConfig, ContextManager
from bluesnail.agent.llm import LLMProvider
from bluesnail.agent.memory import InMemoryStore, MemoryProcessor
from bluesnail.agent.scheduler import Scheduler, SchedulerConfig
from bluesnail.agent.skills import SkillDefinition, SkillManager
from bluesnail.agent.tools import ToolDefinition, ToolManager
from bluesnail.agent.types import AgentResult


@dataclass(slots=True)
class AgentConfig:
    system_prompt: str = "You are a helpful AI assistant."
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    context: ContextConfig = field(default_factory=ContextConfig)


class Agent:
    """Main entry point that wires all modules together."""

    def __init__(
        self,
        llm: LLMProvider,
        *,
        config: AgentConfig | None = None,
        memory: MemoryProcessor | None = None,
        tools: ToolManager | None = None,
        skills: SkillManager | None = None,
        context: ContextManager | None = None,
    ) -> None:
        self.config = config or AgentConfig()
        self.memory = memory or MemoryProcessor(InMemoryStore())
        self.tools = tools or ToolManager()
        self.skills = skills or SkillManager()
        self.context = context or ContextManager(self.config.context)
        self.scheduler = Scheduler(
            llm=llm,
            memory=self.memory,
            tools=self.tools,
            skills=self.skills,
            context=self.context,
            config=self.config.scheduler,
        )

    def run(
        self,
        user_input: str,
        *,
        session_id: str | None = None,
        extra_context: str = "",
    ) -> AgentResult:
        return self.scheduler.run(
            user_input,
            system_prompt=self.config.system_prompt,
            session_id=session_id,
            extra_context=extra_context,
        )

    def remember(self, key: str, content: str, metadata: dict | None = None) -> None:
        self.memory.store.remember(key, content, metadata)

    def register_tool(self, tool: ToolDefinition) -> None:
        self.tools.register(tool)

    def register_skill(self, skill: SkillDefinition) -> None:
        self.skills.register(skill)

    def clear_memory(self) -> None:
        self.memory.store.clear()

    def clear_conversation(self) -> None:
        self.memory.store.clear_messages()
