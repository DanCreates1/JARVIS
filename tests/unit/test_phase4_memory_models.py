from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from jarvis.core import ContextProjection, Message, MessageRole, SensitivityClass
from jarvis.llm.routing import RoutingPolicy
from jarvis.memory import (
    MemoryCategory,
    MemoryProvenance,
    ProvenanceSource,
    ProvenanceTrust,
    local_memory_host_id,
)
from jarvis.memory.extraction import extract_memory_candidates


def test_extractor_emits_typed_candidates_without_committing_truth() -> None:
    extracted = extract_memory_candidates(
        "My name is Avery. I prefer concise answers for status reports. "
        "Remind me to renew the synthetic test certificate."
    )

    assert [item.category for item in extracted] == [
        MemoryCategory.PROFILE,
        MemoryCategory.PROFILE,
        MemoryCategory.TASK,
    ]
    assert extracted[0].key == "profile.name"
    assert extracted[1].key == "preference.status.reports"
    assert all(0 <= item.confidence <= 1 for item in extracted)
    assert extract_memory_candidates("ordinary question with no explicit memory statement") == ()
    assert extract_memory_candidates("x" * 10_001) == ()


def test_provenance_requires_typed_reference_and_untrusted_extracted_content() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="typed reference"):
        MemoryProvenance(
            id="p1",
            source_type=ProvenanceSource.MESSAGE,
            source_id="message-1",
            trust=ProvenanceTrust.UNTRUSTED_CONTENT,
            created_at=now,
        )
    with pytest.raises(ValidationError, match="remains untrusted"):
        MemoryProvenance(
            id="p2",
            source_type=ProvenanceSource.MESSAGE,
            source_id="message-1",
            message_id="message-1",
            trust=ProvenanceTrust.TRUSTED_HOST,
            created_at=now,
        )


def test_local_memory_identity_is_stable_scoped_and_not_request_selected() -> None:
    first = local_memory_host_id(user_name="TestUser", device_name="TestDevice")
    second = local_memory_host_id(user_name="testuser", device_name="testdevice")
    other = local_memory_host_id(user_name="testuser", device_name="other-device")

    assert first == second
    assert first.startswith("host-memory-")
    assert first != other
    assert "testuser" not in first


def test_only_system_messages_can_carry_retrieval_sensitivity() -> None:
    projection = ContextProjection(
        content="<memory-context>synthetic</memory-context>",
        sensitivity=SensitivityClass.PRIVATE,
        source_ids=("memory-1",),
        source="durable_memory",
    )
    message = Message(
        conversation_id="conversation-1",
        role=MessageRole.SYSTEM,
        content=projection.content,
        context_sensitivity=projection.sensitivity,
        context_source=projection.source,
    )
    assert message.context_sensitivity is SensitivityClass.PRIVATE

    with pytest.raises(ValidationError, match="only system context"):
        Message(
            conversation_id="conversation-1",
            role=MessageRole.USER,
            content="synthetic",
            context_sensitivity=SensitivityClass.PRIVATE,
            context_source="durable_memory",
        )


def test_private_memory_context_forces_local_route_even_for_public_query() -> None:
    decision = RoutingPolicy().decide(
        "What color is the public sky?",
        forced_sensitivity=SensitivityClass.PRIVATE,
    )
    assert decision.sensitivity is SensitivityClass.PRIVATE
    assert decision.chosen_role.value == "local"
