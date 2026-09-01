from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from itertools import count
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import ValidationError

from jarvis.computer.actions import (
    ActionCanonicalizer,
    ActionPreparationError,
    ComputerActionError,
    PreparedAction,
    prepare_action,
)
from jarvis.computer.audio import (
    AudioPostconditionError,
    MasterVolumeOperation,
    MasterVolumeReceipt,
    MasterVolumeState,
)
from jarvis.computer.clipboard import (
    ClipboardChangedError,
    ClipboardError,
    ClipboardMutationReceipt,
    ClipboardRollbackReceipt,
    ClipboardSnapshot,
)
from jarvis.computer.config import (
    ApplicationPolicy,
    BrowserTargetPolicy,
    ComputerAccessPolicy,
)
from jarvis.computer.extra_actions import (
    OpenBrowserTargetHandler,
    SetClipboardTextHandler,
    SetMasterVolumeHandler,
)
from jarvis.computer.windows import (
    ExecutableEnrollment,
    FileIdentity,
    IdentityMismatchError,
)
from jarvis.core import ApprovalRule, PermissionLevel, ToolSideEffect
from jarvis.permissions import (
    ActionDefinition,
    ActionEffect,
    CanonicalAction,
    PostconditionStatus,
    RollbackStatus,
)
from tests.fakes.phase3 import FIXED_NOW, actor

EVENT_CONTEXT = UUID("12345678-1234-5678-9234-567812345678")


def policy(
    root: Path,
    *,
    maximum_level: PermissionLevel = PermissionLevel.LEVEL_2,
    enabled: bool = True,
    max_clipboard_bytes: int = 8 * 1024,
    browser: bool = False,
) -> ComputerAccessPolicy:
    applications: dict[str, ApplicationPolicy] = {}
    targets: dict[str, BrowserTargetPolicy] = {}
    browser_application: str | None = None
    if browser:
        applications["browser"] = ApplicationPolicy(
            executable=root / "browser.exe",
            sha256="a" * 64,
            arguments=("--new-window", "--safe-mode"),
        )
        targets["docs"] = BrowserTargetPolicy(url="https://example.com/docs")
        browser_application = "browser"
    return ComputerAccessPolicy(
        enabled=enabled,
        maximum_permission_level=maximum_level,
        controlled_root=root / "controlled-files",
        applications=applications,
        browser_targets=targets,
        browser_application=browser_application,
        max_clipboard_bytes=max_clipboard_bytes,
    )


def canonical_action(
    definition: ActionDefinition,
    prepared: PreparedAction,
    *,
    key: str = "extra-action-1",
) -> CanonicalAction:
    return CanonicalAction.create(
        request_id=f"request-{key}",
        conversation_id="conversation-1",
        tool_call_id="tool-call-1",
        action_id=definition.action_id,
        action_version=definition.version,
        actor=actor(capabilities=definition.tool.required_capabilities),
        normalized_arguments=prepared.normalized_arguments,
        permission_level=definition.tool.permission_level,
        approval_rule=definition.tool.approval_rule,
        policy_version="phase3-v1",
        idempotency_key=key,
        human_effect=prepared.human_effect,
        recovery_limits=prepared.recovery_limits,
        precondition=prepared.precondition,
        created_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=2),
    )


class FakeVolume:
    def __init__(self, scalar: float = 0.25, muted: bool = False) -> None:
        self.state = MasterVolumeState(scalar=scalar, muted=muted)
        self.set_calls: list[tuple[float, UUID]] = []
        self.mismatch_once = False

    def read(self) -> MasterVolumeState:
        return self.state

    def set_scalar(self, value: float, *, event_context: UUID) -> MasterVolumeReceipt:
        before = self.state
        self.set_calls.append((value, event_context))
        if self.mismatch_once:
            self.mismatch_once = False
            self.state = MasterVolumeState(scalar=0.7, muted=before.muted)
            raise AudioPostconditionError(
                operation=MasterVolumeOperation.SET_SCALAR,
                event_context=event_context,
                before=before,
                observed=self.state,
                requested_scalar=value,
            )
        self.state = MasterVolumeState(scalar=value, muted=before.muted)
        return MasterVolumeReceipt(
            operation=MasterVolumeOperation.SET_SCALAR,
            event_context=event_context,
            before=before,
            after=self.state,
            requested_scalar=value,
        )


def volume_handler(tmp_path: Path, fake: FakeVolume) -> SetMasterVolumeHandler:
    return SetMasterVolumeHandler(
        policy(tmp_path, maximum_level=PermissionLevel.LEVEL_1),
        read_state=fake.read,
        set_scalar=fake.set_scalar,
        event_context_factory=lambda: EVENT_CONTEXT,
    )


def test_volume_prepare_is_read_only_and_binds_exact_state_and_event_context(
    tmp_path: Path,
) -> None:
    fake = FakeVolume(scalar=0.25, muted=True)
    handler = volume_handler(tmp_path, fake)

    prepared = prepare_action(handler, {"percent": 60})

    assert isinstance(handler, ActionCanonicalizer)
    assert prepared.normalized_arguments == {"percent": 60}
    assert prepared.precondition == {
        "before_scalar": 0.25,
        "before_muted": True,
        "target_scalar": 0.6,
        "event_context": str(EVENT_CONTEXT),
    }
    assert "60%" in prepared.human_effect
    assert fake.set_calls == []
    tool = handler.definition.tool
    assert tool.permission_level is PermissionLevel.LEVEL_1
    assert tool.approval_rule is ApprovalRule.EXPLICIT_ENABLEMENT
    assert tool.max_result_items == 5
    assert handler.definition.supports_rollback is True
    assert handler.definition.effect_may_outlive_cancellation is True
    with pytest.raises(ValidationError):
        prepare_action(handler, {"percent": 50.0})
    with pytest.raises(ValidationError):
        prepare_action(handler, {"percent": 101})


@pytest.mark.asyncio
async def test_volume_execute_verifies_and_rolls_back_only_unchanged_result(
    tmp_path: Path,
) -> None:
    fake = FakeVolume(scalar=0.2, muted=False)
    handler = volume_handler(tmp_path, fake)
    prepared = prepare_action(handler, {"percent": 75})
    action = canonical_action(handler.definition, prepared)

    effect = await handler.execute(action)
    evidence = await handler.verify(action, effect)
    rollback = await handler.rollback(action, effect, reason="injected mismatch")

    assert fake.set_calls == [(0.75, EVENT_CONTEXT), (0.2, EVENT_CONTEXT)]
    assert effect.result == {
        "requested_percent": 75,
        "observed_scalar": 0.75,
        "observed_muted": False,
        "event_context": str(EVENT_CONTEXT),
        "verified": True,
    }
    assert evidence.status is PostconditionStatus.PASSED
    assert rollback.status is RollbackStatus.SUCCEEDED
    assert fake.state == MasterVolumeState(scalar=0.2, muted=False)

    second_fake = FakeVolume(scalar=0.2, muted=False)
    second = volume_handler(tmp_path, second_fake)
    second_prepared = prepare_action(second, {"percent": 75})
    second_action = canonical_action(second.definition, second_prepared, key="volume-2")
    second_effect = await second.execute(second_action)
    second_fake.state = MasterVolumeState(scalar=0.7, muted=False)

    refused = await second.rollback(second_action, second_effect, reason="audit failure")

    assert refused.status is RollbackStatus.FAILED
    assert second_fake.set_calls == [(0.75, EVENT_CONTEXT)]
    assert second_fake.state.scalar == 0.7


@pytest.mark.asyncio
async def test_volume_precondition_drift_blocks_mutation(tmp_path: Path) -> None:
    fake = FakeVolume(scalar=0.2)
    handler = volume_handler(tmp_path, fake)
    prepared = prepare_action(handler, {"percent": 50})
    action = canonical_action(handler.definition, prepared)
    fake.state = MasterVolumeState(scalar=0.3, muted=False)

    with pytest.raises(IdentityMismatchError):
        await handler.execute(action)

    assert fake.set_calls == []


@pytest.mark.asyncio
async def test_volume_postcondition_error_preserves_effect_for_automatic_rollback(
    tmp_path: Path,
) -> None:
    fake = FakeVolume(scalar=0.2, muted=False)
    fake.mismatch_once = True
    handler = volume_handler(tmp_path, fake)
    prepared = prepare_action(handler, {"percent": 75})
    action = canonical_action(handler.definition, prepared, key="volume-mismatch")

    effect = await handler.execute(action)
    evidence = await handler.verify(action, effect)
    rollback = await handler.rollback(action, effect, reason="postcondition_mismatch")

    assert effect.result["verified"] is False
    assert effect.result["observed_scalar"] == 0.7
    assert evidence.status is PostconditionStatus.MISMATCH
    assert rollback.status is RollbackStatus.SUCCEEDED
    assert fake.state.scalar == 0.2


def _clipboard_digest(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-16-le")).hexdigest()


class FakeClipboard:
    def __init__(self, text: str | None = "prior secret", formats: tuple[int, ...] = (13,)) -> None:
        self.text = text
        self.formats = formats
        self.sequence = 10
        self.set_calls: list[str] = []
        self.rollback_calls: list[tuple[str | None, str]] = []

    def snapshot(self, *, max_bytes: int) -> ClipboardSnapshot:
        encoded = self.text.encode("utf-16-le") if self.text is not None else b""
        if len(encoded) > max_bytes:
            raise ClipboardError("clipboard exceeds limit")
        return ClipboardSnapshot(
            sequence=self.sequence,
            text=self.text,
            text_sha256=_clipboard_digest(self.text),
            utf16_bytes=len(encoded),
            formats=self.formats,
        )

    def set_text(self, text: str, *, max_bytes: int) -> ClipboardMutationReceipt:
        self.set_calls.append(text)
        if set(self.formats).difference({1, 7, 13, 16}):
            raise ClipboardError("clipboard contains non-text formats")
        before = self.snapshot(max_bytes=max_bytes)
        encoded = text.encode("utf-16-le")
        if len(encoded) > max_bytes:
            raise ClipboardError("clipboard exceeds limit")
        self.text = text
        self.formats = (13,)
        self.sequence += 1
        digest = _clipboard_digest(text)
        assert digest is not None
        return ClipboardMutationReceipt(
            before_sequence=before.sequence,
            after_sequence=self.sequence,
            before_sha256=before.text_sha256,
            after_sha256=digest,
            utf16_bytes=len(encoded),
            changed=before.text != text,
            verified=True,
        )

    def rollback(
        self,
        previous_text: str | None,
        *,
        expected_current_sha256: str,
        max_bytes: int,
    ) -> ClipboardRollbackReceipt:
        self.rollback_calls.append((previous_text, expected_current_sha256))
        if self.snapshot(max_bytes=max_bytes).text_sha256 != expected_current_sha256:
            raise ClipboardChangedError("clipboard changed")
        before_sequence = self.sequence
        self.text = previous_text
        self.sequence += 1
        return ClipboardRollbackReceipt(
            before_sequence=before_sequence,
            after_sequence=self.sequence,
            restored_sha256=_clipboard_digest(previous_text),
            verified=True,
        )


def clipboard_handler(
    tmp_path: Path,
    fake: FakeClipboard,
    *,
    maximum_bytes: int = 8 * 1024,
    recovery_maximum_entries: int = 64,
    recovery_ttl_seconds: float = 15 * 60,
    monotonic: Callable[[], float] = time.monotonic,
) -> SetClipboardTextHandler:
    tokens = count(1)
    return SetClipboardTextHandler(
        policy(tmp_path, max_clipboard_bytes=maximum_bytes),
        read_snapshot=fake.snapshot,
        set_text=fake.set_text,
        rollback_text=fake.rollback,
        recovery_maximum_entries=recovery_maximum_entries,
        recovery_ttl_seconds=recovery_ttl_seconds,
        token_factory=lambda: f"clipboard-token-{next(tokens):08d}",
        monotonic=monotonic,
    )


@pytest.mark.asyncio
async def test_clipboard_prepare_retains_metadata_only_then_execute_materializes_plaintext(
    tmp_path: Path,
) -> None:
    fake = FakeClipboard(text="prior secret")
    handler = clipboard_handler(tmp_path, fake, recovery_maximum_entries=1)

    first = prepare_action(handler, {"text": "first approved value"})
    denied_style = prepare_action(handler, {"text": "never executed"})
    first_token = cast(str, first.precondition["recovery_token"])
    denied_token = cast(str, denied_style.precondition["recovery_token"])

    assert handler._recovery.materialized_count == 0
    assert handler._recovery.get(first_token) is None
    assert handler._recovery.get(denied_token) is None
    reservation = handler._recovery._reservations[first_token]
    assert not hasattr(reservation, "previous_text")
    assert "prior secret" not in repr(reservation)
    action = canonical_action(handler.definition, first, key="clipboard-materialize")

    await handler.execute(action)

    entry = handler._recovery.get(first_token)
    assert handler._recovery.materialized_count == 1
    assert entry is not None and entry.previous_text == "prior secret"
    assert handler._recovery.get(denied_token) is None


@pytest.mark.asyncio
async def test_clipboard_restart_materializes_prior_text_after_exact_revalidation(
    tmp_path: Path,
) -> None:
    fake = FakeClipboard(text="prior restart secret")
    preparing_handler = clipboard_handler(tmp_path, fake)
    prepared = prepare_action(preparing_handler, {"text": "approved after restart"})
    token = cast(str, prepared.precondition["recovery_token"])

    restarted_handler = clipboard_handler(tmp_path, fake)
    action = canonical_action(
        restarted_handler.definition,
        prepared,
        key="clipboard-restart",
    )
    effect = await restarted_handler.execute(action)

    entry = restarted_handler._recovery.get(token)
    assert entry is not None and entry.previous_text == "prior restart secret"
    assert fake.text == "approved after restart"
    rollback = await restarted_handler.rollback(action, effect, reason="restart regression")
    assert rollback.status is RollbackStatus.SUCCEEDED
    assert fake.text == "prior restart secret"


@pytest.mark.asyncio
async def test_clipboard_current_reservation_expiry_never_uses_restart_fallback(
    tmp_path: Path,
) -> None:
    fake = FakeClipboard(text="prior")
    now = [100.0]
    handler = clipboard_handler(
        tmp_path,
        fake,
        recovery_ttl_seconds=60,
        monotonic=lambda: now[0],
    )
    prepared = prepare_action(handler, {"text": "approved"})
    action = canonical_action(handler.definition, prepared, key="clipboard-expired")
    now[0] += 61

    with pytest.raises(ComputerActionError, match="reservation is unavailable"):
        await handler.execute(action)

    assert fake.set_calls == []


@pytest.mark.asyncio
async def test_clipboard_mismatched_existing_reservation_cannot_cross_bind(
    tmp_path: Path,
) -> None:
    fake = FakeClipboard(text="first prior")
    handler = clipboard_handler(tmp_path, fake)
    first = prepare_action(handler, {"text": "first approved"})
    first_token = cast(str, first.precondition["recovery_token"])
    fake.text = "second prior"
    fake.sequence += 1
    second = prepare_action(handler, {"text": "second approved"})
    cross_bound = second.model_copy(
        update={"precondition": {**second.precondition, "recovery_token": first_token}}
    )
    action = canonical_action(handler.definition, cross_bound, key="clipboard-cross-bound")

    with pytest.raises(ComputerActionError, match="reservation is unavailable"):
        await handler.execute(action)

    assert fake.set_calls == []


@pytest.mark.asyncio
async def test_clipboard_binds_exact_text_but_receipts_and_evidence_are_text_free(
    tmp_path: Path,
) -> None:
    fake = FakeClipboard(text="prior secret")
    handler = clipboard_handler(tmp_path, fake)
    exact_text = "  approved text\nwith whitespace  "

    prepared = prepare_action(handler, {"text": exact_text})
    assert prepared.normalized_arguments == {"text": exact_text}
    assert json.dumps(exact_text, ensure_ascii=False) in prepared.human_effect
    assert "prior secret" not in json.dumps(prepared.model_dump(mode="json"))
    assert fake.set_calls == []
    action = canonical_action(handler.definition, prepared, key="clipboard")

    effect = await handler.execute(action)
    evidence = await handler.verify(action, effect)

    serialized_result = json.dumps(effect.result)
    serialized_context = json.dumps(effect.rollback_context)
    serialized_evidence = json.dumps(evidence.model_dump(mode="json"))
    for sensitive_text in (exact_text, "prior secret"):
        assert sensitive_text not in serialized_result
        assert sensitive_text not in serialized_context
        assert sensitive_text not in serialized_evidence
    assert evidence.status is PostconditionStatus.PASSED
    assert handler._recovery.materialized_count == 1
    assert effect.result["text_sha256"] == _clipboard_digest(exact_text)
    assert handler.definition.tool.permission_level is PermissionLevel.LEVEL_2
    assert handler.definition.tool.approval_rule is ApprovalRule.POLICY_OR_EXPLICIT
    assert handler.definition.tool.max_result_items == 4
    assert handler.definition.supports_rollback is True
    assert handler.definition.effect_may_outlive_cancellation is True


@pytest.mark.asyncio
async def test_clipboard_mismatch_has_broker_rollback_context_and_restores_volatile_text(
    tmp_path: Path,
) -> None:
    fake = FakeClipboard(text="prior secret")
    handler = clipboard_handler(tmp_path, fake)
    prepared = prepare_action(handler, {"text": "approved"})
    action = canonical_action(handler.definition, prepared, key="clipboard-rollback")
    effect = await handler.execute(action)
    mismatched = ActionEffect(
        result={**cast(dict[str, Any], effect.result), "verified": False},
        rollback_context=effect.rollback_context,
    )

    evidence = await handler.verify(action, mismatched)
    rollback = await handler.rollback(action, effect, reason="postcondition_mismatch")

    assert evidence.status is PostconditionStatus.MISMATCH
    assert rollback.status is RollbackStatus.SUCCEEDED
    assert fake.text == "prior secret"
    assert fake.rollback_calls == [("prior secret", cast(str, effect.result["text_sha256"]))]
    assert "prior secret" not in json.dumps(rollback.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_clipboard_primitive_rejects_nontext_formats_without_handler_bypass(
    tmp_path: Path,
) -> None:
    fake = FakeClipboard(text=None, formats=(13, 49161))
    handler = clipboard_handler(tmp_path, fake)
    prepared = prepare_action(handler, {"text": "approved"})
    action = canonical_action(handler.definition, prepared, key="clipboard-format")

    with pytest.raises(ClipboardError, match="non-text"):
        await handler.execute(action)
    with pytest.raises(ComputerActionError, match="reservation is unavailable"):
        await handler.execute(action)

    assert fake.set_calls == ["approved"]
    assert fake.text is None
    assert handler._recovery.materialized_count == 0


def test_clipboard_policy_bytes_and_exact_approval_display_are_bounded(tmp_path: Path) -> None:
    fake = FakeClipboard(text=None)
    handler = clipboard_handler(tmp_path, fake, maximum_bytes=8)

    with pytest.raises(ValueError, match="UTF-16"):
        prepare_action(handler, {"text": "12345"})
    with pytest.raises(ValidationError, match="NUL"):
        prepare_action(handler, {"text": "bad\x00text"})

    display_handler = clipboard_handler(tmp_path, fake)
    with pytest.raises(ActionPreparationError, match="approval display"):
        prepare_action(display_handler, {"text": "x" * 2_000})


@pytest.mark.asyncio
async def test_clipboard_precondition_drift_blocks_set(tmp_path: Path) -> None:
    fake = FakeClipboard(text="before")
    handler = clipboard_handler(tmp_path, fake)
    prepared = prepare_action(handler, {"text": "approved"})
    action = canonical_action(handler.definition, prepared, key="clipboard-drift")
    fake.text = "changed elsewhere"
    fake.sequence += 1

    with pytest.raises(IdentityMismatchError):
        await handler.execute(action)

    assert fake.set_calls == []


@pytest.mark.asyncio
async def test_clipboard_rollback_refuses_to_overwrite_later_change(tmp_path: Path) -> None:
    fake = FakeClipboard(text="before")
    handler = clipboard_handler(tmp_path, fake)
    prepared = prepare_action(handler, {"text": "approved"})
    action = canonical_action(handler.definition, prepared, key="clipboard-later-change")
    effect = await handler.execute(action)
    fake.text = "later user value"
    fake.sequence += 1

    rollback = await handler.rollback(action, effect, reason="terminal audit failure")

    assert rollback.status is RollbackStatus.FAILED
    assert fake.text == "later user value"


@dataclass(frozen=True)
class FakeLaunchObservation:
    pid: int
    image_verified: bool = True


def fake_enrollment(path: Path, digest: str = "a" * 64) -> ExecutableEnrollment:
    return ExecutableEnrollment(
        path=path,
        identity=FileIdentity(
            path=path,
            final_path=rf"\\?\Volume{{test}}\apps\{path.name}",
            volume_serial=100,
            file_id="1" * 32,
            size=10_000,
            modified_100ns=1_000,
            link_count=1,
            attributes=0,
            sha256=digest,
        ),
        sha256=digest,
    )


def test_browser_prepare_allows_only_configured_target_and_fixed_enrollment(
    tmp_path: Path,
) -> None:
    configured = policy(tmp_path, browser=True)
    launches: list[tuple[ExecutableEnrollment, tuple[str, ...]]] = []
    handler = OpenBrowserTargetHandler(
        configured,
        capture_enrollment=fake_enrollment,
        launch_browser=lambda enrollment, arguments: (
            launches.append((enrollment, arguments)) or FakeLaunchObservation(pid=42)
        ),
    )

    prepared = prepare_action(handler, {"target_id": "docs"})

    assert prepared.normalized_arguments == {"target_id": "docs"}
    assert prepared.precondition["url"] == "https://example.com/docs"
    assert prepared.precondition["executable_sha256"] == "a" * 64
    assert prepared.precondition["executable_file_id"] == "1" * 32
    assert handler.definition.tool.input_schema["properties"]["target_id"]["enum"] == ["docs"]
    assert handler.definition.tool.permission_level is PermissionLevel.LEVEL_2
    assert handler.definition.tool.side_effect is ToolSideEffect.EXTERNAL
    assert handler.definition.tool.max_result_items == 5
    assert handler.definition.effect_may_outlive_cancellation is True
    assert launches == []
    with pytest.raises(ValidationError, match="extra_forbidden"):
        prepare_action(handler, {"target_id": "docs", "url": "https://evil.example"})
    with pytest.raises(ActionPreparationError, match="not configured"):
        prepare_action(handler, {"target_id": "other"})


@pytest.mark.asyncio
async def test_browser_execute_appends_only_allowlisted_url_to_fixed_argv(
    tmp_path: Path,
) -> None:
    configured = policy(tmp_path, browser=True)
    enrollment = fake_enrollment(tmp_path / "browser.exe")
    launches: list[tuple[ExecutableEnrollment, tuple[str, ...]]] = []

    def launch(
        observed_enrollment: ExecutableEnrollment,
        arguments: tuple[str, ...],
    ) -> FakeLaunchObservation:
        launches.append((observed_enrollment, arguments))
        return FakeLaunchObservation(pid=4242)

    handler = OpenBrowserTargetHandler(
        configured,
        capture_enrollment=lambda _path: enrollment,
        launch_browser=launch,
    )
    prepared = prepare_action(handler, {"target_id": "docs"})
    action = canonical_action(handler.definition, prepared, key="browser")

    effect = await handler.execute(action)
    evidence = await handler.verify(action, effect)
    rollback = await handler.rollback(action, effect, reason="test")

    assert launches == [
        (
            enrollment,
            ("--new-window", "--safe-mode", "https://example.com/docs"),
        )
    ]
    assert "https://example.com/docs" not in json.dumps(effect.result)
    assert effect.result["target_id"] == "docs"
    assert evidence.status is PostconditionStatus.PASSED
    assert rollback.status is RollbackStatus.UNAVAILABLE
    assert handler.definition.supports_rollback is False


def test_browser_enrollment_digest_and_policy_gate_fail_closed(tmp_path: Path) -> None:
    configured = policy(tmp_path, browser=True)
    with pytest.raises(IdentityMismatchError, match="SHA-256"):
        OpenBrowserTargetHandler(
            configured,
            capture_enrollment=lambda path: fake_enrollment(path, "b" * 64),
        )
    with pytest.raises(ValueError, match="disabled"):
        OpenBrowserTargetHandler(
            configured.model_copy(update={"enabled": False}),
            capture_enrollment=fake_enrollment,
        )
    with pytest.raises(ValueError, match="does not enable"):
        OpenBrowserTargetHandler(
            configured.model_copy(update={"maximum_permission_level": PermissionLevel.LEVEL_1}),
            capture_enrollment=fake_enrollment,
        )


@pytest.mark.parametrize(
    ("handler_type", "maximum_level"),
    [
        (SetMasterVolumeHandler, PermissionLevel.LEVEL_0),
        (SetClipboardTextHandler, PermissionLevel.LEVEL_1),
    ],
)
def test_handlers_refuse_policy_below_registered_level(
    tmp_path: Path,
    handler_type: type[SetMasterVolumeHandler] | type[SetClipboardTextHandler],
    maximum_level: PermissionLevel,
) -> None:
    with pytest.raises(ValueError, match="does not enable"):
        handler_type(policy(tmp_path, maximum_level=maximum_level))
