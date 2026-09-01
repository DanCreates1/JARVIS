"""Application service coordinating proposal, trusted review, and broker execution.

The caller supplies a reviewed ``ActionCanonicalizer`` for each proposal. The
coordinator does not discover tools dynamically. Its broker must be constructed with
the corresponding fixed handlers, and its permission engine and broker must share the
same policy version. Model output is accepted only as typed raw arguments; it never
selects a callable or creates a grant.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, model_validator

from jarvis.core.models import Identifier

from .canonical import sha256_fingerprint
from .contracts import PrivilegeBroker, TrustedApprovalSurface
from .models import (
    MAX_ACTION_TTL,
    MAX_APPROVAL_TTL,
    MAX_GRANT_TTL,
    ActionDefinition,
    ActionPolicyDecision,
    ActorContext,
    ApprovalDecision,
    ApprovalGrant,
    ApprovalRequest,
    CanonicalAction,
    DomainModel,
    ExecutionOutcome,
    ExecutionReceipt,
    InteractionInterface,
    PolicyDisposition,
)
from .policy import PermissionEngine
from .sqlite_store import (
    ActionStoreConflictError,
    ApprovalRequestRecord,
    ApprovalSource,
    ApprovalStatus,
    ControlIntentEvent,
    ControlIntentOutcome,
    GrantStatus,
    SQLiteActionStore,
)

if TYPE_CHECKING:
    from jarvis.computer.actions import ActionCanonicalizer, PreparedAction

Now = Callable[[], datetime]
IdFactory = Callable[[str], str]
NonceFactory = Callable[[], str]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _crypto_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(16)}"


def _crypto_nonce() -> str:
    return f"nonce-{secrets.token_hex(32)}"


class ActionCoordinatorStatus(StrEnum):
    DENIED = "denied"
    PENDING = "pending"
    APPROVED = "approved"
    EXECUTED = "executed"


ResultCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z][a-z0-9_.-]*$",
    ),
]


class ActionCoordinatorResult(DomainModel):
    """Public lifecycle result with exact authority objects and no raw secret payloads."""

    status: ActionCoordinatorStatus
    action: CanonicalAction | None = None
    request: ApprovalRequest | None = None
    decision: ActionPolicyDecision | None = None
    approval_decision: ApprovalDecision | None = None
    approval_id: Identifier | None = None
    grant_id: Identifier | None = None
    receipt: ExecutionReceipt | None = None
    code: ResultCode | None = None
    message: Annotated[str, Field(min_length=1, max_length=2_000)] | None = None

    @model_validator(mode="after")
    def validate_lifecycle_shape(self) -> Self:
        if self.request is not None:
            if self.action is not None and self.action != self.request.action:
                raise ValueError("result action must equal its exact approval request action")
            if self.approval_id != self.request.approval_id:
                raise ValueError("result approval identifier must match its request")
        if (
            self.approval_decision is not None
            and self.request is not None
            and (
                self.approval_decision.approval_id != self.request.approval_id
                or self.approval_decision.action_fingerprint != self.request.action.fingerprint
            )
        ):
            raise ValueError("result approval decision must match its request")
        if self.receipt is not None:
            if self.grant_id != self.receipt.grant_id:
                raise ValueError("result grant identifier must match its receipt")
            if self.action is not None and (
                self.receipt.action_fingerprint != self.action.fingerprint
                or self.receipt.request_id != self.action.request_id
            ):
                raise ValueError("result receipt must match its exact action")

        has_error = self.code is not None or self.message is not None
        if has_error and (self.code is None or self.message is None):
            raise ValueError("result error code and message must be present together")
        if self.status is ActionCoordinatorStatus.DENIED:
            if not has_error:
                raise ValueError("denied coordinator result requires a safe error")
        elif has_error:
            raise ValueError("non-denied coordinator result cannot contain an error")

        if self.status is ActionCoordinatorStatus.PENDING:
            if (
                self.action is None
                or self.request is None
                or self.decision is None
                or self.decision.disposition is PolicyDisposition.DENY
                or self.grant_id is not None
                or self.receipt is not None
            ):
                raise ValueError("pending result requires a non-denied exact proposal")
        elif self.status is ActionCoordinatorStatus.APPROVED:
            if (
                self.action is None
                or self.request is None
                or self.approval_decision is None
                or not self.approval_decision.approved
                or self.grant_id is None
                or self.receipt is not None
            ):
                raise ValueError("approved result requires an exact approval and grant")
        elif self.status is ActionCoordinatorStatus.EXECUTED and (
            self.action is None
            or self.request is None
            or self.grant_id is None
            or self.receipt is None
        ):
            raise ValueError("executed result requires request, grant, and receipt")
        return self


class ActionCoordinator:
    """Coordinate exact durable authority; fixed handlers remain broker-owned."""

    def __init__(
        self,
        *,
        store: SQLiteActionStore,
        permission_engine: PermissionEngine,
        broker: PrivilegeBroker,
        action_ttl: timedelta = timedelta(minutes=2),
        approval_ttl: timedelta = timedelta(seconds=90),
        grant_ttl: timedelta = timedelta(seconds=30),
        now: Now = _utc_now,
        id_factory: IdFactory = _crypto_id,
        nonce_factory: NonceFactory = _crypto_nonce,
    ) -> None:
        _validate_ttl_bound(action_ttl, MAX_ACTION_TTL, "action_ttl")
        _validate_ttl_bound(approval_ttl, MAX_APPROVAL_TTL, "approval_ttl")
        _validate_ttl_bound(grant_ttl, MAX_GRANT_TTL, "grant_ttl")
        self._store = store
        self._permission_engine = permission_engine
        self._broker = broker
        self._action_ttl = action_ttl
        self._approval_ttl = approval_ttl
        self._grant_ttl = grant_ttl
        self._now = now
        self._id_factory = id_factory
        self._nonce_factory = nonce_factory

    @property
    def policy_version(self) -> str:
        """Policy version embedded into every proposal and rechecked by the broker."""
        return self._permission_engine.policy_version

    async def propose(
        self,
        canonicalizer: ActionCanonicalizer,
        raw_arguments: BaseModel,
        *,
        actor: ActorContext,
        source: ApprovalSource | InteractionInterface | str,
        conversation_id: str | None = None,
        tool_call_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> ActionCoordinatorResult:
        """Prepare and evaluate one typed raw action without invoking its handler."""
        from jarvis.computer.actions import prepare_action

        now = self._now_utc()
        actor = ActorContext.model_validate(actor.model_dump())
        try:
            source_value = ApprovalSource(str(source))
        except ValueError:
            return self._denied(
                code="invalid_source",
                message="Action proposal source is not trusted or supported.",
            )
        try:
            definition = ActionDefinition.model_validate(canonicalizer.definition.model_dump())
            prepared = prepare_action(canonicalizer, raw_arguments)
        except Exception:
            return self._denied(
                code="action_preparation_failed",
                message="Action arguments or preconditions could not be prepared safely.",
            )

        key = idempotency_key or self._id_factory("idempotency")
        existing = await self._store.get_approval_request_by_idempotency_key(
            key,
            expire_as_of=now,
        )
        if existing is not None:
            return await self._result_for_existing_proposal(
                existing,
                definition=definition,
                prepared=prepared,
                actor=actor,
                source=source_value,
                conversation_id=conversation_id,
                tool_call_id=tool_call_id,
            )

        try:
            action = CanonicalAction.create(
                request_id=self._id_factory("request"),
                conversation_id=conversation_id,
                tool_call_id=tool_call_id,
                action_id=definition.action_id,
                action_version=definition.version,
                actor=actor,
                normalized_arguments=prepared.normalized_arguments,
                permission_level=definition.tool.permission_level,
                approval_rule=definition.tool.approval_rule,
                policy_version=self.policy_version,
                idempotency_key=key,
                human_effect=prepared.human_effect,
                recovery_limits=prepared.recovery_limits,
                precondition=prepared.precondition,
                created_at=now,
                expires_at=now + self._action_ttl,
            )
        except ValueError:
            return self._denied(
                code="invalid_proposal_authority",
                message="Action authority identifiers or expiry were invalid.",
            )

        decision = await self._permission_engine.decide(
            action=action,
            definition=definition,
            actor=actor,
        )
        if decision.disposition is PolicyDisposition.DENY:
            await self._record_intent_best_effort(
                action=action,
                source=source_value,
                outcome=ControlIntentOutcome.DENIED,
                request_id=None,
                occurred_at=now,
            )
            return self._denied(
                action=action,
                decision=decision,
                code=decision.rule_id,
                message=decision.reason,
            )

        request = ApprovalRequest(
            approval_id=self._id_factory("approval"),
            action=action,
            requested_at=now,
            expires_at=min(now + self._approval_ttl, action.expires_at),
        )
        try:
            stored = await self._store.create_approval_request(
                request,
                source=source_value,
                risk=definition.tool.risk,
                rule_id=decision.rule_id,
            )
        except ActionStoreConflictError:
            raced = await self._store.get_approval_request_by_idempotency_key(
                key,
                expire_as_of=now,
            )
            if raced is None:
                return self._denied(
                    code="action_state_conflict",
                    message="Action proposal could not be bound to durable authority state.",
                )
            return await self._result_for_existing_proposal(
                raced,
                definition=definition,
                prepared=prepared,
                actor=actor,
                source=source_value,
                conversation_id=conversation_id,
                tool_call_id=tool_call_id,
            )

        await self._record_intent_best_effort(
            action=stored.request.action,
            source=source_value,
            outcome=ControlIntentOutcome.PROPOSED,
            request_id=stored.request.action.request_id,
            occurred_at=stored.request.requested_at,
        )
        return ActionCoordinatorResult(
            status=ActionCoordinatorStatus.PENDING,
            action=stored.request.action,
            request=stored.request,
            decision=decision,
            approval_id=stored.request.approval_id,
        )

    async def review(
        self,
        approval_id: str,
        surface: TrustedApprovalSurface,
    ) -> ActionCoordinatorResult:
        """Obtain one trusted exact decision and issue a short one-use grant."""
        now = self._now_utc()
        record = await self._store.get_approval_request(
            approval_id,
            expire_as_of=now,
        )
        if record is None:
            return self._denied(
                code="approval_not_found",
                message="Approval request does not exist.",
            )
        if record.status is ApprovalStatus.DENIED:
            return self._denied(
                action=record.request.action,
                request=record.request,
                approval_decision=record.decision,
                code="approval_denied",
                message=(
                    record.decision.reason
                    if record.decision is not None and record.decision.reason
                    else "Exact action approval was denied."
                ),
            )
        if record.status is ApprovalStatus.EXPIRED:
            return self._denied(
                action=record.request.action,
                request=record.request,
                code="approval_expired",
                message="Approval request expired before a grant was issued.",
            )
        if record.status is not ApprovalStatus.PENDING:
            return await self._result_for_decided_record(record)

        try:
            decision = ApprovalDecision.model_validate(
                (await surface.review(record.request)).model_dump()
            )
        except Exception:
            return self._denied(
                action=record.request.action,
                request=record.request,
                code="approval_surface_failed",
                message="Trusted approval surface did not return a valid exact decision.",
            )
        if not decision.approved:
            try:
                denied = await self._store.record_denial(decision)
            except (ValueError, RuntimeError, KeyError):
                return self._denied(
                    action=record.request.action,
                    request=record.request,
                    code="approval_binding_mismatch",
                    message="Approval denial did not match the exact pending request.",
                )
            await self._record_intent_best_effort(
                action=denied.request.action,
                source=denied.source,
                outcome=ControlIntentOutcome.DENIED,
                request_id=denied.request.action.request_id,
                occurred_at=decision.decided_at,
            )
            return self._denied(
                action=denied.request.action,
                request=denied.request,
                approval_decision=decision,
                code="approval_denied",
                message=decision.reason or "Exact action approval was denied.",
            )

        issued_at = max(now, decision.decided_at)
        expires_at = min(
            issued_at + self._grant_ttl,
            record.request.expires_at,
            record.request.action.expires_at,
        )
        if expires_at <= issued_at:
            await self._store.expire_approval(
                approval_id,
                expired_at=max(issued_at, record.request.expires_at),
            )
            return self._denied(
                action=record.request.action,
                request=record.request,
                approval_decision=decision,
                code="approval_expired",
                message="Approval expired before a one-use grant could be issued.",
            )
        try:
            grant = await self._store.issue_grant(
                decision,
                grant_id=self._id_factory("grant"),
                nonce=self._nonce_factory(),
                issued_at=issued_at,
                expires_at=expires_at,
            )
        except (ValueError, RuntimeError, KeyError):
            return self._denied(
                action=record.request.action,
                request=record.request,
                code="approval_binding_mismatch",
                message="Approval could not issue an exact one-use grant.",
            )
        return ActionCoordinatorResult(
            status=ActionCoordinatorStatus.APPROVED,
            action=record.request.action,
            request=record.request,
            approval_decision=decision,
            approval_id=record.request.approval_id,
            grant_id=grant.grant_id,
        )

    async def execute(
        self,
        grant_or_id: ApprovalGrant | str,
        *,
        actor: ActorContext,
    ) -> ActionCoordinatorResult:
        """Execute one active exact grant through the fixed broker only."""
        now = self._now_utc()
        actor = ActorContext.model_validate(actor.model_dump())
        await self._store.expire_stale(now=now)
        if isinstance(grant_or_id, str):
            grant_record = await self._store.get_grant_record(grant_or_id)
            supplied_grant: ApprovalGrant | None = None
        else:
            try:
                supplied_grant = ApprovalGrant.model_validate(grant_or_id.model_dump())
            except ValueError:
                return self._denied(
                    code="grant_binding_mismatch",
                    message="Supplied grant authority data is invalid.",
                )
            grant_record = await self._store.get_grant_record(supplied_grant.grant_id)
        if grant_record is None:
            return self._denied(
                code="grant_not_found",
                message="One-use grant does not exist.",
            )
        grant = grant_record.grant
        request_record = await self._store.get_approval_request(grant.approval_id)
        if request_record is None:
            return self._denied(
                code="action_state_unavailable",
                message="Grant approval state could not be loaded.",
            )
        if supplied_grant is not None and supplied_grant != grant:
            return self._denied(
                action=grant.action,
                request=request_record.request,
                code="grant_binding_mismatch",
                message="Supplied grant differs from durable exact authority data.",
            )
        if not actor.has_execution_authority_for(grant.action.actor):
            return self._denied(
                action=grant.action,
                request=request_record.request,
                approval_decision=request_record.decision,
                grant_id=grant.grant_id,
                code="actor_mismatch",
                message=(
                    "Execution context does not preserve the grant's exact identity, "
                    "interface, assurance, and capabilities."
                ),
            )
        if grant_record.status is not GrantStatus.ACTIVE:
            receipt = await self._store.get_receipt(grant.action.idempotency_key)
            code = {
                GrantStatus.CLAIMED: "grant_replayed",
                GrantStatus.REVOKED: "grant_revoked",
                GrantStatus.EXPIRED: "grant_expired",
            }[grant_record.status]
            return self._denied(
                action=grant.action,
                request=request_record.request,
                approval_decision=request_record.decision,
                grant_id=grant.grant_id,
                receipt=receipt,
                code=code,
                message="One-use grant is no longer active.",
            )
        if grant.expires_at <= now or grant.action.expires_at <= now:
            await self._store.expire_stale(now=now)
            return self._denied(
                action=grant.action,
                request=request_record.request,
                approval_decision=request_record.decision,
                grant_id=grant.grant_id,
                code="grant_expired",
                message="Grant or exact action expired before execution.",
            )

        receipt = await self._broker.execute(grant, actor=actor)
        status = (
            ActionCoordinatorStatus.DENIED
            if receipt.outcome is ExecutionOutcome.DENIED
            else ActionCoordinatorStatus.EXECUTED
        )
        if status is ActionCoordinatorStatus.DENIED:
            return self._denied(
                action=grant.action,
                request=request_record.request,
                approval_decision=request_record.decision,
                grant_id=grant.grant_id,
                receipt=receipt,
                code=receipt.error_code or "broker_denied",
                message=receipt.error_message or "Fixed broker denied exact action execution.",
            )
        return ActionCoordinatorResult(
            status=ActionCoordinatorStatus.EXECUTED,
            action=grant.action,
            request=request_record.request,
            approval_decision=request_record.decision,
            approval_id=grant.approval_id,
            grant_id=grant.grant_id,
            receipt=receipt,
        )

    async def _result_for_existing_proposal(
        self,
        record: ApprovalRequestRecord,
        *,
        definition: ActionDefinition,
        prepared: PreparedAction,
        actor: ActorContext,
        source: ApprovalSource,
        conversation_id: str | None,
        tool_call_id: str | None,
    ) -> ActionCoordinatorResult:
        action = record.request.action
        if not _proposal_matches(
            record,
            definition=definition,
            prepared=prepared,
            actor=actor,
            source=source,
            policy_version=self.policy_version,
            conversation_id=conversation_id,
            tool_call_id=tool_call_id,
        ):
            return self._denied(
                code="idempotency_conflict",
                message="Idempotency key is already bound to different exact authority data.",
            )
        decision = await self._permission_engine.decide(
            action=action,
            definition=definition,
            actor=actor,
        )
        if decision.disposition is PolicyDisposition.DENY:
            return self._denied(
                action=action,
                request=record.request,
                decision=decision,
                approval_decision=record.decision,
                code=decision.rule_id,
                message=decision.reason,
            )
        if record.rule_id != decision.rule_id:
            return self._denied(
                code="policy_rule_conflict",
                message="Stored proposal no longer matches the active exact policy rule.",
            )
        if record.status is ApprovalStatus.PENDING:
            return ActionCoordinatorResult(
                status=ActionCoordinatorStatus.PENDING,
                action=action,
                request=record.request,
                decision=decision,
                approval_id=record.request.approval_id,
            )
        return await self._result_for_decided_record(record, decision=decision)

    async def _result_for_decided_record(
        self,
        record: ApprovalRequestRecord,
        *,
        decision: ActionPolicyDecision | None = None,
    ) -> ActionCoordinatorResult:
        action = record.request.action
        if record.status is ApprovalStatus.DENIED:
            return self._denied(
                action=action,
                request=record.request,
                decision=decision,
                approval_decision=record.decision,
                code="approval_denied",
                message=(
                    record.decision.reason
                    if record.decision is not None and record.decision.reason
                    else "Exact action approval was denied."
                ),
            )
        if record.status is ApprovalStatus.EXPIRED:
            return self._denied(
                action=action,
                request=record.request,
                decision=decision,
                approval_decision=record.decision,
                code="approval_expired",
                message="Exact action approval or grant expired.",
            )
        receipt = await self._store.get_receipt(action.idempotency_key)
        grant_record = await self._store.get_grant_for_approval(record.request.approval_id)
        if receipt is not None and grant_record is not None:
            return ActionCoordinatorResult(
                status=ActionCoordinatorStatus.EXECUTED,
                action=action,
                request=record.request,
                decision=decision,
                approval_decision=record.decision,
                approval_id=record.request.approval_id,
                grant_id=grant_record.grant.grant_id,
                receipt=receipt,
            )
        if (
            grant_record is not None
            and grant_record.status is GrantStatus.ACTIVE
            and record.decision is not None
        ):
            return ActionCoordinatorResult(
                status=ActionCoordinatorStatus.APPROVED,
                action=action,
                request=record.request,
                decision=decision,
                approval_decision=record.decision,
                approval_id=record.request.approval_id,
                grant_id=grant_record.grant.grant_id,
            )
        if grant_record is not None and grant_record.status is not GrantStatus.ACTIVE:
            code = {
                GrantStatus.CLAIMED: "grant_replayed",
                GrantStatus.REVOKED: "grant_revoked",
                GrantStatus.EXPIRED: "grant_expired",
            }[grant_record.status]
            return self._denied(
                action=action,
                request=record.request,
                decision=decision,
                approval_decision=record.decision,
                grant_id=grant_record.grant.grant_id,
                code=code,
                message="One-use grant is no longer active.",
            )
        return self._denied(
            action=action,
            request=record.request,
            decision=decision,
            approval_decision=record.decision,
            code="action_state_unavailable",
            message="Durable action lifecycle is incomplete or inconsistent.",
        )

    async def _record_intent_best_effort(
        self,
        *,
        action: CanonicalAction,
        source: ApprovalSource,
        outcome: ControlIntentOutcome,
        request_id: str | None,
        occurred_at: datetime,
    ) -> None:
        event_id = "intent-" + sha256_fingerprint(
            {
                "idempotency_key": action.idempotency_key,
                "action_id": action.action_id,
                "actor": action.actor,
                "source": source,
                "outcome": outcome,
            }
        ).removeprefix("sha256:")
        event = ControlIntentEvent(
            event_id=event_id,
            actor_id=action.actor.host_id,
            session_id=action.actor.session_id,
            source=source,
            intent=action.action_id,
            outcome=outcome,
            request_id=request_id,
            created_at=occurred_at,
        )
        try:
            await self._store.record_control_intent(event)
        except Exception:
            return

    @staticmethod
    def _denied(
        *,
        code: str,
        message: str,
        action: CanonicalAction | None = None,
        request: ApprovalRequest | None = None,
        decision: ActionPolicyDecision | None = None,
        approval_decision: ApprovalDecision | None = None,
        grant_id: str | None = None,
        receipt: ExecutionReceipt | None = None,
    ) -> ActionCoordinatorResult:
        return ActionCoordinatorResult(
            status=ActionCoordinatorStatus.DENIED,
            action=action,
            request=request,
            decision=decision,
            approval_decision=approval_decision,
            approval_id=request.approval_id if request is not None else None,
            grant_id=grant_id,
            receipt=receipt,
            code=code,
            message=message,
        )

    def _now_utc(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("coordinator clock must return a timezone-aware datetime")
        return value.astimezone(UTC)


def _proposal_matches(
    record: ApprovalRequestRecord,
    *,
    definition: ActionDefinition,
    prepared: PreparedAction,
    actor: ActorContext,
    source: ApprovalSource,
    policy_version: str,
    conversation_id: str | None,
    tool_call_id: str | None,
) -> bool:
    action = record.request.action
    return (
        record.source is source
        and record.risk is definition.tool.risk
        and action.action_id == definition.action_id
        and action.action_version == definition.version
        and action.actor == actor
        and action.normalized_arguments == prepared.normalized_arguments
        and action.permission_level is definition.tool.permission_level
        and action.approval_rule is definition.tool.approval_rule
        and action.policy_version == policy_version
        and action.human_effect == prepared.human_effect
        and action.recovery_limits == prepared.recovery_limits
        and action.precondition == prepared.precondition
        and action.conversation_id == conversation_id
        and action.tool_call_id == tool_call_id
    )


def _validate_ttl_bound(value: timedelta, maximum: timedelta, name: str) -> None:
    if value <= timedelta(0) or value > maximum:
        raise ValueError(f"{name} must be in (0, {maximum.total_seconds():.0f} seconds]")
