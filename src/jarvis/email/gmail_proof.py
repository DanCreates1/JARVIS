"""One explicitly selected bounded live read; only sanitized aggregates leave the command."""

from __future__ import annotations

from time import perf_counter

from .gmail import GmailReadProvider
from .models import EmailError, EmailMessage, EmailThread
from .service import EmailService


async def selected_thread_proof(
    provider: GmailReadProvider, provider_thread_id: str
) -> dict[str, object]:
    if provider._max_messages != 3:
        raise EmailError("gmail_proof_configuration")
    started = perf_counter()
    thread = await provider.read_thread(provider.canonical_id(provider_thread_id, kind="t"))

    class Snapshot:
        async def read_thread(self, thread_id: str) -> EmailThread:
            if thread_id != thread.id:
                raise EmailError("gmail_provenance")
            return thread

        async def list_threads(self) -> tuple[str, ...]:
            raise EmailError("gmail_proof_configuration")

        async def read_message(self, thread_id: str, message_id: str) -> EmailMessage:
            selected = await self.read_thread(thread_id)
            for message in selected.messages:
                if message.id == message_id:
                    return message
            raise EmailError("message_not_found")

    # Preparation reuses the observed volatile thread; never repeats the selected network read.
    service = EmailService(Snapshot(), source_kind="provider")
    summary = await service.summarize(thread.id)
    extracted = await service.extract(thread.id)
    projection = await service.project(thread.id)
    draft = await service.draft(
        thread.id,
        recipients=("owner@example.invalid",),
        subject="Phase 15 unsent preparation proof",
        body="Owner-reviewed proposal only. Do not send.",
    )
    valid_ids = {item.id for item in thread.messages}
    if (
        any(item.message_id not in valid_ids for item in (*summary.evidence, *extracted.evidence))
        or len(projection.content) > 8000
        or draft.sent
        or draft.stored
    ):
        raise EmailError("gmail_proof_failed")
    return {
        "pass": True,
        "threads": 1,
        "messages": len(thread.messages),
        "elapsed_ms": round((perf_counter() - started) * 1000, 3),
        "provenance_verified": True,
        "draft_sent": False,
        "draft_stored": False,
        "mailbox_cache": False,
        "cloud_calls": 0,
        "research_calls": 0,
        "provider_writes": 0,
        "cost_usd": 0,
    }
