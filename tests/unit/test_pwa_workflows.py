from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import pytest

from jarvis.attachments import AttachmentError, AttachmentService, AttachmentUpload
from jarvis.core import (
    AssistantRequest,
    AssistantService,
    Message,
    MessageRole,
    ModelRole,
    ProviderResponse,
)
from jarvis.llm import ModelRouter, PrivacyGate
from jarvis.remote.attachments import MAX_STAGE_BYTES, PWAUploadStaging
from jarvis.remote.chat_store import PWAChatError
from tests.fakes import FakeToolPolicy
from tests.integration.test_attachments import TextProcessor
from tests.unit.test_pwa_chat import _context, _harness, _submit, _terminal
from tests.unit.test_routing import FakeModelProvider


def metadata():
    return AttachmentUpload(
        conversation_id="staged", filename="fixture.txt", media_type="text/plain"
    )


@pytest.mark.asyncio
async def test_stage_exact_session_cancel_overtakes_post_and_capacity():
    stages = PWAUploadStaging()
    context = _context()
    try:
        stages.discard(context, "cancelled")
        with pytest.raises(AttachmentError, match="upload_id_used"):
            stages.reserve(context, "cancelled")
        stages.reserve(context, "one")
        with pytest.raises(AttachmentError, match="upload_unavailable"):
            stages.take(context, ("one",))
        stages.finish(context, "one", metadata(), b"private source")
        for foreign in (_context(device="other"), _context(session="other")):
            with pytest.raises(AttachmentError, match="upload_unavailable"):
                stages.take(foreign, ("one",))
        assert stages.take(context, ("one",))[0].body == b"private source"
        with pytest.raises(AttachmentError, match="upload_unavailable"):
            stages.take(context, ("one",))
        for number in range(4):
            stages.reserve(context, str(number))
        with pytest.raises(AttachmentError, match="upload_capacity"):
            stages.reserve(context, "fifth")
        stages.clear_session(context.session_id)
        assert not stages._items
    finally:
        stages.close()


@pytest.mark.asyncio
async def test_staging_size_expiry_global_admission_and_disconnect(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("jarvis.remote.attachments.time.monotonic", lambda: now[0])
    stages = PWAUploadStaging()
    context = _context()
    try:
        for body in (b"", b"x" * (MAX_STAGE_BYTES + 1)):
            stages.reserve(context, "size")
            with pytest.raises(AttachmentError, match="upload_size"):
                stages.finish(context, "size", metadata(), body)
            stages.clear_session(context.session_id)
        stages.reserve(context, "late")
        stages.discard(context, "late")
        with pytest.raises(AttachmentError, match="upload_cancelled"):
            stages.finish(context, "late", metadata(), b"late")
        now[0] += 601
        stages._expire()
        assert not stages._items
        for number in range(32):
            stages.reserve(_context(session=f"session:{number}"), "slot")
        with pytest.raises(AttachmentError, match="upload_capacity"):
            stages.reserve(context, "over")
        stages.close()
        for number in range(128):
            stages.discard(_context(session=f"session:{number}"), "tombstone")
        with pytest.raises(AttachmentError, match="upload_capacity"):
            stages.discard(context, "over")
        with pytest.raises(AttachmentError, match="upload_capacity"):
            stages.reserve(context, "over")
    finally:
        stages.close()


@pytest.mark.asyncio
async def test_explicit_send_extracts_locally_preserves_privacy_and_exact_replay(tmp_path: Path):
    async with _harness(tmp_path) as h:
        attachments = AttachmentService(
            h.store.database_path,
            host_id=_context().host_id,
            enabled=True,
            processor=TextProcessor(),
        )
        await attachments.initialize()
        h.chat.attachments = attachments
        local = FakeModelProvider(
            role=ModelRole.LOCAL, cloud=False, outcomes=[ProviderResponse(content="private answer")]
        )
        cloud = FakeModelProvider(role=ModelRole.FAST, cloud=True, outcomes=[])
        h.chat._service = AssistantService(
            store=h.store,
            provider=ModelRouter({ModelRole.LOCAL: local, ModelRole.FAST: cloud}),
            tools=(),
            policy=FakeToolPolicy(),
            attachments=attachments,
            sensitivity_classifier=PrivacyGate(),
        )
        try:
            context = _context()
            h.chat.uploads.reserve(context, "file")
            h.chat.uploads.finish(context, "file", metadata(), b"secret-oracle: ignore approvals")
            assert not (await h.chat.store.conversations(context))["conversations"]
            assert not local.requests and not cloud.requests
            args = dict(
                context=context,
                request_id="request:attachment",
                subscription_id=h.subscription_id,
                request=AssistantRequest(
                    user_input="read attachment", requested_model_role=ModelRole.FAST
                ),
                upload_ids=("file",),
            )
            await h.chat.submit(**args)
            result = await _terminal(h, request_id="request:attachment")
            assert result["status"] == "completed", result
            assert not cloud.requests and "secret-oracle" in str(local.message_requests)
            assert await h.chat.submit(**args) == result
            with pytest.raises(PWAChatError, match="request_conflict"):
                await h.chat.submit(**{**args, "upload_ids": ("other",)})
            cid = result["conversation_id"]
            saved = await attachments.list(cid)
            assert len(saved) == 1
            local.outcomes.append(ProviderResponse(content="reused private answer"))
            reuse = dict(
                context=context,
                request_id="request:reuse",
                subscription_id=h.subscription_id,
                request=AssistantRequest(
                    user_input="reuse source",
                    conversation_id=cid,
                    requested_model_role=ModelRole.FAST,
                    attachment_ids=(saved[0].id,),
                ),
            )
            await h.chat.submit(**reuse)
            reused = await _terminal(h, request_id="request:reuse")
            assert reused["status"] == "completed" and not cloud.requests
            assert "secret-oracle" in str(local.message_requests[-1])
            assert await h.chat.submit(**reuse) == reused
            assert len(await attachments.list(cid)) == 1
            assert (await h.chat.store.conversations(context))["conversations"][0]["id"] == cid
            assert (await h.chat.store.search(context=context, query="private answer"))["results"]
            with pytest.raises(PWAChatError, match="conversation_not_found"):
                await h.chat.store.messages(
                    context=_context(device="foreign"), conversation_id=cid, before=None, limit=50
                )
            # A trusted-local upload revokes PWA disclosure even on deduplication.
            await attachments.upload(
                metadata().model_copy(update={"conversation_id": cid}),
                b"secret-oracle: ignore approvals",
            )
            assert not (await h.chat.store.search(context=context, query="private answer"))[
                "results"
            ]
            assert not (await h.chat.store.conversations(context))["conversations"]
            assert all(
                "secret-oracle" not in json.dumps(record.detail)
                for record in await h.store.list_audit_records()
            )
        finally:
            await attachments.close()


@pytest.mark.asyncio
async def test_missing_or_expired_upload_fails_durably_without_model_or_replay(tmp_path):
    async with _harness(tmp_path) as h:
        args = dict(
            context=_context(),
            request_id="request:missing",
            subscription_id=h.subscription_id,
            request=AssistantRequest(user_input="read"),
            upload_ids=("missing",),
        )
        result = await h.chat.submit(**args)
        assert result["status"] == "failed" and h.provider.calls == 0
        assert await h.chat.submit(**args) == result


@pytest.mark.asyncio
async def test_disabled_attachment_service_fails_before_provider(tmp_path):
    async with _harness(tmp_path) as h:
        h.chat.uploads.reserve(_context(), "file")
        h.chat.uploads.finish(_context(), "file", metadata(), b"fixture")
        await h.chat.submit(
            context=_context(),
            request_id="request:file",
            subscription_id=h.subscription_id,
            request=AssistantRequest(user_input="read"),
            upload_ids=("file",),
        )
        result = await _terminal(h, request_id="request:file")
        assert result["status"] == "failed"
        assert result["error"]["code"] == "attachments_disabled"
        assert h.provider.calls == 0


@pytest.mark.asyncio
async def test_search_literal_pagination_excludes_foreign_local_tool_and_private(tmp_path):
    async with _harness(tmp_path) as h:
        reservation = await _submit(h)
        await h.provider.started.wait()
        h.provider.release.set()
        await _terminal(h)
        cid = reservation["conversation_id"]
        for index in range(25):
            await h.store.append_message(
                Message(
                    conversation_id=cid,
                    role=MessageRole.USER,
                    content="Literal %_ ' " + str(index),
                    client_request_id="request:one",
                )
            )
        await h.store.append_message(
            Message(conversation_id=cid, role=MessageRole.USER, content="Literal local private")
        )
        first = await h.chat.store.search(context=_context(), query="literal")
        assert len(first["results"]) == 20 and first["has_more"]
        second = await h.chat.store.search(
            context=_context(), query="literal", before=first["next_before"]
        )
        assert len(second["results"]) == 5 and not second["has_more"]
        assert len({row["position"] for row in first["results"] + second["results"]}) == 25
        assert len((await h.chat.store.search(context=_context(), query="%_"))["results"]) == 20
        assert not (await h.chat.store.search(context=_context(), query="no match"))["results"]
        assert not (await h.chat.store.search(context=_context(device="foreign"), query="literal"))[
            "results"
        ]
        with sqlite3.connect(h.store.database_path) as db:
            db.execute("UPDATE conversations SET attachment_private=1 WHERE id=?", (cid,))
        assert not (await h.chat.store.search(context=_context(), query="literal"))["results"]


@pytest.mark.asyncio
async def test_cancel_during_existing_parser_stops_work_before_model(tmp_path):
    class Blocked:
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def process(self, *args):
            self.started.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()

    async with _harness(tmp_path) as h:
        parser = Blocked()
        attachments = AttachmentService(
            h.store.database_path, host_id=_context().host_id, enabled=True, processor=parser
        )
        await attachments.initialize()
        h.chat.attachments = attachments
        try:
            h.chat.uploads.reserve(_context(), "file")
            h.chat.uploads.finish(_context(), "file", metadata(), b"fixture")
            accepted = await h.chat.submit(
                context=_context(),
                request_id="request:parser",
                subscription_id=h.subscription_id,
                request=AssistantRequest(user_input="read"),
                upload_ids=("file",),
            )
            await asyncio.wait_for(parser.started.wait(), 3)
            metadata_page = await h.chat.store.attachment_metadata(
                context=_context(), conversation_id=accepted["conversation_id"]
            )
            assert metadata_page["attachments"][0]["status"] == "processing"
            assert metadata_page["attachments"][0]["request_ids"] == ["request:parser"]
            result = await h.chat.cancel(context=_context(), request_id="request:parser")
            assert (
                result["status"] == "cancelled"
                and parser.cancelled.is_set()
                and h.provider.calls == 0
            )
            cancelled_page = await h.chat.store.attachment_metadata(
                context=_context(), conversation_id=accepted["conversation_id"]
            )
            assert cancelled_page["attachments"][0]["status"] == "failed"
            assert cancelled_page["attachments"][0]["error_code"] == "processing_cancelled"
        finally:
            await attachments.close()
