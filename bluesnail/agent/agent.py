"""High-level Agent facade."""
from __future__ import annotations
from dataclasses import dataclass, field
import os

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
        # Read PROJECT.md if it exists and merge with system prompt
        project_path = ".agent/PROJECT.md"
        if os.path.exists(project_path):
            with open(project_path, "r", encoding="utf-8") as f:
                project_content = f.read().strip()
            
            # If config is provided and has a system_prompt, use it as base
            # Otherwise use default
            base_prompt = config.system_prompt if config and config.system_prompt else "You are a helpful AI assistant."
            
            # Combine project content with base prompt
            if project_content:
                combined_prompt = f"{base_prompt}\n\n---\n\nProject Background:\n{project_content}"
            else:
                combined_prompt = base_prompt
            
            # Update config with combined prompt
            if config:
                config.system_prompt = combined_prompt
            else:
                config = AgentConfig(system_prompt=combined_prompt)
        
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