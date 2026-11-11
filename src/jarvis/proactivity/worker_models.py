"""Content-minimized bounded worker authority; no task or outbound authority."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Self
from uuid import uuid4

import aiosqlite
from pydantic import Field, field_validator, model_validator

from jarvis.core.models import CoreModel, Identifier

from .models import Digest, FeatureName, ProactivityRule, RuleStatus
from .policy import HostProactivityPolicy


class WorkerDeniedError(RuntimeError):
    """A fixed, content-free worker denial; callers must stop."""


def policy_digest(policy: HostProactivityPolicy) -> str:
    values = asdict(policy)
    values["enabled_features"] = sorted(policy.enabled_features)
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def check_worker_rule(rule: ProactivityRule, permit: WorkerPermit | None) -> None:
    if permit is not None and (
        rule.status is not RuleStatus.ACTIVE
        or rule.proposal.expires_at <= utc_now()
        or HostProactivityPolicy().is_quiet_time(rule, at=utc_now())
    ):
        raise WorkerDeniedError("worker rule expired, disabled or quiet")


class WorkerPlan(CoreModel):
    host_id: Identifier
    review_id: Identifier = Field(default_factory=lambda: f"worker-review:{uuid4()}")
    expected_generation: Annotated[int, Field(ge=0)]
    policy_sha256: Digest
    features: Annotated[tuple[FeatureName, ...], Field(min_length=1, max_length=20)]
    poll_seconds: Annotated[int, Field(strict=True, ge=1, le=60)] = 5
    max_ticks: Annotated[int, Field(strict=True, ge=1, le=3_600)] = 3_600
    created_at: datetime
    expires_at: datetime

    @field_validator("features")
    @classmethod
    def unique_features(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("worker features must be unique")
        return tuple(sorted(value))

    @field_validator("created_at", "expires_at")
    @classmethod
    def aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("worker clock must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def bounded_lifetime(self) -> Self:
        if not timedelta(0) < self.expires_at - self.created_at <= timedelta(seconds=3_600):
            raise ValueError("worker approval lifetime must be positive and at most 3600 seconds")
        return self

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()

    def validate_policy(self, policy: HostProactivityPolicy, *, runner_enabled: bool) -> None:
        if (
            not runner_enabled
            or not policy.enabled
            or self.policy_sha256 != policy_digest(policy)
            or not set(self.features) <= policy.enabled_features
        ):
            raise WorkerDeniedError("worker policy is disabled or changed")


@dataclass(frozen=True, slots=True)
class WorkerPermit:
    host_id: str
    generation: int
    owner_token: str
    features: tuple[str, ...]


async def check_worker_permit(
    connection: aiosqlite.Connection,
    permit: WorkerPermit | None,
    *,
    host_id: str,
    feature: str | None = None,
) -> None:
    """Check inside the same IMMEDIATE transaction as every background mutation.

    Stop/re-enable/lease takeover serialize against that transaction. Use a fresh clock,
    never the tick's earlier schedule timestamp, to fence expiry during slow evaluations.
    """
    if permit is None:
        return
    if permit.host_id != host_id or (feature is not None and feature not in permit.features):
        raise WorkerDeniedError("worker scope denied")
    async with connection.execute(
        """SELECT enabled, generation, owner_token, lease_expires_at, expires_at
           FROM proactivity_worker_controls WHERE host_id = ?""",
        (host_id,),
    ) as cursor:
        row = await cursor.fetchone()
    now = utc_now().isoformat(timespec="microseconds")
    if (
        row is None
        or not row[0]
        or row[1] != permit.generation
        or row[2] != permit.owner_token
        or row[3] is None
        or row[3] <= now
        or row[4] <= now
    ):
        raise WorkerDeniedError("worker authority expired or revoked")
