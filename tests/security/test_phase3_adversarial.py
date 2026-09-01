"""Cross-layer adversarial acceptance tests for controlled computer access."""

from __future__ import annotations

import asyncio
import hashlib
import os
from datetime import datetime, timedelta
from itertools import count
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

import jarvis.computer.windows as windows
from jarvis.broker import LocalActionBroker
from jarvis.computer.actions import (
    ApplicationLaunchHandler,
    MediaControlArguments,
    MediaControlHandler,
    MediaOperation,
    PreparedAction,
    ReversibleMoveArguments,
    prepare_action,
)
from jarvis.computer.config import (
    AppGroupPolicy,
    ApplicationPolicy,
    ComputerAccessPolicy,
    PrinterPolicy,
)
from jarvis.computer.extra_actions import OpenBrowserTargetArguments
from jarvis.computer.hands_free import (
    HandsFreeDecisionReason,
    HandsFreeDecisionRecord,
    HandsFreeDisposition,
    HandsFreeProposal,
    HandsFreeProposalGate,
    HandsFreeRequest,
)
from jarvis.computer.printing import (
    PrintControlledTextArguments,
    PrintControlledTextHandler,
    PrintSpoolError,
    PrintSubmissionReceipt,
)
from jarvis.computer.registry import ComputerActionRegistry
from jarvis.computer.windows import (
    AllowedRootGuard,
    ExecutableEnrollment,
    FileIdentity,
    FixedExecutableLauncher,
    IdentityMismatchError,
    MediaInputResult,
    MediaKey,
)
from jarvis.core import PermissionLevel, ToolRetryPolicy
from jarvis.permissions import (
    ActionAuditEvent,
    ActionDefinition,
    ActionHandler,
    ActorContext,
    AuthenticationAssurance,
    CanonicalAction,
    ExecutionOutcome,
    InteractionInterface,
    PostconditionStatus,
    RollbackStatus,
)
from jarvis.voice.models import AcousticEventType, HandsFreeIntent, HandsFreeIntentType
from tests.fakes.phase3 import (
    FIXED_NOW,
    POLICY_VERSION,
    FakeActionHandler,
    InMemoryActionAudit,
    InMemoryActionState,
    action_definition,
    actor,
    approval_grant,
    canonical_action,
)


def _fake_enrollment(path: Path, digest: str) -> ExecutableEnrollment:
    identity = FileIdentity(
        path=path,
        final_path=rf"\\?\Volume{{security}}\apps\{path.name}",
        volume_serial=701,
        file_id="ab" * 16,
        size=4_096,
        modified_100ns=123_456,
        link_count=1,
        attributes=0,
        sha256=digest,
    )
    return ExecutableEnrollment(path=path, identity=identity, sha256=digest)


def _broker(
    handler: ActionHandler,
    *,
    now: datetime = FIXED_NOW,
) -> tuple[LocalActionBroker, InMemoryActionState, InMemoryActionAudit]:
    state = InMemoryActionState()
    audit = InMemoryActionAudit()
    identifiers = count(1)
    broker = LocalActionBroker(
        (handler,),
        state_store=state,
        audit_store=audit,
        policy_version=POLICY_VERSION,
        now=lambda: now,
        id_factory=lambda prefix: f"{prefix}-security-{next(identifiers)}",
    )
    return broker, state, audit


def _canonical_from_prepared(
    definition: ActionDefinition,
    prepared: PreparedAction,
    *,
    key: str,
) -> CanonicalAction:
    return CanonicalAction.create(
        request_id=f"request-{key}",
        conversation_id="conversation-security",
        tool_call_id="tool-call-security",
        action_id=definition.action_id,
        action_version=definition.version,
        actor=actor(capabilities=definition.tool.required_capabilities),
        normalized_arguments=prepared.normalized_arguments,
        permission_level=definition.tool.permission_level,
        approval_rule=definition.tool.approval_rule,
        policy_version=POLICY_VERSION,
        idempotency_key=key,
        human_effect=prepared.human_effect,
        recovery_limits=prepared.recovery_limits,
        precondition=prepared.precondition,
        created_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=2),
    )


def test_untrusted_argument_and_path_injection_never_reaches_a_side_effect(
    tmp_path: Path,
) -> None:
    digest = "a" * 64
    executable = tmp_path / "reviewed.exe"
    policy = ComputerAccessPolicy(
        enabled=True,
        maximum_permission_level=PermissionLevel.LEVEL_2,
        controlled_root=tmp_path,
        applications={
            "reviewed": ApplicationPolicy(
                executable=executable,
                sha256=digest,
                arguments=("--fixed-safe-mode",),
            )
        },
    )
    launch_attempts = 0

    def forbidden_launch(
        _enrollment: ExecutableEnrollment,
        _arguments: tuple[str, ...],
    ) -> object:
        nonlocal launch_attempts
        launch_attempts += 1
        raise AssertionError("injected arguments reached application launcher")

    handler = ApplicationLaunchHandler(
        policy,
        capture_enrollment=lambda path: _fake_enrollment(path, digest),
        launch_application=forbidden_launch,
    )

    with pytest.raises(ValidationError):
        prepare_action(
            handler,
            {
                "application_id": "reviewed",
                "arguments": ["--open", "https://attacker.invalid; calc.exe"],
            },
        )
    with pytest.raises(ValidationError):
        prepare_action(handler, {"application_id": "reviewed && calc.exe"})
    with pytest.raises(ValidationError):
        OpenBrowserTargetArguments.model_validate(
            {
                "target_id": "docs",
                "url": "https://attacker.invalid/",
                "arguments": ["--disable-security"],
            }
        )

    for malicious_path in (
        "../outside.txt",
        "safe\\..\\outside.txt",
        "C:/Windows/System32/config/SAM",
        "safe/file.txt:alternate-stream",
        "safe/file.txt\x00.exe",
    ):
        with pytest.raises(ValidationError):
            ReversibleMoveArguments.model_validate(
                {"source": malicious_path, "destination": "archive/file.txt"}
            )

    assert launch_attempts == 0


@pytest.mark.skipif(os.name != "nt", reason="executable enrollment is a Windows primitive")
def test_executable_substitution_is_detected_before_process_creation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executable = tmp_path / "reviewed.exe"
    executable.write_bytes(b"MZ-reviewed-image")
    enrollment = ExecutableEnrollment.capture(executable)
    executable.write_bytes(b"MZ-attacker-image")

    monkeypatch.setattr(windows, "_require_non_elevated", lambda: None)

    def forbidden_popen(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("substituted executable reached process creation")

    monkeypatch.setattr(windows.subprocess, "Popen", forbidden_popen)

    with pytest.raises(IdentityMismatchError, match="identity or SHA-256 changed"):
        FixedExecutableLauncher(enrollment).launch()


@pytest.mark.asyncio
async def test_grants_are_single_effect_stale_safe_and_identity_bound() -> None:
    definition = action_definition(PermissionLevel.LEVEL_2)
    handler = FakeActionHandler(definition)
    broker, state, _audit = _broker(handler)

    valid_action = canonical_action(definition, idempotency_key="valid-grant")
    valid_grant = approval_grant(valid_action, grant_id="grant-valid")
    first = await broker.execute(valid_grant, actor=valid_action.actor)
    replay = await broker.execute(valid_grant, actor=valid_action.actor)

    stale_at = FIXED_NOW - timedelta(minutes=3)
    stale_action = canonical_action(
        definition,
        now=stale_at,
        idempotency_key="stale-grant",
    )
    stale = await broker.execute(
        approval_grant(stale_action, now=stale_at, grant_id="grant-stale"),
        actor=stale_action.actor,
    )

    cross_action = canonical_action(definition, idempotency_key="cross-identity")
    cross_identity = actor(session_id="session-other", device_id="device-other")
    crossed = await broker.execute(
        approval_grant(cross_action, grant_id="grant-cross"),
        actor=cross_identity,
    )

    original = canonical_action(definition, idempotency_key="mutated-arguments")
    original_grant = approval_grant(original, grant_id="grant-mutated")
    mutated_action = original.model_copy(
        update={"normalized_arguments": {"value": "../../injected"}}
    )
    mutated_grant = original_grant.model_copy(update={"action": mutated_action})
    mutated = await broker.execute(mutated_grant, actor=original.actor)

    assert first.outcome is ExecutionOutcome.SUCCEEDED
    assert replay.receipt_id == first.receipt_id
    assert stale.outcome is ExecutionOutcome.DENIED
    assert stale.error_code == "grant_expired"
    assert crossed.outcome is ExecutionOutcome.DENIED
    assert crossed.error_code == "actor_mismatch"
    assert mutated.outcome is ExecutionOutcome.DENIED
    assert mutated.error_code == "action_fingerprint_mismatch"
    assert handler.execute_calls == 1
    assert state.claim_count == 1


@pytest.mark.asyncio
async def test_same_identity_cannot_downgrade_current_authentication_context() -> None:
    definition = action_definition(PermissionLevel.LEVEL_2)
    handler = FakeActionHandler(definition)
    broker, state, _audit = _broker(handler)
    action = canonical_action(definition, idempotency_key="authentication-downgrade")
    grant = approval_grant(action, grant_id="grant-authentication-downgrade")
    unauthenticated = ActorContext(
        host_id=action.actor.host_id,
        session_id=action.actor.session_id,
        device_id=action.actor.device_id,
        interface=action.actor.interface,
        assurance=AuthenticationAssurance.UNAUTHENTICATED,
        authenticated_at=None,
        capabilities=(),
    )

    receipt = await broker.execute(grant, actor=unauthenticated)

    assert receipt.outcome is ExecutionOutcome.DENIED
    assert handler.execute_calls == 0
    assert state.claim_count == 0


@pytest.mark.asyncio
async def test_model_facing_runtime_adapter_cannot_call_computer_side_effect() -> None:
    send_attempts: list[MediaKey] = []

    def forbidden_send(key: MediaKey) -> MediaInputResult:
        send_attempts.append(key)
        raise AssertionError("model-facing tool invoked a Windows input primitive")

    action = MediaControlHandler(send_input=forbidden_send)
    registry = ComputerActionRegistry((action,))
    model_tool = registry.tool("control_media")
    assert model_tool is not None

    result = await model_tool.invoke(MediaControlArguments(operation=MediaOperation.PLAY_PAUSE))

    assert result.is_error is True
    assert result.data == {"code": "broker_required"}
    assert send_attempts == []


@pytest.mark.asyncio
async def test_cancellation_consumes_grant_and_attempts_recovery_once() -> None:
    definition = action_definition(PermissionLevel.LEVEL_2)
    handler = FakeActionHandler(definition, block=True)
    broker, state, audit = _broker(handler)
    action = canonical_action(definition, idempotency_key="cancelled-action")
    grant = approval_grant(action, grant_id="grant-cancelled")

    task = asyncio.create_task(broker.execute(grant, actor=action.actor))
    await asyncio.wait_for(handler.execute_started.wait(), timeout=1)
    task.cancel()
    receipt = await asyncio.wait_for(task, timeout=1)
    replay = await broker.execute(grant, actor=action.actor)

    assert receipt.outcome is ExecutionOutcome.CANCELLED
    assert receipt.error_code == "execution_cancelled"
    assert receipt.rollback.status is RollbackStatus.SUCCEEDED
    assert replay.receipt_id == receipt.receipt_id
    assert handler.execute_calls == 1
    assert handler.rollback_calls == 1
    assert handler.rollback_reasons == ["execution_cancelled"]
    assert state.complete_count == 1
    assert len(audit.events) == 2


class _BlockingStartAudit:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.block = asyncio.Event()

    async def append_action_event(self, _event: ActionAuditEvent) -> None:
        self.started.set()
        await self.block.wait()


@pytest.mark.asyncio
async def test_cancellation_while_start_audit_is_pending_returns_terminal_receipt() -> None:
    definition = action_definition(PermissionLevel.LEVEL_2)
    handler = FakeActionHandler(definition)
    state = InMemoryActionState()
    audit = _BlockingStartAudit()
    broker = LocalActionBroker(
        (handler,),
        state_store=state,
        audit_store=audit,
        policy_version=POLICY_VERSION,
        now=lambda: FIXED_NOW,
        id_factory=lambda prefix: f"{prefix}-cancel-start-audit",
    )
    action = canonical_action(definition, idempotency_key="cancel-start-audit")
    grant = approval_grant(action, grant_id="grant-cancel-start-audit")

    task = asyncio.create_task(broker.execute(grant, actor=action.actor))
    await asyncio.wait_for(audit.started.wait(), timeout=1)
    task.cancel()
    receipt = await asyncio.wait_for(task, timeout=1)

    assert receipt.outcome is ExecutionOutcome.CANCELLED
    assert handler.execute_calls == 0
    assert state.complete_count == 1


@pytest.mark.asyncio
async def test_postcondition_and_rollback_failure_remain_terminal_and_typed() -> None:
    definition = action_definition(PermissionLevel.LEVEL_2)
    handler = FakeActionHandler(
        definition,
        verify_status=PostconditionStatus.MISMATCH,
        rollback_status=RollbackStatus.FAILED,
    )
    broker, state, _audit = _broker(handler)
    action = canonical_action(definition, idempotency_key="failed-recovery")

    receipt = await broker.execute(
        approval_grant(action, grant_id="grant-failed-recovery"),
        actor=action.actor,
    )

    assert receipt.outcome is ExecutionOutcome.POSTCONDITION_MISMATCH
    assert receipt.error_code == "postcondition_mismatch"
    assert receipt.postcondition.status is PostconditionStatus.MISMATCH
    assert receipt.rollback.status is RollbackStatus.FAILED
    assert handler.execute_calls == 1
    assert handler.rollback_calls == 1
    assert state.complete_count == 1


class _FakePrintGuard:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _identity(self, path: Path, *, compute_sha256: bool) -> FileIdentity:
        payload = path.read_bytes()
        return FileIdentity(
            path=path,
            final_path=rf"\\?\Volume{{security}}\controlled\{path.name}",
            volume_serial=801,
            file_id="cd" * 16,
            size=len(payload),
            modified_100ns=654_321,
            link_count=1,
            attributes=0,
            sha256=hashlib.sha256(payload).hexdigest() if compute_sha256 else None,
        )

    def probe_existing_file(
        self,
        path: str | os.PathLike[str],
        *,
        compute_sha256: bool = False,
        for_mutation: bool = False,
    ) -> FileIdentity:
        del for_mutation
        candidate = Path(path)
        assert candidate.is_relative_to(self.root)
        return self._identity(candidate, compute_sha256=compute_sha256)

    def revalidate(
        self,
        expected: FileIdentity,
        *,
        for_mutation: bool = False,
    ) -> FileIdentity:
        del for_mutation
        current = self._identity(expected.path, compute_sha256=expected.sha256 is not None)
        if not expected.unchanged(current):
            raise IdentityMismatchError("fake controlled document identity changed")
        return current


@pytest.mark.asyncio
async def test_printer_failure_is_sanitized_never_retried_and_not_rolled_back(
    tmp_path: Path,
) -> None:
    document = tmp_path / "approved.txt"
    document.write_text("private controlled document", encoding="utf-8")
    policy = ComputerAccessPolicy(
        enabled=True,
        maximum_permission_level=PermissionLevel.LEVEL_2,
        controlled_root=tmp_path,
        printers={"office": PrinterPolicy(system_name="Exact Office Queue")},
        max_print_bytes=1_024,
        max_print_copies=1,
    )
    submissions: list[tuple[str, str, int]] = []

    def fail_submit(system_name: str, text: str, *, copies: int) -> PrintSubmissionReceipt:
        submissions.append((system_name, text, copies))
        raise PrintSpoolError("printer rejected attacker-secret-token")

    handler = PrintControlledTextHandler(
        policy,
        guard=cast(AllowedRootGuard, _FakePrintGuard(tmp_path)),
        submit=fail_submit,
    )
    prepared = handler.prepare(
        PrintControlledTextArguments(file="approved.txt", printer_id="office", copies=1)
    )
    action = _canonical_from_prepared(handler.definition, prepared, key="printer-failure")
    broker, state, audit = _broker(handler)

    receipt = await broker.execute(
        approval_grant(action, grant_id="grant-printer-failure"),
        actor=action.actor,
    )

    serialized = receipt.model_dump_json()
    assert receipt.outcome is ExecutionOutcome.FAILED
    assert receipt.error_code == "handler_failed"
    assert receipt.rollback.status is RollbackStatus.UNAVAILABLE
    assert handler.definition.tool.retry_policy is ToolRetryPolicy.NEVER
    assert submissions == [("Exact Office Queue", "private controlled document", 1)]
    assert state.claim_count == 1
    assert len(audit.events) == 2
    assert "attacker-secret-token" not in serialized
    assert "private controlled document" not in serialized
    assert "Exact Office Queue" not in serialized


def test_gesture_replay_and_sensitive_mapping_never_create_authority(tmp_path: Path) -> None:
    voice_actor = ActorContext(
        host_id="host-gesture",
        session_id="actor-session-gesture",
        device_id="device-gesture",
        interface=InteractionInterface.VOICE,
        assurance=AuthenticationAssurance.LOCAL_SESSION,
        authenticated_at=FIXED_NOW,
        capabilities=(),
    )
    policy = ComputerAccessPolicy(
        enabled=True,
        maximum_permission_level=PermissionLevel.LEVEL_2,
        controlled_root=tmp_path,
        applications={
            "fixture": ApplicationPolicy(
                executable=tmp_path / "fixture.exe",
                sha256="e" * 64,
            )
        },
        app_groups={"main": AppGroupPolicy(applications=("fixture",))},
        hands_free_app_group="main",
    )
    proposals: list[HandsFreeProposal] = []
    decisions: list[HandsFreeDecisionRecord] = []
    identifiers = count(1)
    gate = HandsFreeProposalGate(
        policy=policy,
        actor=voice_actor,
        active_source_session_id="voice-session-gesture",
        proposal_callback=proposals.append,
        decision_sink=decisions.append,
        now=lambda: FIXED_NOW,
        id_factory=lambda: f"{next(identifiers):08d}",
    )

    intent = HandsFreeIntent(
        session_id="voice-session-gesture",
        source=AcousticEventType.DOUBLE_CLAP,
        intent=HandsFreeIntentType.LAUNCH_APP_GROUP,
        confidence=0.99,
        detected_at=FIXED_NOW,
        event_id="acoustic-event-security-1",
    )
    request = HandsFreeRequest(
        intent=intent,
        actor=voice_actor,
        nonce="nonce-security-0001",
        mapped_permission_level=PermissionLevel.LEVEL_1,
    )

    first = gate.evaluate(request)
    replay = gate.evaluate(request)
    sensitive = gate.evaluate(
        HandsFreeRequest(
            intent=intent.model_copy(update={"event_id": "acoustic-event-security-2"}),
            actor=voice_actor,
            nonce="nonce-security-0002",
            mapped_permission_level=PermissionLevel.LEVEL_2,
        )
    )

    assert first.disposition is HandsFreeDisposition.PROPOSE
    assert replay.disposition is HandsFreeDisposition.DENY
    assert replay.reason is HandsFreeDecisionReason.EVENT_REPLAY
    assert sensitive.disposition is HandsFreeDisposition.DENY
    assert sensitive.reason is HandsFreeDecisionReason.MAPPING_PERMISSION_DENIED
    assert len(proposals) == 1
    assert proposals[0].approval_granted is False
    assert proposals[0].execution_authorized is False
    assert decisions == [first, replay, sensitive]
