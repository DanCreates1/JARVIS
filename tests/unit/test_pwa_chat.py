from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
import pytest

from jarvis.core import (
    AssistantRequest,
    AssistantService,
    Message,
    MessageRole,
    ProviderResponse,
    ToolCall,
    ToolDefinition,
)
from jarvis.memory import SQLiteConversationStore
from jarvis.remote import PWAEventHub, PWAEventTopic, PWATransportError
from jarvis.remote.chat import PWAChatCoordinator
from jarvis.remote.chat_store import MAX_CHAT_RESPONSE_BYTES, PWAChatError, SQLitePWAChatStore
from jarvis.remote.service import RemoteAuthenticationError
from tests.fakes import FakeChatProvider, FakeToolPolicy
from tests.unit.test_phase8_pwa_transport import _context


@pytest.mark.parametrize(
    "missing_columns",
    [(), ("start_sequence",), ("end_sequence",), ("start_sequence", "end_sequence")],
)
async def test_legacy_phone_schema_preserves_receipts_and_supports_retry(
    tmp_path: Path, missing_columns: tuple[str, ...]
) -> None:
    database = tmp_path / "legacy-phone.db"
    original = SQLitePWAChatStore(database)
    await original.initialize()
    _, accepted = await original.reserve(
        context=_context(),
        request_id="request:preserved",
        fingerprint="original",
        conversation_id=None,
    )
    completed = {**accepted, "status": "completed", "reply": "Public fixture"}
    await original.complete(context=_context(), request_id="request:preserved", result=completed)
    await original.close()

    # Reproduce the already-applied early migration 017, with neither sequence column.
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER pwa_chat_conversation_deleted")
        for column in missing_columns:
            connection.execute(f"ALTER TABLE pwa_chat_requests DROP COLUMN {column}")
        before = connection.execute(
            "SELECT host_id,device_id,request_id,fingerprint,conversation_id,session_id,"
            "status,result_json,created_at,updated_at FROM pwa_chat_requests"
        ).fetchall()

    upgraded = SQLitePWAChatStore(database)
    try:
        await upgraded.initialize()
        with sqlite3.connect(database) as connection:
            assert (
                connection.execute(
                    "SELECT host_id,device_id,request_id,fingerprint,conversation_id,session_id,"
                    "status,result_json,created_at,updated_at FROM pwa_chat_requests"
                ).fetchall()
                == before
            )
        assert await upgraded.get(context=_context(), request_id="request:preserved") == completed
        is_new, replay = await upgraded.reserve(
            context=_context(),
            request_id="request:preserved",
            fingerprint="original",
            conversation_id=None,
        )
        assert not is_new and replay == completed
        is_new, running = await upgraded.reserve(
            context=_context(), request_id="request:new", fingerprint="new", conversation_id=None
        )
        assert is_new and running["status"] == "running"
        await upgraded.recover_interrupted()
        assert (await upgraded.get(context=_context(), request_id="request:new"))[
            "status"
        ] == "interrupted"
        barrier = await upgraded.cancel_unknown(context=_context(), request_id="request:delayed")
        is_new, replay = await upgraded.reserve(
            context=_context(),
            request_id="request:delayed",
            fingerprint="delayed",
            conversation_id=None,
        )
        assert not is_new and replay == barrier
    finally:
        await upgraded.close()
    reopened = SQLitePWAChatStore(database)
    try:
        await reopened.initialize()
        assert await reopened.get(context=_context(), request_id="request:preserved") == completed
        with sqlite3.connect(database) as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "DELETE FROM conversations WHERE id=?", (accepted["conversation_id"],)
            )
        deleted = await reopened.get(context=_context(), request_id="request:preserved")
        assert deleted["status"] == "interrupted" and deleted["reply"] is None
        is_new, replay = await reopened.reserve(
            context=_context(),
            request_id="request:preserved",
            fingerprint="original",
            conversation_id=None,
        )
        assert not is_new and replay == deleted
    finally:
        await reopened.close()


async def test_legacy_phone_schema_cancelled_upgrade_rolls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = tmp_path / "legacy-cancel.db"
    original = SQLitePWAChatStore(database)
    await original.initialize()
    await original.close()
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE pwa_chat_requests DROP COLUMN start_sequence")
        connection.execute("ALTER TABLE pwa_chat_requests DROP COLUMN end_sequence")

    execute = aiosqlite.Connection.execute

    def cancel_second_add(connection: aiosqlite.Connection, sql: str, *args: object):
        if sql == "ALTER TABLE pwa_chat_requests ADD COLUMN end_sequence INTEGER":
            raise asyncio.CancelledError
        return execute(connection, sql, *args)

    upgraded = SQLitePWAChatStore(database)
    with monkeypatch.context() as patch:
        patch.setattr(aiosqlite.Connection, "execute", cancel_second_add)
        with pytest.raises(asyncio.CancelledError):
            await upgraded.initialize()
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(pwa_chat_requests)")}
        assert "start_sequence" not in columns and "end_sequence" not in columns
    try:
        await upgraded.initialize()
        assert (await upgraded.cancel_unknown(context=_context(), request_id="request:retry"))[
            "status"
        ] == "cancelled"
    finally:
        await upgraded.close()


class _BlockingProvider:
    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cleaned = asyncio.Event()

    async def chat(
        self, *, messages: Sequence[Message], tools: Sequence[ToolDefinition]
    ) -> ProviderResponse:
        self.calls += 1
        self.started.set()
        try:
            await self.release.wait()
            return ProviderResponse(content="public fixture reply")
        finally:
            self.cleaned.set()


class _Authority:
    def __init__(self) -> None:
        self.revoked = False

    async def validate_context(self, *args: object, **kwargs: object) -> None:
        if self.revoked:
            raise RemoteAuthenticationError("session_revoked")


@dataclass
class _Harness:
    chat: PWAChatCoordinator
    store: SQLiteConversationStore
    hub: PWAEventHub
    provider: _BlockingProvider
    subscription_id: str
    authority: _Authority


@asynccontextmanager
async def _harness(tmp_path: Path) -> AsyncIterator[_Harness]:
    store = SQLiteConversationStore(tmp_path / "phone.db")
    await store.initialize()
    provider = _BlockingProvider()
    service = AssistantService(provider=provider, store=store, tools=(), policy=FakeToolPolicy())
    hub = PWAEventHub()
    subscription = await hub.subscribe(context=_context(), topics=(PWAEventTopic.CHAT,))
    authority = _Authority()
    chat = PWAChatCoordinator(
        service=service,
        conversations=store,
        hub=hub,
        identity=authority,  # type: ignore[arg-type]
    )
    await chat.initialize()
    try:
        yield _Harness(chat, store, hub, provider, subscription.id, authority)
    finally:
        await chat.close()
        await hub.close()
        await store.close()


async def _submit(harness: _Harness, *, request_id: str = "request:one", **kwargs: object) -> dict:
    return await harness.chat.submit(
        context=_context(),
        request_id=request_id,
        subscription_id=harness.subscription_id,
        request=AssistantRequest(user_input="public fixture", **kwargs),
    )


async def _terminal(harness: _Harness, *, request_id: str = "request:one") -> dict:
    async with asyncio.timeout(3):
        while True:
            result = await harness.chat.store.get(context=_context(), request_id=request_id)
            if result["status"] != "running":
                tasks = [
                    item.task for item in harness.chat._active.values() if item.task is not None
                ]
                if tasks:
                    await asyncio.gather(*tasks)
                return result
            await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_lost_ack_subscription_reset_session_renewal_and_restart_generate_once(
    tmp_path: Path,
) -> None:
    async with _harness(tmp_path) as h:
        first = await _submit(h)
        await h.provider.started.wait()
        replay = await _submit(h)
        assert replay == first and h.provider.calls == 1
        assert len(await h.store.recent_messages(first["conversation_id"], limit=10)) == 1
        await h.hub.close_subscription(context=_context(), subscription_id=h.subscription_id)
        renewed = _context(session="session:renewed")
        subscription = await h.hub.subscribe(context=renewed, topics=(PWAEventTopic.CHAT,))
        rebound = await h.chat.status(
            context=renewed,
            request_id="request:one",
            subscription_id=subscription.id,
        )
        assert rebound == first
        await h.chat.clear_session(_context().session_id)
        assert not h.provider.cleaned.is_set()
        h.provider.release.set()
        terminal = await _terminal(h)
        assert terminal["status"] == "completed" and h.provider.calls == 1
        events = await h.hub.read(
            context=renewed, subscription_id=subscription.id, after_cursor=0, limit=100
        )
        assert events.events[-1].event_type == "chat.completed"
        assert events.events[-1].payload["reply"] == "public fixture reply"
        history = await h.chat.store.messages(
            context=renewed, conversation_id=first["conversation_id"], before=None, limit=50
        )
        assert [row["role"] for row in history["messages"]] == ["user", "assistant"]
        assert {row["request_id"] for row in history["messages"]} == {"request:one"}
        assert history["requests"][0]["status"] == "completed"
        with pytest.raises(PWAChatError, match="request_conflict"):
            await h.chat.submit(
                context=renewed,
                request_id="request:one",
                subscription_id=subscription.id,
                request=AssistantRequest(user_input="changed"),
            )
    async with _harness(tmp_path) as restarted:
        repeated = await _submit(restarted)
        assert repeated == terminal and restarted.provider.calls == 0
        conversations = await restarted.chat.store.conversations(_context())
        assert conversations["conversations"][0]["id"] == terminal["conversation_id"]
        history = await restarted.chat.store.messages(
            context=_context(), conversation_id=terminal["conversation_id"], before=None, limit=50
        )
        assert [row["content"] for row in history["messages"]] == [
            "public fixture",
            "public fixture reply",
        ]


@pytest.mark.asyncio
async def test_cancel_stops_actual_assistant_provider_and_keeps_one_user_turn(
    tmp_path: Path,
) -> None:
    async with _harness(tmp_path) as h:
        first = await _submit(h)
        await h.provider.started.wait()
        cancelled = await h.chat.cancel(context=_context(), request_id="request:one")
        assert cancelled["status"] == "cancelled" and h.provider.cleaned.is_set()
        assert await _submit(h) == cancelled and h.provider.calls == 1
        assert [
            message.role
            for message in await h.store.recent_messages(first["conversation_id"], limit=10)
        ] == [MessageRole.USER]
        audits = await h.store.list_audit_records()
        assert sorted((record.action, record.outcome.value) for record in audits) == [
            ("pwa.chat", "failed"),
            ("pwa.chat", "requested"),
        ]
        assert all("public fixture" not in json.dumps(record.detail) for record in audits)


@pytest.mark.asyncio
async def test_cancel_overtakes_unknown_post_and_survives_restart(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        cancelled = await h.chat.cancel(context=_context(), request_id="request:one")
        assert cancelled["status"] == "cancelled" and cancelled["conversation_id"] is None
        assert await _submit(h) == cancelled
        assert h.provider.calls == 0
        assert (await h.chat.store.conversations(_context()))["conversations"] == []
    async with _harness(tmp_path) as restarted:
        assert await _submit(restarted) == cancelled and restarted.provider.calls == 0


@pytest.mark.asyncio
async def test_immediate_cancel_before_background_task_starts_settles_reservation(
    tmp_path: Path,
) -> None:
    async with _harness(tmp_path) as h:
        await _submit(h)
        result = await h.chat.cancel(context=_context(), request_id="request:one")
        assert result["status"] == "cancelled"
        assert h.provider.calls == 0
        assert await _submit(h) == result


@pytest.mark.asyncio
async def test_restart_interruption_never_replays_committed_user_turn(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        is_new, result = await h.chat.store.reserve(
            context=_context(),
            request_id="request:crash",
            fingerprint="digest",
            conversation_id=None,
        )
        assert is_new
        await h.store.append_message(
            Message(
                conversation_id=result["conversation_id"],
                role=MessageRole.USER,
                content="public fixture",
                client_request_id="request:crash",
            )
        )
    async with _harness(tmp_path) as restarted:
        result = await restarted.chat.store.get(
            context=_context(session="session:new"), request_id="request:crash"
        )
        assert result["status"] == "interrupted" and result["error"]["code"] == "core_restarted"
        is_new, replay = await restarted.chat.store.reserve(
            context=_context(session="session:new"),
            request_id="request:crash",
            fingerprint="digest",
            conversation_id=None,
        )
        assert not is_new and replay == result
        history = await restarted.chat.store.messages(
            context=_context(), conversation_id=result["conversation_id"], before=None, limit=50
        )
        assert (
            len(history["messages"]) == 1
            and history["messages"][0]["request_id"] == "request:crash"
        )
        assert restarted.provider.calls == 0


@pytest.mark.asyncio
async def test_foreign_local_and_obsolete_subscription_ownership_denied(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        first = await _submit(h)
        await h.provider.started.wait()
        foreign = _context(device="device:foreign", session="session:foreign")
        with pytest.raises(PWAChatError, match="request_not_found"):
            await h.chat.store.get(context=foreign, request_id="request:one")
        with pytest.raises(PWAChatError, match="conversation_not_found"):
            await h.chat.store.messages(
                context=foreign, conversation_id=first["conversation_id"], before=None, limit=50
            )
        assert (await h.chat.store.conversations(foreign))["conversations"] == []
        foreign_sub = await h.hub.subscribe(context=foreign, topics=(PWAEventTopic.CHAT,))
        with pytest.raises(PWAChatError, match="conversation_not_found"):
            await h.chat.submit(
                context=foreign,
                request_id="request:foreign",
                subscription_id=foreign_sub.id,
                request=AssistantRequest(
                    user_input="public fixture", conversation_id=first["conversation_id"]
                ),
            )
        with pytest.raises(PWATransportError, match="subscription_not_found"):
            await h.chat.submit(
                context=foreign,
                request_id="request:one",
                subscription_id=h.subscription_id,
                request=AssistantRequest(user_input="public fixture"),
            )
        local = await h.store.create_conversation(metadata={"private": "local-only"})
        with pytest.raises(PWAChatError, match="conversation_not_found"):
            await h.chat.submit(
                context=foreign,
                request_id="request:local",
                subscription_id=foreign_sub.id,
                request=AssistantRequest(user_input="public fixture", conversation_id=local.id),
            )


@pytest.mark.asyncio
async def test_one_active_turn_ceiling_atomic_across_store_connections(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        second = SQLitePWAChatStore(h.store.database_path)
        await second.initialize()
        try:
            results = await asyncio.gather(
                h.chat.store.reserve(
                    context=_context(),
                    request_id="request:race",
                    fingerprint="digest",
                    conversation_id=None,
                ),
                second.reserve(
                    context=_context(),
                    request_id="request:race",
                    fingerprint="digest",
                    conversation_id=None,
                ),
            )
            assert sorted(result[0] for result in results) == [False, True]
            assert results[0][1] == results[1][1]
            with pytest.raises(PWAChatError, match="request_running"):
                await second.reserve(
                    context=_context(),
                    request_id="request:second",
                    fingerprint="other",
                    conversation_id=None,
                )
        finally:
            await second.close()


@pytest.mark.asyncio
async def test_deleted_history_retains_content_free_no_replay_receipt(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        first = await _submit(h)
        await h.provider.started.wait()
        h.provider.release.set()
        await _terminal(h)
        assert await h.store.delete_conversation(first["conversation_id"])
        replay = await _submit(h)
        assert replay["status"] == "interrupted" and replay["conversation_id"] is None
        assert replay["error"]["code"] == "conversation_deleted" and replay["reply"] is None
        assert h.provider.calls == 1
        assert (await h.chat.store.conversations(_context()))["conversations"] == []


@pytest.mark.asyncio
async def test_bounded_paginated_history_omits_tool_and_planning_messages(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        _, reservation = await h.chat.store.reserve(
            context=_context(),
            request_id="request:history",
            fingerprint="digest",
            conversation_id=None,
        )
        cid = reservation["conversation_id"]
        for index in range(5):
            await h.store.append_message(
                Message(
                    conversation_id=cid,
                    role=MessageRole.USER,
                    content=f"public {index}",
                    client_request_id="request:history",
                )
            )
        await h.store.append_message(
            Message(
                conversation_id=cid,
                role=MessageRole.ASSISTANT,
                content="internal planning",
                tool_calls=(ToolCall(id="tool:one", name="public_tool", arguments={}),),
            )
        )
        await h.store.append_message(
            Message(
                conversation_id=cid,
                role=MessageRole.ASSISTANT,
                content="",
                tool_calls=(ToolCall(id="tool:two", name="public_tool", arguments={}),),
            )
        )
        await h.store.append_message(
            Message(
                conversation_id=cid,
                role=MessageRole.TOOL,
                content="internal tool",
                tool_call_id="tool:one",
                tool_name="public_tool",
            )
        )
        await h.store.append_message(
            Message(
                conversation_id=cid,
                role=MessageRole.ASSISTANT,
                content="public final reply",
                client_request_id="request:history",
            )
        )
        first = await h.chat.store.messages(
            context=_context(), conversation_id=cid, before=None, limit=2
        )
        assert [row["content"] for row in first["messages"]] == ["public 4", "public final reply"]
        assert first["has_more"]
        second = await h.chat.store.messages(
            context=_context(), conversation_id=cid, before=first["next_before"], limit=50
        )
        assert [row["content"] for row in second["messages"]] == [
            "public 0",
            "public 1",
            "public 2",
            "public 3",
        ]
        assert not second["has_more"]
        await h.store.append_message(
            Message(
                conversation_id=cid,
                role=MessageRole.USER,
                content="\x01" * 100_000,
                client_request_id="request:history",
            )
        )
        large = await h.chat.store.messages(
            context=_context(), conversation_id=cid, before=None, limit=50
        )
        assert len(json.dumps(large, ensure_ascii=False).encode("utf-8")) < MAX_CHAT_RESPONSE_BYTES
        assert large["messages"][-1]["truncated"]


@pytest.mark.asyncio
async def test_authority_revocation_cancels_core_provider(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        await _submit(h)
        await h.provider.started.wait()
        h.authority.revoked = True
        result = await _terminal(h)
        assert result["status"] == "cancelled" and h.provider.cleaned.is_set()


@pytest.mark.asyncio
async def test_generation_deadline_cleans_provider_without_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("jarvis.remote.chat.MAX_PHONE_TURN_SECONDS", 0.2)
    async with _harness(tmp_path) as h:
        await _submit(h)
        await h.provider.started.wait()
        result = await _terminal(h)
        assert result["status"] == "failed" and result["error"]["code"] == "request_timeout"
        assert h.provider.cleaned.is_set() and h.provider.calls == 1
        assert await _submit(h) == result and h.provider.calls == 1


@pytest.mark.asyncio
async def test_large_terminal_reply_remains_bounded_and_durable(tmp_path: Path) -> None:
    async with _harness(tmp_path) as h:
        provider = FakeChatProvider((ProviderResponse(content="\x01" * 100_000),))
        h.chat._service = AssistantService(
            provider=provider, store=h.store, tools=(), policy=FakeToolPolicy()
        )
        await _submit(h)
        result = await _terminal(h)
        assert result["status"] == "completed" and result["reply_truncated"]
        assert len(json.dumps(result, ensure_ascii=False).encode("utf-8")) < MAX_CHAT_RESPONSE_BYTES
        retained = h.hub._subscriptions[h.subscription_id].events
        page = await h.hub.read(
            context=_context(),
            subscription_id=h.subscription_id,
            after_cursor=retained[0].cursor - 1,
            limit=100,
        )
        assert (
            page.events[-1].event_type == "chat.completed"
            and page.events[-1].payload["reply_truncated"]
        )
        assert (
            len((await h.store.recent_messages(result["conversation_id"], limit=10))[-1].content)
            == 100_000
        )


@pytest.mark.asyncio
async def test_local_private_flags_and_local_messages_never_escape_phone_history(
    tmp_path: Path,
) -> None:
    async with _harness(tmp_path) as h:
        first = await _submit(h)
        await h.provider.started.wait()
        h.provider.release.set()
        await _terminal(h)
        cid = first["conversation_id"]
        await h.store.append_message(
            Message(
                conversation_id=cid,
                role=MessageRole.ASSISTANT,
                content="synthetic private local reply",
            )
        )
        history = await h.chat.store.messages(
            context=_context(), conversation_id=cid, before=None, limit=50
        )
        assert [row["content"] for row in history["messages"]] == [
            "public fixture",
            "public fixture reply",
        ]
        await h.store.mark_email_private(cid)
        assert (await h.chat.store.conversations(_context()))["conversations"] == []
        for operation in (
            h.chat.store.messages(context=_context(), conversation_id=cid, before=None, limit=50),
            h.chat.store.get(context=_context(), request_id="request:one"),
            _submit(h),
        ):
            with pytest.raises(PWAChatError, match="conversation_not_found"):
                await operation
        assert h.provider.calls == 1


@pytest.mark.asyncio
async def test_local_deletion_during_generation_stops_provider_and_emits_interrupted(
    tmp_path: Path,
) -> None:
    async with _harness(tmp_path) as h:
        first = await _submit(h)
        await h.provider.started.wait()
        assert await h.store.delete_conversation(first["conversation_id"])
        result = await _terminal(h)
        assert result["status"] == "interrupted" and result["conversation_id"] is None
        assert h.provider.cleaned.is_set() and h.provider.calls == 1
        page = await h.hub.read(
            context=_context(), subscription_id=h.subscription_id, after_cursor=0, limit=100
        )
        assert page.events[-1].event_type == "chat.interrupted"
        assert page.events[-1].payload["conversation_id"] is None
        assert not any(event.event_type == "chat.delta" for event in page.events)
        assert (await h.store.list_audit_records())[0].conversation_id is None


@pytest.mark.asyncio
async def test_concurrent_immediate_cancel_has_one_terminal_audit_and_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with _harness(tmp_path) as h:
        await _submit(h)
        active = next(iter(h.chat._active.values()))
        assert active.task is not None and not active.started
        active.task.cancel()
        save_started = asyncio.Event()
        release_save = asyncio.Event()
        original = h.chat._save_result

        async def delayed_save(*args: object, **kwargs: object) -> None:
            save_started.set()
            await release_save.wait()
            await original(*args, **kwargs)

        monkeypatch.setattr(h.chat, "_save_result", delayed_save)
        first = asyncio.create_task(h.chat.cancel(context=_context(), request_id="request:one"))
        second = None
        try:
            await asyncio.wait_for(save_started.wait(), timeout=3)
            second = asyncio.create_task(
                h.chat.cancel(context=_context(), request_id="request:one")
            )
            done, _ = await asyncio.wait({second}, timeout=0.05)
            assert not done, "Concurrent cancellation returned before terminal storage committed"
        finally:
            release_save.set()
            results = await asyncio.gather(first, *([second] if second is not None else []))
        assert results[0] == results[1] and results[0]["status"] == "cancelled"
        assert h.provider.calls == 0
        audits = await h.store.list_audit_records()
        assert sum(record.detail["status"] == "cancelled" for record in audits) == 1
        page = await h.hub.read(
            context=_context(), subscription_id=h.subscription_id, after_cursor=0, limit=100
        )
        assert sum(event.event_type == "chat.cancelled" for event in page.events) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failures", [1, 2])
async def test_result_storage_failure_recovers_without_generation_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failures: int
) -> None:
    async with _harness(tmp_path) as h:
        original = h.chat.store.complete
        calls = 0

        async def fail_then_complete(**kwargs: object) -> None:
            nonlocal calls
            calls += 1
            if calls <= failures:
                raise RuntimeError("synthetic database unavailable")
            await original(**kwargs)

        monkeypatch.setattr(h.chat.store, "complete", fail_then_complete)
        await _submit(h)
        await h.provider.started.wait()
        h.provider.release.set()
        active = next(iter(h.chat._active.values()))
        assert active.task is not None
        await asyncio.gather(active.task, return_exceptions=True)
        result = await h.chat.status(
            context=_context(), request_id="request:one", subscription_id=h.subscription_id
        )
        assert result["status"] == ("completed" if failures == 1 else "interrupted")
        assert await _submit(h) == result and h.provider.calls == 1
