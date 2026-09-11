"""Phase 9C pinned deployment, activation, health, and offline-resilience boundary."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tempfile
from collections import Counter, deque
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import BinaryIO, Final, Self, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jarvis.remote.migration import (
    DatabaseState,
    OwnershipTransition,
    OwnershipTransitionReceipt,
    SchemaMigration,
    analyze_database,
)
from jarvis.remote.topology import (
    OwnershipDomain,
    TopologyManifest,
    TopologyNodeRole,
    TopologyProfile,
)

DEPLOYMENT_MANIFEST_FORMAT: Final = "jarvis-deployment-v1"
DEPLOYMENT_STATE_FORMAT: Final = "jarvis-deployment-state-v1"
RELEASE_STATE_FORMAT: Final = "jarvis-release-state-v1"
MAX_DEPLOYMENT_DOCUMENT_BYTES: Final = 1_048_576
MAX_HEALTH_EVENTS: Final = 1_024
MIN_DEPLOYMENT_FREE_BYTES: Final = 256 * 1_024 * 1_024
_DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"
_IDENTIFIER_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$"
_PACKAGE_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\.(?:whl|tar\.gz)$"
_CAPABILITY_PATTERN: Final = r"^[a-z][a-z0-9_.-]{0,127}$"
_SHARED_DOMAINS: Final = frozenset(
    domain
    for domain in OwnershipDomain
    if domain
    not in {
        OwnershipDomain.DEVICE_SETTINGS,
        OwnershipDomain.COMPUTER_EFFECTS,
        OwnershipDomain.MEDIA_CAPTURE,
    }
)
_DeploymentDocument = TypeVar("_DeploymentDocument", bound=BaseModel)


class DeploymentErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    DOCUMENT_INVALID = "document_invalid"
    RELEASE_MISMATCH = "release_mismatch"
    TOPOLOGY_MISMATCH = "topology_mismatch"
    RECEIPT_MISMATCH = "receipt_mismatch"
    DATABASE_MISMATCH = "database_mismatch"
    OWNERSHIP_MISMATCH = "ownership_mismatch"
    UNSAFE_SERVICE = "unsafe_service"
    DESTINATION_EXISTS = "destination_exists"
    STATE_CONFLICT = "state_conflict"
    HEALTH_CHECK_FAILED = "health_check_failed"
    IO_FAILED = "io_failed"


class DeploymentError(RuntimeError):
    """Stable, content-free deployment failure."""

    def __init__(self, code: DeploymentErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class DeploymentRole(StrEnum):
    LOCAL_CORE = "local-core"
    SERVER_CORE = "server-core"
    LAPTOP_DEVICE = "laptop-device"


class DeploymentTransition(StrEnum):
    ACTIVATE = "activate"
    UPDATE = "update"
    ROLLBACK = "rollback"


class AvailabilityMode(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"
    OFFLINE = "offline"
    DENIED = "denied"


class HealthReason(StrEnum):
    STARTING = "starting"
    READY = "ready"
    SHUTTING_DOWN = "shutting_down"
    RELEASE_INVALID = "release_invalid"
    TOPOLOGY_INVALID = "topology_invalid"
    RECEIPT_INVALID = "receipt_invalid"
    DATABASE_INVALID = "database_invalid"
    TLS_UNAVAILABLE = "tls_unavailable"
    PROTOCOL_STALE = "protocol_stale"
    NETWORK_PARTITION = "network_partition"
    OVERLOADED = "overloaded"
    DISK_PRESSURE = "disk_pressure"
    DISK_FULL = "disk_full"


class ServiceHardening(BaseModel):
    """Portable assertions mirrored by the checked-in systemd unit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_as_user: str = Field(default="jarvis", pattern=r"^[a-z_][a-z0-9_-]{0,30}$")
    replica_count: int = Field(default=1, ge=1, le=1)
    bind_host: str = Field(default="127.0.0.1", pattern=r"^127\.0\.0\.1$")
    bind_port: int = Field(default=8765, ge=1, le=65535)
    root_filesystem_read_only: bool = True
    no_new_privileges: bool = True
    private_devices: bool = True
    capability_bounding_set: tuple[str, ...] = ()
    tasks_max: int = Field(default=256, ge=16, le=512)
    memory_max_bytes: int = Field(default=2 * 1_024 * 1_024 * 1_024, ge=256 * 1_024 * 1_024)
    cpu_quota_percent: int = Field(default=200, ge=25, le=800)
    open_files_max: int = Field(default=1_024, ge=128, le=4_096)

    @field_validator("run_as_user")
    @classmethod
    def reject_privileged_user(cls, value: str) -> str:
        if value in {"root", "0"}:
            raise ValueError("service user must be non-root")
        return value

    @model_validator(mode="after")
    def require_hardening(self) -> Self:
        if not (
            self.root_filesystem_read_only
            and self.no_new_privileges
            and self.private_devices
            and not self.capability_bounding_set
        ):
            raise ValueError("service hardening controls cannot be relaxed")
        return self


class DeploymentManifest(BaseModel):
    """Root-owned desired state. Hash is pinned separately by service configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str = Field(default=DEPLOYMENT_MANIFEST_FORMAT, pattern=r"^jarvis-deployment-v1$")
    deployment_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    created_at: datetime
    role: DeploymentRole
    node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    topology_profile: TopologyProfile
    topology_epoch: int = Field(ge=1)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    release_sha256: str = Field(pattern=_DIGEST_PATTERN)
    package_name: str = Field(pattern=_PACKAGE_PATTERN)
    python_version: str = Field(pattern=r"^3\.11\.[0-9]{1,3}$")
    database_path: str | None = Field(default=None, max_length=1_024)
    ownership_receipt_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    offline_capabilities: tuple[str, ...] = Field(default=(), max_length=64)
    minimum_free_bytes: int = Field(
        default=MIN_DEPLOYMENT_FREE_BYTES, ge=64 * 1_024 * 1_024, le=64 * 1_024**3
    )
    maximum_inflight_requests: int = Field(default=64, ge=1, le=1_024)
    telemetry_event_limit: int = Field(default=256, ge=16, le=MAX_HEALTH_EVENTS)
    hardening: ServiceHardening = Field(default_factory=ServiceHardening)

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("database_path")
    @classmethod
    def validate_database_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip() or "\x00" in value or not Path(value).is_absolute():
            raise ValueError("database path must be absolute")
        return value

    @field_validator("offline_capabilities")
    @classmethod
    def normalize_offline_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("offline capabilities must be unique")
        import re

        if any(re.fullmatch(_CAPABILITY_PATTERN, item) is None for item in value):
            raise ValueError("invalid offline capability")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def require_role_shape(self) -> Self:
        core_role = self.role in {DeploymentRole.LOCAL_CORE, DeploymentRole.SERVER_CORE}
        if core_role != (self.database_path is not None):
            raise ValueError("only core deployments may own a database path")
        if self.role is DeploymentRole.LOCAL_CORE:
            if self.topology_profile is not TopologyProfile.LOCAL_ONLY:
                raise ValueError("local core requires local-only topology")
            if self.topology_epoch == 1 and self.ownership_receipt_sha256 is not None:
                raise ValueError("initial local deployment cannot use an ownership receipt")
            if self.topology_epoch > 1 and self.ownership_receipt_sha256 is None:
                raise ValueError("post-migration local deployment requires rollback receipt")
        elif self.topology_profile is TopologyProfile.LOCAL_ONLY:
            raise ValueError("remote deployment role requires remote topology")
        if self.role is DeploymentRole.SERVER_CORE and self.ownership_receipt_sha256 is None:
            raise ValueError("server core requires cutover receipt")
        if self.role is DeploymentRole.LAPTOP_DEVICE and self.ownership_receipt_sha256 is not None:
            raise ValueError("device node cannot consume ownership receipt")
        return self

    @property
    def digest(self) -> str:
        return _sha256_bytes(_canonical_json(self.model_dump(mode="json")) + b"\n")


class DeploymentStateReceipt(BaseModel):
    """Root-owned content-free chain authorizing one pinned release to start."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str = Field(default=DEPLOYMENT_STATE_FORMAT, pattern=r"^jarvis-deployment-state-v1$")
    operation_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    sequence: int = Field(ge=1)
    transition: DeploymentTransition
    created_at: datetime
    deployment_manifest_sha256: str = Field(pattern=_DIGEST_PATTERN)
    previous_state_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    release_sha256: str = Field(pattern=_DIGEST_PATTERN)
    topology_profile: TopologyProfile
    topology_epoch: int = Field(ge=1)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    ownership_receipt_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    active_owner_node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    accepted_migration_state_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    verified_database_state_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    verified_database_schema_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    verified_database_migrations: tuple[SchemaMigration, ...] = ()

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_chain(self) -> Self:
        if self.sequence == 1:
            if self.transition is not DeploymentTransition.ACTIVATE:
                raise ValueError("first deployment state must activate")
            if self.previous_state_sha256 is not None:
                raise ValueError("first deployment state cannot have predecessor")
        elif self.previous_state_sha256 is None:
            raise ValueError("later deployment state requires predecessor")
        return self

    @property
    def digest(self) -> str:
        return _sha256_bytes(_canonical_json(self.model_dump(mode="json")) + b"\n")


class DeploymentActivation(BaseModel):
    """Verified runtime placement; contains no path, private data, or credential."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: DeploymentRole
    node_id: str
    release_sha256: str
    topology_profile: TopologyProfile
    topology_epoch: int
    topology_digest: str
    deployment_manifest_sha256: str
    deployment_state_sha256: str | None
    active_owner_node_id: str
    offline_capabilities: tuple[str, ...]


class OfflineDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    allowed: bool
    mode: AvailabilityMode
    reason: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")


class HealthEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observed_at: datetime
    reason: HealthReason
    healthy: bool
    latency_ms: float = Field(ge=0, le=3_600_000)


class HealthSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    live: bool
    ready: bool
    reason: HealthReason
    samples: int = Field(ge=0)
    p50_ms: float = Field(ge=0)
    p95_ms: float = Field(ge=0)
    counters: Mapping[str, int]


class ReleaseState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    format: str = Field(default=RELEASE_STATE_FORMAT, pattern=r"^jarvis-release-state-v1$")
    generation: int = Field(ge=1)
    current_release_sha256: str = Field(pattern=_DIGEST_PATTERN)
    previous_release_sha256: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return value.astimezone(UTC)


class DeploymentHealthMonitor:
    """Bounded typed health telemetry. It never accepts free-form labels or payloads."""

    _CRITICAL = frozenset(
        {
            HealthReason.RELEASE_INVALID,
            HealthReason.TOPOLOGY_INVALID,
            HealthReason.RECEIPT_INVALID,
            HealthReason.DATABASE_INVALID,
            HealthReason.TLS_UNAVAILABLE,
            HealthReason.PROTOCOL_STALE,
            HealthReason.OVERLOADED,
            HealthReason.DISK_FULL,
            HealthReason.SHUTTING_DOWN,
        }
    )

    def __init__(self, *, max_events: int = 256) -> None:
        if not 16 <= max_events <= MAX_HEALTH_EVENTS:
            raise ValueError("health event limit must be 16-1024")
        self._events: deque[HealthEvent] = deque(maxlen=max_events)
        self._reason = HealthReason.STARTING
        self._live = True
        self._ready = False

    def observe(
        self,
        reason: HealthReason,
        *,
        healthy: bool,
        latency_ms: float = 0,
        observed_at: datetime | None = None,
    ) -> HealthSnapshot:
        now = (observed_at or datetime.now(UTC)).astimezone(UTC)
        event = HealthEvent(
            observed_at=now,
            reason=reason,
            healthy=healthy,
            latency_ms=latency_ms,
        )
        self._events.append(event)
        if reason is HealthReason.SHUTTING_DOWN:
            self._live = False
            self._ready = False
            self._reason = reason
        elif healthy:
            if reason is HealthReason.READY:
                self._ready = True
                self._reason = reason
            elif reason is HealthReason.NETWORK_PARTITION:
                self._reason = reason
        else:
            self._ready = False
            self._reason = reason
        return self.snapshot()

    def snapshot(self) -> HealthSnapshot:
        latencies = sorted(event.latency_ms for event in self._events)
        counters = Counter(event.reason.value for event in self._events)
        return HealthSnapshot(
            live=self._live,
            ready=self._ready and self._reason not in self._CRITICAL,
            reason=self._reason,
            samples=len(self._events),
            p50_ms=_percentile(latencies, 0.50),
            p95_ms=_percentile(latencies, 0.95),
            counters=dict(sorted(counters.items())),
        )


def build_deployment_manifest(
    *,
    topology: TopologyManifest,
    role: DeploymentRole,
    node_id: str,
    release_artifact: Path,
    python_version: str,
    database_path: Path | None = None,
    ownership_receipt: OwnershipTransitionReceipt | None = None,
    created_at: datetime | None = None,
) -> DeploymentManifest:
    """Build reviewed desired state from exact files and immutable topology."""
    release_sha256 = _safe_file_sha256(release_artifact)
    node = next((item for item in topology.nodes if item.id == node_id), None)
    if node is None:
        raise DeploymentError(DeploymentErrorCode.TOPOLOGY_MISMATCH, "node is absent from topology")
    if role in {DeploymentRole.LOCAL_CORE, DeploymentRole.SERVER_CORE}:
        if TopologyNodeRole.CORE_PRIMARY not in node.roles:
            raise DeploymentError(
                DeploymentErrorCode.OWNERSHIP_MISMATCH, "core deployment node is not primary"
            )
        if any(topology.owner_for(domain) != node_id for domain in _SHARED_DOMAINS):
            raise DeploymentError(
                DeploymentErrorCode.OWNERSHIP_MISMATCH, "core deployment lacks shared ownership"
            )
    elif TopologyNodeRole.DEVICE_NODE not in node.roles:
        raise DeploymentError(
            DeploymentErrorCode.OWNERSHIP_MISMATCH, "device deployment node lacks device role"
        )
    receipt_digest = ownership_receipt.digest if ownership_receipt is not None else None
    return DeploymentManifest(
        deployment_id=f"deployment:{uuid4()}",
        created_at=created_at or datetime.now(UTC),
        role=role,
        node_id=node_id,
        topology_profile=topology.profile,
        topology_epoch=topology.epoch,
        topology_digest=topology.digest,
        release_sha256=release_sha256,
        package_name=release_artifact.name,
        python_version=python_version,
        database_path=str(database_path.resolve()) if database_path is not None else None,
        ownership_receipt_sha256=receipt_digest,
        offline_capabilities=node.offline_capabilities,
    )


def write_deployment_manifest(destination: Path, manifest: DeploymentManifest) -> None:
    """Write a reviewed deployment manifest once with private permissions."""
    _write_private_json_exclusive(destination, manifest.model_dump(mode="json"))


def create_deployment_state(
    destination: Path,
    *,
    deployment: DeploymentManifest,
    topology: TopologyManifest,
    release_artifact: Path,
    database: Path | None,
    ownership_receipt: OwnershipTransitionReceipt | None,
    previous_state: DeploymentStateReceipt | None = None,
    transition: DeploymentTransition = DeploymentTransition.ACTIVATE,
    created_at: datetime | None = None,
) -> DeploymentStateReceipt:
    """Verify placement and write one exclusive root-owned activation/update receipt."""
    database_state = _verify_deployment_inputs(
        deployment=deployment,
        topology=topology,
        release_artifact=release_artifact,
        database=database,
        ownership_receipt=ownership_receipt,
        require_snapshot_match=(
            previous_state is None or transition is DeploymentTransition.ROLLBACK
        ),
    )
    if previous_state is None:
        if transition is not DeploymentTransition.ACTIVATE:
            raise DeploymentError(
                DeploymentErrorCode.STATE_CONFLICT, "first deployment transition must activate"
            )
        sequence = 1
        previous_digest = None
    else:
        if transition is DeploymentTransition.ACTIVATE:
            raise DeploymentError(
                DeploymentErrorCode.STATE_CONFLICT, "later deployment transition cannot activate"
            )
        _verify_previous_state(previous_state, deployment, ownership_receipt, transition)
        sequence = previous_state.sequence + 1
        previous_digest = previous_state.digest
    active_owner = topology.owner_for(OwnershipDomain.IDENTITY)
    receipt = DeploymentStateReceipt(
        operation_id=f"deployment-state:{uuid4()}",
        sequence=sequence,
        transition=transition,
        created_at=created_at or datetime.now(UTC),
        deployment_manifest_sha256=deployment.digest,
        previous_state_sha256=previous_digest,
        release_sha256=deployment.release_sha256,
        topology_profile=topology.profile,
        topology_epoch=topology.epoch,
        topology_digest=topology.digest,
        ownership_receipt_sha256=(
            ownership_receipt.digest if ownership_receipt is not None else None
        ),
        active_owner_node_id=active_owner,
        accepted_migration_state_sha256=(
            ownership_receipt.accepted_state_sha256 if ownership_receipt is not None else None
        ),
        verified_database_state_sha256=(
            database_state.content_sha256 if database_state is not None else None
        ),
        verified_database_schema_sha256=(
            database_state.schema_sha256 if database_state is not None else None
        ),
        verified_database_migrations=(
            database_state.migrations if database_state is not None else ()
        ),
    )
    _write_private_json_exclusive(destination, receipt.model_dump(mode="json"))
    return receipt


def verify_runtime_deployment(
    *,
    deployment: DeploymentManifest,
    expected_deployment_sha256: str,
    state: DeploymentStateReceipt | None,
    expected_state_sha256: str | None,
    topology: TopologyManifest,
    release_artifact: Path,
    database: Path | None,
    ownership_receipt: OwnershipTransitionReceipt | None,
) -> DeploymentActivation:
    """Fail closed before opening a remote-core listener or writable store."""
    if deployment.digest != expected_deployment_sha256:
        raise DeploymentError(
            DeploymentErrorCode.RELEASE_MISMATCH, "deployment manifest digest does not match"
        )
    database_state = _verify_deployment_inputs(
        deployment=deployment,
        topology=topology,
        release_artifact=release_artifact,
        database=database,
        ownership_receipt=ownership_receipt,
        require_snapshot_match=False,
    )
    requires_state = deployment.role is not DeploymentRole.LAPTOP_DEVICE
    if requires_state:
        if state is None or expected_state_sha256 is None or state.digest != expected_state_sha256:
            raise DeploymentError(
                DeploymentErrorCode.RECEIPT_MISMATCH, "deployment state receipt is unavailable"
            )
        if state.deployment_manifest_sha256 != deployment.digest:
            raise DeploymentError(
                DeploymentErrorCode.RECEIPT_MISMATCH, "deployment state does not bind manifest"
            )
        if (
            state.release_sha256 != deployment.release_sha256
            or state.topology_digest != topology.digest
            or state.topology_epoch != topology.epoch
            or state.topology_profile is not topology.profile
            or state.ownership_receipt_sha256 != deployment.ownership_receipt_sha256
            or state.active_owner_node_id != topology.owner_for(OwnershipDomain.IDENTITY)
        ):
            raise DeploymentError(
                DeploymentErrorCode.RECEIPT_MISMATCH, "deployment state binding does not match"
            )
        state_digest = state.digest
    else:
        if state is not None or expected_state_sha256 is not None:
            raise DeploymentError(
                DeploymentErrorCode.RECEIPT_MISMATCH, "device node cannot consume core state"
            )
        state_digest = None
    if (
        database_state is not None
        and state is not None
        and (
            state.verified_database_state_sha256 is None
            or state.verified_database_schema_sha256 != database_state.schema_sha256
            or state.verified_database_migrations != database_state.migrations
        )
    ):
        raise DeploymentError(
            DeploymentErrorCode.DATABASE_MISMATCH,
            "core database schema does not match deployment state",
        )
    return DeploymentActivation(
        role=deployment.role,
        node_id=deployment.node_id,
        release_sha256=deployment.release_sha256,
        topology_profile=topology.profile,
        topology_epoch=topology.epoch,
        topology_digest=topology.digest,
        deployment_manifest_sha256=deployment.digest,
        deployment_state_sha256=state_digest,
        active_owner_node_id=topology.owner_for(OwnershipDomain.IDENTITY),
        offline_capabilities=deployment.offline_capabilities,
    )


def decide_availability(
    activation: DeploymentActivation,
    *,
    capability: str,
    connected: bool,
    mutates_shared_state: bool = False,
    causes_device_effect: bool = False,
) -> OfflineDecision:
    """Return deterministic partition behavior without electing a new owner."""
    if activation.topology_profile is TopologyProfile.LOCAL_ONLY:
        return OfflineDecision(allowed=True, mode=AvailabilityMode.LOCAL, reason="local_owner")
    if connected:
        return OfflineDecision(allowed=True, mode=AvailabilityMode.REMOTE, reason="remote_owner")
    if activation.role is not DeploymentRole.LAPTOP_DEVICE:
        return OfflineDecision(
            allowed=False, mode=AvailabilityMode.DENIED, reason="core_unavailable"
        )
    if mutates_shared_state:
        return OfflineDecision(
            allowed=False, mode=AvailabilityMode.DENIED, reason="shared_write_denied"
        )
    if causes_device_effect:
        return OfflineDecision(allowed=False, mode=AvailabilityMode.DENIED, reason="effect_denied")
    if capability not in activation.offline_capabilities:
        return OfflineDecision(
            allowed=False, mode=AvailabilityMode.DENIED, reason="capability_unavailable"
        )
    return OfflineDecision(allowed=True, mode=AvailabilityMode.OFFLINE, reason="declared_offline")


def stage_release(
    source: Path,
    release_root: Path,
    *,
    expected_sha256: str,
) -> Path:
    """Copy one pinned artifact into an immutable no-overwrite release directory."""
    if not release_root.is_dir() or release_root.is_symlink():
        raise DeploymentError(DeploymentErrorCode.INVALID_INPUT, "release root is unavailable")
    actual = _safe_file_sha256(source)
    if actual != expected_sha256:
        raise DeploymentError(DeploymentErrorCode.RELEASE_MISMATCH, "release digest does not match")
    destination_dir = release_root / expected_sha256
    destination = destination_dir / source.name
    try:
        destination_dir.mkdir(mode=0o700, exist_ok=False)
        with source.open("rb") as input_file, _open_private_exclusive(destination) as output:
            shutil.copyfileobj(input_file, output, length=1_048_576)
            output.flush()
            os.fsync(output.fileno())
        if _safe_file_sha256(destination) != expected_sha256:
            raise DeploymentError(
                DeploymentErrorCode.RELEASE_MISMATCH, "staged release digest does not match"
            )
        return destination
    except FileExistsError as exc:
        raise DeploymentError(
            DeploymentErrorCode.DESTINATION_EXISTS, "release is already staged"
        ) from exc
    except BaseException:
        if destination.exists():
            destination.unlink(missing_ok=True)
        with suppress(OSError):
            destination_dir.rmdir()
        raise


def promote_release(
    state_path: Path,
    *,
    candidate_sha256: str,
    expected_current_sha256: str | None,
    probe: Callable[[str], bool],
    now: datetime | None = None,
) -> ReleaseState:
    """Atomically select a healthy pinned release; state stays unchanged on failed probe."""
    with _state_update_lock(state_path):
        current = load_release_state(state_path) if state_path.exists() else None
        actual_current = current.current_release_sha256 if current is not None else None
        if actual_current != expected_current_sha256:
            raise DeploymentError(DeploymentErrorCode.STATE_CONFLICT, "release state changed")
        if not probe(candidate_sha256):
            raise DeploymentError(DeploymentErrorCode.HEALTH_CHECK_FAILED, "candidate is not ready")
        next_state = ReleaseState(
            generation=1 if current is None else current.generation + 1,
            current_release_sha256=candidate_sha256,
            previous_release_sha256=actual_current,
            updated_at=now or datetime.now(UTC),
        )
        _write_private_json_atomic(state_path, next_state.model_dump(mode="json"))
        return next_state


def rollback_release(
    state_path: Path,
    *,
    expected_current_sha256: str,
    probe: Callable[[str], bool],
    now: datetime | None = None,
) -> ReleaseState:
    """Atomically select the last healthy release and retain the failed release as previous."""
    with _state_update_lock(state_path):
        current = load_release_state(state_path)
        if current.current_release_sha256 != expected_current_sha256:
            raise DeploymentError(DeploymentErrorCode.STATE_CONFLICT, "release state changed")
        candidate = current.previous_release_sha256
        if candidate is None:
            raise DeploymentError(DeploymentErrorCode.STATE_CONFLICT, "no rollback release exists")
        if not probe(candidate):
            raise DeploymentError(DeploymentErrorCode.HEALTH_CHECK_FAILED, "rollback is not ready")
        rolled_back = ReleaseState(
            generation=current.generation + 1,
            current_release_sha256=candidate,
            previous_release_sha256=current.current_release_sha256,
            updated_at=now or datetime.now(UTC),
        )
        _write_private_json_atomic(state_path, rolled_back.model_dump(mode="json"))
        return rolled_back


def load_deployment_manifest(path: Path) -> DeploymentManifest:
    return _load_document(path, DeploymentManifest)


def load_deployment_state(path: Path) -> DeploymentStateReceipt:
    return _load_document(path, DeploymentStateReceipt)


def load_release_state(path: Path) -> ReleaseState:
    return _load_document(path, ReleaseState)


def load_topology_manifest(path: Path) -> TopologyManifest:
    """Load a bounded, duplicate-free topology document from a regular file."""
    return _load_document(path, TopologyManifest)


def load_ownership_receipt(path: Path) -> OwnershipTransitionReceipt:
    """Load a bounded, duplicate-free ownership receipt from a regular file."""
    return _load_document(path, OwnershipTransitionReceipt)


def _verify_deployment_inputs(
    *,
    deployment: DeploymentManifest,
    topology: TopologyManifest,
    release_artifact: Path,
    database: Path | None,
    ownership_receipt: OwnershipTransitionReceipt | None,
    require_snapshot_match: bool,
) -> DatabaseState | None:
    if platform.python_version() != deployment.python_version:
        raise DeploymentError(
            DeploymentErrorCode.RELEASE_MISMATCH, "runtime Python version does not match"
        )
    if (
        topology.profile is not deployment.topology_profile
        or topology.epoch != deployment.topology_epoch
        or topology.digest != deployment.topology_digest
    ):
        raise DeploymentError(DeploymentErrorCode.TOPOLOGY_MISMATCH, "topology does not match")
    node = next((item for item in topology.nodes if item.id == deployment.node_id), None)
    if node is None or tuple(node.offline_capabilities) != deployment.offline_capabilities:
        raise DeploymentError(
            DeploymentErrorCode.TOPOLOGY_MISMATCH, "deployment node does not match"
        )
    if _safe_file_sha256(release_artifact) != deployment.release_sha256:
        raise DeploymentError(DeploymentErrorCode.RELEASE_MISMATCH, "release digest does not match")
    if release_artifact.name != deployment.package_name:
        raise DeploymentError(DeploymentErrorCode.RELEASE_MISMATCH, "release name does not match")
    capacity_path = database.parent if database is not None else release_artifact.parent
    try:
        free_bytes = shutil.disk_usage(capacity_path).free
    except OSError as exc:
        raise DeploymentError(
            DeploymentErrorCode.IO_FAILED, "deployment capacity cannot be verified"
        ) from exc
    if free_bytes < deployment.minimum_free_bytes:
        raise DeploymentError(DeploymentErrorCode.IO_FAILED, "deployment capacity is below minimum")
    _verify_ownership_receipt(deployment, topology, ownership_receipt)
    if deployment.database_path is None:
        if database is not None:
            raise DeploymentError(
                DeploymentErrorCode.DATABASE_MISMATCH, "device deployment cannot use database"
            )
        return None
    if database is None or str(database.resolve()) != str(Path(deployment.database_path).resolve()):
        raise DeploymentError(DeploymentErrorCode.DATABASE_MISMATCH, "database path does not match")
    try:
        state = analyze_database(database)
    except Exception as exc:
        raise DeploymentError(
            DeploymentErrorCode.DATABASE_MISMATCH, "database verification failed"
        ) from exc
    if ownership_receipt is not None and require_snapshot_match:
        if state.content_sha256 != ownership_receipt.accepted_state_sha256:
            raise DeploymentError(
                DeploymentErrorCode.DATABASE_MISMATCH, "accepted database state does not match"
            )
        expected_database_sha = ownership_receipt.target_database_sha256
        if state.database_sha256 != expected_database_sha:
            raise DeploymentError(
                DeploymentErrorCode.DATABASE_MISMATCH, "accepted database bytes do not match"
            )
    return state


def _verify_ownership_receipt(
    deployment: DeploymentManifest,
    topology: TopologyManifest,
    receipt: OwnershipTransitionReceipt | None,
) -> None:
    expected = deployment.ownership_receipt_sha256
    if expected is None:
        if receipt is not None:
            raise DeploymentError(
                DeploymentErrorCode.RECEIPT_MISMATCH, "unexpected ownership receipt"
            )
        return
    if receipt is None or receipt.digest != expected:
        raise DeploymentError(DeploymentErrorCode.RECEIPT_MISMATCH, "ownership receipt mismatch")
    required_transition = (
        OwnershipTransition.CUTOVER
        if deployment.role is DeploymentRole.SERVER_CORE
        else OwnershipTransition.ROLLBACK
    )
    active_owner = topology.owner_for(OwnershipDomain.IDENTITY)
    if (
        receipt.transition is not required_transition
        or receipt.topology_profile is not topology.profile
        or receipt.topology_epoch != topology.epoch
        or receipt.topology_digest != topology.digest
        or receipt.active_owner_node_id != active_owner
        or deployment.node_id != active_owner
    ):
        raise DeploymentError(
            DeploymentErrorCode.OWNERSHIP_MISMATCH, "ownership receipt does not authorize node"
        )


def _verify_previous_state(
    previous: DeploymentStateReceipt,
    deployment: DeploymentManifest,
    ownership_receipt: OwnershipTransitionReceipt | None,
    transition: DeploymentTransition,
) -> None:
    expected_ownership = ownership_receipt.digest if ownership_receipt is not None else None
    if transition is DeploymentTransition.UPDATE:
        valid = (
            previous.topology_profile is deployment.topology_profile
            and previous.topology_epoch == deployment.topology_epoch
            and previous.topology_digest == deployment.topology_digest
            and previous.ownership_receipt_sha256 == expected_ownership
        )
    else:
        valid = (
            ownership_receipt is not None
            and ownership_receipt.transition is OwnershipTransition.ROLLBACK
            and ownership_receipt.previous_receipt_sha256 == previous.ownership_receipt_sha256
            and ownership_receipt.from_owner_node_id == previous.active_owner_node_id
            and ownership_receipt.accepted_state_sha256 == previous.accepted_migration_state_sha256
            and previous.topology_epoch < deployment.topology_epoch
            and previous.topology_profile is not TopologyProfile.LOCAL_ONLY
            and deployment.topology_profile is TopologyProfile.LOCAL_ONLY
        )
    if not valid:
        raise DeploymentError(
            DeploymentErrorCode.STATE_CONFLICT, "previous deployment state does not match"
        )


def _load_document(path: Path, model: type[_DeploymentDocument]) -> _DeploymentDocument:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("unsafe path")
        payload = path.read_bytes()
        if not payload or len(payload) > MAX_DEPLOYMENT_DOCUMENT_BYTES:
            raise ValueError("document size is invalid")
        parsed = json.loads(payload, object_pairs_hook=_unique_object)
        return model.model_validate(parsed)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise DeploymentError(
            DeploymentErrorCode.DOCUMENT_INVALID, "deployment document is unavailable or invalid"
        ) from exc


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate document key")
        result[key] = value
    return result


def _safe_file_sha256(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("unsafe path")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1_048_576), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError as exc:
        raise DeploymentError(
            DeploymentErrorCode.INVALID_INPUT, "deployment file unavailable"
        ) from exc


def _write_private_json_exclusive(path: Path, value: object) -> None:
    payload = _canonical_json(value) + b"\n"
    try:
        with _open_private_exclusive(path) as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as exc:
        raise DeploymentError(
            DeploymentErrorCode.DESTINATION_EXISTS, "deployment destination exists"
        ) from exc
    except OSError as exc:
        path.unlink(missing_ok=True)
        raise DeploymentError(DeploymentErrorCode.IO_FAILED, "deployment write failed") from exc


def _write_private_json_atomic(path: Path, value: object) -> None:
    if not path.parent.is_dir() or path.parent.is_symlink() or path.is_symlink():
        raise DeploymentError(DeploymentErrorCode.INVALID_INPUT, "state path is unsafe")
    payload = _canonical_json(value) + b"\n"
    temporary: Path | None = None
    try:
        descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(raw)
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise DeploymentError(DeploymentErrorCode.IO_FAILED, "state update failed") from exc


@contextmanager
def _state_update_lock(state_path: Path) -> Iterator[None]:
    lock_path = state_path.with_name(f".{state_path.name}.lock")
    acquired = False
    try:
        with _open_private_exclusive(lock_path) as lock:
            acquired = True
            lock.flush()
            os.fsync(lock.fileno())
            yield
    except FileExistsError as exc:
        raise DeploymentError(
            DeploymentErrorCode.STATE_CONFLICT, "release state update is already active"
        ) from exc
    except OSError as exc:
        raise DeploymentError(DeploymentErrorCode.IO_FAILED, "release state lock failed") from exc
    finally:
        if acquired:
            lock_path.unlink(missing_ok=True)


def _open_private_exclusive(path: Path) -> BinaryIO:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags, 0o600)
    return os.fdopen(descriptor, "wb")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, min(len(values) - 1, int(len(values) * quantile + 0.999999) - 1))
    return round(values[index], 6)
