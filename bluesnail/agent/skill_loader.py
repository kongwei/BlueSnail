"""Load standard Agent Skill packages from disk."""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from bluesnail.agent.tools import _build_parameters_schema

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_FRONTMATTER_LINE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")


@dataclass(slots=True)
class AgentSkillPackage:
    """Standard skill package loaded from a skill directory."""

    name: str
    description: str
    instructions: str
    skill_dir: Path
    handler: Callable[..., Any]
    parameters: dict[str, Any] = field(default_factory=dict)
    disable_model_invocation: bool = True

    @property
    def skill_md_path(self) -> Path:
        return self.skill_dir / "SKILL.md"

    @property
    def handler_path(self) -> Path | None:
        path = self.skill_dir / "scripts" / "handler.py"
        return path if path.exists() else None


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    match = _FRONTMATTER_PATTERN.match(content.strip())
    if not match:
        return {}, content.strip()

    raw_meta, body = match.group(1), match.group(2).strip()
    metadata: dict[str, str] = {}
    for line in raw_meta.splitlines():
        parsed = _FRONTMATTER_LINE.match(line.strip())
        if not parsed:
            continue
        key, value = parsed.group(1), parsed.group(2).strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        metadata[key] = value
    return metadata, body


def load_handler(skill_dir: Path) -> Callable[..., Any]:
    handler_path = skill_dir / "scripts" / "handler.py"
    if not handler_path.exists():
        raise FileNotFoundError(f"Skill handler not found: {handler_path}")

    module_name = f"bluesnail_skill_{skill_dir.name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, handler_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load skill handler: {handler_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for attr in ("run", "execute", "handler"):
        candidate = getattr(module, attr, None)
        if callable(candidate):
            return candidate

    raise AttributeError(
        f"Skill handler must define run(), execute(), or handler(): {handler_path}"
    )


def load_skill_package(skill_dir: Path) -> AgentSkillPackage:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")

    metadata, instructions = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = metadata.get("name") or skill_dir.name
    description = metadata.get("description", "").strip()
    if not description:
        raise ValueError(f"Skill description is required in {skill_md}")

    disable_model_invocation = _parse_bool(
        metadata.get("disable-model-invocation", "true")
    )
    handler = load_handler(skill_dir)
    parameters = _build_parameters_schema(handler)

    return AgentSkillPackage(
        name=name,
        description=description,
        instructions=instructions,
        skill_dir=skill_dir.resolve(),
        handler=handler,
        parameters=parameters,
        disable_model_invocation=disable_model_invocation,
    )


def discover_skill_packages(root: Path) -> list[AgentSkillPackage]:
    if not root.exists():
        return []

    packages: list[AgentSkillPackage] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if skill_md.exists():
            packages.append(load_skill_package(entry))
    return packages


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}
