from __future__ import annotations

import asyncio
import sqlite3
import sys
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.proactivity import (
    ForegroundProactivityRunner,
    HostProactivityPolicy,
    ProactivityProposal,
    ProactivityProvenance,
    ProposalSource,
    QuietHours,
    SQLiteProactivityRunnerStore,
    SQLiteProactivityStore,
    TriggerSchedule,
    TrustedActivation,
)
from jarvis.proactivity.worker import BoundedProactivityWorker
from jarvis.proactivity.worker_models import WorkerDeniedError, WorkerPlan, policy_digest
from jarvis.proactivity.worker_store import SQLiteProactivityWorkerStore

HOST = "host:worker-test"
FEATURE = "task.checkin"
NOW = datetime(2026, 11, 8, 19, 0, tzinfo=UTC)


def policy() -> HostProactivityPolicy:
    return HostProactivityPolicy(enabled=True, enabled_features=frozenset({FEATURE}))


def plan(*, now: datetime = NOW, generation: int = 0, **updates) -> WorkerPlan:
    values = dict(
        host_id=HOST,
        expected_generation=generation,
        policy_sha256=policy_digest(policy()),
        features=(FEATURE,),
        created_at=now,
        expires_at=now + timedelta(minutes=10),
        poll_seconds=1,
    )
    values.update(updates)
    return WorkerPlan(**values)


@pytest.fixture
def clock(monkeypatch):
    current = [NOW]
    for module in ("worker_models", "worker_store", "worker"):
        monkeypatch.setattr(f"jarvis.proactivity.{module}.utc_now", lambda: current[0])
    return current


async def active_rule(database: Path, *, now=NOW, due=None, quiet=(), feature=FEATURE):
    due = due or now + timedelta(seconds=2)
    proposal = ProactivityProposal(
        title="PRIVATE-WORKER-CANARY; never preview or disclose",
        feature=feature,
        schedule=TriggerSchedule(
            kind="once",
            timezone="UTC",
            local_date=due.date(),
            local_time=due.time().replace(tzinfo=None),
        ),
        quiet_hours=quiet,
        provenance=ProactivityProvenance(source_type=ProposalSource.HOST, source_id="test:worker"),
        created_at=now,
        expires_at=now + timedelta(hours=1),
    )
    p = replace(policy(), enabled_features=frozenset({FEATURE, feature}))
    async with SQLiteProactivityStore(database) as rules:
        draft = await rules.create_rule(host_id=HOST, preview=p.preview(proposal, now=now), now=now)
        return await rules.activate(
            TrustedActivation(
                approval_id=f"activation:{draft.id}",
                host_id=HOST,
                rule_id=draft.id,
                expected_version=1,
                expected_proposal_sha256=draft.proposal_sha256,
                approved_at=now,
                expires_at=now + timedelta(minutes=1),
            ),
            policy=p,
            now=now,
        )


async def tick(database, permit, *, now):
    async with (
        SQLiteProactivityStore(database) as rules,
        SQLiteProactivityRunnerStore(database) as inbox,
    ):
        return await ForegroundProactivityRunner(
            policy_store=rules,
            runner_store=inbox,
            task_store=None,
            policy=policy(),
            runner_enabled=True,
        ).tick(host_id=HOST, runner_id="test:worker", worker_permit=permit, now=now)


@pytest.mark.parametrize(
    "updates",
    [
        {"poll_seconds": 0},
        {"poll_seconds": 61},
        {"poll_seconds": True},
        {"max_ticks": 0},
        {"max_ticks": 3_601},
        {"features": ()},
        {"features": (FEATURE, FEATURE)},
        {"features": ("private\npreview",)},
        {"expires_at": NOW},
        {"expires_at": NOW + timedelta(seconds=3_601)},
        {"created_at": NOW.replace(tzinfo=None)},
        {"send_allowed": True},
        {"task_id": "task:forged"},
        {"provider": "calendar"},
    ],
)
def test_worker_plan_bounds_and_no_content_or_effect_authority(updates):
    with pytest.raises(ValidationError):
        plan(**updates)


@pytest.mark.parametrize(
    "changed,enabled",
    [
        (HostProactivityPolicy(), True),
        (policy(), False),
        (replace(policy(), enabled_features=frozenset()), True),
        (replace(policy(), max_candidates_per_hour=1), True),
    ],
)
def test_config_or_feature_revocation_denies(changed, enabled):
    with pytest.raises(WorkerDeniedError):
        plan().validate_policy(changed, runner_enabled=enabled)


async def test_default_off_and_host_isolation(tmp_path, clock):
    async with SQLiteProactivityWorkerStore(tmp_path / "core.db") as control:
        assert await control.status(host_id=HOST) == {
            "generation": 0,
            "enabled": False,
            "running": False,
            "ticks_reserved": 0,
        }
        with pytest.raises(WorkerDeniedError):
            await control.claim(host_id=HOST)
        await control.enable(plan())
        with pytest.raises(WorkerDeniedError):
            await control.claim(host_id="host:other")


@pytest.mark.parametrize("backwards", [1, 301, 86_400])
async def test_restart_after_backward_clock_jump_denies_before_claim(tmp_path, clock, backwards):
    async with SQLiteProactivityWorkerStore(tmp_path / "clock.db") as control:
        await control.enable(plan())
        clock[0] -= timedelta(seconds=backwards)
        with pytest.raises(WorkerDeniedError):
            await control.claim(host_id=HOST)
        assert not (await control.status(host_id=HOST))["running"]


async def test_clock_jump_between_claim_and_process_deadline_fails_closed(
    tmp_path, clock, monkeypatch
):
    db = tmp_path / "clock-gap.db"
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan())
        monkeypatch.setattr("jarvis.proactivity.worker.utc_now", lambda: NOW - timedelta(days=1))
        result = await asyncio.wait_for(
            BoundedProactivityWorker(
                db,
                host_id=HOST,
                policy_supplier=lambda: (policy(), True),
            ).run(),
            timeout=2,
        )
        assert result.ticks == 0 and result.reason == "revoked_or_budget_exhausted"
        assert not (await control.status(host_id=HOST))["running"]


async def test_exact_generation_stale_review_and_persistent_tick_budget(tmp_path, clock):
    db = tmp_path / "core.db"
    p = plan(max_ticks=2)
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(p)
        with pytest.raises(WorkerDeniedError):
            await control.enable(p)
        _, permit = await control.claim(host_id=HOST)
        await control.reserve_tick(permit, p)
        await control.release(permit)
    async with SQLiteProactivityWorkerStore(db) as control:
        _, permit = await control.claim(host_id=HOST)
        await control.reserve_tick(permit, p)
        with pytest.raises(WorkerDeniedError):
            await control.reserve_tick(permit, p)
        await control.release(permit)
        with pytest.raises(WorkerDeniedError):
            await control.claim(host_id=HOST)
        clock[0] += timedelta(minutes=6)
        with pytest.raises(WorkerDeniedError, match="stale"):
            await control.enable(plan(generation=1))


async def test_concurrent_claim_expired_lease_and_stale_release(tmp_path, clock):
    db = tmp_path / "core.db"
    async with (
        SQLiteProactivityWorkerStore(db) as first,
        SQLiteProactivityWorkerStore(db) as second,
    ):
        await first.enable(plan())
        results = await asyncio.gather(
            first.claim(host_id=HOST),
            second.claim(host_id=HOST),
            return_exceptions=True,
        )
        assert sum(isinstance(r, tuple) for r in results) == 1
        old = next(r[1] for r in results if isinstance(r, tuple))
        clock[0] += timedelta(seconds=91)
        _, new = await second.claim(host_id=HOST)
        with pytest.raises(WorkerDeniedError):
            await first.reserve_tick(old, plan())
        await first.release(old)
        await second.check(new)
        await second.stop(host_id=HOST)
        with pytest.raises(WorkerDeniedError):
            await second.check(new)


async def test_background_due_once_no_early_or_duplicate_and_private_rows(tmp_path, clock):
    db = tmp_path / "core.db"
    await active_rule(db)
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan())
        _, permit = await control.claim(host_id=HOST)
        await control.reserve_tick(permit, plan())
        assert (await tick(db, permit, now=NOW)).candidates_created == 0
        clock[0] += timedelta(seconds=2)
        first = await tick(db, permit, now=clock[0])
        assert first.candidates_created == first.notifications_ready == 1
        assert (await tick(db, permit, now=clock[0])).notifications_ready == 0
        await control.stop(host_id=HOST)
    with closing(sqlite3.connect(db)) as connection:
        for table in (
            "proactivity_candidates",
            "proactivity_dispatches",
            "proactivity_notifications",
            "proactivity_runner_events",
            "proactivity_worker_controls",
        ):
            data = repr(connection.execute(f"SELECT * FROM {table}").fetchall())
            assert "PRIVATE-WORKER-CANARY" not in data
        assert connection.execute("SELECT COUNT(*) FROM planning_tasks").fetchone()[0] == 0
        assert (
            connection.execute("SELECT plan_json FROM proactivity_worker_controls").fetchone()[0]
            is None
        )


@pytest.mark.parametrize("mode", ["stop", "replace", "lease", "host", "feature", "expiry"])
async def test_stale_permit_denies_every_candidate_write(tmp_path, clock, mode):
    db = tmp_path / "core.db"
    await active_rule(db)
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan())
        _, permit = await control.claim(host_id=HOST)
        clock[0] += timedelta(seconds=2)
        if mode == "stop":
            await control.stop(host_id=HOST)
        elif mode == "replace":
            await control.enable(plan(now=clock[0], generation=1))
        elif mode == "lease":
            clock[0] += timedelta(seconds=91)
        elif mode == "host":
            permit = replace(permit, host_id="host:other")
        elif mode == "feature":
            permit = replace(permit, features=("other.feature",))
        else:
            clock[0] += timedelta(hours=1)
        if mode == "feature":
            assert (await tick(db, permit, now=clock[0])).candidates_created == 0
        else:
            with pytest.raises(WorkerDeniedError):
                await tick(db, permit, now=clock[0])
    with closing(sqlite3.connect(db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM proactivity_candidates").fetchone()[0] == 0


async def test_stop_between_claim_and_completion_is_transactionally_fenced(tmp_path, clock):
    db = tmp_path / "core.db"
    rule = await active_rule(db)
    async with (
        SQLiteProactivityWorkerStore(db) as control,
        SQLiteProactivityStore(db) as rules,
        SQLiteProactivityRunnerStore(db) as inbox,
    ):
        await control.enable(plan())
        _, permit = await control.claim(host_id=HOST)
        clock[0] += timedelta(seconds=2)
        _, candidate = await rules.evaluate_and_record(
            host_id=HOST,
            rule_id=rule.id,
            policy=policy(),
            now=clock[0],
            worker_permit=permit,
        )
        assert candidate
        dispatch, _ = await inbox.claim_next(
            host_id=HOST,
            runner_id="test",
            lease_seconds=30,
            notification_ttl_seconds=60,
            now=clock[0],
            worker_permit=permit,
        )
        await control.stop(host_id=HOST)
        with pytest.raises(WorkerDeniedError):
            await inbox.complete_local_notification(
                host_id=HOST,
                candidate_id=candidate.id,
                lease_id=dispatch.lease_id,
                now=clock[0],
                worker_permit=permit,
            )
        assert await inbox.list_notifications(host_id=HOST) == ()


async def test_quiet_stale_and_nonallowlisted_feature_never_notifies(tmp_path, clock):
    db = tmp_path / "core.db"
    await active_rule(db, quiet=(QuietHours(start=time(18), end=time(20)),))
    await active_rule(db, feature="calendar.unapproved")
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan())
        _, permit = await control.claim(host_id=HOST)
        clock[0] += timedelta(seconds=2)
        assert (await tick(db, permit, now=clock[0])).notifications_ready == 0
        clock[0] += timedelta(seconds=301)
        _, permit = await control.claim(host_id=HOST)
        assert (await tick(db, permit, now=clock[0])).notifications_ready == 0


async def test_real_worker_budget_cancel_and_disable_observation(tmp_path):
    db = tmp_path / "core.db"
    now = datetime.now(UTC)
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan(now=now, max_ticks=2))
    result = await BoundedProactivityWorker(
        db, host_id=HOST, policy_supplier=lambda: (policy(), True)
    ).run()
    assert result.ticks == 2
    assert result.reason == "revoked_or_budget_exhausted"
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.stop(host_id=HOST)
        await control.enable(plan(now=datetime.now(UTC), generation=2))
        running = asyncio.create_task(
            BoundedProactivityWorker(
                db,
                host_id=HOST,
                policy_supplier=lambda: (policy(), True),
            ).run()
        )
        for _ in range(100):
            if (await control.status(host_id=HOST))["running"]:
                break
            await asyncio.sleep(0.02)
        await control.stop(host_id=HOST)
        result = await asyncio.wait_for(running, timeout=2)
        assert result.reason == "revoked_or_budget_exhausted"
        assert not (await control.status(host_id=HOST))["running"]


async def test_cancelled_worker_drains_and_releases_lease(tmp_path):
    db = tmp_path / "core.db"
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan(now=datetime.now(UTC)))
        running = asyncio.create_task(
            BoundedProactivityWorker(
                db,
                host_id=HOST,
                policy_supplier=lambda: (policy(), True),
            ).run()
        )
        for _ in range(100):
            if (await control.status(host_id=HOST))["running"]:
                break
            await asyncio.sleep(0.02)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert not (await control.status(host_id=HOST))["running"]
        _, permit = await control.claim(host_id=HOST)
        await control.release(permit)


async def test_real_process_kill_reenable_and_no_duplicate_inbox(tmp_path):
    db = tmp_path / "process.db"
    now = datetime.now(UTC)
    await active_rule(db, now=now, due=now + timedelta(milliseconds=100))
    script = """
import asyncio, sys
from jarvis.proactivity.worker import BoundedProactivityWorker
from jarvis.proactivity.policy import HostProactivityPolicy
policy = HostProactivityPolicy(enabled=True, enabled_features=frozenset({'task.checkin'}))
asyncio.run(BoundedProactivityWorker(sys.argv[1], host_id='host:worker-test',
    policy_supplier=lambda: (policy, True)).run())
"""
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan(now=now))
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            str(db),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            for _ in range(250):
                with closing(sqlite3.connect(db)) as connection:
                    count = connection.execute(
                        "SELECT COUNT(*) FROM proactivity_notifications"
                    ).fetchone()[0]
                if count == 1:
                    break
                await asyncio.sleep(0.02)
            assert count == 1
            with pytest.raises(WorkerDeniedError, match="another"):
                await control.claim(host_id=HOST)
        finally:
            child.kill()
            await asyncio.wait_for(child.communicate(), timeout=10)
        # No takeover of an unexpired lease merely because its process died.
        with pytest.raises(WorkerDeniedError, match="another"):
            await control.claim(host_id=HOST)
        await control.stop(host_id=HOST)
        await control.enable(plan(now=datetime.now(UTC), generation=2, max_ticks=1))
        resumed = await BoundedProactivityWorker(
            db,
            host_id=HOST,
            policy_supplier=lambda: (policy(), True),
        ).run()
        assert resumed.ticks == 1 and resumed.inbox_items == 0
        with closing(sqlite3.connect(db)) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM proactivity_notifications").fetchone()[0]
                == 1
            )


async def test_tick_timeout_cancels_work_and_releases_lease(tmp_path, monkeypatch):
    db = tmp_path / "timeout.db"
    cancelled = asyncio.Event()

    async def hanging(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(ForegroundProactivityRunner, "tick", hanging)
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan(now=datetime.now(UTC)))
        result = await BoundedProactivityWorker(
            db,
            host_id=HOST,
            policy_supplier=lambda: (policy(), True),
        ).run()
        assert result.reason == "tick_timeout" and cancelled.is_set()
        assert not (await control.status(host_id=HOST))["running"]


async def test_persistence_failure_rolls_back_and_stops_worker(tmp_path, monkeypatch):
    db = tmp_path / "failure.db"
    now = datetime.now(UTC)
    await active_rule(db, now=now, due=now + timedelta(milliseconds=50))
    original = SQLiteProactivityStore._append_event

    async def fail_candidate(self, connection, **kwargs):
        if kwargs.get("candidate_id") is not None:
            raise OSError("PRIVATE-DATABASE-ERROR-CANARY")
        return await original(self, connection, **kwargs)

    monkeypatch.setattr(SQLiteProactivityStore, "_append_event", fail_candidate)
    await asyncio.sleep(0.06)
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan(now=datetime.now(UTC)))
        with pytest.raises(OSError):
            await BoundedProactivityWorker(
                db,
                host_id=HOST,
                policy_supplier=lambda: (policy(), True),
            ).run()
        assert not (await control.status(host_id=HOST))["running"]
        with closing(sqlite3.connect(db)) as connection:
            assert (
                connection.execute("SELECT COUNT(*) FROM proactivity_candidates").fetchone()[0] == 0
            )


@pytest.mark.parametrize("change", ["global", "feature", "runner"])
async def test_running_policy_revocation_stops_before_second_tick(tmp_path, change):
    db = tmp_path / "revoke.db"
    current = [policy(), True]
    async with SQLiteProactivityWorkerStore(db) as control:
        await control.enable(plan(now=datetime.now(UTC), poll_seconds=60))
        running = asyncio.create_task(
            BoundedProactivityWorker(
                db,
                host_id=HOST,
                policy_supplier=lambda: (current[0], current[1]),
            ).run()
        )
        for _ in range(100):
            if (await control.status(host_id=HOST))["ticks_reserved"]:
                break
            await asyncio.sleep(0.02)
        if change == "global":
            current[0] = replace(policy(), enabled=False)
        elif change == "feature":
            current[0] = replace(policy(), enabled_features=frozenset())
        else:
            current[1] = False
        result = await asyncio.wait_for(running, timeout=2)
        assert result.ticks == 1 and result.reason == "revoked_or_budget_exhausted"
