"""WebUI API tests."""

import json

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from bluesnail.integration import (
    ACTIVATE_SKILL_NAME,
    RUN_SKILL_SCRIPT_NAME,
    Agent,
    AgentConfig,
    MockLLMProvider,
)
from bluesnail.llm.openai_compatible import OpenAICompatibleProvider
from bluesnail.core.types import LLMResponse
from bluesnail.skills import create_default_skills
from bluesnail.web.app import create_app
from bluesnail.web.llm_config import LLMConfig


def build_test_agent(monkeypatch=None) -> tuple[Agent, LLMConfig]:
    llm = MockLLMProvider(default_content="你好，我是助手。")
    llm.queue_tool_call(
        "call_1",
        ACTIVATE_SKILL_NAME,
        {"name": "get-weather"},
    )
    llm.queue_tool_call(
        "call_2",
        RUN_SKILL_SCRIPT_NAME,
        {
            "skill": "get-weather",
            "script": "scripts/get_weather.py",
            "arguments": ["--city", "上海"],
        },
        then_content="上海今天天气晴朗，气温约 26°C。",
    )
    config = LLMConfig(
        api_key="sk-test",
        model="test-model",
        base_url="https://api.example.com/v1",
    )
    agent = Agent(
        llm=llm,
        skills=create_default_skills(),
        config=AgentConfig(system_prompt=config.system_prompt),
    )
    return agent, config


@pytest.fixture
def client(monkeypatch) -> TestClient:
    class FakeCompleted:
        returncode = 0
        stdout = '{"city":"上海","temperature":"26C","weather":"clear sky"}'
        stderr = ""

    monkeypatch.setattr(
        "bluesnail.skills.manager.subprocess.run",
        lambda *args, **kwargs: FakeCompleted(),
    )
    agent, config = build_test_agent()
    app = create_app(agent, config)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "filesystem_workspace" in data


def test_index(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "BlueSnail" in response.text
    assert "LLM 配置" in response.text
    assert "markdown.js" in response.text
    assert "highlight.min.js" in response.text
    assert "Skills" in response.text
    assert "当前流程" in response.text
    assert "打开流程编排" in response.text
    assert "/workflow" in response.text
    assert "workflowForm" not in response.text


def test_workflow_page(client: TestClient) -> None:
    response = client.get("/workflow")
    assert response.status_code == 200
    assert "流程编排" in response.text
    assert "workflow.js" in response.text
    assert "流程 ID" in response.text


def test_list_skills(client: TestClient) -> None:
    response = client.get("/api/skills")
    assert response.status_code == 200
    data = response.json()
    assert any(skill["name"] == "get-weather" for skill in data["skills"])


def test_get_llm_config(client: TestClient) -> None:
    response = client.get("/api/llm/config")
    assert response.status_code == 200
    data = response.json()
    assert data["model"] == "test-model"
    assert data["api_key_set"] is True


def test_update_llm_config(client: TestClient) -> None:
    from bluesnail.web.llm_config import config_path

    response = client.put(
        "/api/llm/config",
        json={
            "api_key": "sk-updated",
            "system_prompt": "You are a test assistant.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["system_prompt"] == "You are a test assistant."
    assert data["api_key_set"] is True

    saved = json.loads(config_path().read_text(encoding="utf-8"))
    assert saved["api_key"] == "sk-updated"
    assert saved["system_prompt"] == "You are a test assistant."


def test_update_llm_config_requires_key(client: TestClient) -> None:
    agent, config = build_test_agent()
    config = LLMConfig(api_key="", model="test-model")
    app = create_app(agent, config)
    empty_client = TestClient(app)
    response = empty_client.put(
        "/api/llm/config",
        json={
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    )
    assert response.status_code == 400


def test_test_llm_openai(client: TestClient, monkeypatch) -> None:
    def mock_chat(self, messages, tools=None):
        return LLMResponse(content="OK", finish_reason="stop")

    monkeypatch.setattr(OpenAICompatibleProvider, "chat", mock_chat)
    response = client.post(
        "/api/llm/test",
        json={
            "base_url": "https://api.example.com/v1",
            "model": "test-model",
            "api_key": "sk-test",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["reply"] == "OK"


def test_chat(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "你好"})
    assert response.status_code == 200
    data = response.json()
    assert data["answer"]
    assert data["iterations"] >= 1


def test_chat_with_skill(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "上海天气怎么样？"})
    assert response.status_code == 200
    data = response.json()
    assert "26" in data["answer"] or "天气" in data["answer"]
    assert any(step["skill_results"] for step in data["steps"])
    assert data["reasoning"]["steps"]
    assert data["reasoning"]["steps"][0]["input_messages"]


def test_chat_stream(client: TestClient) -> None:
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"message": "上海天气怎么样？"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events: list[tuple[str, dict]] = []
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                part, buffer = buffer.split("\n\n", 1)
                if not part.strip():
                    continue
                event_type = "message"
                data_line = ""
                for line in part.split("\n"):
                    if line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_line = line[5:].strip()
                if data_line:
                    events.append((event_type, json.loads(data_line)))

    event_types = [event_type for event_type, _ in events]
    assert "start" in event_types
    assert "workflow" in event_types
    assert "step" in event_types
    assert "done" in event_types
    assert event_types.index("start") < event_types.index("step")
    assert event_types.index("step") < event_types.index("done")

    workflow_events = [data for event_type, data in events if event_type == "workflow"]
    assert any(item["phase"] == "before" for item in workflow_events)
    assert any(item["step_type"] == "llm" and item["phase"] == "after" for item in workflow_events)

    step_events = [data for event_type, data in events if event_type == "step"]
    assert len(step_events) >= 2
    assert step_events[0]["tool_calls"]
    assert not step_events[0]["tool_results"] and not step_events[0]["skill_results"]
    assert any(step["skill_results"] for step in step_events)

    done_payload = next(data for event_type, data in events if event_type == "done")
    assert done_payload["answer"]
    assert done_payload["reasoning"]["steps"]


def test_chat_reasoning_contains_context(client: TestClient) -> None:
    response = client.post("/api/chat", json={"message": "你好"})
    assert response.status_code == 200
    data = response.json()
    reasoning = data["reasoning"]
    assert reasoning["run_context"]["system_prompt"]
    assert reasoning["run_context"]["skill_context"]
    assert reasoning["steps"][0]["input_messages"]


def test_clear_and_remember(client: TestClient) -> None:
    client.post("/api/chat", json={"message": "hello"})
    clear_response = client.post("/api/clear")
    assert clear_response.status_code == 200

    remember_response = client.post(
        "/api/remember",
        json={"key": "pref", "content": "likes Chinese"},
    )
    assert remember_response.status_code == 200

    history_response = client.get("/api/history")
    assert history_response.status_code == 200


def test_get_and_update_workflow(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BLUESNAIL_CONFIG_DIR", str(tmp_path))
    response = client.get("/api/workflow")
    assert response.status_code == 200
    data = response.json()
    assert data["active_id"]
    assert data["workflows"]

    catalog = client.get("/api/workflow/catalog")
    assert catalog.status_code == 200
    assert catalog.json()["step_types"]

    payload = data
    payload["active_id"] = payload["workflows"][0]["id"]
    payload["workflows"][0]["max_iterations"] = 7
    update = client.put("/api/workflow", json=payload)
    assert update.status_code == 200
    assert update.json()["workflows"][0]["max_iterations"] == 7

    invalid = client.put(
        "/api/workflow",
        json={"active_id": "nope", "workflows": payload["workflows"]},
    )
    assert invalid.status_code == 400


def test_reset_workflow(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BLUESNAIL_CONFIG_DIR", str(tmp_path))
    reset = client.post("/api/workflow/reset")
    assert reset.status_code == 200
    data = reset.json()
    assert data["active_id"] == "react"
    assert any(item["id"] == "direct" for item in data["workflows"])


def test_activate_workflow_by_id_or_name(client: TestClient, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BLUESNAIL_CONFIG_DIR", str(tmp_path))
    reset = client.post("/api/workflow/reset")
    assert reset.status_code == 200

    by_name = client.put("/api/workflow/active", json={"ref": "直接回答"})
    assert by_name.status_code == 200
    assert by_name.json()["id"] == "direct"
    assert by_name.json()["name"] == "直接回答"

    by_id = client.put("/api/workflow/active", json={"ref": "react"})
    assert by_id.status_code == 200
    assert by_id.json()["id"] == "react"

    active = client.get("/api/workflow/active")
    assert active.status_code == 200
    assert active.json()["id"] == "react"

    missing = client.put("/api/workflow/active", json={"ref": "does-not-exist"})
    assert missing.status_code == 400
