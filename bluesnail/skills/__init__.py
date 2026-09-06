"""Skills module: package loader, manager, and built-in packages."""

from __future__ import annotations

import os
from pathlib import Path

from bluesnail.skills.loader import AgentSkillPackage
from bluesnail.skills.manager import (
    ACTIVATE_SKILL_NAME,
    BUILTIN_SKILLS_DIR,
    RUN_SKILL_SCRIPT_NAME,
    SkillDefinition,
    SkillManager,
    SkillRegistry,
)

__all__ = [
    "ACTIVATE_SKILL_NAME",
    "BUILTIN_SKILLS_DIR",
    "RUN_SKILL_SCRIPT_NAME",
    "AgentSkillPackage",
    "SkillDefinition",
    "SkillManager",
    "SkillRegistry",
    "create_default_skills",
    "discover_skill_directories",
]


def discover_skill_directories() -> list[Path]:
    """Discover Agent Skills directories (agentskills.io client layout).

    Later entries override earlier ones on name collision. Order:

    1. Built-in BlueSnail skills
    2. User-level ``~/.agents/skills`` and ``~/.cursor/skills``
    3. Project-level ``.agents/skills`` and ``.cursor/skills``
    4. ``BLUESNAIL_SKILL_DIRS`` (pathsep-separated)
    """
    directories: list[Path] = [BUILTIN_SKILLS_DIR]

    home = Path.home()
    for relative in (Path(".agents") / "skills", Path(".cursor") / "skills"):
        user_dir = home / relative
        if user_dir.is_dir():
            directories.append(user_dir.resolve())

    for relative in (Path(".agents") / "skills", Path(".cursor") / "skills"):
        project_dir = Path.cwd() / relative
        if project_dir.is_dir():
            directories.append(project_dir.resolve())

    custom = os.getenv("BLUESNAIL_SKILL_DIRS", "")
    for item in custom.split(os.pathsep):
        if item.strip():
            directories.append(Path(item.strip()).resolve())

    return directories


def create_default_skills(extra_dirs: list[Path] | None = None) -> SkillManager:
    """Load built-in and discovered standard skill packages."""
    manager = SkillManager()
    directories = discover_skill_directories()
    if extra_dirs:
        directories.extend(extra_dirs)
    manager.load_from_directories(directories)
    return manager
