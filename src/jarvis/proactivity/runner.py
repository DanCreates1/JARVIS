"""Explicit foreground Phase 11B runner; never a daemon or task executor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from jarvis.planning import SQLiteTaskStore, TaskRecord, TaskStatus

from .models import EvaluationCode, RuleStatus, TriggerEvent
from .policy import HostProactivityPolicy
from .runner_models import CandidateDispatch, DispatchState, RunnerTickResult
from .runner_store import SQLiteProactivityRunnerStore
from .sqlite_store import SQLiteProactivityStore


class ProactivityRunnerDisabledError(RuntimeError):
    pass


class ProactivityHandoffDeniedError(RuntimeError):
    pass


class ForegroundProactivityRunner:
    """Run one bounded evaluation/notification pass under caller-owned lifetime."""

    def __init__(
        self,
        *,
        policy_store: SQLiteProactivityStore,
        runner_store: SQLiteProactivityRunnerStore,
        task_store: SQLiteTaskStore,
        policy: HostProactivityPolicy,
        runner_enabled: bool = False,
        task_handoff_enabled: bool = False,
        lease_seconds: int = 30,
        notification_ttl_seconds: int = 3_600,
        max_snooze_seconds: int = 86_400,
    ) -> None:
        if not 1 <= lease_seconds <= 60:
            raise ValueError("runner lease must be 1 through 60 seconds")
        if not 60 <= notification_ttl_seconds <= 86_400:
            raise ValueError("notification TTL must be 60 through 86400 seconds")
        if not 60 <= max_snooze_seconds <= 86_400:
            raise ValueError("maximum snooze must be 60 through 86400 seconds")
        self._policy_store = policy_store
        self._runner_store = runner_store
        self._task_store = task_store
        self._policy = policy
        self._runner_enabled = runner_enabled
        self._task_handoff_enabled = task_handoff_enabled
        self._lease_seconds = lease_seconds
        self._notification_ttl_seconds = notification_ttl_seconds
        self._max_snooze_seconds = max_snooze_seconds

    async def tick(
        self,
        *,
        host_id: str,
        runner_id: str,
        now: datetime | None = None,
        event: TriggerEvent | None = None,
    ) -> RunnerTickResult:
        if not self._runner_enabled or not self._policy.enabled:
            raise ProactivityRunnerDisabledError("foreground proactivity runner is disabled")
        timestamp = _aware(now or datetime.now(UTC))
        rules = await self._policy_store.list_rules(
            host_id=host_id, status=RuleStatus.ACTIVE, limit=500
        )
        created = 0
        denied = 0
        for rule in rules:
            decision, candidate = await self._policy_store.evaluate_and_record(
                host_id=host_id,
                rule_id=rule.id,
                policy=self._policy,
                now=timestamp,
                event=event,
            )
            if candidate is not None:
                created += 1
            elif decision.code not in {
                EvaluationCode.NOT_DUE,
                EvaluationCode.EVENT_REQUIRED,
                EvaluationCode.EVENT_MISMATCH,
                EvaluationCode.DUPLICATE,
            }:
                denied += 1
        dispatch, recovered = await self._runner_store.claim_next(
            host_id=host_id,
            runner_id=runner_id,
            lease_seconds=self._lease_seconds,
            notification_ttl_seconds=self._notification_ttl_seconds,
            now=timestamp,
        )
        if dispatch is None:
            return RunnerTickResult(
                rules_evaluated=len(rules), candidates_created=created, denied=denied
            )
        rule = await self._policy_store.require_rule(host_id=host_id, rule_id=dispatch.rule_id)
        if rule.status is not RuleStatus.ACTIVE or rule.proposal.expires_at <= timestamp:
            await self._runner_store.cancel(
                host_id=host_id,
                candidate_id=dispatch.candidate_id,
                expected_version=dispatch.version,
                now=timestamp,
            )
            return RunnerTickResult(
                rules_evaluated=len(rules),
                candidates_created=created,
                recovered_leases=int(recovered),
                denied=denied + 1,
            )
        if self._policy.is_quiet_time(rule, at=timestamp):
            until = min(
                dispatch.expires_at - timedelta(microseconds=1),
                timestamp + timedelta(seconds=60),
            )
            if until < timestamp + timedelta(seconds=60):
                await self._runner_store.cancel(
                    host_id=host_id,
                    candidate_id=dispatch.candidate_id,
                    expected_version=dispatch.version,
                    now=timestamp,
                )
            else:
                await self._runner_store.snooze(
                    host_id=host_id,
                    candidate_id=dispatch.candidate_id,
                    expected_version=dispatch.version,
                    until=until,
                    max_snooze_seconds=self._max_snooze_seconds,
                    now=timestamp,
                )
            return RunnerTickResult(
                rules_evaluated=len(rules),
                candidates_created=created,
                recovered_leases=int(recovered),
                denied=denied + 1,
            )
        assert dispatch.lease_id is not None
        await self._runner_store.complete_local_notification(
            host_id=host_id,
            candidate_id=dispatch.candidate_id,
            lease_id=dispatch.lease_id,
            now=timestamp,
        )
        return RunnerTickResult(
            rules_evaluated=len(rules),
            candidates_created=created,
            notifications_ready=1,
            recovered_leases=int(recovered),
            denied=denied,
        )

    async def accept_handoff(
        self,
        *,
        host_id: str,
        candidate_id: str,
        task_id: str,
        expected_version: int,
        now: datetime | None = None,
    ) -> CandidateDispatch:
        if not self._runner_enabled or not self._task_handoff_enabled:
            raise ProactivityHandoffDeniedError("proactive task handoff is disabled")
        timestamp = _aware(now or datetime.now(UTC))
        dispatch = await self._runner_store.require_dispatch(
            host_id=host_id, candidate_id=candidate_id
        )
        if dispatch.version != expected_version:
            raise ProactivityHandoffDeniedError("candidate dispatch changed")
        if dispatch.state not in {DispatchState.NOTIFIED, DispatchState.SNOOZED}:
            raise ProactivityHandoffDeniedError("candidate is not available for handoff")
        rule = await self._policy_store.require_rule(host_id=host_id, rule_id=dispatch.rule_id)
        if rule.status is not RuleStatus.ACTIVE or rule.proposal.expires_at <= timestamp:
            raise ProactivityHandoffDeniedError("proactivity rule is inactive or expired")
        if rule.proposal.scope.task_template_id != task_id:
            raise ProactivityHandoffDeniedError("task does not match the activated rule")
        task = await self._task_store.require_task(host_id=host_id, task_id=task_id)
        self._validate_task_handoff(rule=rule, task=task, now=timestamp)
        return await self._runner_store.create_handoff(
            host_id=host_id,
            candidate_id=candidate_id,
            expected_version=expected_version,
            task=task,
            now=timestamp,
        )

    @staticmethod
    def _validate_task_handoff(*, rule: object, task: TaskRecord, now: datetime) -> None:
        from .models import ProactivityRule

        assert isinstance(rule, ProactivityRule)
        if task.status not in {TaskStatus.PROPOSED, TaskStatus.READY}:
            raise ProactivityHandoffDeniedError("task is not in a handoff-safe state")
        if task.graph.deadline_at <= now:
            raise ProactivityHandoffDeniedError("task deadline expired")
        budget = rule.proposal.budget
        task_budget = task.graph.budget
        if (
            task_budget.max_steps > budget.max_task_steps
            or task_budget.max_provider_requests > budget.max_provider_requests
            or task_budget.max_tool_calls > budget.max_tool_calls
            or task_budget.max_tokens > budget.max_tokens
            or task_budget.max_cost_usd > budget.max_cost_usd
            or task_budget.max_concurrency > budget.max_concurrency
        ):
            raise ProactivityHandoffDeniedError("task budget exceeds activated rule")
        if any(node.approval_grant_id is not None for node in task.graph.nodes):
            raise ProactivityHandoffDeniedError(
                "pre-bound effect grants are not accepted; bind fresh approval after handoff"
            )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("runner clock must be timezone-aware")
    return value.astimezone(UTC)
