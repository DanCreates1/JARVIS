from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from datetime import UTC, date, datetime, time, timedelta
from importlib.resources import files
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from jarvis.proactivity import (
    DeviceOwnershipConflictError,
    DeviceOwnershipDeniedError,
    DeviceOwnershipNotFoundError,
    HostProactivityPolicy,
    OwnershipEventType,
    OwnershipKind,
    ProactivityBudget,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityScope,
    ProposalSource,
    PWAProactivityAdapter,
    SQLiteProactivityDeviceStore,
    SQLiteProactivityRunnerStore,
    SQLiteProactivityStore,
    TriggerKind,
    TriggerSchedule,
    TrustedActivation,
)
from jarvis.remote import (
    DeviceType,
    EnrollmentCompletion,
    RemoteIdentityContext,
    RemoteIdentityService,
    RemoteScope,
    RemoteSessionKind,
    SQLiteRemoteIdentityStore,
    build_enrollment_proof,
    encode_base64url,
)

HOST = "host:phase11c"
FEATURE = "task.checkin"
NOW = datetime.now(UTC).replace(microsecond=0)


def _policy() -> HostProactivityPolicy:
    return HostProactivityPolicy(
        enabled=True,
        enabled_features=frozenset({FEATURE}),
        max_task_steps=1,
        max_provider_requests=0,
        max_tool_calls=0,
        max_tokens=0,
    )


async def _seed_candidate(database: Path) -> str:
    scheduled = NOW + timedelta(minutes=1)
    proposal = ProactivityProposal(
        title="Private fixture title",
        feature=FEATURE,
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="UTC",
            local_date=date.fromisoformat(scheduled.date().isoformat()),
            local_time=time(scheduled.hour, scheduled.minute),
        ),
        budget=ProactivityBudget(
            max_candidates_per_hour=1,
            max_candidates_per_day=1,
            max_attention_seconds_per_day=30,
            max_task_steps=1,
            max_provider_requests=0,
            max_tool_calls=0,
            max_tokens=0,
        ),
        scope=ProactivityScope(task_template_id="task:phase11c", data_classes=("task_state",)),
        provenance=ProactivityProvenance(source_type=ProposalSource.TEST, source_id="test:11c"),
        created_at=NOW,
        expires_at=NOW + timedelta(days=1),
    )
    policy = _policy()
    preview = policy.preview(proposal, now=NOW)
    async with SQLiteProactivityStore(database) as store:
        draft = await store.create_rule(host_id=HOST, preview=preview, now=NOW)
        active = await store.activate(
            TrustedActivation(
                approval_id="activation:phase11c",
                host_id=HOST,
                rule_id=draft.id,
                expected_version=1,
                expected_proposal_sha256=draft.proposal_sha256,
                approved_at=NOW,
                expires_at=NOW + timedelta(minutes=5),
            ),
            policy=policy,
            now=NOW,
        )
        decision, candidate = await store.evaluate_and_record(
            host_id=HOST,
            rule_id=active.id,
            policy=policy,
            now=scheduled,
        )
        assert decision.eligible and candidate is not None
    async with SQLiteProactivityRunnerStore(database) as runner:
        dispatch, _ = await runner.claim_next(
            host_id=HOST,
            runner_id="runner:phase11c",
            lease_seconds=30,
            notification_ttl_seconds=3_600,
            now=scheduled,
        )
        assert dispatch is not None and dispatch.lease_id is not None
        await runner.complete_local_notification(
            host_id=HOST,
            candidate_id=dispatch.candidate_id,
            lease_id=dispatch.lease_id,
            now=scheduled,
        )
        return dispatch.candidate_id


async def _enroll_device(
    service: RemoteIdentityService, *, name: str, scopes: tuple[RemoteScope, ...]
) -> str:
    key = Ed25519PrivateKey.generate()
    public_key = encode_base64url(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )
    ticket = await service.create_enrollment(
        host_id=HOST,
        display_name=name,
        device_type=DeviceType.BROWSER,
        approved_scopes=scopes,
        risk_ceiling=1,
    )
    record = await service.complete_enrollment(
        EnrollmentCompletion(
            enrollment_id=ticket.id,
            challenge=ticket.challenge,
            public_key=public_key,
            proof_signature=encode_base64url(
                key.sign(
                    build_enrollment_proof(
                        enrollment_id=ticket.id,
                        challenge=ticket.challenge,
                        public_key=public_key,
                        protocol_version="1",
                    )
                )
            ),
        ),
    )
    return record.id


def _context(device_id: str, scopes: frozenset[RemoteScope], *, expires: datetime | None = None):
    return RemoteIdentityContext(
        host_id=HOST,
        device_id=device_id,
        session_id=f"session:{device_id}",
        key_version=1,
        audience="jarvis-api",
        scopes=scopes,
        session_kind=RemoteSessionKind.BROWSER,
        authenticated_at=NOW,
        expires_at=expires or NOW + timedelta(hours=1),
    )


async def _setup(database: Path):
    candidate_id = await _seed_candidate(database)
    scopes = (
        RemoteScope.CLIENT_PROACTIVITY_READ,
        RemoteScope.CLIENT_PROACTIVITY_MANAGE,
    )
    remote_store = SQLiteRemoteIdentityStore(database)
    await remote_store.initialize()
    try:
        service = RemoteIdentityService(remote_store, clock=lambda: NOW)
        first = await _enroll_device(service, name="First", scopes=scopes)
        second = await _enroll_device(service, name="Second", scopes=scopes)
    finally:
        await remote_store.close()
    store = SQLiteProactivityDeviceStore(database)
    await store.initialize()
    await store.set_control(host_id=HOST, enabled=True, now=NOW)
    for device_id in (first, second):
        await store.bind_device(
            host_id=HOST,
            device_id=device_id,
            feature=FEATURE,
            allow_manage=True,
            expires_at=NOW + timedelta(days=1),
            now=NOW,
        )
    adapter = PWAProactivityAdapter(
        store,
        configured_enabled=True,
        policy_enabled=True,
        enabled_features=frozenset({FEATURE}),
        lease_seconds=60,
    )
    full = frozenset(scopes)
    return (
        candidate_id,
        first,
        second,
        store,
        adapter,
        _context(first, full),
        _context(second, full),
    )


@pytest.mark.asyncio
async def test_single_owner_cas_handoff_and_content_free_visibility(tmp_path: Path) -> None:
    database = tmp_path / "jarvis.db"
    candidate, first, second, store, adapter, first_context, second_context = await _setup(database)
    try:
        visible = await adapter.list_visible(context=first_context, now=NOW + timedelta(minutes=1))
        assert len(visible) == 1
        payload = visible[0].model_dump(mode="json")
        assert payload["generic_content_only"] is True
        assert not ({"title", "prompt", "task", "memory", "research", "effect"} & payload.keys())

        results = await asyncio.gather(
            adapter.claim(
                context=first_context,
                candidate_id=candidate,
                expected_version=1,
                now=NOW + timedelta(minutes=1),
            ),
            adapter.claim(
                context=second_context,
                candidate_id=candidate,
                expected_version=1,
                now=NOW + timedelta(minutes=1),
            ),
            return_exceptions=True,
        )
        winners = [result for result in results if not isinstance(result, BaseException)]
        losers = [result for result in results if isinstance(result, BaseException)]
        assert len(winners) == len(losers) == 1
        assert isinstance(losers[0], DeviceOwnershipConflictError)
        owner = winners[0]
        assert owner.owner_kind is OwnershipKind.DEVICE
        owner_context = first_context if owner.owner_device_id == first else second_context
        other_context = second_context if owner.owner_device_id == first else first_context
        other_id = second if owner.owner_device_id == first else first

        with pytest.raises(DeviceOwnershipDeniedError):
            await adapter.renew(
                context=other_context,
                candidate_id=candidate,
                expected_version=owner.version,
                now=NOW + timedelta(minutes=1, seconds=1),
            )
        handed = await adapter.handoff(
            context=owner_context,
            candidate_id=candidate,
            target_device_id=other_id,
            expected_version=owner.version,
            now=NOW + timedelta(minutes=1, seconds=1),
        )
        assert handed.owner_device_id == other_id
        with pytest.raises(DeviceOwnershipDeniedError):
            await adapter.release(
                context=owner_context,
                candidate_id=candidate,
                expected_version=handed.version,
                now=NOW + timedelta(minutes=1, seconds=2),
            )
        released = await adapter.release(
            context=other_context,
            candidate_id=candidate,
            expected_version=handed.version,
            now=NOW + timedelta(minutes=1, seconds=2),
        )
        assert released.owner_kind is OwnershipKind.LOCAL_HOST
        events = await store.list_events(host_id=HOST, candidate_id=candidate)
        assert [event.event_type for event in events] == [
            OwnershipEventType.LOCAL_OWNER_CREATED,
            OwnershipEventType.DEVICE_CLAIMED,
            OwnershipEventType.DEVICE_HANDOFF,
            OwnershipEventType.DEVICE_RELEASED,
        ]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_partition_expiry_kill_binding_and_identity_revocation_reclaim(
    tmp_path: Path,
) -> None:
    database = tmp_path / "jarvis.db"
    candidate, first, _, store, adapter, first_context, _ = await _setup(database)
    try:
        claimed = await adapter.claim(
            context=first_context,
            candidate_id=candidate,
            expected_version=1,
            now=NOW + timedelta(minutes=1),
        )
        with pytest.raises(DeviceOwnershipConflictError):
            await adapter.renew(
                context=first_context,
                candidate_id=candidate,
                expected_version=claimed.version,
                now=NOW + timedelta(minutes=2, seconds=1),
            )
        local = (
            await store.list_ownerships(host_id=HOST, now=NOW + timedelta(minutes=2, seconds=1))
        )[0]
        assert local.owner_kind is OwnershipKind.LOCAL_HOST

        claimed = await adapter.claim(
            context=first_context,
            candidate_id=candidate,
            expected_version=local.version,
            now=NOW + timedelta(minutes=2, seconds=2),
        )
        control = await store.set_control(
            host_id=HOST, enabled=False, now=NOW + timedelta(minutes=2, seconds=3)
        )
        assert not control.enabled
        assert (await store.list_ownerships(host_id=HOST))[0].owner_kind is OwnershipKind.LOCAL_HOST
        with pytest.raises(DeviceOwnershipDeniedError):
            await adapter.list_visible(
                context=first_context, now=NOW + timedelta(minutes=2, seconds=4)
            )

        await store.set_control(
            host_id=HOST, enabled=True, now=NOW + timedelta(minutes=2, seconds=5)
        )
        local = (await store.list_ownerships(host_id=HOST))[0]
        claimed = await adapter.claim(
            context=first_context,
            candidate_id=candidate,
            expected_version=local.version,
            now=NOW + timedelta(minutes=2, seconds=6),
        )
        binding = await store.require_binding(host_id=HOST, device_id=first, feature=FEATURE)
        await store.revoke_binding(
            host_id=HOST,
            device_id=first,
            feature=FEATURE,
            expected_version=binding.version,
            now=NOW + timedelta(minutes=2, seconds=7),
        )
        assert (await store.list_ownerships(host_id=HOST))[0].owner_kind is OwnershipKind.LOCAL_HOST

        await store.bind_device(
            host_id=HOST,
            device_id=first,
            feature=FEATURE,
            allow_manage=True,
            expires_at=NOW + timedelta(days=1),
            now=NOW + timedelta(minutes=2, seconds=8),
        )
        local = (await store.list_ownerships(host_id=HOST))[0]
        await adapter.claim(
            context=first_context,
            candidate_id=candidate,
            expected_version=local.version,
            now=NOW + timedelta(minutes=2, seconds=9),
        )
        remote_store = SQLiteRemoteIdentityStore(database)
        await remote_store.initialize()
        try:
            service = RemoteIdentityService(
                remote_store, clock=lambda: NOW + timedelta(minutes=2, seconds=10)
            )
            await service.revoke_device(host_id=HOST, device_id=first)
        finally:
            await remote_store.close()
        assert (await store.list_ownerships(host_id=HOST))[0].owner_kind is OwnershipKind.LOCAL_HOST
        revoked = await store.require_binding(host_id=HOST, device_id=first, feature=FEATURE)
        assert revoked.state.value == "revoked"
        assert claimed.version < (await store.list_ownerships(host_id=HOST))[0].version
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_scope_session_binding_and_config_intersection_fail_closed(tmp_path: Path) -> None:
    database = tmp_path / "jarvis.db"
    candidate, first, _, store, adapter, full_context, _ = await _setup(database)
    read_context = _context(first, frozenset({RemoteScope.CLIENT_PROACTIVITY_READ}))
    manage_context = _context(first, frozenset({RemoteScope.CLIENT_PROACTIVITY_MANAGE}))
    try:
        assert await adapter.list_visible(context=read_context, now=NOW + timedelta(minutes=1))
        for context in (read_context, manage_context):
            with pytest.raises(DeviceOwnershipDeniedError):
                await adapter.claim(
                    context=context,
                    candidate_id=candidate,
                    expected_version=1,
                    now=NOW + timedelta(minutes=1),
                )
        expired = _context(
            first,
            full_context.scopes,
            expires=NOW + timedelta(seconds=30),
        )
        with pytest.raises(DeviceOwnershipDeniedError):
            await adapter.list_visible(context=expired, now=NOW + timedelta(minutes=1))
        wrong_audience = full_context.model_copy(update={"audience": "other-api"})
        with pytest.raises(DeviceOwnershipDeniedError):
            await adapter.list_visible(context=wrong_audience, now=NOW + timedelta(minutes=1))

        empty_features = PWAProactivityAdapter(
            store,
            configured_enabled=True,
            policy_enabled=True,
            enabled_features=frozenset(),
        )
        assert (
            await empty_features.list_visible(context=full_context, now=NOW + timedelta(minutes=1))
            == ()
        )
        with pytest.raises(DeviceOwnershipDeniedError):
            await empty_features.claim(
                context=full_context,
                candidate_id=candidate,
                expected_version=1,
                now=NOW + timedelta(minutes=1),
            )
        disabled = PWAProactivityAdapter(
            store,
            configured_enabled=False,
            policy_enabled=True,
            enabled_features=frozenset({FEATURE}),
        )
        with pytest.raises(DeviceOwnershipDeniedError):
            await disabled.list_visible(context=full_context, now=NOW + timedelta(minutes=1))
        with pytest.raises(ValidationError):
            await store.bind_device(
                host_id=HOST,
                device_id=first,
                feature="../../private",
                allow_manage=False,
                expires_at=NOW + timedelta(days=1),
                now=NOW,
            )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_trusted_local_handoff_reclaim_and_store_boundaries(tmp_path: Path) -> None:
    database = tmp_path / "jarvis.db"
    candidate, first, _, store, _, _, _ = await _setup(database)
    try:
        bindings = await store.list_bindings(host_id=HOST, device_id=first)
        assert len(bindings) == 1 and bindings[0].feature == FEATURE
        with pytest.raises(ValueError):
            await store.list_bindings(host_id=HOST, limit=0)
        with pytest.raises(ValueError):
            await store.list_ownerships(host_id=HOST, limit=0)
        with pytest.raises(ValueError):
            await store.list_events(host_id=HOST, candidate_id=candidate, limit=0)
        with pytest.raises(ValueError):
            await store.local_handoff(
                host_id=HOST,
                target_device_id=first,
                candidate_id=candidate,
                expected_version=1,
                lease_seconds=301,
                now=NOW + timedelta(minutes=1),
            )

        handed = await store.local_handoff(
            host_id=HOST,
            target_device_id=first,
            candidate_id=candidate,
            expected_version=1,
            lease_seconds=60,
            now=NOW + timedelta(minutes=1),
        )
        assert handed.owner_device_id == first
        async with SQLiteProactivityRunnerStore(database) as runner:
            await runner.dismiss(
                host_id=HOST,
                candidate_id=candidate,
                expected_version=2,
                now=NOW + timedelta(minutes=1, seconds=1),
            )
        with pytest.raises(DeviceOwnershipDeniedError, match="inactive"):
            await store.renew(
                host_id=HOST,
                device_id=first,
                candidate_id=candidate,
                expected_version=handed.version,
                lease_seconds=60,
                now=NOW + timedelta(minutes=1, seconds=1),
            )
        with pytest.raises(DeviceOwnershipDeniedError):
            await store.local_handoff(
                host_id=HOST,
                target_device_id=first,
                candidate_id=candidate,
                expected_version=handed.version,
                lease_seconds=60,
                now=NOW + timedelta(minutes=1, seconds=1),
            )
        with pytest.raises(DeviceOwnershipConflictError):
            await store.local_reclaim(
                host_id=HOST,
                candidate_id=candidate,
                expected_version=1,
                now=NOW + timedelta(minutes=1, seconds=1),
            )
        reclaimed = await store.local_reclaim(
            host_id=HOST,
            candidate_id=candidate,
            expected_version=handed.version,
            now=NOW + timedelta(minutes=1, seconds=1),
        )
        assert reclaimed.owner_kind is OwnershipKind.LOCAL_HOST
        with pytest.raises(DeviceOwnershipDeniedError):
            await store.local_reclaim(
                host_id=HOST,
                candidate_id=candidate,
                expected_version=reclaimed.version,
                now=NOW + timedelta(minutes=1, seconds=2),
            )
        with pytest.raises(DeviceOwnershipConflictError):
            await store.revoke_binding(
                host_id=HOST,
                device_id=first,
                feature=FEATURE,
                expected_version=999,
                now=NOW + timedelta(minutes=1),
            )
    finally:
        await store.close()
        await store.close()


@pytest.mark.asyncio
async def test_default_control_lifecycle_and_missing_records(tmp_path: Path) -> None:
    store = SQLiteProactivityDeviceStore(tmp_path / "jarvis.db")
    await store.initialize()
    await store.initialize()
    try:
        control = await store.get_control(host_id=HOST)
        assert not control.enabled and control.version == control.kill_generation == 1
        with pytest.raises(DeviceOwnershipNotFoundError):
            await store.require_binding(host_id=HOST, device_id="device:missing", feature=FEATURE)
        with pytest.raises(ValueError):
            await store.list_visible(host_id=HOST, device_id="device:missing", limit=0)
        with pytest.raises(ValueError):
            PWAProactivityAdapter(store, lease_seconds=29)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_migration_backfills_existing_phase11b_owner_and_event(tmp_path: Path) -> None:
    database = tmp_path / "legacy-phase11b.db"
    encoded_now = NOW.isoformat(timespec="microseconds")
    encoded_expiry = (NOW + timedelta(hours=1)).isoformat(timespec="microseconds")
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                applied_at TEXT NOT NULL
            )
            """
        )
        root = files("jarvis.memory.migrations")
        for version in range(1, 13):
            resource = next(
                item for item in root.iterdir() if item.name.startswith(f"{version:03d}_")
            )
            connection.executescript(resource.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                (version, resource.name, encoded_now),
            )
        connection.execute(
            """
            INSERT INTO proactivity_rules
                (id, host_id, status, proposal_sha256, record_json, version,
                 expires_at, created_at, updated_at)
            VALUES ('rule:legacy', ?, 'active', ?, '{}', 1, ?, ?, ?)
            """,
            (HOST, "a" * 64, encoded_expiry, encoded_now, encoded_now),
        )
        connection.execute(
            """
            INSERT INTO proactivity_candidates
                (id, host_id, rule_id, feature, occurrence_key, scheduled_for,
                 attention_seconds, created_at, expires_at)
            VALUES ('candidate:legacy', ?, 'rule:legacy', ?, 'once:legacy', ?, 1, ?, ?)
            """,
            (HOST, FEATURE, encoded_now, encoded_now, encoded_expiry),
        )
        connection.execute(
            """
            INSERT INTO proactivity_dispatches
                (candidate_id, host_id, rule_id, state, version, attempts,
                 expires_at, created_at, updated_at)
            VALUES ('candidate:legacy', ?, 'rule:legacy', 'claimed', 1, 1, ?, ?, ?)
            """,
            (HOST, encoded_expiry, encoded_now, encoded_now),
        )
        connection.commit()

    async with SQLiteProactivityDeviceStore(database) as store:
        ownership = (await store.list_ownerships(host_id=HOST, now=NOW))[0]
        events = await store.list_events(host_id=HOST, candidate_id="candidate:legacy")
    assert ownership.owner_kind is OwnershipKind.LOCAL_HOST
    assert len(events) == 1
    assert events[0].reason_code == "phase11c_migration_backfill"
