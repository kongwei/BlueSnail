"""Load Agent Skills packages from disk (agentskills.io open standard).

A skill is a directory with a required ``SKILL.md``. Bundled ``scripts/``,
``references/``, and ``assets/`` are optional. Agents follow progressive
disclosure: metadata first, full instructions on activation, resources on demand.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)
_FRONTMATTER_LINE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")
_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

_RESOURCE_DIRS = ("scripts", "references", "assets")
_logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AgentSkillPackage:
    """Standard Agent Skill package loaded from a skill directory."""

    name: str
    description: str
    instructions: str
    skill_dir: Path
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    allowed_tools: str | None = None
    disable_model_invocation: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def skill_md_path(self) -> Path:
        return self.skill_dir / "SKILL.md"

    @property
    def location(self) -> Path:
        """Absolute path to SKILL.md (agentskills catalog ``location``)."""
        return self.skill_md_path

    def list_resources(self, *, max_files: int = 50) -> list[str]:
        """List bundled resource paths relative to the skill directory."""
        resources: list[str] = []
        for dirname in _RESOURCE_DIRS:
            root = self.skill_dir / dirname
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    resources.append(path.relative_to(self.skill_dir).as_posix())
                    if len(resources) >= max_files:
                        return resources
        return resources


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-like frontmatter from a SKILL.md document."""
    match = _FRONTMATTER_PATTERN.match(content.strip())
    if not match:
        return {}, content.strip()

    raw_meta, body = match.group(1), match.group(2).strip()
    metadata: dict[str, Any] = {}
    current_map_key: str | None = None

    for raw_line in raw_meta.splitlines():
        if not raw_line.strip():
            current_map_key = None
            continue

        # Nested map entries: "  key: value" under a parent key ending with ":"
        if current_map_key and (raw_line.startswith("  ") or raw_line.startswith("\t")):
            nested = _FRONTMATTER_LINE.match(raw_line.strip())
            if nested:
                nested_key, nested_value = nested.group(1), nested.group(2).strip()
                parent = metadata.setdefault(current_map_key, {})
                if not isinstance(parent, dict):
                    parent = {}
                    metadata[current_map_key] = parent
                parent[nested_key] = _strip_quotes(nested_value)
            continue

        parsed = _FRONTMATTER_LINE.match(raw_line.strip())
        if not parsed:
            current_map_key = None
            continue

        key, value = parsed.group(1), parsed.group(2).strip()
        if value == "":
            current_map_key = key
            metadata[key] = {}
            continue

        current_map_key = None
        metadata[key] = _strip_quotes(value)

    return metadata, body


def load_skill_package(skill_dir: Path) -> AgentSkillPackage:
    """Load one skill directory. Only ``SKILL.md`` is required."""
    skill_dir = skill_dir.resolve()
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        raise FileNotFoundError(f"SKILL.md not found in {skill_dir}")

    metadata, instructions = parse_frontmatter(skill_md.read_text(encoding="utf-8"))
    name = str(metadata.get("name") or skill_dir.name).strip()
    description = str(metadata.get("description", "")).strip()
    if not description:
        raise ValueError(f"Skill description is required in {skill_md}")

    warnings = _validate_name(name, skill_dir.name)
    if len(description) > 1024:
        warnings.append(
            f"Skill description exceeds 1024 characters ({len(description)})"
        )

    raw_metadata = metadata.get("metadata")
    extra_metadata: dict[str, str] = {}
    if isinstance(raw_metadata, dict):
        extra_metadata = {str(k): str(v) for k, v in raw_metadata.items()}

    return AgentSkillPackage(
        name=name,
        description=description,
        instructions=instructions,
        skill_dir=skill_dir,
        license=_optional_str(metadata.get("license")),
        compatibility=_optional_str(metadata.get("compatibility")),
        metadata=extra_metadata,
        allowed_tools=_optional_str(metadata.get("allowed-tools")),
        disable_model_invocation=_parse_bool(
            metadata.get("disable-model-invocation", "false")
        ),
        warnings=warnings,
    )


def discover_skill_packages(root: Path) -> list[AgentSkillPackage]:
    """Discover skill packages under ``root`` (one level of subdirectories)."""
    if not root.exists():
        return []

    packages: list[AgentSkillPackage] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name in {".git", "node_modules", "__pycache__"}:
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            package = load_skill_package(entry)
        except (OSError, ValueError) as exc:
            _logger.warning("Skipping skill at %s: %s", entry, exc)
            continue
        for warning in package.warnings:
            _logger.warning("Skill %s: %s", package.name, warning)
        packages.append(package)
    return packages


def format_skill_activation(package: AgentSkillPackage) -> str:
    """Wrap activated skill content for progressive disclosure (tier 2)."""
    resources = package.list_resources()
    scripts = [path for path in resources if path.startswith("scripts/")]
    lines = [
        f'<skill_content name="{package.name}">',
        package.instructions.strip(),
        "",
        f"Skill directory: {package.skill_dir}",
        "Relative paths in this skill are relative to the skill directory.",
    ]
    if resources:
        lines.append("")
        lines.append("<skill_resources>")
        for relative in resources:
            lines.append(f"  <file>{relative}</file>")
        lines.append("</skill_resources>")
    lines.append("")
    lines.append(
        "IMPORTANT: Activation only loaded these instructions. "
        "You must continue the skill workflow before answering the user."
    )
    if scripts:
        example = scripts[0]
        lines.append(
            "To run a bundled script, call run_skill_script with "
            f'skill="{package.name}", script="{example}", and any CLI arguments. '
            "Do not stop after activate_skill alone."
        )
    else:
        lines.append(
            "Follow the instructions above using available tools, "
            "then answer the user. Do not stop after activate_skill alone."
        )
    lines.append("</skill_content>")
    return "\n".join(lines)


def format_available_skills_xml(
    entries: list[tuple[str, str, Path | None]],
) -> str:
    """Build the agentskills-recommended ``<available_skills>`` catalog.

    Each entry is ``(name, description, location)`` where ``location`` is the
    absolute path to ``SKILL.md`` when available.
    """
    if not entries:
        return ""

    chunks = ["<available_skills>"]
    for name, description, location in entries:
        chunks.extend(
            [
                "<skill>",
                "<name>",
                name,
                "</name>",
                "<description>",
                description,
                "</description>",
            ]
        )
        if location is not None:
            chunks.extend(
                [
                    "<location>",
                    str(location),
                    "</location>",
                ]
            )
        chunks.append("</skill>")
    chunks.append("</available_skills>")
    return "\n".join(chunks)


def _validate_name(name: str, directory_name: str) -> list[str]:
    warnings: list[str] = []
    if len(name) > 64:
        warnings.append(f"name exceeds 64 characters ({len(name)})")
    if not _NAME_PATTERN.fullmatch(name):
        warnings.append(
            "name should be lowercase alphanumeric with single hyphens "
            f"(got {name!r})"
        )
    if name != directory_name:
        warnings.append(
            f"name {name!r} does not match parent directory {directory_name!r}"
        )
    return warnings


def _strip_quotes(value: str) -> str:
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
