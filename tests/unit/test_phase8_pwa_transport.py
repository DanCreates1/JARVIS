from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from jarvis.remote import (
    PWAEvent,
    PWAEventHub,
    PWAEventTopic,
    PWATransportError,
    RemoteIdentityContext,
    RemoteScope,
    RemoteSessionKind,
)


def _context(*, device: str = "device:one", session: str = "session:one") -> RemoteIdentityContext:
    return RemoteIdentityContext(
        host_id="host:one",
        device_id=device,
        session_id=session,
        key_version=1,
        audience="jarvis-api",
        scopes=frozenset(
            {
                RemoteScope.EVENTS_READ,
                RemoteScope.CLIENT_CHAT,
                RemoteScope.CLIENT_TASKS_READ,
                RemoteScope.CLIENT_STATUS_READ,
            }
        ),
        session_kind=RemoteSessionKind.BROWSER,
        authenticated_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_pwa_event_resume_is_ordered_bounded_and_session_isolated() -> None:
    hub = PWAEventHub(max_events=3)
    owner = _context()
    subscription = await hub.subscribe(
        context=owner,
        topics=(PWAEventTopic.CHAT, PWAEventTopic.TASKS),
    )

    for index in range(1, 5):
        event = await hub.publish(
            context=owner,
            subscription_id=subscription.id,
            topic=PWAEventTopic.CHAT,
            event_type="chat.delta",
            request_id="request:one",
            payload={"index": index},
        )
        assert event.cursor == index

    with pytest.raises(PWATransportError, match="cursor_expired"):
        await hub.read(
            context=owner,
            subscription_id=subscription.id,
            after_cursor=0,
            limit=100,
        )

    resumed = await hub.read(
        context=owner,
        subscription_id=subscription.id,
        after_cursor=1,
        limit=2,
    )
    assert [event.cursor for event in resumed.events] == [2, 3]
    assert resumed.next_cursor == 3
    assert resumed.has_more

    other_session = _context(session="session:other")
    with pytest.raises(PWATransportError, match="subscription_not_found"):
        await hub.read(
            context=other_session,
            subscription_id=subscription.id,
            after_cursor=1,
            limit=10,
        )
    assert await hub.clear_session(owner.session_id) == 1
    assert hub.subscription_count == 0


@pytest.mark.asyncio
async def test_pwa_transport_rejects_unsubscribed_oversized_and_zombie_state() -> None:
    hub = PWAEventHub(max_per_session=1, retention=timedelta(minutes=1))
    context = _context()
    subscription = await hub.subscribe(context=context, topics=(PWAEventTopic.DEVICE,))

    with pytest.raises(PWATransportError, match="subscription_limit"):
        await hub.subscribe(context=context, topics=(PWAEventTopic.CHAT,))
    with pytest.raises(PWATransportError, match="topic_not_subscribed"):
        await hub.publish(
            context=context,
            subscription_id=subscription.id,
            topic=PWAEventTopic.CHAT,
            event_type="chat.started",
            payload={},
        )
    with pytest.raises(PWATransportError, match="event_too_large"):
        await hub.publish(
            context=context,
            subscription_id=subscription.id,
            topic=PWAEventTopic.DEVICE,
            event_type="device.status",
            payload={"private": "x" * 70_000},
        )

    assert await hub.close_subscription(context=context, subscription_id=subscription.id)
    with pytest.raises(PWATransportError, match="subscription_not_found"):
        await hub.publish(
            context=context,
            subscription_id=subscription.id,
            topic=PWAEventTopic.DEVICE,
            event_type="device.zombie",
            payload={},
        )
    with pytest.raises(PWATransportError, match="subscription_not_found"):
        await hub.read(
            context=context,
            subscription_id=subscription.id,
            after_cursor=0,
            limit=10,
        )


@pytest.mark.asyncio
async def test_pwa_transport_serializes_concurrent_publish_cursors() -> None:
    hub = PWAEventHub()
    context = _context()
    subscription = await hub.subscribe(context=context, topics=(PWAEventTopic.CHAT,))

    await asyncio.gather(
        *(
            hub.publish(
                context=context,
                subscription_id=subscription.id,
                topic=PWAEventTopic.CHAT,
                event_type="chat.delta",
                payload={"index": index},
            )
            for index in range(100)
        )
    )
    page = await hub.read(
        context=context,
        subscription_id=subscription.id,
        after_cursor=0,
        limit=100,
    )
    assert [event.cursor for event in page.events] == list(range(1, 101))


@pytest.mark.asyncio
async def test_pwa_transport_evicts_events_at_byte_ceiling() -> None:
    hub = PWAEventHub()
    context = _context()
    subscription = await hub.subscribe(context=context, topics=(PWAEventTopic.CHAT,))
    for index in range(5):
        await hub.publish(
            context=context,
            subscription_id=subscription.id,
            topic=PWAEventTopic.CHAT,
            event_type="chat.delta",
            payload={"index": index, "content": "x" * 60_000},
        )

    with pytest.raises(PWATransportError, match="cursor_expired"):
        await hub.read(
            context=context,
            subscription_id=subscription.id,
            after_cursor=0,
            limit=10,
        )
    page = await hub.read(
        context=context,
        subscription_id=subscription.id,
        after_cursor=1,
        limit=10,
    )
    assert [event.cursor for event in page.events] == [2, 3, 4, 5]


@pytest.mark.asyncio
async def test_pwa_request_idempotency_and_session_expiry_are_exact() -> None:
    hub = PWAEventHub()
    context = _context()
    started, cached = await hub.begin_request(context=context, request_id="request:one")
    assert started and cached is None
    repeated, running = await hub.begin_request(context=context, request_id="request:one")
    assert not repeated and running is None
    await hub.complete_request(
        context=context,
        request_id="request:one",
        result={"status": "completed"},
    )
    repeated, cached = await hub.begin_request(context=context, request_id="request:one")
    assert not repeated and cached == {"status": "completed"}

    expiring = context.model_copy(update={"expires_at": datetime.now(UTC) + timedelta(seconds=5)})
    subscription = await hub.subscribe(context=expiring, topics=(PWAEventTopic.CHAT,))
    assert subscription.expires_at == expiring.expires_at
    assert await hub.clear_session(context.session_id) == 1
    assert hub.request_count == 0


@pytest.mark.asyncio
async def test_pwa_transport_capacity_expiry_and_waiter_fail_closed() -> None:
    with pytest.raises(ValueError, match="ceilings"):
        PWAEventHub(max_subscriptions=0)
    with pytest.raises(ValueError, match="retention"):
        PWAEventHub(retention=timedelta(hours=2))
    with pytest.raises(ValueError, match="timezone"):
        PWAEvent(
            cursor=1,
            topic=PWAEventTopic.CHAT,
            event_type="chat.delta",
            payload={},
            created_at=datetime(2026, 1, 1),  # noqa: DTZ001 - deliberately invalid input
        )

    context = _context()
    hub = PWAEventHub()
    subscription = await hub.subscribe(context=context, topics=(PWAEventTopic.CHAT,))
    with pytest.raises(ValueError, match="bounds"):
        await hub.read(
            context=context,
            subscription_id=subscription.id,
            after_cursor=-1,
            limit=1,
        )
    empty = await hub.read(
        context=context,
        subscription_id=subscription.id,
        after_cursor=0,
        limit=1,
        wait_seconds=0.001,
    )
    assert empty.events == ()

    waiter = asyncio.create_task(
        hub.read(
            context=context,
            subscription_id=subscription.id,
            after_cursor=0,
            limit=1,
            wait_seconds=1,
        )
    )
    await asyncio.sleep(0)
    await hub.clear_session(context.session_id)
    with pytest.raises(PWATransportError, match="subscription_not_found"):
        await waiter
    assert not await hub.close_subscription(
        context=context,
        subscription_id=subscription.id,
    )


@pytest.mark.asyncio
async def test_pwa_request_cache_is_bounded_and_rejects_oversized_results() -> None:
    hub = PWAEventHub()
    context = _context()
    for index in range(128):
        assert await hub.begin_request(context=context, request_id=f"request:{index}") == (
            True,
            None,
        )
    with pytest.raises(PWATransportError, match="transport_capacity"):
        await hub.begin_request(context=context, request_id="request:overflow")

    await hub.complete_request(context=context, request_id="request:0", result={"ok": True})
    assert await hub.begin_request(context=context, request_id="request:replacement") == (
        True,
        None,
    )
    await hub.abandon_request(context=context, request_id="request:replacement")

    await hub.clear_session(context.session_id)
    await hub.begin_request(context=context, request_id="request:large")
    with pytest.raises(PWATransportError, match="request_result_too_large"):
        await hub.complete_request(
            context=context,
            request_id="request:large",
            result="x" * 262_144,
        )
    with pytest.raises(PWATransportError, match="request_not_found"):
        await hub.complete_request(
            context=context,
            request_id="request:missing",
            result={},
        )
    await hub.close()
    assert hub.request_count == 0
