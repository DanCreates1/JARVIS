from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, time, timedelta

import aiosqlite
import pytest

from jarvis.proactivity import (
    EvaluationCode,
    HostProactivityPolicy,
    ProactivityConflictError,
    ProactivityNotFoundError,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityScope,
    ProactivityStateError,
    ProposalSource,
    RuleStatus,
    SQLiteProactivityStore,
    TriggerKind,
    TriggerSchedule,
    TrustedActivation,
)

NOW = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)


def proposal() -> ProactivityProposal:
    return ProactivityProposal(
        title="Daily public briefing",
        feature="daily.briefing",
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="America/Toronto",
            local_date=date(2026, 9, 14),
            local_time=time(10, 1),
        ),
        scope=ProactivityScope(),
        provenance=ProactivityProvenance(
            source_type=ProposalSource.HOST,
            source_id="request:1",
        ),
        created_at=NOW,
        expires_at=NOW + timedelta(days=7),
    )


def policy(*, enabled: bool = True) -> HostProactivityPolicy:
    return HostProactivityPolicy(
        enabled=enabled,
        enabled_features=frozenset({"daily.briefing"}),
    )


def activation(
    rule_id: str, version: int, digest: str, *, host_id: str = "host:1"
) -> TrustedActivation:
    return TrustedActivation(
        approval_id="activation:1",
        host_id=host_id,
        rule_id=rule_id,
        expected_version=version,
        expected_proposal_sha256=digest,
        approved_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


@pytest.mark.asyncio
async def test_draft_preview_activation_restart_and_content_free_candidate(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    preview = policy().preview(proposal(), now=NOW)
    async with SQLiteProactivityStore(database) as store:
        draft = await store.create_rule(host_id="host:1", preview=preview, now=NOW)
        assert draft.status is RuleStatus.DRAFT
        inactive, candidate = await store.evaluate_and_record(
            host_id="host:1", rule_id=draft.id, policy=policy(), now=NOW + timedelta(minutes=1)
        )
        assert inactive.code is EvaluationCode.RULE_INACTIVE
        assert candidate is None
        active = await store.activate(
            activation(draft.id, draft.version, draft.proposal_sha256), policy=policy(), now=NOW
        )
        assert active.status is RuleStatus.ACTIVE

    async with SQLiteProactivityStore(database) as store:
        restored = await store.require_rule(host_id="host:1", rule_id=draft.id)
        assert restored.status is RuleStatus.ACTIVE
        decision, candidate = await store.evaluate_and_record(
            host_id="host:1",
            rule_id=draft.id,
            policy=policy(),
            now=NOW + timedelta(minutes=1),
        )
        assert decision.code is EvaluationCode.CANDIDATE_CREATED
        assert candidate is not None
        assert candidate.execution_authorized is False
        assert candidate.notification_sent is False
        assert candidate.content_retained is False
        duplicate, repeated = await store.evaluate_and_record(
            host_id="host:1",
            rule_id=draft.id,
            policy=policy(),
            now=NOW + timedelta(minutes=1),
        )
        assert duplicate.code is EvaluationCode.DUPLICATE
        assert repeated is None


@pytest.mark.asyncio
async def test_exact_activation_rejects_wrong_host_digest_version_expiry_and_replay(
    tmp_path,
) -> None:
    async with SQLiteProactivityStore(tmp_path / "jarvis.db") as store:
        preview = policy().preview(proposal(), now=NOW)
        drafts = [
            await store.create_rule(host_id="host:1", preview=preview, now=NOW) for _ in range(5)
        ]
        with pytest.raises(ProactivityNotFoundError):
            await store.activate(
                activation(drafts[0].id, 1, drafts[0].proposal_sha256, host_id="host:2"),
                policy=policy(),
                now=NOW,
            )
        with pytest.raises(ProactivityConflictError):
            await store.activate(
                activation(drafts[1].id, 2, drafts[1].proposal_sha256),
                policy=policy(),
                now=NOW,
            )
        with pytest.raises(ProactivityConflictError):
            await store.activate(activation(drafts[2].id, 1, "f" * 64), policy=policy(), now=NOW)
        expired = activation(drafts[3].id, 1, drafts[3].proposal_sha256).model_copy(
            update={
                "approval_id": "activation:expired",
                "approved_at": NOW - timedelta(minutes=5),
                "expires_at": NOW,
            }
        )
        with pytest.raises(Exception, match="expired"):
            await store.activate(expired, policy=policy(), now=NOW)
        first = activation(drafts[4].id, 1, drafts[4].proposal_sha256).model_copy(
            update={"approval_id": "activation:shared"}
        )
        await store.activate(first, policy=policy(), now=NOW)
        with pytest.raises(ProactivityStateError):
            await store.activate(first, policy=policy(), now=NOW)


@pytest.mark.asyncio
async def test_global_disable_rule_disable_host_isolation_and_clock_staleness(tmp_path) -> None:
    async with SQLiteProactivityStore(tmp_path / "jarvis.db") as store:
        preview = policy().preview(proposal(), now=NOW)
        draft = await store.create_rule(host_id="host:1", preview=preview, now=NOW)
        active = await store.activate(
            activation(draft.id, 1, draft.proposal_sha256), policy=policy(), now=NOW
        )
        denied, _ = await store.evaluate_and_record(
            host_id="host:1",
            rule_id=active.id,
            policy=policy(enabled=False),
            now=NOW + timedelta(minutes=1),
        )
        assert denied.code is EvaluationCode.GLOBAL_DISABLED
        stale, _ = await store.evaluate_and_record(
            host_id="host:1",
            rule_id=active.id,
            policy=policy(),
            now=NOW + timedelta(minutes=7),
        )
        assert stale.code is EvaluationCode.STALE_OCCURRENCE
        with pytest.raises(ProactivityNotFoundError):
            await store.require_rule(host_id="host:2", rule_id=active.id)
        disabled = await store.disable(
            host_id="host:1", rule_id=active.id, expected_version=active.version, now=NOW
        )
        result, _ = await store.evaluate_and_record(
            host_id="host:1",
            rule_id=active.id,
            policy=policy(),
            now=NOW + timedelta(minutes=1),
        )
        assert disabled.status is RuleStatus.DISABLED
        assert result.code is EvaluationCode.RULE_INACTIVE


@pytest.mark.asyncio
async def test_expiry_is_durable_and_cannot_create_candidate(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    async with SQLiteProactivityStore(database) as store:
        value = proposal().model_copy(update={"expires_at": NOW + timedelta(minutes=2)})
        preview = policy().preview(value, now=NOW)
        draft = await store.create_rule(host_id="host:1", preview=preview, now=NOW)
        await store.activate(
            activation(draft.id, 1, draft.proposal_sha256), policy=policy(), now=NOW
        )
        result, candidate = await store.evaluate_and_record(
            host_id="host:1",
            rule_id=draft.id,
            policy=policy(),
            now=NOW + timedelta(minutes=2),
        )
        assert result.code is EvaluationCode.RULE_EXPIRED
        assert candidate is None

    async with SQLiteProactivityStore(database) as store:
        restored = await store.require_rule(host_id="host:1", rule_id=draft.id)
        assert restored.status is RuleStatus.EXPIRED


@pytest.mark.asyncio
async def test_concurrent_duplicate_claim_has_one_candidate(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    async with SQLiteProactivityStore(database) as setup:
        preview = policy().preview(proposal(), now=NOW)
        draft = await setup.create_rule(host_id="host:1", preview=preview, now=NOW)
        await setup.activate(
            activation(draft.id, 1, draft.proposal_sha256), policy=policy(), now=NOW
        )

    async def attempt() -> EvaluationCode:
        async with SQLiteProactivityStore(database) as store:
            result, _ = await store.evaluate_and_record(
                host_id="host:1",
                rule_id=draft.id,
                policy=policy(),
                now=NOW + timedelta(minutes=1),
            )
            return result.code

    results = await asyncio.gather(*(attempt() for _ in range(10)))
    assert results.count(EvaluationCode.CANDIDATE_CREATED) == 1
    assert all(
        code in {EvaluationCode.CANDIDATE_CREATED, EvaluationCode.DUPLICATE} for code in results
    )


@pytest.mark.asyncio
async def test_export_refuses_overwrite_and_delete_is_transitive(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    export_path = tmp_path / "proactivity.json"
    async with SQLiteProactivityStore(database) as store:
        preview = policy().preview(proposal(), now=NOW)
        draft = await store.create_rule(host_id="host:1", preview=preview, now=NOW)
        active = await store.activate(
            activation(draft.id, 1, draft.proposal_sha256), policy=policy(), now=NOW
        )
        await store.evaluate_and_record(
            host_id="host:1",
            rule_id=active.id,
            policy=policy(),
            now=NOW + timedelta(minutes=1),
        )
        receipt = await store.export(host_id="host:1", path=export_path, now=NOW)
        assert (receipt.rule_count, receipt.candidate_count, receipt.event_count) == (1, 1, 3)
        payload = json.loads(export_path.read_text(encoding="utf-8"))
        assert payload["candidates"][0]["execution_authorized"] is False
        with pytest.raises(FileExistsError):
            await store.export(host_id="host:1", path=export_path, now=NOW)
        deleted = await store.delete_rule(host_id="host:1", rule_id=active.id, now=NOW)
        assert deleted.deleted_candidates == 1
        assert deleted.deleted_events == 3

    async with aiosqlite.connect(database) as connection:
        for table in (
            "proactivity_rules",
            "proactivity_activations",
            "proactivity_candidates",
            "proactivity_events",
        ):
            row = await (await connection.execute(f"SELECT COUNT(*) FROM {table}")).fetchone()
            assert row == (0,)
        tombstone = await (
            await connection.execute(
                "SELECT rule_id, deleted_candidates, deleted_events FROM proactivity_tombstones"
            )
        ).fetchone()
        assert tombstone == (active.id, 1, 3)


@pytest.mark.asyncio
async def test_corrupt_record_fails_closed(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    async with SQLiteProactivityStore(database) as store:
        preview = policy().preview(proposal(), now=NOW)
        draft = await store.create_rule(host_id="host:1", preview=preview, now=NOW)
    async with aiosqlite.connect(database) as connection:
        await connection.execute(
            "UPDATE proactivity_rules SET record_json = ? WHERE id = ?",
            ('{"status":"active"}', draft.id),
        )
        await connection.commit()
    async with SQLiteProactivityStore(database) as store:
        with pytest.raises(Exception, match="invalid"):
            await store.require_rule(host_id="host:1", rule_id=draft.id)
