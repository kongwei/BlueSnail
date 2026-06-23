"""Tests for standard Agent Skill packages."""

import importlib.util
from pathlib import Path
from bluesnail.agent.skill_loader import (
    discover_skill_packages,
    load_skill_package,
    parse_frontmatter,
)
from bluesnail.agent.skills import BUILTIN_SKILLS_DIR, SkillManager
from bluesnail.agent.types import ToolCall
from bluesnail.skills import create_default_skills


def test_parse_frontmatter():
    content = """---
name: demo-skill
description: Demo skill for tests.
disable-model-invocation: true
---

# Demo

Do the thing.
"""
    metadata, body = parse_frontmatter(content)
    assert metadata["name"] == "demo-skill"
    assert "Demo skill" in metadata["description"]
    assert body.startswith("# Demo")


def test_load_get_weather_package():
    package = load_skill_package(BUILTIN_SKILLS_DIR / "get-weather")
    assert package.name == "get-weather"
    assert package.handler_path is not None
    assert "weather" in package.description.lower()
    assert package.instructions.startswith("# Get Weather")


def test_discover_builtin_skills():
    packages = discover_skill_packages(BUILTIN_SKILLS_DIR)
    assert any(pkg.name == "get-weather" for pkg in packages)


def test_create_default_skills_loads_packages():
    skills = create_default_skills()
    names = [skill.name for skill in skills.list_skills()]
    assert "get-weather" in names


def test_run_get_weather_skill(monkeypatch):
    def fake_http_get_json(base_url: str, params: dict) -> dict:
        if "geocoding-api" in base_url:
            return {
                "results": [
                    {
                        "name": "上海",
                        "latitude": 31.2222,
                        "longitude": 121.4581,
                        "country": "中国",
                    }
                ]
            }
        return {
            "current": {
                "temperature_2m": 26.4,
                "weather_code": 0,
                "relative_humidity_2m": 58,
                "wind_speed_10m": 12.6,
            }
        }

    handler_path = BUILTIN_SKILLS_DIR / "get-weather" / "scripts" / "handler.py"
    spec = importlib.util.spec_from_file_location(
        "get_weather_handler_test",
        handler_path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "http_get_json", fake_http_get_json)

    skills = SkillManager()
    package = load_skill_package(BUILTIN_SKILLS_DIR / "get-weather")
    skills.register_package(package)
    skills.registry.get("get-weather").handler = module.run

    result = skills.run(
        ToolCall(id="call_1", name="get-weather", arguments={"city": "上海"})
    )
    assert "上海" in result.content
    assert "26.4" in result.content
    assert not result.is_error


def test_skill_schema_uses_standard_prefix():
    skills = create_default_skills()
    schema = next(
        item for item in skills.schemas() if item["function"]["name"] == "get-weather"
    )
    assert schema["function"]["description"].startswith("[Skill:get-weather]")


def test_programmatic_skill_registration():
    manager = SkillManager()

    @manager.skill(description="Reverse text")
    def reverse_text(text: str) -> str:
        return text[::-1]

    result = manager.run(
        ToolCall(id="call_1", name="reverse_text", arguments={"text": "abc"})
    )
    assert result.content == "cba"


def test_build_context_lists_loaded_skills():
    skills = create_default_skills()
    context = skills.build_context()
    assert "get-weather" in context
