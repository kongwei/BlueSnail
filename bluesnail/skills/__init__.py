"""Built-in Agent Skill packages for BlueSnail."""

from __future__ import annotations

import os
from pathlib import Path

from bluesnail.agent.skills import BUILTIN_SKILLS_DIR, SkillManager

__all__ = ["BUILTIN_SKILLS_DIR", "create_default_skills", "discover_skill_directories"]


def discover_skill_directories() -> list[Path]:
    """Discover standard skill directories."""
    directories = [BUILTIN_SKILLS_DIR]

    project_dir = Path(".cursor/skills")
    if project_dir.exists():
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
