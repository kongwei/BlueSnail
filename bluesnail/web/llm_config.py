"""LLM configuration for WebUI."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from bluesnail.agent import Agent
from bluesnail.agent.llm import LLMProvider
from bluesnail.agent.providers.openai_compatible import OpenAICompatibleProvider

_DEFAULT_SYSTEM_PROMPT = (
    "You are BlueSnail, a helpful AI assistant with tool-use capabilities."
)


@dataclass
class LLMConfig:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key: str = ""
    timeout: float = 60.0
    system_prompt: str = _DEFAULT_SYSTEM_PROMPT

    @classmethod
    def from_env(cls) -> LLMConfig:
        return cls(
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            timeout=float(os.getenv("LLM_TIMEOUT", "60")),
            system_prompt=os.getenv("BLUESNAIL_SYSTEM_PROMPT", _DEFAULT_SYSTEM_PROMPT),
        )

    def masked_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["api_key_set"] = bool(self.api_key)
        data["api_key_hint"] = _mask_api_key(self.api_key)
        data.pop("api_key", None)
        return data

    def merge_update(self, payload: dict[str, Any]) -> LLMConfig:
        updated = LLMConfig(**asdict(self))
        for key in ("base_url", "model", "timeout", "system_prompt"):
            if key in payload and payload[key] is not None:
                setattr(updated, key, payload[key])
        if payload.get("api_key"):
            updated.api_key = payload["api_key"]
        if not updated.api_key:
            raise ValueError("API Key is required.")
        if not updated.base_url:
            updated.base_url = "https://api.openai.com/v1"
        if not updated.model:
            updated.model = "gpt-4o-mini"
        return updated


def config_path() -> Path:
    custom = os.getenv("BLUESNAIL_CONFIG_DIR")
    if custom:
        return Path(custom) / "llm_config.json"
    return Path.home() / ".bluesnail" / "llm_config.json"


def load_config() -> LLMConfig:
    path = config_path()
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        data.pop("provider", None)
        allowed = set(asdict(LLMConfig()).keys())
        return LLMConfig(**{key: data[key] for key in allowed if key in data})
    return LLMConfig.from_env()


def save_config(config: LLMConfig) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def create_llm_provider(config: LLMConfig) -> LLMProvider:
    return OpenAICompatibleProvider(
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        timeout=config.timeout,
    )


def apply_llm_config(agent: Agent, config: LLMConfig) -> None:
    agent.scheduler.llm = create_llm_provider(config)
    agent.config.system_prompt = config.system_prompt


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}...{api_key[-4:]}"
