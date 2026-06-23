"""Skill management module."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bluesnail.agent.exceptions import SkillNotFoundError
from bluesnail.agent.skill_loader import AgentSkillPackage, discover_skill_packages
from bluesnail.agent.tools import _build_parameters_schema, _stringify_result
from bluesnail.agent.types import SkillResult, ToolCall

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


@dataclass(slots=True)
class SkillDefinition:
    name: str
    description: str
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    skill_dir: Path | None = None
    disable_model_invocation: bool = True

    @classmethod
    def from_package(cls, package: AgentSkillPackage) -> SkillDefinition:
        return cls(
            name=package.name,
            description=package.description,
            handler=package.handler,
            parameters=package.parameters,
            instructions=package.instructions,
            skill_dir=package.skill_dir,
            disable_model_invocation=package.disable_model_invocation,
        )

    def to_openai_schema(self) -> dict[str, Any]:
        description = f"[Skill:{self.name}] {self.description}"
        if self.instructions:
            preview = self.instructions.strip()
            if len(preview) > 600:
                preview = preview[:600] + "..."
            description = f"{description}\n\n{preview}"
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": description,
                "parameters": self.parameters
                or {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "instructions": self.instructions,
            "parameters": self.parameters,
            "skill_dir": str(self.skill_dir) if self.skill_dir else None,
            "disable_model_invocation": self.disable_model_invocation,
        }


class SkillRegistry:
    """Register and lookup skills by name."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Skill already registered: {skill.name}")
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> SkillDefinition:
        try:
            return self._skills[name]
        except KeyError as exc:
            raise SkillNotFoundError(f"Skill not found: {name}") from exc

    def has(self, name: str) -> bool:
        return name in self._skills

    def list_skills(self) -> list[SkillDefinition]:
        return list(self._skills.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [skill.to_openai_schema() for skill in self._skills.values()]


class SkillExecutor:
    """Execute skill invocations."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def execute(self, call: ToolCall) -> SkillResult:
        skill = self.registry.get(call.name)
        try:
            result = skill.handler(**call.arguments)
            content = _stringify_result(result)
            return SkillResult(
                skill_call_id=call.id,
                name=call.name,
                content=content,
            )
        except SkillNotFoundError:
            raise
        except Exception as exc:
            return SkillResult(
                skill_call_id=call.id,
                name=call.name,
                content=str(exc),
                is_error=True,
            )


class SkillManager:
    """Facade for registering and invoking agent skills."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.registry = registry or SkillRegistry()
        self.executor = SkillExecutor(self.registry)

    def skill(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        instructions: str = "",
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for programmatic skill registration."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            skill_name = name or func.__name__
            skill_description = description or (func.__doc__ or "").strip() or skill_name
            skill_parameters = parameters or _build_parameters_schema(func)
            self.registry.register(
                SkillDefinition(
                    name=skill_name,
                    description=skill_description,
                    handler=func,
                    parameters=skill_parameters,
                    instructions=instructions,
                )
            )
            return func

        return decorator

    def register(self, skill: SkillDefinition) -> None:
        self.registry.register(skill)

    def register_package(self, package: AgentSkillPackage) -> None:
        self.registry.register(SkillDefinition.from_package(package))

    def load_from_directory(self, directory: Path) -> list[SkillDefinition]:
        loaded: list[SkillDefinition] = []
        for package in discover_skill_packages(directory):
            definition = SkillDefinition.from_package(package)
            self.registry.register(definition)
            loaded.append(definition)
        return loaded

    def load_from_directories(self, directories: list[Path]) -> list[SkillDefinition]:
        loaded: list[SkillDefinition] = []
        for directory in directories:
            loaded.extend(self.load_from_directory(directory))
        return loaded

    def has(self, name: str) -> bool:
        return self.registry.has(name)

    def run(self, call: ToolCall) -> SkillResult:
        return self.executor.execute(call)

    def run_many(self, calls: list[ToolCall]) -> list[SkillResult]:
        return [self.run(call) for call in calls]

    def schemas(self) -> list[dict[str, Any]]:
        return self.registry.schemas()

    def list_skills(self) -> list[SkillDefinition]:
        return self.registry.list_skills()

    def build_context(self) -> str:
        skills = self.list_skills()
        if not skills:
            return ""
        lines = [f"- {skill.name}: {skill.description}" for skill in skills]
        return "Available skills:\n" + "\n".join(lines)
