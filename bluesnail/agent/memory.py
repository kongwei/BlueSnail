"""Memory processing module."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import deque
from typing import Iterable

from bluesnail.agent.types import MemoryEntry, Message, Role


class MemoryStore(ABC):
    """Abstract memory store for conversation and long-term knowledge."""

    @abstractmethod
    def add_message(self, message: Message) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_messages(self, limit: int | None = None) -> list[Message]:
        raise NotImplementedError

    @abstractmethod
    def remember(self, key: str, content: str, metadata: dict | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def recall(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


class InMemoryStore(MemoryStore):
    """In-memory implementation with short-term and long-term storage."""

    def __init__(
        self,
        max_messages: int = 200,
        max_long_term: int = 1000,
    ) -> None:
        self._messages: deque[Message] = deque(maxlen=max_messages)
        self._long_term: list[MemoryEntry] = []
        self._max_long_term = max_long_term

    def add_message(self, message: Message) -> None:
        self._messages.append(message)

    def add_messages(self, messages: Iterable[Message]) -> None:
        for message in messages:
            self.add_message(message)

    def get_messages(self, limit: int | None = None) -> list[Message]:
        items = list(self._messages)
        if limit is not None:
            return items[-limit:]
        return items

    def remember(self, key: str, content: str, metadata: dict | None = None) -> None:
        entry = MemoryEntry(key=key, content=content, metadata=metadata or {})
        self._long_term.append(entry)
        if len(self._long_term) > self._max_long_term:
            self._long_term = self._long_term[-self._max_long_term :]

    def recall(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        if not query.strip():
            return []

        tokens = _tokenize(query)
        scored: list[MemoryEntry] = []
        for entry in self._long_term:
            haystack = f"{entry.key} {entry.content}".lower()
            score = sum(1 for token in tokens if token in haystack)
            if score > 0:
                scored.append(
                    MemoryEntry(
                        key=entry.key,
                        content=entry.content,
                        metadata=entry.metadata,
                        created_at=entry.created_at,
                        score=float(score),
                    )
                )

        scored.sort(key=lambda item: (item.score, item.created_at), reverse=True)
        return scored[:top_k]

    def clear(self) -> None:
        self._messages.clear()
        self._long_term.clear()

    def clear_messages(self) -> None:
        self._messages.clear()

    def clear_long_term(self) -> None:
        self._long_term.clear()


class MemoryProcessor:
    """High-level memory operations used by the agent runtime."""

    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store or InMemoryStore()

    def record_turn(self, user: Message, assistant: Message) -> None:
        self.store.add_message(user)
        self.store.add_message(assistant)

    def record_messages(self, messages: Iterable[Message]) -> None:
        for message in messages:
            self.store.add_message(message)

    def build_recall_context(self, query: str, top_k: int = 3) -> str:
        entries = self.store.recall(query, top_k=top_k)
        if not entries:
            return ""
        lines = [f"- [{entry.key}] {entry.content}" for entry in entries]
        return "Relevant memories:\n" + "\n".join(lines)

    def summarize_recent(self, limit: int = 10) -> str:
        messages = self.store.get_messages(limit=limit)
        if not messages:
            return ""
        lines: list[str] = []
        for message in messages:
            if message.role in {Role.USER, Role.ASSISTANT}:
                lines.append(f"{message.role}: {message.content}")
        return "\n".join(lines)


def _tokenize(text: str) -> list[str]:
    return [token for token in re.split(r"\W+", text.lower()) if token]
