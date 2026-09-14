from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, time, timedelta

import aiosqlite
import pytest

from jarvis.planning import (
    SQLiteTaskStore,
    TaskBudget,
    TaskCharge,
    TaskHandlerRegistry,
    TaskNodeProposal,
    TaskPlanProposal,
    TaskPlanValidator,
    TaskProvenance,
    TaskStatus,
    ValueTaskHandler,
)
from jarvis.proactivity import (
    DispatchState,
    ForegroundProactivityRunner,
    HostProactivityPolicy,
    NotificationState,
    ProactivityBudget,
    ProactivityHandoffDeniedError,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityRunnerDisabledError,
    ProactivityScope,
    ProposalSource,
    QuietHours,
    RuleStatus,
    RunnerConflictError,
    RunnerNotFoundError,
    RunnerStateError,
    SQLiteProactivityRunnerStore,
    SQLiteProactivityStore,
    TriggerKind,
    TriggerSchedule,
    TrustedActivation,
)

NOW = datetime(2026, 9, 14, 14, 0, tzinfo=UTC)
HOST = "host:runner"


def _policy() -> HostProactivityPolicy:
    return HostProactivityPolicy(
        enabled=True,
        enabled_features=frozenset({"task.checkin"}),
        max_task_steps=2,
        max_provider_requests=0,
        max_tool_calls=1,
        max_tokens=0,
    )


def _proposal(
    task_id: str,
    *,
    quiet_hours: tuple[QuietHours, ...] = (),
    expires_at: datetime = NOW + timedelta(days=1),
) -> ProactivityProposal:
    return ProactivityProposal(
        title="Private title must not enter runner rows",
        feature="task.checkin",
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="UTC",
            local_date=date(2026, 9, 14),
            local_time=time(14, 1),
        ),
        budget=ProactivityBudget(
            max_candidates_per_hour=1,
            max_candidates_per_day=1,
            max_attention_seconds_per_day=30,
            max_task_steps=2,
            max_provider_requests=0,
            max_tool_calls=1,
            max_tokens=0,
        ),
        quiet_hours=quiet_hours,
        scope=ProactivityScope(
            task_template_id=task_id,
            data_classes=("task_state",),
        ),
        provenance=ProactivityProvenance(
            source_type=ProposalSource.HOST,
            source_id="request:runner",
        ),
        created_at=NOW,
        expires_at=expires_at,
    )


async def _create_task(database, *, task_id: str = "task:handoff", steps: int = 1):
    registry = TaskHandlerRegistry([ValueTaskHandler()])
    validator = TaskPlanValidator(
        registry,
        envelope=TaskBudget(
            max_steps=10,
            max_wall_seconds=300,
            max_tokens=0,
            max_provider_requests=0,
            max_retries=0,
            max_tool_calls=10,
            max_concurrency=1,
        ),
        clock=lambda: NOW,
    )
    proposal = TaskPlanProposal(
        objective="Bounded local task",
        owner=HOST,
        provenance=TaskProvenance(source_type="host", source_id="request:task"),
        budget=TaskBudget(
            max_steps=steps,
            max_wall_seconds=300,
            max_tokens=0,
            max_provider_requests=0,
            max_retries=0,
            max_tool_calls=steps,
            max_concurrency=1,
        ),
        deadline_at=NOW + timedelta(minutes=5),
        nodes=tuple(
            TaskNodeProposal(
                id=f"node-{index}",
                handler="task.value",
                arguments={"value": index},
                charge=TaskCharge(tool_calls=1),
            )
            for index in range(steps)
        ),
    )
    graph = validator.validate(proposal, host_id=HOST, task_id=task_id)
    async with SQLiteTaskStore(database) as store:
        return await store.create_task(graph, now=NOW)


async def _create_active_rule(
    database,
    *,
    task_id: str = "task:handoff",
    quiet_hours: tuple[QuietHours, ...] = (),
    expires_at: datetime = NOW + timedelta(days=1),
):
    policy = _policy()
    preview = policy.preview(
        _proposal(task_id, quiet_hours=quiet_hours, expires_at=expires_at), now=NOW
    )
    async with SQLiteProactivityStore(database) as store:
        draft = await store.create_rule(host_id=HOST, preview=preview, now=NOW)
        return await store.activate(
            TrustedActivation(
                approval_id=f"activation:{task_id}",
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


def _runner(policy_store, runner_store, task_store, *, handoff: bool = True):
    return ForegroundProactivityRunner(
        policy_store=policy_store,
        runner_store=runner_store,
        task_store=task_store,
        policy=_policy(),
        runner_enabled=True,
        task_handoff_enabled=handoff,
    )


@pytest.mark.asyncio
async def test_foreground_tick_notifies_once_and_handoff_never_executes(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    task = await _create_task(database)
    await _create_active_rule(database)
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        runner = _runner(policy_store, runner_store, task_store)
        result = await runner.tick(
            host_id=HOST, runner_id="runner:first", now=NOW + timedelta(minutes=1)
        )
        assert (result.candidates_created, result.notifications_ready, result.effects_executed) == (
            1,
            1,
            0,
        )
        duplicate = await runner.tick(
            host_id=HOST, runner_id="runner:duplicate", now=NOW + timedelta(minutes=1)
        )
        assert duplicate.notifications_ready == 0
        notices = await runner_store.list_notifications(host_id=HOST)
        assert len(notices) == 1
        notice = notices[0]
        assert notice.state is NotificationState.ACTIVE
        dispatch = await runner.accept_handoff(
            host_id=HOST,
            candidate_id=notice.candidate_id,
            task_id=task.graph.id,
            expected_version=notice.dispatch_version,
            now=NOW + timedelta(minutes=1),
        )
        assert dispatch.state is DispatchState.HANDED_OFF
        with pytest.raises((RunnerConflictError, ProactivityHandoffDeniedError)):
            await runner.accept_handoff(
                host_id=HOST,
                candidate_id=notice.candidate_id,
                task_id=task.graph.id,
                expected_version=notice.dispatch_version,
                now=NOW + timedelta(minutes=1),
            )
        unchanged = await task_store.require_task(host_id=HOST, task_id=task.graph.id)
        assert unchanged.status is TaskStatus.PROPOSED
        assert all(node.attempts == 0 for node in unchanged.nodes)


@pytest.mark.asyncio
async def test_expired_lease_recovers_without_duplicate_notification(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    await _create_task(database)
    rule = await _create_active_rule(database)
    async with SQLiteProactivityStore(database) as policy_store:
        decision, candidate = await policy_store.evaluate_and_record(
            host_id=HOST,
            rule_id=rule.id,
            policy=_policy(),
            now=NOW + timedelta(minutes=1),
        )
        assert decision.eligible and candidate is not None
    async with SQLiteProactivityRunnerStore(database) as runner_store:
        claimed, recovered = await runner_store.claim_next(
            host_id=HOST,
            runner_id="runner:crashed",
            lease_seconds=30,
            notification_ttl_seconds=3_600,
            now=NOW + timedelta(minutes=1),
        )
        assert claimed is not None and recovered is False
    async with SQLiteProactivityRunnerStore(database) as runner_store:
        reclaimed, recovered = await runner_store.claim_next(
            host_id=HOST,
            runner_id="runner:restart",
            lease_seconds=30,
            notification_ttl_seconds=3_600,
            now=NOW + timedelta(minutes=1, seconds=31),
        )
        assert reclaimed is not None and recovered is True and reclaimed.attempts == 2
        assert reclaimed.lease_id is not None
        await runner_store.complete_local_notification(
            host_id=HOST,
            candidate_id=reclaimed.candidate_id,
            lease_id=reclaimed.lease_id,
            now=NOW + timedelta(minutes=1, seconds=31),
        )
        assert len(await runner_store.list_notifications(host_id=HOST)) == 1
        assert await runner_store.claim_next(
            host_id=HOST,
            runner_id="runner:again",
            lease_seconds=30,
            notification_ttl_seconds=3_600,
            now=NOW + timedelta(minutes=1, seconds=31),
        ) == (None, False)


@pytest.mark.asyncio
async def test_snooze_disable_and_delete_are_transitive_and_content_minimized(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    await _create_task(database)
    rule = await _create_active_rule(database)
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        runner = _runner(policy_store, runner_store, task_store)
        await runner.tick(host_id=HOST, runner_id="runner:first", now=NOW + timedelta(minutes=1))
        notice = (await runner_store.list_notifications(host_id=HOST))[0]
        snoozed = await runner_store.snooze(
            host_id=HOST,
            candidate_id=notice.candidate_id,
            expected_version=notice.dispatch_version,
            until=NOW + timedelta(minutes=3),
            max_snooze_seconds=3_600,
            now=NOW + timedelta(minutes=1),
        )
        assert snoozed.state is DispatchState.SNOOZED
        disabled = await policy_store.disable(
            host_id=HOST,
            rule_id=rule.id,
            expected_version=rule.version,
            now=NOW + timedelta(minutes=1, seconds=1),
        )
        assert disabled.status is RuleStatus.DISABLED
        cancelled = await runner_store.require_dispatch(
            host_id=HOST, candidate_id=notice.candidate_id
        )
        assert cancelled.state is DispatchState.CANCELLED
        async with aiosqlite.connect(database) as connection:
            for table in (
                "proactivity_dispatches",
                "proactivity_notifications",
                "proactivity_runner_events",
            ):
                rows = await (await connection.execute(f"SELECT * FROM {table}")).fetchall()
                assert "Private title" not in repr(rows)
        receipt = await policy_store.delete_rule(host_id=HOST, rule_id=rule.id, now=NOW)
        assert receipt.deleted_candidates == 1
    async with aiosqlite.connect(database) as connection:
        for table in (
            "proactivity_dispatches",
            "proactivity_notifications",
            "proactivity_runner_events",
        ):
            assert await (await connection.execute(f"SELECT COUNT(*) FROM {table}")).fetchone() == (
                0,
            )


@pytest.mark.asyncio
async def test_handoff_rejects_budget_expansion_and_wrong_task(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    await _create_task(database, task_id="task:too-large", steps=3)
    await _create_active_rule(database, task_id="task:too-large")
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        runner = _runner(policy_store, runner_store, task_store)
        await runner.tick(host_id=HOST, runner_id="runner:first", now=NOW + timedelta(minutes=1))
        notice = (await runner_store.list_notifications(host_id=HOST))[0]
        with pytest.raises(ProactivityHandoffDeniedError, match="budget"):
            await runner.accept_handoff(
                host_id=HOST,
                candidate_id=notice.candidate_id,
                task_id="task:too-large",
                expected_version=notice.dispatch_version,
                now=NOW + timedelta(minutes=1),
            )
        with pytest.raises(ProactivityHandoffDeniedError, match="does not match"):
            await runner.accept_handoff(
                host_id=HOST,
                candidate_id=notice.candidate_id,
                task_id="task:wrong",
                expected_version=notice.dispatch_version,
                now=NOW + timedelta(minutes=1),
            )


@pytest.mark.asyncio
async def test_concurrent_claim_has_one_owner(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    await _create_task(database)
    rule = await _create_active_rule(database)
    async with SQLiteProactivityStore(database) as policy_store:
        await policy_store.evaluate_and_record(
            host_id=HOST,
            rule_id=rule.id,
            policy=_policy(),
            now=NOW + timedelta(minutes=1),
        )

    async def claim(index: int):
        async with SQLiteProactivityRunnerStore(database) as store:
            return await store.claim_next(
                host_id=HOST,
                runner_id=f"runner:{index}",
                lease_seconds=30,
                notification_ttl_seconds=3_600,
                now=NOW + timedelta(minutes=1),
            )

    results = await asyncio.gather(*(claim(index) for index in range(10)))
    assert sum(dispatch is not None for dispatch, _ in results) == 1


@pytest.mark.asyncio
async def test_exhausted_recovery_attempts_fail_closed(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    await _create_task(database)
    rule = await _create_active_rule(database)
    async with SQLiteProactivityStore(database) as policy_store:
        await policy_store.evaluate_and_record(
            host_id=HOST,
            rule_id=rule.id,
            policy=_policy(),
            now=NOW + timedelta(minutes=1),
        )
    async with SQLiteProactivityRunnerStore(database) as runner_store:
        dispatch, _ = await runner_store.claim_next(
            host_id=HOST,
            runner_id="runner:first",
            lease_seconds=30,
            notification_ttl_seconds=3_600,
            now=NOW + timedelta(minutes=1),
        )
        assert dispatch is not None
    async with aiosqlite.connect(database) as connection:
        await connection.execute(
            "UPDATE proactivity_dispatches SET attempts = 10 WHERE candidate_id = ?",
            (dispatch.candidate_id,),
        )
        await connection.commit()
    async with SQLiteProactivityRunnerStore(database) as runner_store:
        assert await runner_store.claim_next(
            host_id=HOST,
            runner_id="runner:restart",
            lease_seconds=30,
            notification_ttl_seconds=3_600,
            now=NOW + timedelta(minutes=1, seconds=31),
        ) == (None, False)
        failed = await runner_store.require_dispatch(
            host_id=HOST, candidate_id=dispatch.candidate_id
        )
        assert failed.state is DispatchState.FAILED
        assert failed.failure_code == "lease_attempts_exhausted"
        events = await runner_store.list_events(host_id=HOST, candidate_id=dispatch.candidate_id)
        assert events[-1].reason_code == "lease_attempts_exhausted"


@pytest.mark.asyncio
async def test_runner_gates_and_store_inputs_fail_closed(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        disabled = ForegroundProactivityRunner(
            policy_store=policy_store,
            runner_store=runner_store,
            task_store=task_store,
            policy=_policy(),
        )
        with pytest.raises(ProactivityRunnerDisabledError):
            await disabled.tick(host_id=HOST, runner_id="runner:disabled", now=NOW)
        with pytest.raises(ProactivityHandoffDeniedError):
            await disabled.accept_handoff(
                host_id=HOST,
                candidate_id="candidate:missing",
                task_id="task:missing",
                expected_version=1,
                now=NOW,
            )
        with pytest.raises(RunnerNotFoundError):
            await runner_store.require_dispatch(host_id=HOST, candidate_id="candidate:missing")
        for runner_id, lease, ttl in (("", 30, 60), ("runner:1", 0, 60), ("runner:1", 30, 59)):
            with pytest.raises(ValueError):
                await runner_store.claim_next(
                    host_id=HOST,
                    runner_id=runner_id,
                    lease_seconds=lease,
                    notification_ttl_seconds=ttl,
                    now=NOW,
                )
        with pytest.raises(ValueError):
            await runner_store.list_notifications(host_id=HOST, limit=0)
        with pytest.raises(ValueError):
            await runner_store.list_events(host_id=HOST, candidate_id="candidate:missing", limit=0)
        for arguments in (
            {"lease_seconds": 0},
            {"notification_ttl_seconds": 59},
            {"max_snooze_seconds": 59},
        ):
            with pytest.raises(ValueError):
                ForegroundProactivityRunner(
                    policy_store=policy_store,
                    runner_store=runner_store,
                    task_store=task_store,
                    policy=_policy(),
                    **arguments,
                )


@pytest.mark.asyncio
async def test_snooze_resurfaces_once_then_dismisses_terminally(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    await _create_task(database)
    await _create_active_rule(database)
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        runner = _runner(policy_store, runner_store, task_store)
        await runner.tick(host_id=HOST, runner_id="runner:first", now=NOW + timedelta(minutes=1))
        notice = (await runner_store.list_notifications(host_id=HOST))[0]
        snoozed = await runner_store.snooze(
            host_id=HOST,
            candidate_id=notice.candidate_id,
            expected_version=notice.dispatch_version,
            until=NOW + timedelta(minutes=3),
            max_snooze_seconds=3_600,
            now=NOW + timedelta(minutes=1),
        )
        with pytest.raises(RunnerStateError, match="at least"):
            await runner_store.snooze(
                host_id=HOST,
                candidate_id=notice.candidate_id,
                expected_version=snoozed.version,
                until=NOW + timedelta(minutes=1, seconds=30),
                max_snooze_seconds=3_600,
                now=NOW + timedelta(minutes=1),
            )
        await runner.tick(
            host_id=HOST, runner_id="runner:resurface", now=NOW + timedelta(minutes=3)
        )
        resurfaced = (await runner_store.list_notifications(host_id=HOST))[0]
        assert resurfaced.id == notice.id
        dismissed = await runner_store.dismiss(
            host_id=HOST,
            candidate_id=notice.candidate_id,
            expected_version=resurfaced.dispatch_version,
            now=NOW + timedelta(minutes=3),
        )
        assert dismissed.state is DispatchState.DISMISSED
        with pytest.raises(RunnerStateError):
            await runner_store.cancel(
                host_id=HOST,
                candidate_id=notice.candidate_id,
                expected_version=dismissed.version,
                now=NOW + timedelta(minutes=3),
            )


@pytest.mark.asyncio
async def test_quiet_time_snoozes_or_cancels_near_expiry(tmp_path) -> None:
    quiet = (
        QuietHours(
            start=time(14, 2),
            end=time(15),
            weekdays=(0,),
        ),
    )
    for suffix, expiry, expected in (
        ("snooze", NOW + timedelta(hours=1), DispatchState.SNOOZED),
        ("cancel", NOW + timedelta(minutes=3, seconds=30), DispatchState.CANCELLED),
    ):
        database = tmp_path / f"{suffix}.db"
        await _create_task(database)
        rule = await _create_active_rule(database, quiet_hours=quiet, expires_at=expiry)
        async with SQLiteProactivityStore(database) as seed_store:
            decision, candidate = await seed_store.evaluate_and_record(
                host_id=HOST,
                rule_id=rule.id,
                policy=_policy(),
                now=NOW + timedelta(minutes=1),
            )
            assert decision.eligible and candidate is not None
        async with (
            SQLiteProactivityStore(database) as policy_store,
            SQLiteProactivityRunnerStore(database) as runner_store,
            SQLiteTaskStore(database) as task_store,
        ):
            result = await _runner(policy_store, runner_store, task_store).tick(
                host_id=HOST,
                runner_id=f"runner:{suffix}",
                now=NOW + timedelta(minutes=3),
            )
            assert result.denied >= 1 and result.notifications_ready == 0
            async with aiosqlite.connect(database) as connection:
                row = await (
                    await connection.execute("SELECT state FROM proactivity_dispatches")
                ).fetchone()
            assert row == (expected.value,)


@pytest.mark.asyncio
async def test_accept_rejects_disabled_handoff_and_expired_task(tmp_path) -> None:
    database = tmp_path / "jarvis.db"
    task = await _create_task(database)
    await _create_active_rule(database)
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        no_handoff = _runner(policy_store, runner_store, task_store, handoff=False)
        await no_handoff.tick(
            host_id=HOST, runner_id="runner:first", now=NOW + timedelta(minutes=1)
        )
        notice = (await runner_store.list_notifications(host_id=HOST))[0]
        with pytest.raises(ProactivityHandoffDeniedError, match="disabled"):
            await no_handoff.accept_handoff(
                host_id=HOST,
                candidate_id=notice.candidate_id,
                task_id=task.graph.id,
                expected_version=notice.dispatch_version,
                now=NOW + timedelta(minutes=1),
            )
        with pytest.raises(ProactivityHandoffDeniedError, match="deadline"):
            await _runner(policy_store, runner_store, task_store).accept_handoff(
                host_id=HOST,
                candidate_id=notice.candidate_id,
                task_id=task.graph.id,
                expected_version=notice.dispatch_version,
                now=NOW + timedelta(minutes=6),
            )
