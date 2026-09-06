"""Context module tests."""

from bluesnail.context import ContextManager
from bluesnail.core.types import Message, Role


def test_context_trimming() -> None:
    context = ContextManager()
    messages = [
        Message(role=Role.USER, content="hello"),
        Message(role=Role.ASSISTANT, content="hi"),
    ]
    window = context.build(system_prompt="system", messages=messages)
    llm_messages = context.to_llm_messages(window)
    assert llm_messages[0].role == Role.SYSTEM
    assert len(llm_messages) >= 2
