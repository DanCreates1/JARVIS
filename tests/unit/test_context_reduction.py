from __future__ import annotations

from jarvis.core.context import reduce_conversation_context
from jarvis.core.models import Message, MessageRole, SensitivityClass
from jarvis.llm import PrivacyGate


def _message(role: MessageRole, content: str) -> Message:
    return Message(conversation_id="conversation", role=role, content=content)


def test_context_reduction_summarizes_only_relevant_older_turns_locally() -> None:
    messages = (
        _message(MessageRole.USER, "Discuss public planets and orbital periods."),
        _message(MessageRole.ASSISTANT, "Planets have different orbital periods."),
        _message(MessageRole.USER, "Unrelated cooking question."),
        _message(MessageRole.ASSISTANT, "Use a saucepan."),
        _message(MessageRole.USER, "Explain public planet orbital periods."),
        _message(MessageRole.ASSISTANT, "I will explain them."),
    )

    reduced = reduce_conversation_context(
        messages,
        recent_limit=2,
        summary_max_chars=1_000,
        classify=PrivacyGate().classify,
    )

    assert len(reduced) == 3
    summary = reduced[0]
    assert summary.context_source == "local-conversation-summary"
    assert "orbital periods" in summary.content
    assert "saucepan" not in summary.content
    assert reduced[-2:] == messages[-2:]


def test_relevant_private_summary_keeps_cloud_boundary_closed() -> None:
    messages = (
        _message(MessageRole.USER, "My email is benchmark@example.invalid for planet notes."),
        _message(MessageRole.ASSISTANT, "That planet note is private."),
        _message(MessageRole.USER, "Unrelated public fact."),
        _message(MessageRole.ASSISTANT, "A public fact."),
        _message(MessageRole.USER, "Explain planet notes."),
        _message(MessageRole.ASSISTANT, "Working."),
    )

    reduced = reduce_conversation_context(
        messages,
        recent_limit=2,
        summary_max_chars=1_000,
        classify=PrivacyGate().classify,
    )

    assert reduced[0].disclosure_sensitivity is SensitivityClass.PRIVATE


def test_summary_does_not_turn_ambiguous_text_public_from_an_old_label() -> None:
    ambiguous = _message(MessageRole.ASSISTANT, "Use that planet one.").model_copy(
        update={"disclosure_sensitivity": SensitivityClass.PUBLIC}
    )
    messages = (
        _message(MessageRole.USER, "Discuss a planet option."),
        ambiguous,
        _message(MessageRole.USER, "Unrelated public fact."),
        _message(MessageRole.ASSISTANT, "A public fact."),
        _message(MessageRole.USER, "Use that planet option."),
        _message(MessageRole.ASSISTANT, "Working."),
    )

    reduced = reduce_conversation_context(
        messages,
        recent_limit=2,
        summary_max_chars=1_000,
        classify=PrivacyGate().classify,
    )

    assert reduced[0].disclosure_sensitivity is SensitivityClass.UNKNOWN
