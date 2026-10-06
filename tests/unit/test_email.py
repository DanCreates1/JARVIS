from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.email import (
    EmailError,
    EmailService,
    EmailThread,
    LocalEmailExports,
    build_email_service,
)
from jarvis.email.models import EmailDraft, EmailMessage
from jarvis.email.processing import IsolatedEmailParser


def message(**changes):
    return EmailMessage(
        **{
            "id": "m1",
            "thread_id": "t1",
            "sender": "sender@example.invalid",
            "recipients": "owner@example.invalid",
            "subject": "Synthetic",
            "date": "unknown",
            "text": "Please review proposal by 2026-10-09.\nNo decision yet.",
            "sha256": "a" * 64,
            **changes,
        }
    )


class Provider:
    async def read_thread(self, thread_id):
        return EmailThread(id=thread_id, messages=(message(thread_id=thread_id),))

    async def read_message(self, thread_id, message_id):
        return message(thread_id=thread_id, id=message_id)

    async def list_threads(self):
        return ("t1",)


async def test_prepare_quotes_no_inferred_action_or_recipient():
    service = EmailService(Provider())
    assert await service.list_threads() == ("t1",)
    summary = await service.summarize("t1")
    assert summary.summary_kind == "extractive" and not summary.creates_tasks
    assert summary.evidence[0].quote == message().text
    candidates = await service.extract("t1")
    assert [item.kind for item in candidates.evidence] == ["action_candidate", "date_candidate"]
    assert all(item.message_id == "m1" for item in candidates.evidence)
    draft = await service.draft(
        "t1", recipients=("chosen@example.invalid",), subject="Owner subject", body="Owner response"
    )
    assert draft.recipients == ("chosen@example.invalid",) and not draft.sent and not draft.stored
    assert not hasattr(service, "send") and not hasattr(service.provider, "send")


@pytest.mark.parametrize(
    "changes",
    [
        {"recipients": ("victim@example.invalid\r\nBcc: other@example.invalid",)},
        {"recipients": ("Display <someone@example.invalid>",)},
        {"recipients": ("one@example.invalid", "one@example.invalid")},
        {"subject": "subject\nBcc: other"},
        {"body": "\x00"},
        {"body": " "},
        {"body": "x" * 8001},
        {"sent": True},
        {"stored": True},
    ],
)
def test_draft_validation(changes):
    with pytest.raises(ValidationError):
        EmailDraft(
            **{
                "thread_id": "t1",
                "recipients": ("one@example.invalid",),
                "subject": "subject",
                "body": "body",
                **changes,
            }
        )


async def test_disabled_and_missing_root():
    assert build_email_service(None, enabled=False) is None
    with pytest.raises(EmailError, match="email_root_required"):
        build_email_service(None, enabled=True)
    service = EmailService(Provider(), enabled=False)
    with pytest.raises(EmailError, match="email_disabled"):
        await service.read_thread("t1")
    with pytest.raises(EmailError, match="email_disabled"):
        await service.list_threads()


@pytest.mark.parametrize("variant", ["id", "message_thread", "duplicate"])
async def test_untrusted_provider_provenance(variant):
    class Bad(Provider):
        async def read_thread(self, thread_id):
            return EmailThread(
                id="wrong" if variant == "id" else thread_id,
                messages=(
                    (message(), message())
                    if variant == "duplicate"
                    else (message(thread_id="wrong" if variant == "message_thread" else thread_id),)
                ),
            )

    with pytest.raises(EmailError, match="provider_provenance"):
        await EmailService(Bad()).read_thread("t1")


async def test_disable_during_read_and_cancellation():
    gate = asyncio.Event()

    class Wait(Provider):
        async def read_thread(self, thread_id):
            await gate.wait()
            return await super().read_thread(thread_id)

    service = EmailService(Wait())
    task = asyncio.create_task(service.read_thread("t1"))
    await asyncio.sleep(0)
    service.enabled = False
    gate.set()
    with pytest.raises(EmailError, match="email_disabled"):
        await task
    service.enabled = True
    gate.clear()
    task = asyncio.create_task(service.read_thread("t1"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_max_projection_unicode_and_long_ids():
    class Many(Provider):
        async def read_thread(self, thread_id):
            return EmailThread(
                id=thread_id,
                messages=tuple(
                    message(
                        id=f"m{i}" + "x" * 60,
                        thread_id=thread_id,
                        subject='"' * 512,
                        date='"' * 512,
                        text='漢\n"\\' * 8000,
                    )
                    for i in range(16)
                ),
            )

    projection = await EmailService(Many()).project("t" * 64)
    assert len(projection.content) <= 8000
    assert projection.sensitivity.value == "private"
    assert projection.source_ids == ("t" * 64,)
    assert "email:" in projection.content and "omitted" in projection.content


async def test_real_exports_restart_removal_and_read(tmp_path: Path):
    root = tmp_path / "exports"
    (root / "t1").mkdir(parents=True)
    raw = b"From: sender@example.invalid\nSubject: Synthetic\n\nPlease review by 2026-10-09."
    source = root / "t1" / "m1.eml"
    source.write_bytes(raw)
    adapter = LocalEmailExports(root)
    assert await adapter.list_threads() == ("t1",)
    item = await adapter.read_message("t1", "m1")
    assert item.sha256 == hashlib.sha256(raw).hexdigest()
    assert item.text == "Please review by 2026-10-09."
    assert await LocalEmailExports(root).read_thread("t1") == await adapter.read_thread("t1")
    with pytest.raises(EmailError, match="message_not_found"):
        await adapter.read_message("t1", "missing")
    assert source.read_bytes() == raw
    source.unlink()
    with pytest.raises(EmailError, match="thread_empty"):
        await adapter.read_thread("t1")


async def test_real_parser_mime_excludes_html_attachments_and_forwarded_mail():
    raw = (
        b"MIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=x\n\n"
        b"--x\nContent-Type: text/plain; charset=utf-8\n\nplain-oracle\n"
        b"--x\nContent-Type: text/html\n\n<img src='https://tracking.invalid/pixel'>\n"
        b"--x\nContent-Type: text/plain\nContent-Disposition: attachment; filename=evil.txt\n\n"
        b"attachment-oracle\n--x\nContent-Type: message/rfc822\n\nSubject: forward\n\n"
        b"forward-oracle\n--x--\n"
    )
    parsed = await IsolatedEmailParser().parse(raw, thread_id="t1", message_id="m1")
    assert parsed.text == "plain-oracle"


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"x" * 131073,
        b"Content-Type: text/html\n\n<script>evil</script>",
        b"Subject: one\nSubject: two\n\nbody",
        b"Content-Type: text/plain; charset=unknown\n\ntext",
        b"Content-Type: multipart/mixed; boundary=x\n\n--x\n\nno closing boundary",
        b"Content-Type: text/plain; charset=utf-8\n\n\xff",
    ],
    ids=["empty", "oversized", "html", "duplicate-header", "charset", "boundary", "encoding"],
)
async def test_real_parser_rejects_malformed_size_and_unsupported(raw):
    with pytest.raises(EmailError):
        await IsolatedEmailParser().parse(raw, thread_id="t1", message_id="m1")


async def test_parser_timeout_cancel_reap_minimal_environment(tmp_path, monkeypatch):
    import jarvis.email.processing as processing

    parser = IsolatedEmailParser(timeout_seconds=0.05)
    worker = tmp_path / "hang.py"
    worker.write_text("import time; time.sleep(60)", encoding="utf-8")
    parser.worker = worker
    original = processing.asyncio.create_subprocess_exec
    children = []
    spawned = asyncio.Event()

    async def capture(*args, **kwargs):
        assert set(kwargs["env"]) <= {"SystemRoot", "WINDIR"}
        child = await original(*args, **kwargs)
        children.append(child)
        spawned.set()
        return child

    monkeypatch.setattr(processing.asyncio, "create_subprocess_exec", capture)
    monkeypatch.setenv("JARVIS_EMAIL_SECRET", "sentinel")
    with pytest.raises(EmailError, match="parser_timeout"):
        await parser.parse(b"Subject: x\n\nbody", thread_id="t1", message_id="m1")
    assert children and all(child.returncode is not None for child in children)
    parser.timeout_seconds = 5
    spawned.clear()
    task = asyncio.create_task(parser.parse(b"Subject: x\n\nbody", thread_id="t1", message_id="m1"))
    await asyncio.wait_for(spawned.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(child.returncode is not None for child in children)
