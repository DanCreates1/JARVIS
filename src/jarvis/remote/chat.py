"""Core-owned phone turns survive lost acknowledgements without generating twice."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator
from contextlib import aclosing, suppress
from dataclasses import dataclass
from typing import Any, cast

from jarvis.attachments import AttachmentError, AttachmentService
from jarvis.core import AssistantRequest, AssistantService, RuntimeStreamFrame
from jarvis.memory import SQLiteConversationStore
from jarvis.remote.attachments import PWAUploadStaging, StagedAttachment, commit_uploads
from jarvis.remote.chat_store import PWAChatError, SQLitePWAChatStore, chat_result
from jarvis.remote.models import RemoteIdentityContext, RemoteScope
from jarvis.remote.pwa import PWAEventHub, PWAEventTopic, PWATransportError
from jarvis.remote.service import RemoteAuthenticationError, RemoteIdentityService

MAX_ACTIVE_PHONE_TURNS = 64
MAX_PHONE_TURN_SECONDS = 300


@dataclass(slots=True)
class _ActiveTurn:
    context: RemoteIdentityContext
    request_id: str
    conversation_id: str
    subscription_id: str
    task: asyncio.Task[None] | None = None
    cancel_requested: bool = False
    started: bool = False
    settled: bool = False


class PWAChatCoordinator:
    def __init__(
        self,
        *,
        service: AssistantService,
        conversations: SQLiteConversationStore,
        hub: PWAEventHub,
        identity: RemoteIdentityService | None,
        attachments: AttachmentService | None = None,
    ) -> None:
        self.store = SQLitePWAChatStore(conversations.database_path)
        self._service = service
        self._conversations = conversations
        self._hub = hub
        self._identity = identity
        self.attachments = attachments
        self.uploads = PWAUploadStaging()
        self._active: dict[tuple[str, str, str], _ActiveTurn] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        await self.store.initialize()
        await self.store.recover_interrupted()

    async def submit(
        self,
        *,
        context: RemoteIdentityContext,
        request_id: str,
        subscription_id: str,
        request: AssistantRequest,
        upload_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        # Validate transport ownership even on replay before attaching its current stream.
        await self._hub.validate_subscription(
            context=context, subscription_id=subscription_id, topic=PWAEventTopic.CHAT
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "message": request.user_input,
                    "conversation_id": request.conversation_id,
                    "model_role": request.requested_model_role,
                    "reasoning_level": request.reasoning_level,
                    **({"upload_ids": upload_ids} if upload_ids else {}),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        key = (context.host_id, context.device_id, request_id)
        async with self._lock:
            if len(self._active) >= MAX_ACTIVE_PHONE_TURNS and key not in self._active:
                # Completed replays remain available under process capacity pressure.
                try:
                    existing = await self.store.get(context=context, request_id=request_id)
                except PWAChatError:
                    raise PWAChatError("chat_capacity") from None
                if existing["status"] == "running":
                    raise PWAChatError("chat_capacity")
            is_new, result = await self.store.reserve(
                context=context,
                request_id=request_id,
                fingerprint=fingerprint,
                conversation_id=request.conversation_id,
            )
            if not is_new:
                active = self._active.get(key)
                if active is not None:
                    active.context = context
                    active.subscription_id = subscription_id
                elif result["status"] == "running":
                    result = await self._interrupt_orphan(context, request_id, result)
                return result
            conversation_id = str(result["conversation_id"])
            active = _ActiveTurn(context, request_id, conversation_id, subscription_id)
            try:
                staged = self.uploads.take(context, upload_ids)
            except AttachmentError:
                result = chat_result(
                    request_id, conversation_id, "failed", error="upload_unavailable"
                )
                await self.store.complete(context=context, request_id=request_id, result=result)
                return result
            self._active[key] = active
            active.task = asyncio.create_task(
                self._run(
                    active,
                    request.model_copy(
                        update={
                            "conversation_id": conversation_id,
                            "metadata": {
                                **request.metadata,
                                "interface": "browser",
                                "pwa_request_id": request_id,
                            },
                        }
                    ),
                    key,
                    staged,
                )
            )
            active.task.add_done_callback(_consume_task_outcome)
        return result

    async def cancel(self, *, context: RemoteIdentityContext, request_id: str) -> dict[str, Any]:
        try:
            result = await self.store.get(context=context, request_id=request_id)
        except PWAChatError as exc:
            if exc.code != "request_not_found":
                raise
            result = await self.store.cancel_unknown(context=context, request_id=request_id)
            if result["status"] == "cancelled":
                await self._conversations.append_audit_record(
                    conversation_id=None,
                    action="pwa.chat",
                    outcome="failed",
                    risk="read_only",
                    detail={"request_id": request_id, "status": "cancelled"},
                )
        if result["status"] != "running":
            return result
        key = (context.host_id, context.device_id, request_id)
        async with self._lock:
            active = self._active.get(key)
            if active is not None and active.task is not None:
                task = active.task
                if not active.cancel_requested:
                    active.cancel_requested = True
                    task.cancel()
            else:
                task = None
                result = await self._interrupt_orphan(context, request_id, result)
        if task is not None:
            with suppress(TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            if task.cancelled() and active is not None and not active.started:
                await self._settle_unstarted(active)
        return await self.store.get(context=context, request_id=request_id)

    async def status(
        self, *, context: RemoteIdentityContext, request_id: str, subscription_id: str | None
    ) -> dict[str, Any]:
        if subscription_id is not None:
            await self._hub.validate_subscription(
                context=context, subscription_id=subscription_id, topic=PWAEventTopic.CHAT
            )
        async with self._lock:
            result = await self.store.get(context=context, request_id=request_id)
            active = self._active.get((context.host_id, context.device_id, request_id))
            if active is not None and subscription_id is not None:
                active.context = context
                active.subscription_id = subscription_id
            elif active is None and result["status"] == "running":
                result = await self._interrupt_orphan(context, request_id, result)
            return result

    async def _interrupt_orphan(
        self, context: RemoteIdentityContext, request_id: str, result: dict[str, Any]
    ) -> dict[str, Any]:
        result = chat_result(
            request_id, result["conversation_id"], "interrupted", error="outcome_unknown"
        )
        await self.store.complete(context=context, request_id=request_id, result=result)
        return await self.store.get(context=context, request_id=request_id)

    async def clear_session(self, session_id: str) -> None:
        self.uploads.clear_session(session_id)
        async with self._lock:
            tasks = [
                item.task
                for item in self._active.values()
                if item.context.session_id == session_id and item.task is not None
            ]
            for item in self._active.values():
                if (
                    item.context.session_id == session_id
                    and item.task is not None
                    and not item.cancel_requested
                ):
                    item.cancel_requested = True
                    item.task.cancel()
        if tasks:
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    asyncio.shield(asyncio.gather(*tasks, return_exceptions=True)), timeout=5
                )
            for item in list(self._active.values()):
                if item.context.session_id == session_id and not item.started:
                    await self._settle_unstarted(item)

    async def close(self) -> None:
        self.uploads.close()
        async with self._lock:
            tasks = [item.task for item in self._active.values() if item.task is not None]
            for item in self._active.values():
                if item.task is not None and not item.cancel_requested:
                    item.cancel_requested = True
                    item.task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for item in list(self._active.values()):
            if not item.started:
                await self._settle_unstarted(item)
        await self.store.close()

    async def _settle_unstarted(self, active: _ActiveTurn) -> None:
        # Concurrent cancels must wait for the terminal receipt, audit and event, rather
        # than interpreting an in-progress settlement as already committed.
        async with self._lock:
            if active.settled:
                return
            active.settled = True
            result = chat_result(
                active.request_id, active.conversation_id, "cancelled", error="cancelled"
            )
            try:
                await self._save_result(active, result)
                await self._audit(active, "cancelled")
                await self._publish(active, "chat.cancelled", result, terminal=True)
            finally:
                self._active.pop(
                    (active.context.host_id, active.context.device_id, active.request_id), None
                )

    async def _save_result(self, active: _ActiveTurn, result: dict[str, Any]) -> None:
        for attempt in range(2):
            try:
                await self.store.complete(
                    context=active.context, request_id=active.request_id, result=result
                )
                return
            except Exception:
                if attempt == 1:
                    raise

    async def _watch_authority(self, active: _ActiveTurn) -> None:
        while True:
            await asyncio.sleep(1)
            context = active.context
            try:
                if self._identity is None:
                    raise RemoteAuthenticationError("identity_unavailable")
                await self._identity.validate_context(
                    context, required_scope=RemoteScope.CLIENT_CHAT
                )
                receipt = await self.store.get(context=context, request_id=active.request_id)
                if receipt["status"] != "running":
                    raise PWAChatError("request_changed")
            except Exception:
                if active.context is context and active.task is not None:
                    active.cancel_requested = True
                    active.task.cancel()
                    return

    async def _run(
        self,
        active: _ActiveTurn,
        request: AssistantRequest,
        key: tuple[str, str, str],
        staged: tuple[StagedAttachment, ...] = (),
    ) -> None:
        active.started = True
        watcher: asyncio.Task[None] | None = None
        result = chat_result(
            active.request_id, active.conversation_id, "failed", error="request_failed"
        )
        try:
            if self._identity is None:
                raise RemoteAuthenticationError("identity_unavailable")
            await self._identity.validate_context(
                active.context, required_scope=RemoteScope.CLIENT_CHAT
            )
            # Watch identity while existing bounded local parsers run, before model work.
            watcher = asyncio.create_task(self._watch_authority(active))
            attachment_ids = await commit_uploads(
                self.attachments, active.context, active.conversation_id, staged
            )
            staged = ()
            request = request.model_copy(update={"attachment_ids": attachment_ids})
            await self._identity.validate_context(
                active.context, required_scope=RemoteScope.CLIENT_CHAT
            )
            await self._audit(active, "started")
            await self._publish(active, "chat.started", {"conversation_id": active.conversation_id})
            terminal = None
            emitted_delta = False
            async with (
                asyncio.timeout(MAX_PHONE_TURN_SECONDS),
                aclosing(
                    cast(AsyncGenerator[RuntimeStreamFrame, None], self._service.stream(request))
                ) as stream,
            ):
                async for frame in stream:
                    if active.cancel_requested:
                        raise asyncio.CancelledError
                    if frame.event is not None:
                        if frame.event.conversation_id not in {None, active.conversation_id}:
                            raise RuntimeError("Core conversation changed")
                        emitted_delta = emitted_delta or frame.event.type.value == "assistant_delta"
                        payload = frame.event.model_dump(mode="json")
                        # Runtime events may include large message/tool objects. Phone events
                        # retain public contract metadata/deltas; canonical text stays in Core.
                        payload.pop("message", None)
                        payload.pop("tool_call", None)
                        payload["conversation_id"] = active.conversation_id
                        delta = payload.get("content_delta")
                        if isinstance(delta, str):
                            for offset in range(0, len(delta), 8_000):
                                await self._publish(
                                    active,
                                    "chat.frame",
                                    {
                                        **payload,
                                        "content_delta": delta[offset : offset + 8_000],
                                    },
                                )
                        else:
                            await self._publish(active, "chat.frame", payload)
                    if frame.result is not None:
                        terminal = frame.result
            if terminal is None or terminal.conversation_id != active.conversation_id:
                raise RuntimeError("Core stream ended without owned result")
            status = "completed" if terminal.status.value == "completed" else "failed"
            result = chat_result(
                active.request_id,
                active.conversation_id,
                status,
                reply=terminal.reply,
                error=terminal.error.code.value if terminal.error is not None else None,
            )
            if not emitted_delta and terminal.reply is not None:
                for offset in range(0, len(terminal.reply), 8_000):
                    await self._publish(
                        active,
                        "chat.delta",
                        {
                            "conversation_id": active.conversation_id,
                            "content_delta": terminal.reply[offset : offset + 8_000],
                        },
                    )
        except asyncio.CancelledError:
            result = chat_result(
                active.request_id, active.conversation_id, "cancelled", error="cancelled"
            )
        except TimeoutError:
            result = chat_result(
                active.request_id, active.conversation_id, "failed", error="request_timeout"
            )
        except AttachmentError:
            result = chat_result(
                active.request_id,
                active.conversation_id,
                "failed",
                error="attachment_processing_failed",
            )
        except Exception:
            pass
        finally:
            if watcher is not None:
                watcher.cancel()
                with suppress(asyncio.CancelledError):
                    await watcher
            try:
                await self._save_result(active, result)
                result = await self.store.get(context=active.context, request_id=active.request_id)
                await self._audit(active, str(result["status"]))
                event_result = dict(result)
                reply = event_result.get("reply")
                while len(json.dumps(event_result, ensure_ascii=False).encode("utf-8")) > 48_000:
                    assert isinstance(reply, str)
                    reply = reply[: len(reply) // 2]
                    event_result["reply"] = reply
                    event_result["reply_truncated"] = True
                event_type = (
                    "chat.completed"
                    if result["status"] == "completed"
                    else f"chat.{result['status']}"
                )
                await self._publish(active, event_type, event_result, terminal=True)
            finally:
                async with self._lock:
                    self._active.pop(key, None)

    async def _publish(
        self,
        active: _ActiveTurn,
        event_type: str,
        payload: dict[str, Any],
        *,
        terminal: bool = False,
    ) -> None:
        if active.cancel_requested and not terminal:
            return
        try:
            receipt = await self.store.get(context=active.context, request_id=active.request_id)
        except PWAChatError:
            return
        if not terminal and receipt["status"] != "running":
            return
        # Closing/resetting one subscription cannot abandon a durable request or restart Core.
        with suppress(PWATransportError):
            await self._hub.publish(
                context=active.context,
                subscription_id=active.subscription_id,
                topic=PWAEventTopic.CHAT,
                event_type=event_type,
                request_id=active.request_id,
                payload=payload,
            )

    async def _audit(self, active: _ActiveTurn, status: str) -> None:
        conversation = await self._conversations.get_conversation(active.conversation_id)
        await self._conversations.append_audit_record(
            conversation_id=active.conversation_id if conversation is not None else None,
            action="pwa.chat",
            outcome="requested"
            if status == "started"
            else "completed"
            if status == "completed"
            else "failed",
            risk="read_only",
            detail={"request_id": active.request_id, "status": status},
        )


def _consume_task_outcome(task: asyncio.Task[None]) -> None:
    # Retrieve failures without logging provider errors or private request content.
    if not task.cancelled():
        task.exception()
