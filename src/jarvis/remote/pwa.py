"""Bounded, session-isolated Phase 8C PWA event transport."""

from __future__ import annotations

import asyncio
import json
from collections import deque
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from jarvis.remote.models import RemoteIdentityContext

MAX_PWA_EVENT_BYTES = 65_536
MAX_PWA_RETAINED_EVENT_BYTES = 262_144
MAX_PWA_EVENTS_PER_SUBSCRIPTION = 256
MAX_PWA_SUBSCRIPTIONS_PER_SESSION = 4
MAX_PWA_SUBSCRIPTIONS = 64
MAX_PWA_TOPICS = 3
MAX_PWA_REQUEST_RESULTS = 128
MAX_PWA_REQUEST_RESULT_BYTES = 131_072


class PWAEventTopic(StrEnum):
    CHAT = "chat"
    TASKS = "tasks"
    DEVICE = "device"


class PWAEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cursor: int = Field(ge=1)
    topic: PWAEventTopic
    event_type: str = Field(pattern=r"^[a-z][a-z0-9_.]{0,63}$")
    request_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$")
    payload: JsonValue
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def require_aware_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("PWA event timestamp must include a timezone")
        return value.astimezone(UTC)


class PWAEventPage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subscription_id: str = Field(pattern=r"^subscription:[0-9a-f-]{36}$")
    events: tuple[PWAEvent, ...]
    next_cursor: int = Field(ge=0)
    earliest_cursor: int = Field(ge=1)
    has_more: bool


class PWASubscription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^subscription:[0-9a-f-]{36}$")
    topics: tuple[PWAEventTopic, ...] = Field(min_length=1, max_length=MAX_PWA_TOPICS)
    next_cursor: int = Field(ge=0)
    expires_at: datetime

    @field_validator("topics")
    @classmethod
    def require_unique_topics(cls, value: tuple[PWAEventTopic, ...]) -> tuple[PWAEventTopic, ...]:
        if len(value) != len(set(value)):
            raise ValueError("subscription topics must be unique")
        return tuple(sorted(value, key=str))


class PWATransportError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(slots=True)
class _SubscriptionState:
    record: PWASubscription
    host_id: str
    device_id: str
    session_id: str
    events: deque[PWAEvent] = field(default_factory=deque)
    event_sizes: deque[int] = field(default_factory=deque)
    retained_event_bytes: int = 0
    next_cursor: int = 1
    closed: bool = False
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)


@dataclass(slots=True)
class _RequestState:
    result: JsonValue | None
    expires_at: datetime


class PWAEventHub:
    """Process-local private payload buffer with exact session ownership and bounded retention."""

    def __init__(
        self,
        *,
        max_subscriptions: int = MAX_PWA_SUBSCRIPTIONS,
        max_per_session: int = MAX_PWA_SUBSCRIPTIONS_PER_SESSION,
        max_events: int = MAX_PWA_EVENTS_PER_SUBSCRIPTION,
        retention: timedelta = timedelta(hours=1),
    ) -> None:
        if max_subscriptions < 1 or max_per_session < 1 or max_events < 1:
            raise ValueError("PWA transport ceilings must be positive")
        if retention <= timedelta(0) or retention > timedelta(hours=1):
            raise ValueError("PWA event retention must be between zero and one hour")
        self._max_subscriptions = max_subscriptions
        self._max_per_session = max_per_session
        self._max_events = max_events
        self._retention = retention
        self._subscriptions: dict[str, _SubscriptionState] = {}
        self._request_results: dict[tuple[str, str], _RequestState] = {}
        self._lock = asyncio.Lock()

    @property
    def subscription_count(self) -> int:
        return len(self._subscriptions)

    @property
    def request_count(self) -> int:
        return len(self._request_results)

    async def subscribe(
        self,
        *,
        context: RemoteIdentityContext,
        topics: tuple[PWAEventTopic, ...],
    ) -> PWASubscription:
        normalized = PWASubscription(
            id=f"subscription:{uuid4()}",
            topics=topics,
            next_cursor=0,
            expires_at=self._expiry(context),
        )
        async with self._lock:
            self._prune_locked()
            owned = sum(
                item.session_id == context.session_id for item in self._subscriptions.values()
            )
            if owned >= self._max_per_session:
                raise PWATransportError("subscription_limit")
            if len(self._subscriptions) >= self._max_subscriptions:
                raise PWATransportError("transport_capacity")
            self._subscriptions[normalized.id] = _SubscriptionState(
                record=normalized,
                host_id=context.host_id,
                device_id=context.device_id,
                session_id=context.session_id,
                events=deque(),
            )
        return normalized

    async def publish(
        self,
        *,
        context: RemoteIdentityContext,
        subscription_id: str,
        topic: PWAEventTopic,
        event_type: str,
        payload: JsonValue,
        request_id: str | None = None,
    ) -> PWAEvent:
        state = await self._owned(context, subscription_id)
        if topic not in state.record.topics:
            raise PWATransportError("topic_not_subscribed")
        async with state.condition:
            if state.closed:
                raise PWATransportError("subscription_not_found")
            candidate = PWAEvent(
                cursor=state.next_cursor,
                topic=topic,
                event_type=event_type,
                request_id=request_id,
                payload=payload,
                created_at=datetime.now(UTC),
            )
            encoded = json.dumps(
                candidate.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
            if len(encoded) > MAX_PWA_EVENT_BYTES:
                raise PWATransportError("event_too_large")
            while state.events and (
                len(state.events) >= self._max_events
                or state.retained_event_bytes + len(encoded) > MAX_PWA_RETAINED_EVENT_BYTES
            ):
                state.events.popleft()
                state.retained_event_bytes -= state.event_sizes.popleft()
            state.events.append(candidate)
            state.event_sizes.append(len(encoded))
            state.retained_event_bytes += len(encoded)
            state.next_cursor += 1
            state.condition.notify_all()
        return candidate

    async def read(
        self,
        *,
        context: RemoteIdentityContext,
        subscription_id: str,
        after_cursor: int,
        limit: int,
        wait_seconds: float = 0,
    ) -> PWAEventPage:
        if after_cursor < 0 or not 1 <= limit <= 500 or not 0 <= wait_seconds <= 25:
            raise ValueError("invalid PWA event read bounds")
        state = await self._owned(context, subscription_id)
        async with state.condition:
            if wait_seconds and state.next_cursor - 1 <= after_cursor:
                with suppress(TimeoutError):
                    await asyncio.wait_for(state.condition.wait(), timeout=wait_seconds)
            if state.closed:
                raise PWATransportError("subscription_not_found")
            events = tuple(state.events)
            next_cursor_snapshot = state.next_cursor
        earliest = events[0].cursor if events else next_cursor_snapshot
        if after_cursor < earliest - 1:
            raise PWATransportError("cursor_expired")
        selected = tuple(item for item in events if item.cursor > after_cursor)[:limit]
        next_cursor = selected[-1].cursor if selected else after_cursor
        return PWAEventPage(
            subscription_id=subscription_id,
            events=selected,
            next_cursor=next_cursor,
            earliest_cursor=earliest,
            has_more=any(item.cursor > next_cursor for item in events),
        )

    async def close_subscription(
        self, *, context: RemoteIdentityContext, subscription_id: str
    ) -> bool:
        async with self._lock:
            state = self._subscriptions.get(subscription_id)
            if state is None:
                return False
            self._require_owner(state, context)
            del self._subscriptions[subscription_id]
            state.closed = True
            self._clear_events(state)
        async with state.condition:
            state.condition.notify_all()
        return True

    async def begin_request(
        self, *, context: RemoteIdentityContext, request_id: str
    ) -> tuple[bool, JsonValue | None]:
        key = (context.session_id, request_id)
        async with self._lock:
            self._prune_locked()
            if key in self._request_results:
                return False, self._request_results[key].result
            if len(self._request_results) >= MAX_PWA_REQUEST_RESULTS:
                completed = next(
                    (
                        item
                        for item, state in self._request_results.items()
                        if state.result is not None
                    ),
                    None,
                )
                if completed is None:
                    raise PWATransportError("transport_capacity")
                del self._request_results[completed]
            self._request_results[key] = _RequestState(
                result=None,
                expires_at=self._expiry(context),
            )
            return True, None

    async def complete_request(
        self,
        *,
        context: RemoteIdentityContext,
        request_id: str,
        result: JsonValue,
    ) -> None:
        encoded = json.dumps(result, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        if len(encoded) > MAX_PWA_REQUEST_RESULT_BYTES:
            await self.abandon_request(context=context, request_id=request_id)
            raise PWATransportError("request_result_too_large")
        key = (context.session_id, request_id)
        async with self._lock:
            state = self._request_results.get(key)
            if state is None or state.expires_at <= datetime.now(UTC):
                self._request_results.pop(key, None)
                raise PWATransportError("request_not_found")
            state.result = result

    async def abandon_request(self, *, context: RemoteIdentityContext, request_id: str) -> None:
        async with self._lock:
            self._request_results.pop((context.session_id, request_id), None)

    async def clear_session(self, session_id: str) -> int:
        async with self._lock:
            ids = [
                key for key, state in self._subscriptions.items() if state.session_id == session_id
            ]
            states = [self._subscriptions.pop(key) for key in ids]
            for state in states:
                state.closed = True
                self._clear_events(state)
            request_ids = [key for key in self._request_results if key[0] == session_id]
            for key in request_ids:
                del self._request_results[key]
        for state in states:
            async with state.condition:
                state.condition.notify_all()
        return len(states)

    async def close(self) -> None:
        async with self._lock:
            states = list(self._subscriptions.values())
            self._subscriptions.clear()
            self._request_results.clear()
            for state in states:
                state.closed = True
                self._clear_events(state)
        for state in states:
            async with state.condition:
                state.condition.notify_all()

    async def _owned(
        self, context: RemoteIdentityContext, subscription_id: str
    ) -> _SubscriptionState:
        async with self._lock:
            self._prune_locked()
            state = self._subscriptions.get(subscription_id)
            if state is None:
                raise PWATransportError("subscription_not_found")
            self._require_owner(state, context)
            return state

    @staticmethod
    def _require_owner(state: _SubscriptionState, context: RemoteIdentityContext) -> None:
        if (
            state.host_id != context.host_id
            or state.device_id != context.device_id
            or state.session_id != context.session_id
        ):
            raise PWATransportError("subscription_not_found")

    def _prune_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [
            key for key, value in self._subscriptions.items() if value.record.expires_at <= now
        ]
        for subscription_id in expired:
            state = self._subscriptions.pop(subscription_id)
            state.closed = True
            self._clear_events(state)
        expired_requests = [
            key for key, value in self._request_results.items() if value.expires_at <= now
        ]
        for request_key in expired_requests:
            del self._request_results[request_key]

    def _expiry(self, context: RemoteIdentityContext) -> datetime:
        now = datetime.now(UTC)
        authenticated = context.authenticated_at or now
        candidates = [authenticated + self._retention, now + self._retention]
        if context.expires_at is not None:
            candidates.append(context.expires_at)
        return min(candidates)

    @staticmethod
    def _clear_events(state: _SubscriptionState) -> None:
        state.events.clear()
        state.event_sizes.clear()
        state.retained_event_bytes = 0
