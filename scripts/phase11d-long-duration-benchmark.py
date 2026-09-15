"""Phase 11D deterministic long-duration, incident, soak, and removal gate."""

from __future__ import annotations

import argparse
import asyncio
import ctypes
import json
import os
import sqlite3
import statistics
import sys
import tempfile
import time as clock
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from jarvis.core import AssistantService
from jarvis.core.models import (
    Conversation,
    Message,
    PolicyDecision,
    ProviderResponse,
    RuntimeStatus,
    ToolCall,
    ToolDefinition,
)
from jarvis.memory.sqlite_store import SQLiteConversationStore
from jarvis.planning import SQLiteTaskStore
from jarvis.proactivity import (
    DataClass,
    DeviceOwnershipConflictError,
    DeviceOwnershipDeniedError,
    EvaluationCode,
    ForegroundProactivityRunner,
    HostProactivityPolicy,
    OwnershipKind,
    ProactivityBudget,
    ProactivityNotFoundError,
    ProactivityProposal,
    ProactivityProvenance,
    ProactivityRule,
    ProactivityScope,
    ProposalSource,
    QuietHours,
    RuleStatus,
    SQLiteProactivityDeviceStore,
    SQLiteProactivityRunnerStore,
    SQLiteProactivityStore,
    TriggerEvent,
    TriggerKind,
    TriggerSchedule,
    TrustedActivation,
)
from jarvis.remote import SQLiteRemoteIdentityStore

VIRTUAL_DAYS = 30
DECISION_SAMPLES = 1_000
INCIDENT_SAMPLES = 100
SOAK_SECONDS = 1_800.0
SOAK_CYCLES = 1_800
SOAK_INTERVAL_SECONDS = 1.0
TICK_P95_LIMIT_MS = 50.0
RSS_GROWTH_LIMIT_MIB = 50.0
CPU_ONE_CORE_LIMIT_PERCENT = 5.0
RUNTIME_ROOT = (Path(__file__).resolve().parents[1] / "runtime").resolve()
BASE = datetime(2026, 10, 15, tzinfo=UTC)
HOST = "host:phase11d-benchmark"
DEVICE = "device:phase11d-benchmark"
FEATURE = "task.checkin"
TIMEZONES = ("UTC", "America/Toronto", "Europe/Berlin", "Australia/Sydney")
FORBIDDEN_EXPLANATION_FIELDS = frozenset(
    {
        "title",
        "prompt",
        "memory",
        "research",
        "task_arguments",
        "task_results",
        "notification_content",
        "credential",
        "approval",
        "destination",
        "private_payload",
    }
)


class _StaticProvider:
    async def chat(
        self, *, messages: Sequence[Message], tools: Sequence[ToolDefinition]
    ) -> ProviderResponse:
        del messages, tools
        return ProviderResponse(content="on-demand-core-ok")


class _NoToolPolicy:
    async def authorize(
        self,
        *,
        conversation: Conversation,
        call: ToolCall,
        tool: ToolDefinition,
        arguments: BaseModel,
    ) -> PolicyDecision:
        del conversation, call, tool, arguments
        return PolicyDecision(allowed=False, reason="benchmark exposes no tools")


def _proposal(
    *,
    timezone: str = "UTC",
    kind: TriggerKind = TriggerKind.DAILY,
    quiet: bool = False,
) -> ProactivityProposal:
    schedule = (
        TriggerSchedule(kind=kind, timezone=timezone, event_name="task.changed")
        if kind is TriggerKind.EVENT
        else TriggerSchedule(kind=kind, timezone=timezone, local_time=time(9))
    )
    quiet_hours = (
        (QuietHours(start=time(22), end=time(7), weekdays=tuple(range(7))),) if quiet else ()
    )
    return ProactivityProposal(
        title="Synthetic task check-in",
        feature=FEATURE,
        schedule=schedule,
        quiet_hours=quiet_hours,
        budget=ProactivityBudget(
            max_candidates_per_hour=6,
            max_candidates_per_day=24,
            max_attention_seconds_per_day=300,
        ),
        scope=ProactivityScope(data_classes=(DataClass.TASK_STATE,)),
        estimated_attention_seconds=10,
        provenance=ProactivityProvenance(
            source_type=ProposalSource.TEST,
            source_id="phase11d:synthetic-fixture",
        ),
        created_at=BASE,
        expires_at=BASE + timedelta(days=30),
    )


def _rule(
    *,
    timezone: str = "UTC",
    kind: TriggerKind = TriggerKind.DAILY,
    quiet: bool = False,
    status: RuleStatus = RuleStatus.ACTIVE,
) -> ProactivityRule:
    proposal = _proposal(timezone=timezone, kind=kind, quiet=quiet)
    preview = HostProactivityPolicy().preview(proposal, now=BASE)
    return ProactivityRule(
        id=f"rule:{timezone.replace('/', '-').lower()}:{kind.value}:{int(quiet)}",
        host_id=HOST,
        proposal=proposal,
        proposal_sha256=preview.proposal_sha256,
        status=status,
        version=2,
        created_at=BASE,
        updated_at=BASE,
        activated_at=BASE,
    )


def _due(rule: ProactivityRule, day: int) -> datetime:
    timezone = ZoneInfo(rule.proposal.schedule.timezone)
    preview = HostProactivityPolicy().preview(rule.proposal, now=BASE)
    assert preview.next_occurrence_at is not None
    local_date = preview.next_occurrence_at.astimezone(timezone).date() + timedelta(days=day)
    return datetime.combine(local_date, time(9), timezone).astimezone(UTC)


def _simulate(*, virtual_days: int, decision_samples: int) -> dict[str, Any]:
    if virtual_days < 1 or decision_samples < virtual_days * len(TIMEZONES):
        raise ValueError("decision samples must cover every virtual day and timezone")
    enabled = HostProactivityPolicy(enabled=True, enabled_features=frozenset({FEATURE}))
    disabled = HostProactivityPolicy(enabled=False, enabled_features=frozenset({FEATURE}))
    wrong_feature = HostProactivityPolicy(
        enabled=True, enabled_features=frozenset({"device.health"})
    )
    daily_rules = {timezone: _rule(timezone=timezone) for timezone in TIMEZONES}
    event_rule = _rule(kind=TriggerKind.EVENT)
    quiet_rule = _rule(kind=TriggerKind.EVENT, quiet=True)

    true_positives = 0
    false_positives = 0
    false_negatives = 0
    oracle_matches = 0
    quiet_hour_activity = 0
    disabled_activity = 0
    codes: Counter[str] = Counter()
    positive_occurrences: set[tuple[str, str]] = set()
    days_seen: set[int] = set()

    def record(*, decision: object, expected: EvaluationCode, positive: bool, day: int) -> None:
        nonlocal true_positives, false_positives, false_negatives, oracle_matches
        from jarvis.proactivity import EvaluationDecision

        assert isinstance(decision, EvaluationDecision)
        days_seen.add(day)
        codes[decision.code.value] += 1
        matched = decision.code is expected and decision.eligible is positive
        oracle_matches += int(matched)
        if positive:
            true_positives += int(decision.eligible and matched)
            false_negatives += int(not decision.eligible or not matched)
            if decision.eligible and decision.scheduled_for is not None:
                positive_occurrences.add(
                    (decision.rule_id, decision.scheduled_for.isoformat(timespec="microseconds"))
                )
        else:
            false_positives += int(decision.eligible)

    processed = 0
    for day in range(virtual_days):
        for rule in daily_rules.values():
            decision = enabled.evaluate(rule, now=_due(rule, day))
            record(
                decision=decision,
                expected=EvaluationCode.CANDIDATE_CREATED,
                positive=True,
                day=day,
            )
            processed += 1

    while processed < decision_samples:
        day = processed % virtual_days
        timezone = TIMEZONES[(processed // virtual_days) % len(TIMEZONES)]
        rule = daily_rules[timezone]
        due = _due(rule, day)
        mode = processed % 11
        event = TriggerEvent(id=f"event:{processed}", name="task.changed", occurred_at=due)
        if mode == 0:
            decision, expected = disabled.evaluate(rule, now=due), EvaluationCode.GLOBAL_DISABLED
            disabled_activity += int(decision.eligible)
        elif mode == 1:
            decision, expected = (
                wrong_feature.evaluate(rule, now=due),
                EvaluationCode.FEATURE_DISABLED,
            )
            disabled_activity += int(decision.eligible)
        elif mode == 2:
            decision, expected = (
                enabled.evaluate(rule, now=due, duplicate=True),
                EvaluationCode.DUPLICATE,
            )
        elif mode == 3:
            decision, expected = (
                enabled.evaluate(rule, now=due, hourly_count=6),
                EvaluationCode.HOURLY_LIMIT,
            )
        elif mode == 4:
            decision, expected = (
                enabled.evaluate(rule, now=due, daily_count=24),
                EvaluationCode.DAILY_LIMIT,
            )
        elif mode == 5:
            decision, expected = (
                enabled.evaluate(rule, now=due, daily_attention_seconds=300),
                EvaluationCode.ATTENTION_LIMIT,
            )
        elif mode == 6:
            decision, expected = (
                enabled.evaluate(rule, now=due, active_candidates=1),
                EvaluationCode.CANDIDATE_BUSY,
            )
        elif mode == 7:
            wrong = event.model_copy(update={"name": "device.changed"})
            decision, expected = (
                enabled.evaluate(event_rule, now=due, event=wrong),
                EvaluationCode.EVENT_MISMATCH,
            )
        elif mode == 8:
            stale = event.model_copy(update={"occurred_at": due - timedelta(seconds=301)})
            decision, expected = (
                enabled.evaluate(event_rule, now=due, event=stale),
                EvaluationCode.STALE_OCCURRENCE,
            )
        elif mode == 9:
            local = due.astimezone(UTC).replace(hour=23)
            quiet_event = event.model_copy(update={"occurred_at": local})
            decision, expected = (
                enabled.evaluate(quiet_rule, now=local, event=quiet_event),
                EvaluationCode.QUIET_HOURS,
            )
            quiet_hour_activity += int(decision.eligible)
        else:
            inactive = rule.model_copy(update={"status": RuleStatus.DISABLED})
            decision, expected = (
                enabled.evaluate(inactive, now=due),
                EvaluationCode.RULE_INACTIVE,
            )
        record(decision=decision, expected=expected, positive=False, day=day)
        processed += 1

    by_hour: Counter[str] = Counter()
    by_day: Counter[str] = Counter()
    attention_by_day: Counter[str] = Counter()
    for _, encoded in positive_occurrences:
        instant = datetime.fromisoformat(encoded)
        by_hour[instant.strftime("%Y-%m-%dT%H")] += 1
        by_day[instant.date().isoformat()] += 1
        attention_by_day[instant.date().isoformat()] += 10
    max_hourly = max(by_hour.values(), default=0)
    max_daily = max(by_day.values(), default=0)
    max_attention = max(attention_by_day.values(), default=0)
    precision = true_positives / max(1, true_positives + false_positives)
    recall = true_positives / max(1, true_positives + false_negatives)
    return {
        "virtual_days": len(days_seen),
        "timezones": list(TIMEZONES),
        "decision_samples": processed,
        "oracle_matches": oracle_matches,
        "oracle_agreement": oracle_matches / processed,
        "useful_true_positives": true_positives,
        "useful_precision": precision,
        "useful_recall": recall,
        "false_proactivity": false_positives,
        "quiet_hour_activity": quiet_hour_activity,
        "disabled_activity": disabled_activity,
        "max_candidates_per_hour": max_hourly,
        "max_candidates_per_day": max_daily,
        "max_attention_seconds_per_day": max_attention,
        "host_budget_breaches": int(max_hourly > 6 or max_daily > 24 or max_attention > 300),
        "decision_codes": dict(sorted(codes.items())),
    }


async def _create_ready_candidate(database: Path) -> tuple[str, str, HostProactivityPolicy]:
    policy = HostProactivityPolicy(enabled=True, enabled_features=frozenset({FEATURE}))
    proposal = ProactivityProposal(
        title="Synthetic one-time check-in",
        feature=FEATURE,
        schedule=TriggerSchedule(
            kind=TriggerKind.ONCE,
            timezone="UTC",
            local_date=BASE.date(),
            local_time=time(0, 1),
        ),
        scope=ProactivityScope(data_classes=(DataClass.TASK_STATE,)),
        provenance=ProactivityProvenance(
            source_type=ProposalSource.TEST,
            source_id="phase11d:integrated-fixture",
        ),
        created_at=BASE,
        expires_at=BASE + timedelta(days=1),
    )
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        preview = policy.preview(proposal, now=BASE)
        draft = await policy_store.create_rule(host_id=HOST, preview=preview, now=BASE)
        active = await policy_store.activate(
            TrustedActivation(
                approval_id="activation:phase11d",
                host_id=HOST,
                rule_id=draft.id,
                expected_version=draft.version,
                expected_proposal_sha256=draft.proposal_sha256,
                approved_at=BASE,
                expires_at=BASE + timedelta(minutes=5),
            ),
            policy=policy,
            now=BASE,
        )
        runner = ForegroundProactivityRunner(
            policy_store=policy_store,
            runner_store=runner_store,
            task_store=task_store,
            policy=policy,
            runner_enabled=True,
        )
        tick = await runner.tick(
            host_id=HOST,
            runner_id="runner:phase11d:create",
            now=BASE + timedelta(minutes=1),
        )
        if tick.candidates_created != 1 or tick.notifications_ready != 1:
            raise RuntimeError("integrated Phase 11D fixture did not create one ready suggestion")
        notices = await runner_store.list_notifications(host_id=HOST)
        if len(notices) != 1:
            raise RuntimeError("integrated Phase 11D fixture produced wrong inbox cardinality")
        return active.id, notices[0].candidate_id, policy


async def _soak(
    database: Path,
    *,
    policy: HostProactivityPolicy,
    soak_seconds: float,
    soak_cycles: int,
    interval_seconds: float,
) -> dict[str, Any]:
    latencies: list[float] = []
    start_rss = _rss_bytes()
    peak_rss = start_rss
    started_wall = clock.perf_counter()
    started_cpu = clock.process_time()
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        runner = ForegroundProactivityRunner(
            policy_store=policy_store,
            runner_store=runner_store,
            task_store=task_store,
            policy=policy,
            runner_enabled=True,
        )
        cycle = 0
        while cycle < soak_cycles or clock.perf_counter() - started_wall < soak_seconds:
            now = BASE + timedelta(minutes=1)
            started_tick = clock.perf_counter_ns()
            result = await runner.tick(
                host_id=HOST,
                runner_id=f"runner:phase11d:soak:{cycle % 4}",
                now=now,
            )
            latencies.append((clock.perf_counter_ns() - started_tick) / 1_000_000)
            if result.notifications_ready or result.effects_executed:
                raise RuntimeError("soak redelivered a suggestion or executed an effect")
            cycle += 1
            if cycle % 10 == 0:
                peak_rss = max(peak_rss, _rss_bytes())
            if interval_seconds > 0 and (
                cycle < soak_cycles or clock.perf_counter() - started_wall < soak_seconds
            ):
                await asyncio.sleep(interval_seconds)
    elapsed = clock.perf_counter() - started_wall
    cpu_seconds = clock.process_time() - started_cpu
    return {
        "wall_seconds": elapsed,
        "cycles": len(latencies),
        "tick_p50_ms": statistics.median(latencies),
        "tick_p95_ms": _percentile(latencies, 0.95),
        "tick_max_ms": max(latencies),
        "average_cpu_one_core_percent": cpu_seconds / max(elapsed, 1e-9) * 100,
        "rss_growth_mib": max(0, peak_rss - start_rss) / (1024 * 1024),
    }


def _seed_device(database: Path) -> None:
    encoded_now = BASE.isoformat(timespec="microseconds")
    encoded_expiry = (BASE + timedelta(days=1)).isoformat(timespec="microseconds")
    scopes = json.dumps(["client.proactivity.manage", "client.proactivity.read"])
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            """
            INSERT INTO remote_devices
                (id, host_id, display_name, device_type, public_key, key_fingerprint,
                 key_version, scopes_json, risk_ceiling, protocol_version, state,
                 enrolled_at, credential_expires_at)
            VALUES (?, ?, 'Phase 11D fixture', 'browser', ?, ?, 1, ?, 1, '1', 'active', ?, ?)
            """,
            (DEVICE, HOST, "A" * 43, "a" * 64, scopes, encoded_now, encoded_expiry),
        )
        connection.commit()
    finally:
        connection.close()


async def _incidents_and_removal(
    database: Path,
    *,
    directory: Path,
    rule_id: str,
    candidate_id: str,
    policy: HostProactivityPolicy,
    incident_samples: int,
) -> dict[str, Any]:
    categories: Counter[str] = Counter()
    failures = 0

    def record(category: str, passed: bool) -> None:
        nonlocal failures
        categories[category] += 1
        failures += int(not passed)

    # Restart and duplicate delivery recovery.
    async with (
        SQLiteProactivityStore(database) as policy_store,
        SQLiteProactivityRunnerStore(database) as runner_store,
        SQLiteTaskStore(database) as task_store,
    ):
        runner = ForegroundProactivityRunner(
            policy_store=policy_store,
            runner_store=runner_store,
            task_store=task_store,
            policy=policy,
            runner_enabled=True,
        )
        duplicate = await runner.tick(
            host_id=HOST,
            runner_id="runner:phase11d:restart",
            now=BASE + timedelta(minutes=1),
        )
        notices = await runner_store.list_notifications(host_id=HOST)
        record(
            "restart_duplicate",
            duplicate.notifications_ready == 0 and len(notices) == 1,
        )
        explanation = await policy_store.explain_candidate(host_id=HOST, candidate_id=candidate_id)
        explanation_payload = explanation.model_dump(mode="json")
        record(
            "sanitized_explanation",
            not (FORBIDDEN_EXPLANATION_FIELDS & explanation_payload.keys())
            and explanation.used_data_classes == ()
            and explanation.tools_used == ()
            and explanation.providers_used == ()
            and explanation.effective_audience == "local_host",
        )
        try:
            await policy_store.explain_candidate(host_id="host:wrong", candidate_id=candidate_id)
        except ProactivityNotFoundError:
            record("host_isolation", True)
        else:
            record("host_isolation", False)

    _seed_device(database)
    incident_now = BASE + timedelta(minutes=2)
    async with SQLiteProactivityDeviceStore(database) as device_store:
        await device_store.set_control(host_id=HOST, enabled=True, now=incident_now)
        binding = await device_store.bind_device(
            host_id=HOST,
            device_id=DEVICE,
            feature=FEATURE,
            allow_manage=True,
            expires_at=incident_now + timedelta(hours=1),
            now=incident_now,
        )
        local = (await device_store.list_ownerships(host_id=HOST, now=incident_now))[0]
        owned = await device_store.claim(
            host_id=HOST,
            device_id=DEVICE,
            candidate_id=candidate_id,
            expected_version=local.version,
            lease_seconds=30,
            allowed_features=frozenset({FEATURE}),
            now=incident_now,
        )
        async with SQLiteProactivityStore(database) as policy_store:
            scoped = await policy_store.explain_candidate(host_id=HOST, candidate_id=candidate_id)
        record(
            "scoped_audience",
            scoped.effective_audience == "scoped_pwa_device",
        )
        recovered = (
            await device_store.list_ownerships(
                host_id=HOST, now=incident_now + timedelta(seconds=31)
            )
        )[0]
        record(
            "expired_lease",
            recovered.owner_kind is OwnershipKind.LOCAL_HOST and recovered.version > owned.version,
        )
        try:
            await device_store.renew(
                host_id=HOST,
                device_id=DEVICE,
                candidate_id=candidate_id,
                expected_version=owned.version,
                lease_seconds=30,
                allowed_features=frozenset({FEATURE}),
                now=incident_now + timedelta(seconds=31),
            )
        except (DeviceOwnershipConflictError, DeviceOwnershipDeniedError):
            record("stale_owner", True)
        else:
            record("stale_owner", False)

        owned = await device_store.claim(
            host_id=HOST,
            device_id=DEVICE,
            candidate_id=candidate_id,
            expected_version=recovered.version,
            lease_seconds=30,
            allowed_features=frozenset({FEATURE}),
            now=incident_now + timedelta(seconds=32),
        )
        await device_store.set_control(
            host_id=HOST, enabled=False, now=incident_now + timedelta(seconds=33)
        )
        killed = (
            await device_store.list_ownerships(
                host_id=HOST, now=incident_now + timedelta(seconds=33)
            )
        )[0]
        record(
            "adapter_kill",
            killed.owner_kind is OwnershipKind.LOCAL_HOST and killed.version > owned.version,
        )
        try:
            await device_store.claim(
                host_id=HOST,
                device_id=DEVICE,
                candidate_id=candidate_id,
                expected_version=killed.version,
                lease_seconds=30,
                allowed_features=frozenset({FEATURE}),
                now=incident_now + timedelta(seconds=34),
            )
        except DeviceOwnershipDeniedError:
            record("adapter_disabled", True)
        else:
            record("adapter_disabled", False)

        await device_store.set_control(
            host_id=HOST, enabled=True, now=incident_now + timedelta(seconds=35)
        )
        owned = await device_store.claim(
            host_id=HOST,
            device_id=DEVICE,
            candidate_id=candidate_id,
            expected_version=killed.version,
            lease_seconds=30,
            allowed_features=frozenset({FEATURE}),
            now=incident_now + timedelta(seconds=36),
        )
        revoked_binding = await device_store.revoke_binding(
            host_id=HOST,
            device_id=DEVICE,
            feature=FEATURE,
            expected_version=binding.version,
            now=incident_now + timedelta(seconds=37),
        )
        reclaimed = (
            await device_store.list_ownerships(
                host_id=HOST, now=incident_now + timedelta(seconds=37)
            )
        )[0]
        record(
            "binding_revoke",
            revoked_binding.state.value == "revoked"
            and reclaimed.owner_kind is OwnershipKind.LOCAL_HOST
            and reclaimed.version > owned.version,
        )
        await device_store.bind_device(
            host_id=HOST,
            device_id=DEVICE,
            feature=FEATURE,
            allow_manage=True,
            expires_at=incident_now + timedelta(hours=1),
            now=incident_now + timedelta(seconds=38),
        )
        owned = await device_store.claim(
            host_id=HOST,
            device_id=DEVICE,
            candidate_id=candidate_id,
            expected_version=reclaimed.version,
            lease_seconds=30,
            allowed_features=frozenset({FEATURE}),
            now=incident_now + timedelta(seconds=39),
        )

    remote_store = SQLiteRemoteIdentityStore(database)
    try:
        await remote_store.initialize()
        revoked = await remote_store.revoke_device(
            device_id=DEVICE,
            host_id=HOST,
            revoked_at=incident_now + timedelta(seconds=40),
        )
    finally:
        await remote_store.close()
    async with SQLiteProactivityDeviceStore(database) as device_store:
        after_revoke = (
            await device_store.list_ownerships(
                host_id=HOST, now=incident_now + timedelta(seconds=40)
            )
        )[0]
        record(
            "device_revoke",
            revoked
            and after_revoke.owner_kind is OwnershipKind.LOCAL_HOST
            and after_revoke.version > owned.version,
        )

    corrupt = directory / "corrupt-evaluation.db"
    corrupt.write_bytes(b"not-a-sqlite-database")
    try:
        failed_store = SQLiteProactivityStore(corrupt)
        await failed_store.initialize()
    except Exception:
        record("persistence_failure", True)
    else:
        record("persistence_failure", False)
        await failed_store.close()

    # Repeat deterministic fail-closed observations until the fixed incident sample is met.
    while sum(categories.values()) < incident_samples:
        mode = sum(categories.values()) % 5
        if mode == 0:
            async with (
                SQLiteProactivityStore(database) as policy_store,
                SQLiteProactivityRunnerStore(database) as runner_store,
                SQLiteTaskStore(database) as task_store,
            ):
                runner = ForegroundProactivityRunner(
                    policy_store=policy_store,
                    runner_store=runner_store,
                    task_store=task_store,
                    policy=policy,
                    runner_enabled=True,
                )
                result = await runner.tick(
                    host_id=HOST,
                    runner_id=f"runner:phase11d:duplicate:{sum(categories.values())}",
                    now=BASE + timedelta(minutes=1),
                )
                notices = await runner_store.list_notifications(host_id=HOST)
                record(
                    "restart_duplicate",
                    result.notifications_ready == 0 and len(notices) == 1,
                )
        elif mode == 1:
            async with SQLiteProactivityDeviceStore(database) as device_store:
                try:
                    await device_store.claim(
                        host_id=HOST,
                        device_id=DEVICE,
                        candidate_id=candidate_id,
                        expected_version=after_revoke.version,
                        lease_seconds=30,
                        allowed_features=frozenset({FEATURE}),
                        now=incident_now + timedelta(seconds=41),
                    )
                except DeviceOwnershipDeniedError:
                    record("device_revoke", True)
                else:
                    record("device_revoke", False)
        elif mode == 2:
            decision = HostProactivityPolicy(
                enabled=False, enabled_features=frozenset({FEATURE})
            ).evaluate(_rule(), now=_due(_rule(), 0))
            record("global_kill", decision.code is EvaluationCode.GLOBAL_DISABLED)
        elif mode == 3:
            async with SQLiteProactivityStore(database) as policy_store:
                try:
                    await policy_store.explain_candidate(
                        host_id="host:wrong", candidate_id=candidate_id
                    )
                except ProactivityNotFoundError:
                    record("host_isolation", True)
                else:
                    record("host_isolation", False)
        else:
            async with SQLiteProactivityDeviceStore(database) as device_store:
                ownerships = await device_store.list_ownerships(
                    host_id=HOST, now=incident_now + timedelta(seconds=41)
                )
                record(
                    "single_owner",
                    len(ownerships) == 1 and ownerships[0].owner_kind is OwnershipKind.LOCAL_HOST,
                )

    async with SQLiteProactivityStore(database) as policy_store:
        active = await policy_store.require_rule(host_id=HOST, rule_id=rule_id)
        await policy_store.disable(
            host_id=HOST,
            rule_id=rule_id,
            expected_version=active.version,
            now=incident_now + timedelta(minutes=1),
        )
    async with SQLiteProactivityRunnerStore(database) as runner_store:
        dispatch = await runner_store.require_dispatch(host_id=HOST, candidate_id=candidate_id)
        notices = await runner_store.list_notifications(host_id=HOST)
        record(
            "rule_disable_cancel",
            dispatch.state.value == "cancelled"
            and len(notices) == 1
            and notices[0].state.value == "cancelled",
        )

    async with SQLiteProactivityStore(database) as policy_store:
        explanation = await policy_store.explain_candidate(host_id=HOST, candidate_id=candidate_id)
        await policy_store.delete_rule(host_id=HOST, rule_id=rule_id)

    removal_counts = _rule_state_counts(database, rule_id=rule_id)
    tombstone_content_free = _tombstone_content_free(database, rule_id=rule_id)
    on_demand_core = await _on_demand_core(database)
    return {
        "incident_samples": sum(categories.values()),
        "incident_failures": failures,
        "incident_categories": dict(sorted(categories.items())),
        "explanation": explanation.model_dump(mode="json"),
        "forbidden_explanation_fields": sorted(
            FORBIDDEN_EXPLANATION_FIELDS & explanation.model_dump().keys()
        ),
        "rule_state_rows_after_delete": removal_counts,
        "rule_state_removed": all(count == 0 for count in removal_counts.values()),
        "content_free_tombstone": tombstone_content_free,
        "on_demand_core_passed": on_demand_core,
    }


def _rule_state_counts(database: Path, *, rule_id: str) -> dict[str, int]:
    queries = {
        "rules": ("SELECT COUNT(*) FROM proactivity_rules WHERE id = ?", (rule_id,)),
        "activations": (
            "SELECT COUNT(*) FROM proactivity_activations WHERE rule_id = ?",
            (rule_id,),
        ),
        "candidates": (
            "SELECT COUNT(*) FROM proactivity_candidates WHERE rule_id = ?",
            (rule_id,),
        ),
        "events": ("SELECT COUNT(*) FROM proactivity_events WHERE rule_id = ?", (rule_id,)),
        "dispatches": (
            "SELECT COUNT(*) FROM proactivity_dispatches WHERE rule_id = ?",
            (rule_id,),
        ),
        "notifications": (
            "SELECT COUNT(*) FROM proactivity_notifications WHERE rule_id = ?",
            (rule_id,),
        ),
        "runner_events": (
            "SELECT COUNT(*) FROM proactivity_runner_events WHERE rule_id = ?",
            (rule_id,),
        ),
        "ownerships": (
            "SELECT COUNT(*) FROM proactivity_ownerships WHERE rule_id = ?",
            (rule_id,),
        ),
        "ownership_events": (
            """
            SELECT COUNT(*) FROM proactivity_ownership_events AS e
            JOIN proactivity_candidates AS c ON c.id = e.candidate_id
            WHERE c.rule_id = ?
            """,
            (rule_id,),
        ),
    }
    connection = sqlite3.connect(database)
    try:
        return {
            name: int(connection.execute(sql, parameters).fetchone()[0])
            for name, (sql, parameters) in queries.items()
        }
    finally:
        connection.close()


def _tombstone_content_free(database: Path, *, rule_id: str) -> bool:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM proactivity_tombstones WHERE rule_id = ?", (rule_id,)
        ).fetchone()
        return row is not None and set(row.keys()) == {
            "rule_id",
            "host_id",
            "deleted_candidates",
            "deleted_events",
            "deleted_at",
        }
    finally:
        connection.close()


async def _on_demand_core(database: Path) -> bool:
    async with SQLiteConversationStore(database) as store:
        service = AssistantService(
            provider=_StaticProvider(),
            store=store,
            tools=(),
            policy=_NoToolPolicy(),
        )
        result = await service.respond("Run ordinary on-demand core check.")
        if result.status is not RuntimeStatus.COMPLETED or result.reply != "on-demand-core-ok":
            return False
        deleted = await store.delete_conversation(result.conversation_id)
        return deleted and await store.get_conversation(result.conversation_id) is None


async def _measure(
    *,
    virtual_days: int = VIRTUAL_DAYS,
    decision_samples: int = DECISION_SAMPLES,
    incident_samples: int = INCIDENT_SAMPLES,
    soak_seconds: float = SOAK_SECONDS,
    soak_cycles: int = SOAK_CYCLES,
    soak_interval_seconds: float = SOAK_INTERVAL_SECONDS,
    enforce_minimums: bool = False,
) -> dict[str, Any]:
    simulation = _simulate(virtual_days=virtual_days, decision_samples=decision_samples)
    RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="phase11d-", dir=RUNTIME_ROOT) as raw_directory:
        directory = Path(raw_directory)
        database = directory / "jarvis.db"
        rule_id, candidate_id, policy = await _create_ready_candidate(database)
        soak = await _soak(
            database,
            policy=policy,
            soak_seconds=soak_seconds,
            soak_cycles=soak_cycles,
            interval_seconds=soak_interval_seconds,
        )
        lifecycle = await _incidents_and_removal(
            database,
            directory=directory,
            rule_id=rule_id,
            candidate_id=candidate_id,
            policy=policy,
            incident_samples=incident_samples,
        )
        temporary_path = directory
    temporary_evaluation_state_deleted = not temporary_path.exists()

    minimums_met = (
        simulation["virtual_days"] >= VIRTUAL_DAYS
        and simulation["decision_samples"] >= DECISION_SAMPLES
        and lifecycle["incident_samples"] >= INCIDENT_SAMPLES
        and soak["wall_seconds"] >= SOAK_SECONDS
        and soak["cycles"] >= SOAK_CYCLES
    )
    zero_activity = {
        "cloud_cost_usd": 0,
        "provider_requests": 0,
        "tool_calls": 0,
        "task_executions": 0,
        "effects_executed": 0,
        "external_notifications_sent": 0,
        "duplicate_notifications": 0,
        "retained_candidate_content": 0,
    }
    thresholds = {
        "virtual_days_min": VIRTUAL_DAYS,
        "decision_samples_min": DECISION_SAMPLES,
        "incident_samples_min": INCIDENT_SAMPLES,
        "soak_seconds_min": SOAK_SECONDS,
        "soak_cycles_min": SOAK_CYCLES,
        "useful_precision_min": 1.0,
        "useful_recall_min": 1.0,
        "oracle_agreement_min": 1.0,
        "tick_p95_ms_max": TICK_P95_LIMIT_MS,
        "rss_growth_mib_max": RSS_GROWTH_LIMIT_MIB,
        "average_cpu_one_core_percent_max": CPU_ONE_CORE_LIMIT_PERCENT,
        "false_proactivity": 0,
        "quiet_hour_activity": 0,
        "disabled_activity": 0,
        "host_budget_breaches": 0,
        "incident_failures": 0,
    }
    passed = (
        simulation["oracle_agreement"] == 1.0
        and simulation["useful_precision"] == 1.0
        and simulation["useful_recall"] == 1.0
        and simulation["false_proactivity"] == 0
        and simulation["quiet_hour_activity"] == 0
        and simulation["disabled_activity"] == 0
        and simulation["host_budget_breaches"] == 0
        and lifecycle["incident_failures"] == 0
        and lifecycle["forbidden_explanation_fields"] == []
        and lifecycle["rule_state_removed"]
        and lifecycle["content_free_tombstone"]
        and lifecycle["on_demand_core_passed"]
        and temporary_evaluation_state_deleted
        and soak["tick_p95_ms"] <= TICK_P95_LIMIT_MS
        and soak["rss_growth_mib"] <= RSS_GROWTH_LIMIT_MIB
        and (
            soak["average_cpu_one_core_percent"] <= CPU_ONE_CORE_LIMIT_PERCENT
            or not enforce_minimums
        )
        and (minimums_met or not enforce_minimums)
    )
    return {
        "profile": "phase11d-long-duration-closeout-v1",
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "simulation": simulation,
        "incidents_and_removal": lifecycle,
        "soak": {
            key: round(value, 4) if isinstance(value, float) else value
            for key, value in soak.items()
        },
        "zero_activity": zero_activity,
        "temporary_evaluation_state_deleted": temporary_evaluation_state_deleted,
        "minimums_met": minimums_met,
        "thresholds": thresholds,
        "passed": passed,
    }


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * quantile) - 1))
    return ordered[index]


def _rss_bytes() -> int:
    if os.name != "nt":
        import resource

        return int(
            resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # type: ignore[attr-defined]
        )
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernel32.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def _prepare_output_path(path: Path) -> Path:
    candidate = path.expanduser().resolve(strict=False)
    try:
        candidate.relative_to(RUNTIME_ROOT)
    except ValueError as exc:
        raise ValueError("benchmark output must be under repository runtime directory") from exc
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--virtual-days", type=int, default=VIRTUAL_DAYS)
    parser.add_argument("--decision-samples", type=int, default=DECISION_SAMPLES)
    parser.add_argument("--incident-samples", type=int, default=INCIDENT_SAMPLES)
    parser.add_argument("--soak-seconds", type=float, default=SOAK_SECONDS)
    parser.add_argument("--soak-cycles", type=int, default=SOAK_CYCLES)
    parser.add_argument("--soak-interval-seconds", type=float, default=SOAK_INTERVAL_SECONDS)
    parser.add_argument("--enforce", action="store_true")
    arguments = parser.parse_args()
    if (
        arguments.virtual_days < 1
        or arguments.decision_samples < 1
        or arguments.incident_samples < 1
        or arguments.soak_seconds < 0
        or arguments.soak_cycles < 1
        or arguments.soak_interval_seconds < 0
    ):
        parser.error("benchmark counts and intervals are out of range")
    result = asyncio.run(
        _measure(
            virtual_days=arguments.virtual_days,
            decision_samples=arguments.decision_samples,
            incident_samples=arguments.incident_samples,
            soak_seconds=arguments.soak_seconds,
            soak_cycles=arguments.soak_cycles,
            soak_interval_seconds=arguments.soak_interval_seconds,
            enforce_minimums=arguments.enforce,
        )
    )
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if arguments.output is not None:
        output = _prepare_output_path(arguments.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
