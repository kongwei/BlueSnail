"""WebUI API tests."""

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from bluesnail.agent import Agent, AgentConfig, MockLLMProvider
from bluesnail.agent.providers.openai_compatible import OpenAICompatibleProvider
from bluesnail.agent.types import LLMResponse
from bluesnail.skills import create_default_skills
from bluesnail.web.app import create_app
from bluesnail.web.llm_config import LLMConfig


def build_test_agent() -> tuple[Agent, LLMConfig]:
    llm = MockLLMProvider(default_content="你好，我是助手。")
    llm.queue_tool_call(
        "call_1",
        "get-weather",
        {"city": "上海"},
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
def client() -> TestClient:
    agent, config = build_test_agent()
    app = create_app(agent, config)
    return TestClient(app)


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_index(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "BlueSnail" in response.text
    assert "LLM 配置" in response.text
    assert "markdown.js" in response.text
    assert "highlight.min.js" in response.text
    assert "Skills" in response.text


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
