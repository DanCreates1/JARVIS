"""Host-bound Phase 4 memory workflows used by runtime and local interfaces."""

from __future__ import annotations

from datetime import UTC, datetime

from jarvis.core import ContextProjection, Message, MessageRole
from jarvis.memory.extraction import extract_memory_candidates
from jarvis.memory.models import (
    MemoryCategory,
    MemoryItem,
    MemoryQuery,
    MemoryState,
    ProvenanceSource,
)
from jarvis.memory.sqlite_memory import SQLiteMemoryStore, untrusted_provenance


class MemoryManager:
    """Bind a store to authenticated/local host scope; request text cannot select the host."""

    def __init__(self, store: SQLiteMemoryStore, *, host_id: str) -> None:
        self.store = store
        self.host_id = host_id

    async def capture_candidates(self, message: Message) -> int:
        if message.role is not MessageRole.USER or message.id is None:
            return 0
        extractions = extract_memory_candidates(message.content)
        for extraction in extractions:
            await self.store.propose(
                host_id=self.host_id,
                category=extraction.category,
                key=extraction.key,
                content=extraction.content,
                confidence=extraction.confidence,
                sensitivity=extraction.sensitivity,
                structured={
                    **extraction.structured,
                    "reason_code": extraction.reason_code,
                },
                provenance=untrusted_provenance(
                    source_type=ProvenanceSource.MESSAGE,
                    source_id=message.id,
                    source_label="explicit statement extracted from host message",
                    conversation_id=message.conversation_id,
                    message_id=message.id,
                    source_content=message.content,
                ),
            )
        return len(extractions)

    async def project(self, query: str) -> ContextProjection | None:
        projection = await self.store.project_for_prompt(
            MemoryQuery(host_id=self.host_id, text=query, limit=8),
            max_items=8,
            max_chars=4_000,
        )
        if not projection.memory_ids:
            return None
        return ContextProjection(
            content=projection.content,
            sensitivity=projection.sensitivity,
            source_ids=projection.memory_ids,
            source="durable_memory",
        )

    async def extract_text_candidate(
        self,
        *,
        text: str,
        conversation_id: str,
        message_id: str,
    ) -> tuple[MemoryItem, ...]:
        """Explicit test/UI helper; output remains candidate-only."""
        now = datetime.now(UTC)
        records = [
            await self.store.propose(
                host_id=self.host_id,
                category=extraction.category,
                key=extraction.key,
                content=extraction.content,
                confidence=extraction.confidence,
                sensitivity=extraction.sensitivity,
                structured={
                    **extraction.structured,
                    "reason_code": extraction.reason_code,
                },
                provenance=untrusted_provenance(
                    source_type=ProvenanceSource.MESSAGE,
                    source_id=message_id,
                    source_label="explicit statement extracted from host message",
                    conversation_id=conversation_id,
                    message_id=message_id,
                    source_content=text,
                    now=now,
                ),
                now=now,
            )
            for extraction in extract_memory_candidates(text)
        ]
        return tuple(records)

    async def committed(self, *, limit: int = 100) -> tuple[MemoryItem, ...]:
        return await self.store.list(
            host_id=self.host_id,
            states=(MemoryState.COMMITTED,),
            categories=tuple(MemoryCategory),
            limit=limit,
        )
