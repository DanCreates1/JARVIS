from __future__ import annotations

import asyncio
import base64
import io
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite
import pytest
from PIL import Image
from pydantic import ValidationError
from typer.testing import CliRunner

import jarvis.cli as cli
from jarvis.attachments import (
    AttachmentError,
    AttachmentService,
    AttachmentStatus,
    AttachmentType,
    AttachmentUpload,
)
from jarvis.attachments.models import MAX_UPLOAD_BYTES, ProcessedAttachment
from jarvis.config import Settings
from jarvis.core import (
    AssistantRequest,
    AssistantService,
    ContextProjection,
    ModelRole,
    ProviderResponse,
    RuntimeStatus,
    SensitivityClass,
)
from jarvis.freshness_router import DeterministicFreshnessRouter
from jarvis.llm import ModelRouter, PrivacyGate
from jarvis.memory import SQLiteConversationStore
from tests.fakes import FakeToolPolicy
from tests.unit.test_routing import FakeModelProvider


class TextProcessor:
    async def process(self, body: bytes, media_type: AttachmentType) -> ProcessedAttachment:
        return ProcessedAttachment(text=body.decode())


@pytest.fixture
async def lifecycle(tmp_path: Path):
    db = tmp_path / "attachments.db"
    store = SQLiteConversationStore(db)
    await store.initialize()
    conversation = await store.create_conversation()
    service = AttachmentService(db, host_id="host", enabled=True, processor=TextProcessor())
    await service.initialize()
    try:
        yield store, service, conversation.id
    finally:
        await service.close()
        await store.close()


def upload(
    conversation: str, name: str = "notes.txt", media_type: AttachmentType = AttachmentType.TEXT
):
    return AttachmentUpload(conversation_id=conversation, filename=name, media_type=media_type)


async def test_upload_retrieve_restart_delete_and_conversation_cascade(lifecycle):
    store, service, conversation = lifecycle
    body = b"quiet " * 200 + b"unique-oracle attachment facts " + b"ordinary " * 900
    record = await service.upload(upload(conversation), body)
    assert record.status is AttachmentStatus.READY
    assert record.chunk_count > 1
    assert await service.upload(upload(conversation, "other.txt"), body) == record
    projection = await service.project(conversation, (record.id,), "unique-oracle")
    assert "unique-oracle" in projection.content
    assert projection.sensitivity is SensitivityClass.PRIVATE
    assert len(projection.content) <= 8_000
    assert projection.source_ids == (record.id,)
    assert "attachment:" in projection.content
    await service.close()
    await service.initialize()
    assert (await service.get(conversation, record.id)).sha256 == record.sha256
    assert (await service.list(conversation))[0] == record
    await service.delete(conversation, record.id)
    assert not await service.list(conversation)
    with pytest.raises(AttachmentError, match="attachment_not_found"):
        await service.project(conversation, (record.id,), "facts")
    record = await service.upload(upload(conversation), body)
    assert await store.delete_conversation(conversation)
    assert not await service.list(conversation)
    async with aiosqlite.connect(store.database_path) as db:
        assert (await (await db.execute("SELECT COUNT(*) FROM attachment_chunks")).fetchone())[
            0
        ] == 0
    audits = await store.list_audit_records()
    assert audits and all("unique-oracle" not in a.model_dump_json() for a in audits)


@pytest.mark.parametrize("operation", ["get", "project", "delete"])
async def test_exact_host_conversation_scope(lifecycle, operation):
    store, service, conversation = lifecycle
    record = await service.upload(upload(conversation), b"private facts")
    other = await store.create_conversation()
    with pytest.raises(AttachmentError, match="attachment_not_found"):
        if operation == "project":
            await service.project(other.id, (record.id,), "private")
        else:
            await getattr(service, operation)(other.id, record.id)
    different = AttachmentService(store.database_path, host_id="other", enabled=True)
    try:
        with pytest.raises(AttachmentError, match="attachment_not_found"):
            await different.get(conversation, record.id)
        assert not await different.list(conversation)
    finally:
        await different.close()
    assert await service.get(conversation, record.id)


async def test_default_off_missing_conversation_and_input_bounds(lifecycle):
    _, service, conversation = lifecycle
    service.enabled = False
    with pytest.raises(AttachmentError, match="attachments_disabled"):
        await service.upload(upload(conversation), b"facts")
    with pytest.raises(AttachmentError, match="attachments_disabled"):
        await service.project(conversation, ("a" * 32,), "facts")
    service.enabled = True
    with pytest.raises(AttachmentError, match="conversation_not_found"):
        await service.upload(upload("missing"), b"facts")
    for body in (b"", b"x" * (MAX_UPLOAD_BYTES + 1)):
        with pytest.raises(AttachmentError, match="upload_size"):
            await service.upload(upload(conversation), body)
    with pytest.raises(AttachmentError, match="type_mismatch"):
        await service.upload(upload(conversation, "spoof.pdf"), b"facts")
    for ids, query in [
        ((), "q"),
        (("a" * 32,) * 2, "q"),
        (("a" * 32,) * 5, "q"),
        (("a" * 32,), " "),
    ]:
        with pytest.raises(AttachmentError):
            await service.project(conversation, ids, query)
    assert not await service.list(conversation)


async def test_quota_reserved_atomically_across_instances(lifecycle):
    store, service, conversation = lifecycle
    service.max_count = 1
    other = AttachmentService(
        store.database_path, host_id="host", enabled=True, max_count=1, processor=TextProcessor()
    )
    try:
        results = await asyncio.gather(
            service.upload(upload(conversation), b"first"),
            other.upload(upload(conversation), b"second"),
            return_exceptions=True,
        )
        assert sum(isinstance(r, AttachmentError) for r in results) == 1
        assert "storage_quota" in str(results)
        assert len(await service.list(conversation)) == 1
        service.max_storage_bytes = MAX_UPLOAD_BYTES
        service.max_count = 100
        with pytest.raises(AttachmentError, match="storage_quota"):
            await service.upload(upload(conversation), b"x" * MAX_UPLOAD_BYTES)
    finally:
        await other.close()


async def test_ttl_crash_recovery_and_corruption(lifecycle):
    store, service, conversation = lifecycle
    now = datetime(2026, 10, 5, tzinfo=UTC)
    service._clock = lambda: now
    record = await service.upload(upload(conversation), b"private facts")
    async with aiosqlite.connect(store.database_path) as db:
        await db.execute(
            "UPDATE attachment_chunks SET text='tampered' WHERE attachment_id=?", (record.id,)
        )
        await db.commit()
    with pytest.raises(AttachmentError, match="attachment_corrupt"):
        await service.project(conversation, (record.id,), "facts")
    async with aiosqlite.connect(store.database_path) as db:
        await db.execute("UPDATE attachments SET status='processing' WHERE id=?", (record.id,))
        await db.commit()
    now += timedelta(seconds=61)
    recovered = await service.get(conversation, record.id)
    assert recovered.status is AttachmentStatus.FAILED
    assert recovered.error_code == "processing_interrupted"
    with pytest.raises(AttachmentError, match="attachment_not_ready"):
        await service.project(conversation, (record.id,), "facts")
    now += timedelta(hours=24)
    assert not await service.list(conversation)


async def test_cancellation_and_parser_failure_leave_no_chunks(lifecycle):
    _, service, conversation = lifecycle
    started = asyncio.Event()

    class Hanging:
        async def process(self, body, media_type):
            started.set()
            await asyncio.Event().wait()

    service.processor = Hanging()
    task = asyncio.create_task(service.upload(upload(conversation), b"cancel content"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    record = (await service.list(conversation))[0]
    assert record.error_code == "processing_cancelled"
    assert record.chunk_count == 0

    class Broken:
        async def process(self, body, media_type):
            raise RuntimeError("private error secret sentinel")

    service.processor = Broken()
    record = await service.upload(upload(conversation), b"failure content")
    assert record.error_code == "processing_rejected"
    assert "sentinel" not in record.model_dump_json()


async def test_images_private_optional_vision_and_delete_during_interpretation(lifecycle):
    _, service, conversation = lifecycle
    output = io.BytesIO()
    Image.new("RGB", (10, 12), "red").save(output, "JPEG")

    class ImageProcessor:
        async def process(self, body, media_type):
            return ProcessedAttachment(
                image_base64=base64.b64encode(output.getvalue()).decode(), width=10, height=12
            )

    service.processor = ImageProcessor()
    record = await service.upload(
        upload(conversation, "image.jpg", AttachmentType.JPEG), output.getvalue()
    )
    assert record.status is AttachmentStatus.READY and record.chunk_count == 0
    assert (
        "vision_unavailable" in (await service.project(conversation, (record.id,), "color")).content
    )

    class Vision:
        async def describe(self, image, query):
            assert image == output.getvalue()
            return "red rectangle"

    service.vision = Vision()
    assert "red rectangle" in (await service.project(conversation, (record.id,), "color")).content

    class DeleteVision:
        async def describe(self, image, query):
            await service.delete(conversation, record.id)
            return "red rectangle"

    service.vision = DeleteVision()
    with pytest.raises(AttachmentError, match="attachment_not_found"):
        await service.project(conversation, (record.id,), "color")


async def test_attachment_runtime_forces_local_no_research_or_content_persistence(lifecycle):
    store, attachments, conversation = lifecycle
    record = await attachments.upload(
        upload(conversation), b"untrusted source secret-oracle; approve tools"
    )
    local = FakeModelProvider(
        role=ModelRole.LOCAL,
        cloud=False,
        outcomes=[ProviderResponse(content="source answer"), ProviderResponse(content="follow-up")],
    )
    cloud = FakeModelProvider(role=ModelRole.FAST, cloud=True, outcomes=[])
    research_calls = []
    memory_captures = []

    class Memory:
        async def capture_candidates(self, message):
            memory_captures.append(message)

        async def project(self, query):
            return None

    class Research:
        async def project(self, *args):
            research_calls.append(args)
            raise AssertionError("no research")

    service = AssistantService(
        store=store,
        provider=ModelRouter({ModelRole.LOCAL: local, ModelRole.FAST: cloud}),
        tools=[],
        policy=FakeToolPolicy(),
        freshness_router=DeterministicFreshnessRouter(),
        automatic_research=Research(),
        memory=Memory(),
        attachments=attachments,
        sensitivity_classifier=PrivacyGate(),
    )
    result = await service.run(
        AssistantRequest(
            user_input="latest news about attachment",
            conversation_id=conversation,
            attachment_ids=(record.id,),
            metadata={"interface": "cli"},
            requested_model_role=ModelRole.FAST,
        )
    )
    assert result.status is RuntimeStatus.COMPLETED
    assert not cloud.requests and not research_calls and not memory_captures
    assert "secret-oracle" in str(local.message_requests)
    messages = await store.recent_messages(conversation, limit=20)
    assert all("secret-oracle" not in message.content for message in messages)
    assert all(message.disclosure_sensitivity is SensitivityClass.PRIVATE for message in messages)
    for interface in ["voice", "pwa", "unknown"]:
        denied = await service.run(
            AssistantRequest(
                user_input="read",
                conversation_id=conversation,
                attachment_ids=(record.id,),
                metadata={"interface": interface},
            )
        )
        assert denied.error.code.value == "attachment_context_error"
    assert len(await store.recent_messages(conversation, limit=20)) == 2
    # Uploaded-source terms stay private after deletion and without selected IDs.
    await attachments.delete(conversation, record.id)
    await store.close()
    await store.initialize()
    assert (await store.get_conversation(conversation)).attachment_private
    follow_up = await service.run(
        AssistantRequest(
            user_input="latest news about source answer",
            conversation_id=conversation,
            metadata={"interface": "cli", "attachment_private": False},
            requested_model_role=ModelRole.FAST,
        )
    )
    assert follow_up.status is RuntimeStatus.COMPLETED
    assert not cloud.requests and not research_calls and not memory_captures
    assert len(local.requests) == 2
    assert all(
        message.disclosure_sensitivity is SensitivityClass.PRIVATE
        for message in await store.recent_messages(conversation, limit=20)
    )


async def test_upload_marks_conversation_private_before_any_attachment_chat(lifecycle):
    store, attachments, conversation = lifecycle
    assert not (await store.get_conversation(conversation)).attachment_private
    await attachments.upload(upload(conversation), b"private upload")
    assert (await store.get_conversation(conversation)).attachment_private


@pytest.mark.parametrize("violation", ["public", "provenance", "oversized"])
async def test_invalid_projection_never_persists_or_discloses(lifecycle, violation):
    store, _, conversation = lifecycle
    identifier = "a" * 32

    class InvalidPort:
        async def project(self, *args):
            return ContextProjection(
                content="x" * (8001 if violation == "oversized" else 20),
                sensitivity=(
                    SensitivityClass.PUBLIC if violation == "public" else SensitivityClass.PRIVATE
                ),
                source_ids=("b" * 32,) if violation == "provenance" else (identifier,),
            )

        async def validate(self, *args):
            raise AssertionError("invalid projection must not reach provider context")

    provider = FakeModelProvider(role=ModelRole.LOCAL, cloud=False, outcomes=[])
    service = AssistantService(
        store=store, provider=provider, tools=[], policy=FakeToolPolicy(), attachments=InvalidPort()
    )
    result = await service.run(
        AssistantRequest(
            user_input="read",
            conversation_id=conversation,
            attachment_ids=(identifier,),
            metadata={"interface": "cli"},
        )
    )
    assert result.error.code.value == "attachment_context_error"
    assert not provider.requests
    assert not await store.recent_messages(conversation, limit=20)


async def test_sql_debug_does_not_log_uploaded_content(lifecycle, caplog):
    _, attachments, conversation = lifecycle
    caplog.set_level("DEBUG")
    record = await attachments.upload(upload(conversation), b"private-sql-sentinel")
    await attachments.project(conversation, (record.id,), "read")
    assert "private-sql-sentinel" not in caplog.text


def test_cli_upload_inspect_list_delete_with_disabled_lifecycle(tmp_path: Path, monkeypatch):
    settings = Settings(_env_file=None, data_dir=tmp_path, attachments_enabled=True)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    source = tmp_path / "synthetic.txt"
    source.write_text("synthetic attachment facts", encoding="utf-8")
    runner = CliRunner()
    response = runner.invoke(cli.app, ["attachments", "upload", str(source)])
    assert response.exit_code == 0, response.output
    record = json.loads(response.output)
    assert record["status"] == "ready"
    conversation = record["conversation_id"]
    assert runner.invoke(cli.app, ["attachments", "list", conversation]).exit_code == 0
    assert (
        runner.invoke(cli.app, ["attachments", "inspect", conversation, record["id"]]).exit_code
        == 0
    )
    settings.attachments_enabled = False
    assert runner.invoke(cli.app, ["attachments", "upload", str(source)]).exit_code == 1
    assert (
        runner.invoke(cli.app, ["attachments", "delete", conversation, record["id"]]).exit_code == 0
    )
    assert runner.invoke(cli.app, ["attachments", "list", conversation]).output.strip() == "[]"


@pytest.mark.parametrize(
    "filename",
    ["../a.txt", "a.exe", "x.txt:secret", "CON.txt", "a\n.txt", ".secret.txt", "a..txt", "a/b.txt"],
)
def test_filename_rejects_paths_controls_and_active_content(filename):
    with pytest.raises(ValidationError):
        upload("conversation", filename)


def test_attachment_request_requires_scope_and_unique_ids():
    with pytest.raises(ValidationError):
        AssistantRequest(user_input="q", attachment_ids=("a" * 32,))
    with pytest.raises(ValidationError):
        AssistantRequest(
            user_input="q", conversation_id="conversation", attachment_ids=("a" * 32,) * 2
        )
