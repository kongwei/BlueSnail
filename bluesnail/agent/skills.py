"""Skill management with Agent Skills progressive disclosure."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bluesnail.agent.exceptions import SkillNotFoundError
from bluesnail.agent.skill_loader import (
    AgentSkillPackage,
    discover_skill_packages,
    format_available_skills_xml,
    format_skill_activation,
)
from bluesnail.agent.tools import _build_parameters_schema, _stringify_result
from bluesnail.agent.types import SkillResult, ToolCall

BUILTIN_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
ACTIVATE_SKILL_NAME = "activate_skill"
RUN_SKILL_SCRIPT_NAME = "run_skill_script"

_SKILL_TOOL_NAMES = frozenset({ACTIVATE_SKILL_NAME, RUN_SKILL_SCRIPT_NAME})

_SKILL_BEHAVIOR = """The following skills provide specialized instructions for specific tasks.
When a task matches a skill's description:
1. Call activate_skill with the skill name to load full instructions.
2. Follow those instructions immediately — if they reference bundled scripts,
   call run_skill_script to execute them (cwd is the skill directory).
3. Only after completing the skill workflow, answer the user.

Do not stop after activate_skill alone. Activation loads instructions; it does
not perform the skill's work."""

_DEFAULT_SCRIPT_TIMEOUT = 60
_MAX_SCRIPT_TIMEOUT = 300
_MAX_SCRIPT_OUTPUT_BYTES = 1_048_576


@dataclass(slots=True)
class SkillDefinition:
    name: str
    description: str
    handler: Callable[..., Any] | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    skill_dir: Path | None = None
    location: Path | None = None
    disable_model_invocation: bool = False
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: str | None = None

    @classmethod
    def from_package(cls, package: AgentSkillPackage) -> SkillDefinition:
        return cls(
            name=package.name,
            description=package.description,
            handler=None,
            parameters={},
            instructions=package.instructions,
            skill_dir=package.skill_dir,
            location=package.location,
            disable_model_invocation=package.disable_model_invocation,
            license=package.license,
            compatibility=package.compatibility,
            metadata=dict(package.metadata),
            allowed_tools=package.allowed_tools,
        )

    @property
    def is_package(self) -> bool:
        return self.skill_dir is not None and self.handler is None

    def to_openai_schema(self) -> dict[str, Any]:
        """Schema for programmatic (callable) skills only."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"[Skill:{self.name}] {self.description}",
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
            "location": str(self.location) if self.location else None,
            "disable_model_invocation": self.disable_model_invocation,
            "license": self.license,
            "compatibility": self.compatibility,
            "metadata": self.metadata,
            "allowed_tools": self.allowed_tools,
            "callable": self.handler is not None,
        }


class SkillRegistry:
    """Register and lookup skills by name."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def register(self, skill: SkillDefinition, *, replace: bool = False) -> None:
        if skill.name in self._skills and not replace:
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

    def model_invocable_packages(self) -> list[SkillDefinition]:
        return [
            skill
            for skill in self._skills.values()
            if skill.is_package and not skill.disable_model_invocation
        ]

    def callable_skills(self) -> list[SkillDefinition]:
        return [skill for skill in self._skills.values() if skill.handler is not None]


class SkillExecutor:
    """Execute skill activations, scripts, and callable skill invocations."""

    def __init__(self, registry: SkillRegistry) -> None:
        self.registry = registry

    def execute(self, call: ToolCall) -> SkillResult:
        try:
            if call.name == ACTIVATE_SKILL_NAME:
                return self._activate(call)
            if call.name == RUN_SKILL_SCRIPT_NAME:
                return self._run_script(call)

            skill = self.registry.get(call.name)
            if skill.handler is None:
                return SkillResult(
                    skill_call_id=call.id,
                    name=call.name,
                    content=(
                        f"Skill {call.name!r} is instruction-based. "
                        f"Call {ACTIVATE_SKILL_NAME} with "
                        f'{{"name": "{call.name}"}} to load instructions, then '
                        f"call {RUN_SKILL_SCRIPT_NAME} to run bundled scripts."
                    ),
                    is_error=True,
                )

            result = skill.handler(**call.arguments)
            return SkillResult(
                skill_call_id=call.id,
                name=call.name,
                content=_stringify_result(result),
            )
        except SkillNotFoundError as exc:
            return SkillResult(
                skill_call_id=call.id,
                name=call.name,
                content=str(exc),
                is_error=True,
            )
        except TypeError as exc:
            return SkillResult(
                skill_call_id=call.id,
                name=call.name,
                content=f"Invalid skill arguments: {exc}",
                is_error=True,
            )
        except Exception as exc:
            return SkillResult(
                skill_call_id=call.id,
                name=call.name,
                content=str(exc),
                is_error=True,
            )

    def _activate(self, call: ToolCall) -> SkillResult:
        skill_name = str(call.arguments.get("name", "")).strip()
        if not skill_name:
            return SkillResult(
                skill_call_id=call.id,
                name=ACTIVATE_SKILL_NAME,
                content="Invalid skill arguments: name is required",
                is_error=True,
            )

        skill = self.registry.get(skill_name)
        if skill.disable_model_invocation:
            return SkillResult(
                skill_call_id=call.id,
                name=ACTIVATE_SKILL_NAME,
                content=f"Skill is not available for model activation: {skill_name}",
                is_error=True,
            )

        if skill.skill_dir is not None:
            package = AgentSkillPackage(
                name=skill.name,
                description=skill.description,
                instructions=skill.instructions,
                skill_dir=skill.skill_dir,
                license=skill.license,
                compatibility=skill.compatibility,
                metadata=dict(skill.metadata),
                allowed_tools=skill.allowed_tools,
                disable_model_invocation=skill.disable_model_invocation,
            )
            content = format_skill_activation(package)
        else:
            body = skill.instructions.strip() or skill.description
            content = (
                f'<skill_content name="{skill.name}">\n'
                f"{body}\n\n"
                "IMPORTANT: Activation only loaded these instructions. "
                "Follow them with available tools before answering the user.\n"
                f"</skill_content>"
            )

        return SkillResult(
            skill_call_id=call.id,
            name=ACTIVATE_SKILL_NAME,
            content=content,
        )

    def _run_script(self, call: ToolCall) -> SkillResult:
        skill_name = str(call.arguments.get("skill", "")).strip()
        script = str(call.arguments.get("script", "")).strip()
        raw_args = call.arguments.get("arguments", [])
        timeout = call.arguments.get("timeout")

        if not skill_name:
            raise TypeError("skill is required")
        if not script:
            raise TypeError("script is required")
        if raw_args is None:
            raw_args = []
        if not isinstance(raw_args, list) or not all(
            isinstance(item, (str, int, float, bool)) for item in raw_args
        ):
            raise TypeError("arguments must be a list of scalars")

        skill = self.registry.get(skill_name)
        if skill.skill_dir is None:
            raise ValueError(
                f"Skill {skill_name!r} has no package directory; "
                "run_skill_script only works for disk-based skills"
            )
        if skill.disable_model_invocation:
            raise ValueError(f"Skill is not available for model use: {skill_name}")

        script_path = _resolve_skill_script(skill.skill_dir, script)
        argv = _build_script_argv(script_path, [str(item) for item in raw_args])
        timeout_seconds = _normalize_timeout(timeout)

        try:
            completed = subprocess.run(
                argv,
                cwd=str(skill.skill_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                shell=False,
                env=os.environ.copy(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"Executable not found: {argv[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Skill script timed out after {timeout_seconds} seconds"
            ) from exc

        stdout, stdout_truncated = _truncate(completed.stdout or "")
        stderr, stderr_truncated = _truncate(completed.stderr or "")
        payload = {
            "skill": skill_name,
            "script": script.replace("\\", "/"),
            "argv": argv,
            "cwd": str(skill.skill_dir),
            "exit_code": int(completed.returncode),
            "stdout": stdout,
            "stderr": stderr,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
        is_error = completed.returncode != 0
        return SkillResult(
            skill_call_id=call.id,
            name=RUN_SKILL_SCRIPT_NAME,
            content=json.dumps(payload, ensure_ascii=False),
            is_error=is_error,
        )


class SkillManager:
    """Facade for discovering, disclosing, and activating Agent Skills."""

    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.registry = registry or SkillRegistry()
        self.executor = SkillExecutor(self.registry)
        self._activated: set[str] = set()

    def skill(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        instructions: str = "",
        parameters: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for programmatic callable skill registration."""

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

    def register(self, skill: SkillDefinition, *, replace: bool = False) -> None:
        self.registry.register(skill, replace=replace)

    def register_package(
        self, package: AgentSkillPackage, *, replace: bool = False
    ) -> None:
        self.registry.register(SkillDefinition.from_package(package), replace=replace)

    def load_from_directory(
        self, directory: Path, *, replace: bool = False
    ) -> list[SkillDefinition]:
        loaded: list[SkillDefinition] = []
        for package in discover_skill_packages(directory):
            definition = SkillDefinition.from_package(package)
            self.registry.register(definition, replace=replace)
            loaded.append(definition)
        return loaded

    def load_from_directories(
        self, directories: list[Path], *, replace_existing: bool = True
    ) -> list[SkillDefinition]:
        """Load skills; later directories override earlier ones on name collision."""
        loaded: list[SkillDefinition] = []
        for directory in directories:
            for package in discover_skill_packages(directory):
                definition = SkillDefinition.from_package(package)
                exists = self.registry.has(definition.name)
                if exists and not replace_existing:
                    continue
                self.registry.register(definition, replace=exists)
                loaded.append(definition)
        return loaded

    def has(self, name: str) -> bool:
        if name in _SKILL_TOOL_NAMES:
            return any(
                not skill.disable_model_invocation
                for skill in self.registry.list_skills()
            )
        return self.registry.has(name)

    def run(self, call: ToolCall) -> SkillResult:
        result = self.executor.execute(call)
        if (
            call.name == ACTIVATE_SKILL_NAME
            and not result.is_error
            and isinstance(call.arguments.get("name"), str)
        ):
            self._activated.add(str(call.arguments["name"]))
        return result

    def run_many(self, calls: list[ToolCall]) -> list[SkillResult]:
        return [self.run(call) for call in calls]

    def schemas(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        activatable = [
            skill
            for skill in self.registry.list_skills()
            if not skill.disable_model_invocation
        ]
        if activatable:
            schemas.append(self._activate_skill_schema(activatable))
        packages = [
            skill
            for skill in self.registry.model_invocable_packages()
            if skill.skill_dir is not None
        ]
        if packages:
            schemas.append(self._run_skill_script_schema(packages))
        for skill in self.registry.callable_skills():
            if skill.disable_model_invocation:
                continue
            schemas.append(skill.to_openai_schema())
        return schemas

    def list_skills(self) -> list[SkillDefinition]:
        return self.registry.list_skills()

    def build_context(self) -> str:
        entries = [
            (skill.name, skill.description, skill.location)
            for skill in self.registry.list_skills()
            if not skill.disable_model_invocation
        ]
        if not entries:
            return ""

        catalog = format_available_skills_xml(entries)
        return f"{_SKILL_BEHAVIOR}\n\n{catalog}"

    def _activate_skill_schema(self, skills: list[SkillDefinition]) -> dict[str, Any]:
        names = sorted({skill.name for skill in skills})
        return {
            "type": "function",
            "function": {
                "name": ACTIVATE_SKILL_NAME,
                "description": (
                    "Load the full instructions for an installed Agent Skill. "
                    "This does NOT execute the skill — after activation you must "
                    "follow the instructions (typically via run_skill_script) "
                    "before answering the user."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Skill name from the available skills catalog",
                            "enum": names,
                        }
                    },
                    "required": ["name"],
                },
            },
        }

    def _run_skill_script_schema(
        self, skills: list[SkillDefinition]
    ) -> dict[str, Any]:
        names = sorted({skill.name for skill in skills})
        return {
            "type": "function",
            "function": {
                "name": RUN_SKILL_SCRIPT_NAME,
                "description": (
                    "Execute a bundled script from an Agent Skill directory. "
                    "Use after activate_skill when the skill instructions reference "
                    "files under scripts/. The command runs with cwd set to the "
                    "skill directory. Example: skill='get-weather', "
                    "script='scripts/get_weather.py', arguments=['--city', '上海']."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill": {
                            "type": "string",
                            "description": "Installed skill name",
                            "enum": names,
                        },
                        "script": {
                            "type": "string",
                            "description": (
                                "Script path relative to the skill directory "
                                "(e.g. scripts/get_weather.py)"
                            ),
                        },
                        "arguments": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "CLI arguments appended after the script path "
                                "(e.g. ['--city', 'Shanghai'])"
                            ),
                        },
                        "timeout": {
                            "type": "number",
                            "description": (
                                f"Optional timeout in seconds "
                                f"(default {_DEFAULT_SCRIPT_TIMEOUT}, "
                                f"max {_MAX_SCRIPT_TIMEOUT})"
                            ),
                        },
                    },
                    "required": ["skill", "script"],
                },
            },
        }


def _resolve_skill_script(skill_dir: Path, script: str) -> Path:
    normalized = script.strip().replace("\\", "/")
    if not normalized or normalized.startswith("/") or ":" in normalized[:3]:
        raise ValueError(f"Script path must be relative to the skill directory: {script}")
    if ".." in Path(normalized).parts:
        raise ValueError(f"Script path must not escape the skill directory: {script}")

    resolved = (skill_dir / normalized).resolve()
    try:
        resolved.relative_to(skill_dir.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Script path escapes skill directory: {script}"
        ) from exc
    if not resolved.is_file():
        raise FileNotFoundError(f"Skill script not found: {script}")
    return resolved


def _build_script_argv(script_path: Path, arguments: list[str]) -> list[str]:
    suffix = script_path.suffix.lower()
    script = str(script_path)
    if suffix == ".py":
        return [sys.executable, script, *arguments]
    if suffix == ".js":
        return ["node", script, *arguments]
    if suffix in {".sh", ".bash"}:
        return ["bash", script, *arguments]
    if suffix == ".ps1":
        return [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script,
            *arguments,
        ]
    return [script, *arguments]


def _normalize_timeout(timeout: Any) -> float:
    if timeout is None:
        value = float(_DEFAULT_SCRIPT_TIMEOUT)
    else:
        value = float(timeout)
    if value <= 0:
        raise ValueError("timeout must be positive")
    return min(value, float(_MAX_SCRIPT_TIMEOUT))


def _truncate(text: str) -> tuple[str, bool]:
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= _MAX_SCRIPT_OUTPUT_BYTES:
        return text, False
    truncated = encoded[:_MAX_SCRIPT_OUTPUT_BYTES].decode("utf-8", errors="ignore")
    return truncated, True
