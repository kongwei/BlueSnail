"""Tests for standard Agent Skill packages (agentskills.io)."""

import importlib.util
import json
from pathlib import Path

from bluesnail.agent.skill_loader import (
    discover_skill_packages,
    format_available_skills_xml,
    load_skill_package,
    parse_frontmatter,
)
from bluesnail.agent.skills import (
    ACTIVATE_SKILL_NAME,
    BUILTIN_SKILLS_DIR,
    RUN_SKILL_SCRIPT_NAME,
    SkillManager,
)
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


def test_load_get_weather_package_without_handler():
    package = load_skill_package(BUILTIN_SKILLS_DIR / "get-weather")
    assert package.name == "get-weather"
    assert "weather" in package.description.lower()
    assert package.instructions.startswith("# Get Weather")
    resources = package.list_resources()
    assert "scripts/get_weather.py" in resources


def test_discover_builtin_skills():
    packages = discover_skill_packages(BUILTIN_SKILLS_DIR)
    assert any(pkg.name == "get-weather" for pkg in packages)


def test_create_default_skills_loads_packages():
    skills = create_default_skills()
    names = [skill.name for skill in skills.list_skills()]
    assert "get-weather" in names


def test_activate_get_weather_skill():
    skills = create_default_skills()
    result = skills.run(
        ToolCall(
            id="call_1",
            name=ACTIVATE_SKILL_NAME,
            arguments={"name": "get-weather"},
        )
    )
    assert not result.is_error
    assert "skill_content" in result.content
    assert "scripts/get_weather.py" in result.content
    assert "Get Weather" in result.content
    assert "run_skill_script" in result.content
    assert "Do not stop after activate_skill alone" in result.content


def test_package_skill_is_not_direct_callable():
    skills = create_default_skills()
    result = skills.run(
        ToolCall(id="call_1", name="get-weather", arguments={"city": "上海"})
    )
    assert result.is_error
    assert ACTIVATE_SKILL_NAME in result.content


def test_run_skill_script(monkeypatch):
    skills = create_default_skills()
    module = _load_weather_script()

    def fake_fetch_weather(city: str) -> dict:
        return {
            "city": city,
            "country": "中国",
            "weather": "clear sky",
            "weather_code": 0,
            "temperature": "26.4C",
            "humidity": "58%",
            "wind_speed": "12.6 km/h",
            "source": "open-meteo.com",
        }

    monkeypatch.setattr(module, "fetch_weather", fake_fetch_weather)

    class FakeCompleted:
        returncode = 0
        stdout = json.dumps(fake_fetch_weather("上海"), ensure_ascii=False)
        stderr = ""

    def fake_run(*args, **kwargs):
        return FakeCompleted()

    monkeypatch.setattr(
        "bluesnail.agent.skills.subprocess.run",
        fake_run,
    )

    result = skills.run(
        ToolCall(
            id="call_2",
            name=RUN_SKILL_SCRIPT_NAME,
            arguments={
                "skill": "get-weather",
                "script": "scripts/get_weather.py",
                "arguments": ["--city", "上海"],
            },
        )
    )
    assert not result.is_error
    payload = json.loads(result.content)
    assert payload["exit_code"] == 0
    assert "26.4C" in payload["stdout"]
    assert payload["skill"] == "get-weather"


def test_run_skill_script_rejects_path_escape():
    skills = create_default_skills()
    result = skills.run(
        ToolCall(
            id="call_2",
            name=RUN_SKILL_SCRIPT_NAME,
            arguments={
                "skill": "get-weather",
                "script": "../secrets.py",
                "arguments": [],
            },
        )
    )
    assert result.is_error
    assert "escape" in result.content.lower() or ".." in result.content


def test_weather_script(monkeypatch):
    module = _load_weather_script()

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

    monkeypatch.setattr(module, "http_get_json", fake_http_get_json)
    payload = module.fetch_weather("上海")
    assert payload["city"] == "上海"
    assert payload["temperature"] == "26.4C"
    assert json.loads(json.dumps(payload))["weather"] == "clear sky"


def test_skill_schema_exposes_activate_and_run_script():
    skills = create_default_skills()
    names = {item["function"]["name"] for item in skills.schemas()}
    assert ACTIVATE_SKILL_NAME in names
    assert RUN_SKILL_SCRIPT_NAME in names
    assert "get-weather" not in names
    run_schema = next(
        item
        for item in skills.schemas()
        if item["function"]["name"] == RUN_SKILL_SCRIPT_NAME
    )
    assert "get-weather" in run_schema["function"]["parameters"]["properties"]["skill"][
        "enum"
    ]


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
    assert "<available_skills>" in context
    assert "activate_skill" in context
    assert "run_skill_script" in context


def test_format_available_skills_xml():
    xml = format_available_skills_xml(
        [("demo", "A demo skill", Path("/tmp/demo/SKILL.md"))]
    )
    assert "<name>\ndemo\n</name>" in xml
    assert "/tmp/demo/SKILL.md" in xml.replace("\\", "/")


def test_instruction_only_skill_directory(tmp_path: Path):
    skill_dir = tmp_path / "summarize-notes"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        """---
name: summarize-notes
description: Summarize meeting notes into action items.
---

# Summarize Notes

1. Read the notes.
2. List action items.
""",
        encoding="utf-8",
    )

    package = load_skill_package(skill_dir)
    assert package.name == "summarize-notes"
    assert package.list_resources() == []

    manager = SkillManager()
    manager.register_package(package)
    result = manager.run(
        ToolCall(
            id="call_1",
            name=ACTIVATE_SKILL_NAME,
            arguments={"name": "summarize-notes"},
        )
    )
    assert not result.is_error
    assert "action items" in result.content.lower()


def _load_weather_script():
    script = BUILTIN_SKILLS_DIR / "get-weather" / "scripts" / "get_weather.py"
    spec = importlib.util.spec_from_file_location("get_weather_script_test", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
