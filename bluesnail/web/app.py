"""FastAPI application for BlueSnail WebUI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from bluesnail.agent import Agent, AgentConfig, ToolManager
from bluesnail.agent.types import AgentResult, Message, Role
from bluesnail.web.llm_config import (
    LLMConfig,
    apply_llm_config,
    create_llm_provider,
    load_config,
    save_config,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    extra_context: str = ""


class ChatResponse(BaseModel):
    answer: str
    iterations: int
    stopped_reason: str
    steps: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    reasoning: dict[str, Any] = Field(default_factory=dict)


class RememberRequest(BaseModel):
    key: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=4000)


class LLMConfigUpdate(BaseModel):
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None
    timeout: float | None = Field(default=None, gt=0, le=600)
    system_prompt: str | None = Field(default=None, min_length=1, max_length=4000)


class LLMTestRequest(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str | None = None
    timeout: float = Field(default=30.0, gt=0, le=600)


def create_app(agent: Agent | None = None, llm_config: LLMConfig | None = None) -> FastAPI:
    app = FastAPI(title="BlueSnail Agent", version="0.1.0")
    app.state.agent = agent or build_default_agent(llm_config)
    app.state.llm_config = llm_config or load_config()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "bluesnail-web"}

    @app.get("/api/llm/config")
    async def get_llm_config() -> dict[str, Any]:
        return app.state.llm_config.masked_dict()

    @app.put("/api/llm/config")
    async def update_llm_config(payload: LLMConfigUpdate) -> dict[str, Any]:
        current: LLMConfig = app.state.llm_config
        try:
            merged = current.merge_update(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        agent = _get_agent(app)
        apply_llm_config(agent, merged)
        save_config(merged)
        app.state.llm_config = merged
        return merged.masked_dict()

    @app.post("/api/llm/test")
    async def test_llm_config(payload: LLMTestRequest) -> dict[str, Any]:
        current: LLMConfig = app.state.llm_config
        test_config = current.merge_update(
            {
                **payload.model_dump(),
                "system_prompt": current.system_prompt,
            }
        )
        llm = create_llm_provider(test_config)
        try:
            response = llm.chat(
                [Message(role=Role.USER, content="请只回复 OK。")],
                tools=None,
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not response.content:
            raise HTTPException(status_code=400, detail="LLM returned empty content.")
        return {
            "ok": True,
            "reply": response.content,
            "model": test_config.model,
        }

    @app.get("/api/tools")
    async def list_tools() -> dict[str, Any]:
        current = _get_agent(app)
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in current.tools.registry.list_tools()
        ]
        return {"tools": tools}

    @app.get("/api/skills")
    async def list_skills() -> dict[str, Any]:
        current = _get_agent(app)
        skills = [skill.to_dict() for skill in current.skills.list_skills()]
        return {"skills": skills}

    @app.get("/api/history")
    async def history() -> dict[str, Any]:
        current = _get_agent(app)
        messages = current.memory.store.get_messages()
        return {"messages": [_serialize_message(message) for message in messages]}

    @app.post("/api/chat", response_model=ChatResponse)
    async def chat(payload: ChatRequest) -> ChatResponse:
        current = _get_agent(app)
        try:
            result = current.run(
                payload.message.strip(),
                session_id=payload.session_id,
                extra_context=payload.extra_context,
            )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return _serialize_result(result)

    @app.post("/api/clear")
    async def clear_conversation() -> dict[str, str]:
        current = _get_agent(app)
        current.clear_conversation()
        return {"status": "cleared"}

    @app.post("/api/remember")
    async def remember(payload: RememberRequest) -> dict[str, str]:
        current = _get_agent(app)
        current.remember(payload.key, payload.content)
        return {"status": "saved", "key": payload.key}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


def _get_agent(app: FastAPI) -> Agent:
    agent = app.state.agent
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent is not initialized.")
    return agent


def _serialize_message(message: Message) -> dict[str, Any]:
    return {
        "role": message.role.value,
        "content": message.content,
        "name": message.name,
        "tool_call_id": message.tool_call_id,
        "metadata": message.metadata,
        "timestamp": message.timestamp.isoformat(),
    }


def _serialize_step(step) -> dict[str, Any]:
    return {
        "iteration": step.iteration,
        "content": step.response.content,
        "finish_reason": step.response.finish_reason,
        "tool_calls": [
            {
                "id": call.id,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in step.response.tool_calls
        ],
        "tool_results": [
            {
                "tool_call_id": item.tool_call_id,
                "name": item.name,
                "content": item.content,
                "is_error": item.is_error,
            }
            for item in step.tool_results
        ],
        "skill_results": [
            {
                "skill_call_id": item.skill_call_id,
                "name": item.name,
                "content": item.content,
                "is_error": item.is_error,
            }
            for item in step.skill_results
        ],
        "input_messages": [
            _serialize_message(message) for message in step.input_messages
        ],
    }


def _serialize_result(result: AgentResult) -> ChatResponse:
    steps = [_serialize_step(step) for step in result.steps]

    visible_messages = [
        _serialize_message(message)
        for message in result.messages
        if message.role in {Role.USER, Role.ASSISTANT, Role.TOOL}
    ]

    reasoning = {
        "run_context": result.run_context,
        "steps": steps,
        "iterations": result.iterations,
        "stopped_reason": result.stopped_reason,
    }

    return ChatResponse(
        answer=result.answer,
        iterations=result.iterations,
        stopped_reason=result.stopped_reason,
        steps=steps,
        messages=visible_messages,
        reasoning=reasoning,
    )


def build_default_agent(llm_config: LLMConfig | None = None) -> Agent:
    from bluesnail.skills import create_default_skills

    config = llm_config or load_config()
    agent = Agent(
        llm=create_llm_provider(config),
        skills=create_default_skills(),
        config=AgentConfig(system_prompt=config.system_prompt),
    )
    agent.remember("webui_hint", "WebUI prefers concise Chinese answers.")
    return agent
