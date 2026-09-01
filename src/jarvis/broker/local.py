"""Normal-user fixed-dispatch broker for Phase 3 Level 0-3 actions.

This broker intentionally has no natural-language, executable-path, argument-array,
or dynamic callable entrypoint. A separately privileged process can replace this
adapter later without changing grant semantics; Level 4 remains disabled here.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from hmac import compare_digest
from uuid import uuid4

from jarvis.core import PermissionLevel, ToolConcurrency
from jarvis.core.models import count_json_leaf_items
from jarvis.permissions import ActionAuditSequenceConflictError
from jarvis.permissions.canonical import canonical_json_bytes, sha256_fingerprint
from jarvis.permissions.contracts import ActionAuditStore, ActionHandler, ActionStateStore
from jarvis.permissions.models import (
    ActionAuditEvent,
    ActionAuditEventType,
    ActionDefinition,
    ActionEffect,
    ActorContext,
    ApprovalGrant,
    ExecutionOutcome,
    ExecutionReceipt,
    PostconditionEvidence,
    PostconditionStatus,
    RollbackReceipt,
    RollbackStatus,
)

Now = Callable[[], datetime]
IdFactory = Callable[[str], str]
AuthorityGuard = Callable[[ApprovalGrant], bool]
ConcurrencyKey = tuple[str, ...]

_MAX_AUDIT_SEQUENCE = 10_000


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _random_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _allow_authority(_grant: ApprovalGrant) -> bool:
    return True


@dataclass(frozen=True, slots=True)
class _RegisteredHandler:
    definition: ActionDefinition
    handler: ActionHandler


@dataclass(slots=True)
class _ConcurrencyEntry:
    lock: asyncio.Lock
    users: int = 0


class _ActionConcurrencyGate:
    """Retain keyed locks only while a holder or waiter still uses them."""

    def __init__(self) -> None:
        self._entries: dict[ConcurrencyKey, _ConcurrencyEntry] = {}

    @asynccontextmanager
    async def hold(self, key: ConcurrencyKey | None) -> AsyncIterator[None]:
        if key is None:
            yield
            return

        entry = self._entries.get(key)
        if entry is None:
            entry = _ConcurrencyEntry(lock=asyncio.Lock())
            self._entries[key] = entry
        entry.users += 1
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            entry.users -= 1
            if entry.users == 0 and self._entries.get(key) is entry:
                del self._entries[key]


@dataclass(frozen=True, slots=True)
class _BrokerError(Exception):
    code: str
    safe_message: str
    outcome: ExecutionOutcome = ExecutionOutcome.FAILED


class LocalActionBroker:
    """Verify an exact one-use grant before deterministic fixed action dispatch."""

    def __init__(
        self,
        handlers: Iterable[ActionHandler],
        *,
        state_store: ActionStateStore,
        audit_store: ActionAuditStore,
        policy_version: str,
        now: Now = _utc_now,
        id_factory: IdFactory = _random_id,
        authority_guard: AuthorityGuard = _allow_authority,
    ) -> None:
        if not policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        registry: dict[str, _RegisteredHandler] = {}
        for handler in handlers:
            definition = ActionDefinition.model_validate(handler.definition)
            if definition.dispatch_key in registry:
                raise ValueError(f"duplicate broker action: {definition.dispatch_key}")
            registry[definition.dispatch_key] = _RegisteredHandler(definition, handler)
        if not registry:
            raise ValueError("broker requires at least one fixed action handler")
        self._registry = registry
        self._state_store = state_store
        self._audit_store = audit_store
        self._policy_version = policy_version.strip()
        self._now = now
        self._id_factory = id_factory
        self._authority_guard = authority_guard
        self._concurrency_gate = _ActionConcurrencyGate()

    async def execute(
        self,
        grant: ApprovalGrant,
        *,
        actor: ActorContext,
    ) -> ExecutionReceipt:
        """Execute or reconcile exactly one approved canonical action."""
        now = self._now_utc()
        existing = await self._existing_receipt(grant, actor, now)
        if existing is not None:
            return existing

        try:
            authority_enabled = self._authority_guard(grant)
        except Exception:
            authority_enabled = False
        if not authority_enabled:
            receipt = self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.DENIED,
                code="authority_disabled",
                message="Computer action authority is disabled or its policy cannot be loaded.",
            )
            await self._audit_best_effort(
                grant,
                ActionAuditEventType.BROKER_REJECTED,
                receipt=receipt,
            )
            return receipt

        registration, validation_error = self._validate_grant(grant, actor, now)
        if validation_error is not None:
            receipt = self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.DENIED,
                code=validation_error.code,
                message=validation_error.safe_message,
            )
            await self._audit_best_effort(
                grant,
                ActionAuditEventType.BROKER_REJECTED,
                receipt=receipt,
            )
            return receipt
        assert registration is not None

        entered = False
        try:
            async with self._concurrency_gate.hold(self._concurrency_key(registration, actor)):
                entered = True
                return await self._execute_without_concurrency(grant, actor=actor)
        except asyncio.CancelledError:
            if entered:
                raise
            return self._error_receipt(
                grant,
                self._now_utc(),
                outcome=ExecutionOutcome.CANCELLED,
                code="execution_cancelled_before_claim",
                message="Action scheduling was cancelled; no effect was attempted.",
            )

    async def _execute_without_concurrency(
        self,
        grant: ApprovalGrant,
        *,
        actor: ActorContext,
    ) -> ExecutionReceipt:
        """Execute or reconcile exactly one approved canonical action."""
        now = self._now_utc()
        existing = await self._existing_receipt(grant, actor, now)
        if existing is not None:
            return existing

        try:
            authority_enabled = self._authority_guard(grant)
        except Exception:
            authority_enabled = False
        if not authority_enabled:
            receipt = self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.DENIED,
                code="authority_disabled",
                message="Computer action authority is disabled or its policy cannot be loaded.",
            )
            await self._audit_best_effort(
                grant,
                ActionAuditEventType.BROKER_REJECTED,
                receipt=receipt,
            )
            return receipt

        registration, validation_error = self._validate_grant(grant, actor, now)
        if validation_error is not None:
            receipt = self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.DENIED,
                code=validation_error.code,
                message=validation_error.safe_message,
            )
            await self._audit_best_effort(
                grant,
                ActionAuditEventType.BROKER_REJECTED,
                receipt=receipt,
            )
            return receipt
        assert registration is not None

        try:
            claimed = await self._state_store.claim_grant(grant, claimed_at=now)
        except asyncio.CancelledError:
            return self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.CANCELLED,
                code="execution_cancelled_before_claim",
                message="Action reservation was cancelled; no effect was attempted.",
            )
        except Exception:
            return self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.FAILED,
                code="action_state_unavailable",
                message="Action state could not be reserved; no effect was attempted.",
            )
        if not claimed:
            raced = await self._existing_receipt(grant, actor, now)
            if raced is not None:
                return raced
            receipt = self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.DENIED,
                code="grant_replayed",
                message="Grant was already claimed, consumed, or conflicted.",
            )
            await self._audit_best_effort(
                grant,
                ActionAuditEventType.BROKER_REJECTED,
                receipt=receipt,
            )
            return receipt

        started_at = self._now_utc()
        try:
            start_sequence = await self._append_required_start_audit(
                grant,
                occurred_at=started_at,
            )
        except asyncio.CancelledError:
            receipt = self._error_receipt(
                grant,
                started_at,
                outcome=ExecutionOutcome.CANCELLED,
                code="execution_cancelled_before_dispatch",
                message="Action was cancelled before dispatch; no effect was attempted.",
            )
            return await self._finalize(
                registration,
                grant,
                receipt,
                None,
                terminal_sequence_start=None,
            )
        except Exception:
            receipt = self._error_receipt(
                grant,
                started_at,
                outcome=ExecutionOutcome.FAILED,
                code="audit_unavailable",
                message="Required start audit could not be persisted; no effect was attempted.",
            )
            return await self._finalize(
                registration,
                grant,
                receipt,
                None,
                terminal_sequence_start=None,
            )

        effect: ActionEffect | None = None
        result_bytes = 0
        try:
            async with asyncio.timeout(registration.definition.tool.timeout_seconds):
                raw_effect = await registration.handler.execute(grant.action)
                effect = ActionEffect.model_validate(raw_effect)
                result_bytes = len(canonical_json_bytes(effect.result))
                if result_bytes > registration.definition.tool.max_result_bytes:
                    raise _BrokerError(
                        "result_limit_exceeded",
                        "Action result exceeded its registered byte limit.",
                    )
                result_items = count_json_leaf_items(
                    effect.result,
                    stop_after=registration.definition.tool.max_result_items,
                )
                if result_items > registration.definition.tool.max_result_items:
                    raise _BrokerError(
                        "result_item_limit_exceeded",
                        "Action result exceeded its registered recursive item limit.",
                    )
                raw_evidence = await registration.handler.verify(grant.action, effect)
                evidence = PostconditionEvidence.model_validate(raw_evidence)
                if evidence.status is not PostconditionStatus.PASSED:
                    raise _BrokerError(
                        "postcondition_mismatch",
                        "Action postcondition was not verified.",
                        ExecutionOutcome.POSTCONDITION_MISMATCH,
                    )
        except asyncio.CancelledError:
            receipt = await self._interrupted_receipt(
                registration,
                grant,
                started_at,
                effect,
                result_bytes,
                requested_outcome=ExecutionOutcome.CANCELLED,
                code="execution_cancelled",
                message="Action was cancelled; recovery was attempted where safe.",
                uncertain_code="execution_cancelled_effect_uncertain",
                uncertain_message=(
                    "Action cancellation interrupted dispatch before an effect receipt was "
                    "available. Native work may still complete; inspect state and recover manually."
                ),
            )
        except TimeoutError:
            receipt = await self._interrupted_receipt(
                registration,
                grant,
                started_at,
                effect,
                result_bytes,
                requested_outcome=ExecutionOutcome.TIMED_OUT,
                code="execution_timed_out",
                message=(
                    "Action exceeded its registered timeout; recovery was attempted where safe."
                ),
                uncertain_code="execution_timed_out_effect_uncertain",
                uncertain_message=(
                    "Action timed out before an effect receipt was available. Native work may "
                    "still complete; inspect state and recover manually."
                ),
            )
        except _BrokerError as error:
            receipt = await self._recovering_receipt(
                registration,
                grant,
                started_at,
                effect,
                result_bytes,
                outcome=error.outcome,
                code=error.code,
                message=error.safe_message,
            )
        except Exception:
            receipt = await self._recovering_receipt(
                registration,
                grant,
                started_at,
                effect,
                result_bytes,
                outcome=ExecutionOutcome.FAILED,
                code="handler_failed",
                message="Fixed action handler failed; recovery was attempted where safe.",
            )
        else:
            receipt = ExecutionReceipt(
                receipt_id=self._id_factory("receipt"),
                grant_id=grant.grant_id,
                request_id=grant.action.request_id,
                action_id=grant.action.action_id,
                action_version=grant.action.action_version,
                action_fingerprint=grant.action.fingerprint,
                actor=grant.action.actor,
                policy_version=grant.action.policy_version,
                idempotency_key=grant.action.idempotency_key,
                outcome=ExecutionOutcome.SUCCEEDED,
                started_at=started_at,
                finished_at=self._now_utc(),
                result=effect.result,
                result_bytes=result_bytes,
                postcondition=evidence,
                rollback=RollbackReceipt(
                    status=RollbackStatus.NOT_NEEDED,
                    summary="Postcondition passed; rollback was not needed.",
                ),
            )

        return await self._finalize(
            registration,
            grant,
            receipt,
            effect,
            terminal_sequence_start=start_sequence + 1,
        )

    @staticmethod
    def _concurrency_key(
        registration: _RegisteredHandler,
        actor: ActorContext,
    ) -> ConcurrencyKey | None:
        concurrency = registration.definition.tool.concurrency
        dispatch_key = registration.definition.dispatch_key
        if concurrency is ToolConcurrency.PARALLEL:
            return None
        if concurrency is ToolConcurrency.SERIAL_GLOBAL:
            return ("global", dispatch_key)
        if concurrency is ToolConcurrency.SERIAL_PER_SESSION:
            return (
                "session",
                dispatch_key,
                actor.host_id,
                actor.session_id,
                actor.device_id,
                actor.interface.value,
            )
        raise ValueError(f"unsupported tool concurrency: {concurrency}")

    async def _existing_receipt(
        self,
        grant: ApprovalGrant,
        actor: ActorContext,
        now: datetime,
    ) -> ExecutionReceipt | None:
        try:
            existing = await self._state_store.get_receipt(grant.action.idempotency_key)
        except Exception:
            return self._error_receipt(
                grant,
                now,
                outcome=ExecutionOutcome.FAILED,
                code="action_state_unavailable",
                message="Action state could not be read; no effect was attempted.",
            )
        if existing is None:
            return None
        if (
            existing.action_fingerprint == grant.action.fingerprint
            and existing.action_id == grant.action.action_id
            and existing.action_version == grant.action.action_version
            and existing.policy_version == grant.action.policy_version
            and actor.has_execution_authority_for(existing.actor)
        ):
            return existing
        return self._error_receipt(
            grant,
            now,
            outcome=ExecutionOutcome.DENIED,
            code="idempotency_conflict",
            message="Idempotency key is already bound to a different exact action.",
        )

    def _validate_grant(
        self,
        grant: ApprovalGrant,
        actor: ActorContext,
        now: datetime,
    ) -> tuple[_RegisteredHandler | None, _BrokerError | None]:
        action = grant.action
        expected_action = sha256_fingerprint(action.fingerprint_payload())
        if not compare_digest(action.fingerprint, expected_action):
            return None, _BrokerError(
                "action_fingerprint_mismatch",
                "Action fingerprint is invalid.",
            )
        expected_grant = sha256_fingerprint(grant.fingerprint_payload())
        if not compare_digest(grant.grant_fingerprint, expected_grant):
            return None, _BrokerError("grant_fingerprint_mismatch", "Grant fingerprint is invalid.")
        if not actor.has_execution_authority_for(action.actor):
            return None, _BrokerError(
                "actor_mismatch",
                (
                    "Execution context does not preserve the grant's exact identity, "
                    "interface, assurance, and capabilities."
                ),
            )
        if grant.approved_by.host_id != action.actor.host_id:
            return None, _BrokerError(
                "approver_mismatch",
                "Grant approver belongs to another host.",
            )
        if action.policy_version != self._policy_version:
            return None, _BrokerError(
                "policy_version_mismatch",
                "Grant was issued under a different policy version.",
            )
        if action.permission_level is PermissionLevel.LEVEL_4:
            return None, _BrokerError("level_4_disabled", "Level 4 actions are disabled.")
        if not _aware_and_future(grant.expires_at, now) or not _aware_and_future(
            action.expires_at, now
        ):
            return None, _BrokerError("grant_expired", "Grant or canonical action has expired.")
        key = f"{action.action_id}@{action.action_version}"
        registration = self._registry.get(key)
        if registration is None:
            return None, _BrokerError("unknown_action", "Grant names no fixed registered action.")
        definition = registration.definition.tool
        if (
            definition.name != action.action_id
            or definition.version != action.action_version
            or definition.permission_level is not action.permission_level
            or definition.approval_rule is not action.approval_rule
        ):
            return None, _BrokerError(
                "definition_mismatch",
                "Grant does not match the fixed registered action definition.",
            )
        return registration, None

    async def _recovering_receipt(
        self,
        registration: _RegisteredHandler,
        grant: ApprovalGrant,
        started_at: datetime,
        effect: ActionEffect | None,
        result_bytes: int,
        *,
        outcome: ExecutionOutcome,
        code: str,
        message: str,
        known_evidence: PostconditionEvidence | None = None,
    ) -> ExecutionReceipt:
        evidence = known_evidence or await self._verify_for_recovery(registration, grant, effect)
        rollback = await self._rollback_for_recovery(registration, grant, effect, reason=code)
        return ExecutionReceipt(
            receipt_id=self._id_factory("receipt"),
            grant_id=grant.grant_id,
            request_id=grant.action.request_id,
            action_id=grant.action.action_id,
            action_version=grant.action.action_version,
            action_fingerprint=grant.action.fingerprint,
            actor=grant.action.actor,
            policy_version=grant.action.policy_version,
            idempotency_key=grant.action.idempotency_key,
            outcome=outcome,
            started_at=started_at,
            finished_at=self._now_utc(),
            result=None,
            result_bytes=result_bytes,
            postcondition=evidence,
            rollback=rollback,
            error_code=code,
            error_message=message,
        )

    async def _interrupted_receipt(
        self,
        registration: _RegisteredHandler,
        grant: ApprovalGrant,
        started_at: datetime,
        effect: ActionEffect | None,
        result_bytes: int,
        *,
        requested_outcome: ExecutionOutcome,
        code: str,
        message: str,
        uncertain_code: str,
        uncertain_message: str,
    ) -> ExecutionReceipt:
        """Never claim cancellation means no effect after native dispatch began."""
        if effect is not None or not registration.definition.effect_may_outlive_cancellation:
            return await self._recovering_receipt(
                registration,
                grant,
                started_at,
                effect,
                result_bytes,
                outcome=requested_outcome,
                code=code,
                message=message,
            )
        return ExecutionReceipt(
            receipt_id=self._id_factory("receipt"),
            grant_id=grant.grant_id,
            request_id=grant.action.request_id,
            action_id=grant.action.action_id,
            action_version=grant.action.action_version,
            action_fingerprint=grant.action.fingerprint,
            actor=grant.action.actor,
            policy_version=grant.action.policy_version,
            idempotency_key=grant.action.idempotency_key,
            outcome=ExecutionOutcome.UNCERTAIN,
            started_at=started_at,
            finished_at=self._now_utc(),
            result=None,
            result_bytes=0,
            postcondition=PostconditionEvidence(
                status=PostconditionStatus.UNKNOWN,
                summary="Effect state is unknown because dispatch did not return a receipt.",
            ),
            rollback=RollbackReceipt(
                status=RollbackStatus.UNAVAILABLE,
                summary=(
                    "Automatic rollback is unsafe while interrupted native work may still finish; "
                    "manual reconciliation is required."
                ),
            ),
            error_code=uncertain_code,
            error_message=uncertain_message,
        )

    async def _verify_for_recovery(
        self,
        registration: _RegisteredHandler,
        grant: ApprovalGrant,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        try:
            async with asyncio.timeout(registration.definition.rollback_timeout_seconds):
                raw = await registration.handler.verify(grant.action, effect)
            return PostconditionEvidence.model_validate(raw)
        except BaseException:
            return PostconditionEvidence(
                status=PostconditionStatus.UNKNOWN,
                summary="Postcondition could not be determined during recovery.",
            )

    async def _rollback_for_recovery(
        self,
        registration: _RegisteredHandler,
        grant: ApprovalGrant,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        if not registration.definition.supports_rollback:
            return RollbackReceipt(
                status=RollbackStatus.UNAVAILABLE,
                summary="Registered action has no automatic rollback.",
            )
        try:
            async with asyncio.timeout(registration.definition.rollback_timeout_seconds):
                raw = await registration.handler.rollback(grant.action, effect, reason=reason)
            return RollbackReceipt.model_validate(raw)
        except BaseException:
            return RollbackReceipt(
                status=RollbackStatus.FAILED,
                summary="Rollback failed or exceeded its registered timeout.",
            )

    async def _finalize(
        self,
        registration: _RegisteredHandler,
        grant: ApprovalGrant,
        receipt: ExecutionReceipt,
        effect: ActionEffect | None,
        *,
        terminal_sequence_start: int | None,
    ) -> ExecutionReceipt:
        """Persist terminal state before publishing the supplementary terminal audit."""
        try:
            await self._complete_grant_uncancellable(grant, receipt)
        except Exception:
            if receipt.outcome is ExecutionOutcome.SUCCEEDED:
                receipt = await self._recovering_receipt(
                    registration,
                    grant,
                    receipt.started_at,
                    effect,
                    receipt.result_bytes,
                    outcome=ExecutionOutcome.FAILED,
                    code="action_state_unavailable",
                    message=(
                        "Terminal action state failed after the effect; recovery was attempted."
                    ),
                    known_evidence=receipt.postcondition,
                )
                with suppress(Exception):
                    await self._complete_grant_uncancellable(grant, receipt)
        await self._append_terminal_audit_best_effort(
            grant,
            receipt,
            minimum_sequence=terminal_sequence_start,
        )
        return receipt

    async def _complete_grant_uncancellable(
        self,
        grant: ApprovalGrant,
        receipt: ExecutionReceipt,
    ) -> None:
        """Once claimed, suppress caller cancellation until terminal state is durable."""
        task = asyncio.create_task(self._state_store.complete_grant(grant, receipt))
        while True:
            try:
                await asyncio.shield(task)
                return
            except asyncio.CancelledError:
                if task.cancelled():
                    raise RuntimeError("terminal state task was cancelled") from None
                if task.done():
                    task.result()
                    return

    async def _append_terminal_audit_best_effort(
        self,
        grant: ApprovalGrant,
        receipt: ExecutionReceipt,
        *,
        minimum_sequence: int | None,
    ) -> None:
        if minimum_sequence is None:
            return
        for sequence in range(minimum_sequence, _MAX_AUDIT_SEQUENCE + 1):
            try:
                await self._audit_store.append_action_event(
                    self._audit_event(
                        grant,
                        ActionAuditEventType.EXECUTION_FINISHED,
                        sequence=sequence,
                        occurred_at=receipt.finished_at,
                        receipt=receipt,
                    )
                )
                return
            except asyncio.CancelledError:
                return
            except ActionAuditSequenceConflictError:
                continue
            except Exception:
                return

    async def _append_required_start_audit(
        self,
        grant: ApprovalGrant,
        *,
        occurred_at: datetime,
    ) -> int:
        for sequence in range(1, _MAX_AUDIT_SEQUENCE + 1):
            try:
                await self._audit_store.append_action_event(
                    self._audit_event(
                        grant,
                        ActionAuditEventType.EXECUTION_STARTED,
                        sequence=sequence,
                        occurred_at=occurred_at,
                    )
                )
            except ActionAuditSequenceConflictError:
                continue
            else:
                return sequence
        raise ActionAuditSequenceConflictError("action audit sequence capacity exhausted")

    async def _audit_best_effort(
        self,
        grant: ApprovalGrant,
        event_type: ActionAuditEventType,
        *,
        receipt: ExecutionReceipt,
    ) -> None:
        for sequence in range(1, _MAX_AUDIT_SEQUENCE + 1):
            try:
                await self._audit_store.append_action_event(
                    self._audit_event(
                        grant,
                        event_type,
                        sequence=sequence,
                        occurred_at=receipt.finished_at,
                        receipt=receipt,
                    )
                )
            except asyncio.CancelledError:
                return
            except ActionAuditSequenceConflictError:
                continue
            except Exception:
                return
            else:
                return

    def _audit_event(
        self,
        grant: ApprovalGrant,
        event_type: ActionAuditEventType,
        *,
        sequence: int,
        occurred_at: datetime,
        receipt: ExecutionReceipt | None = None,
    ) -> ActionAuditEvent:
        return ActionAuditEvent(
            event_id=self._id_factory("audit"),
            sequence=sequence,
            type=event_type,
            request_id=grant.action.request_id,
            grant_id=grant.grant_id,
            action_id=grant.action.action_id,
            action_version=grant.action.action_version,
            action_fingerprint=grant.action.fingerprint,
            occurred_at=occurred_at,
            outcome=receipt.outcome if receipt is not None else None,
            error_code=receipt.error_code if receipt is not None else None,
            detail={"result_bytes": receipt.result_bytes} if receipt is not None else {},
        )

    def _error_receipt(
        self,
        grant: ApprovalGrant,
        timestamp: datetime,
        *,
        outcome: ExecutionOutcome,
        code: str,
        message: str,
    ) -> ExecutionReceipt:
        return ExecutionReceipt(
            receipt_id=self._id_factory("receipt"),
            grant_id=grant.grant_id,
            request_id=grant.action.request_id,
            action_id=grant.action.action_id,
            action_version=grant.action.action_version,
            action_fingerprint=grant.action.fingerprint,
            actor=grant.action.actor,
            policy_version=grant.action.policy_version,
            idempotency_key=grant.action.idempotency_key,
            outcome=outcome,
            started_at=timestamp,
            finished_at=timestamp,
            postcondition=PostconditionEvidence(
                status=PostconditionStatus.NOT_RUN,
                summary="No brokered effect was attempted.",
            ),
            rollback=RollbackReceipt(
                status=RollbackStatus.NOT_NEEDED,
                summary="No brokered effect was attempted.",
            ),
            error_code=code,
            error_message=message,
        )

    def _now_utc(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("broker clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


def _aware_and_future(expiry: datetime, now: datetime) -> bool:
    return expiry.tzinfo is not None and expiry.utcoffset() is not None and expiry > now
