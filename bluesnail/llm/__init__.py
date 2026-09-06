"""LLM provider module."""

from bluesnail.llm.provider import BaseLLMProvider, LLMProvider, MockLLMProvider

__all__ = [
    "BaseLLMProvider",
    "LLMProvider",
    "MockLLMProvider",
    "OpenAICompatibleProvider",
]


def __getattr__(name: str):
    if name == "OpenAICompatibleProvider":
        from bluesnail.llm.openai_compatible import OpenAICompatibleProvider

        return OpenAICompatibleProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
