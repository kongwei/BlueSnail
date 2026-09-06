"""Memory module tests."""

from bluesnail.memory import MemoryProcessor


def test_memory_recall() -> None:
    memory = MemoryProcessor()
    memory.store.remember("python", "Python 3.12 supports better typing.")
    hits = memory.store.recall("python typing")
    assert hits
    assert hits[0].key == "python"


def test_summarize_recent() -> None:
    from bluesnail.core.types import Message, Role

    memory = MemoryProcessor()
    memory.record_turn(
        Message(role=Role.USER, content="hi"),
        Message(role=Role.ASSISTANT, content="hello"),
    )
    summary = memory.summarize_recent()
    assert "hi" in summary
    assert "hello" in summary
