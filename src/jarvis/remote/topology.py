"""Phase 9A topology ownership and authenticated capability negotiation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Never, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jarvis.remote.models import RemoteIdentityContext, RemoteScope
from jarvis.remote.signing import REQUEST_AUDIENCE

TOPOLOGY_PROTOCOL_VERSION: Final = "1.0"
_IDENTIFIER_PATTERN: Final = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$"
_CAPABILITY_PATTERN: Final = r"^[a-z][a-z0-9_.-]{0,127}$"
_VERSION_PATTERN: Final = r"^[1-9][0-9]{0,3}\.[0-9]{1,4}$"
_DIGEST_PATTERN: Final = r"^[0-9a-f]{64}$"
_MAX_NEGOTIATED_CAPABILITIES: Final = 64
_DEVICE_OWNED_DOMAINS: Final = frozenset(
    {
        "device-settings",
        "computer-effects",
        "media-capture",
    }
)


class TopologyProfile(StrEnum):
    LOCAL_ONLY = "local-only"
    SPLIT = "split"
    SERVER_PRIMARY = "server-primary"


class TopologyNodeRole(StrEnum):
    CORE_PRIMARY = "core-primary"
    GATEWAY = "gateway"
    DEVICE_NODE = "device-node"
    OFFLINE_CORE = "offline-core"


class OwnershipDomain(StrEnum):
    IDENTITY = "identity"
    SESSIONS_REPLAY = "sessions-replay"
    CONVERSATIONS = "conversations"
    MEMORY = "memory"
    RESEARCH = "research"
    TASKS = "tasks"
    PERMISSION_AUTHORITY = "permission-authority"
    AUDIT = "audit"
    DEVICE_SETTINGS = "device-settings"
    COMPUTER_EFFECTS = "computer-effects"
    MEDIA_CAPTURE = "media-capture"


class NetworkLossBehavior(StrEnum):
    KEEP_LOCAL_OWNER = "keep-local-owner"
    USE_DECLARED_OFFLINE_CAPABILITIES = "use-declared-offline-capabilities"
    FAIL_CLOSED = "fail-closed"


class TopologyNode(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=_IDENTIFIER_PATTERN)
    roles: tuple[TopologyNodeRole, ...] = Field(min_length=1, max_length=4)
    capabilities: tuple[str, ...] = Field(default=(), max_length=_MAX_NEGOTIATED_CAPABILITIES)
    offline_capabilities: tuple[str, ...] = Field(
        default=(), max_length=_MAX_NEGOTIATED_CAPABILITIES
    )

    @field_validator("roles")
    @classmethod
    def normalize_roles(cls, value: tuple[TopologyNodeRole, ...]) -> tuple[TopologyNodeRole, ...]:
        if len(value) != len(set(value)):
            raise ValueError("node roles must be unique")
        return tuple(sorted(value, key=str))

    @field_validator("capabilities", "offline_capabilities")
    @classmethod
    def normalize_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("node capabilities must be unique")
        for capability in value:
            if not _matches_capability(capability):
                raise ValueError("invalid topology capability")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def require_offline_subset(self) -> Self:
        if not set(self.offline_capabilities).issubset(self.capabilities):
            raise ValueError("offline capabilities must be a subset of node capabilities")
        if self.offline_capabilities and TopologyNodeRole.OFFLINE_CORE not in self.roles:
            raise ValueError("offline capabilities require the offline-core role")
        return self


class OwnershipAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    domain: OwnershipDomain
    owner_node_id: str = Field(pattern=_IDENTIFIER_PATTERN)


class TopologyManifest(BaseModel):
    """Static desired topology. It grants neither runtime authority nor migration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile: TopologyProfile
    host_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    epoch: int = Field(default=1, ge=1)
    nodes: tuple[TopologyNode, ...] = Field(min_length=1, max_length=16)
    ownership: tuple[OwnershipAssignment, ...] = Field(
        min_length=len(OwnershipDomain), max_length=len(OwnershipDomain)
    )
    network_loss_behavior: NetworkLossBehavior

    @field_validator("nodes")
    @classmethod
    def unique_nodes(cls, value: tuple[TopologyNode, ...]) -> tuple[TopologyNode, ...]:
        if len({node.id for node in value}) != len(value):
            raise ValueError("topology node IDs must be unique")
        return tuple(sorted(value, key=lambda node: node.id))

    @field_validator("ownership")
    @classmethod
    def normalize_ownership(
        cls, value: tuple[OwnershipAssignment, ...]
    ) -> tuple[OwnershipAssignment, ...]:
        domains = {item.domain for item in value}
        if len(domains) != len(value):
            raise ValueError("each ownership domain must have exactly one owner")
        if domains != set(OwnershipDomain):
            raise ValueError("ownership map must cover every domain exactly once")
        return tuple(sorted(value, key=lambda item: item.domain.value))

    @model_validator(mode="after")
    def validate_topology_shape(self) -> Self:
        node_by_id = {node.id: node for node in self.nodes}
        if any(item.owner_node_id not in node_by_id for item in self.ownership):
            raise ValueError("ownership refers to an unknown node")
        core_nodes = [node for node in self.nodes if TopologyNodeRole.CORE_PRIMARY in node.roles]
        if len(core_nodes) != 1:
            raise ValueError("topology must have exactly one primary core")
        if self.profile is TopologyProfile.LOCAL_ONLY:
            if len(self.nodes) != 1:
                raise ValueError("local-only topology must contain exactly one node")
            node = self.nodes[0]
            required_roles = {
                TopologyNodeRole.CORE_PRIMARY,
                TopologyNodeRole.GATEWAY,
                TopologyNodeRole.DEVICE_NODE,
                TopologyNodeRole.OFFLINE_CORE,
            }
            if set(node.roles) != required_roles:
                raise ValueError("local-only node must own all runtime roles")
            if any(item.owner_node_id != node.id for item in self.ownership):
                raise ValueError("local-only node must own every domain")
            if self.network_loss_behavior is not NetworkLossBehavior.KEEP_LOCAL_OWNER:
                raise ValueError("local-only topology must retain its local owner on network loss")
        else:
            device_nodes = [
                node for node in self.nodes if TopologyNodeRole.DEVICE_NODE in node.roles
            ]
            if len(self.nodes) < 2 or not device_nodes:
                raise ValueError("remote topology requires a primary core and a device node")
            if self.network_loss_behavior is NetworkLossBehavior.KEEP_LOCAL_OWNER:
                raise ValueError("remote topology must declare bounded fallback or fail closed")
            for item in self.ownership:
                owner = node_by_id[item.owner_node_id]
                if item.domain.value in _DEVICE_OWNED_DOMAINS:
                    if TopologyNodeRole.DEVICE_NODE not in owner.roles:
                        raise ValueError("device-local domains require a device-node owner")
                elif TopologyNodeRole.CORE_PRIMARY not in owner.roles:
                    raise ValueError("shared state domains require the primary-core owner")
        return self

    def owner_for(self, domain: OwnershipDomain) -> str:
        return next(item.owner_node_id for item in self.ownership if item.domain == domain)

    @property
    def digest(self) -> str:
        payload = self.model_dump(mode="json")
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class ProtocolHello(BaseModel):
    """Signed request body from an already-enrolled topology peer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    host_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    session_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    audience: str = Field(default=REQUEST_AUDIENCE, pattern=r"^jarvis-api$")
    profile: TopologyProfile
    topology_epoch: int = Field(ge=1)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    supported_versions: tuple[str, ...] = Field(min_length=1, max_length=8)
    minimum_version: str = Field(pattern=_VERSION_PATTERN)
    offered_capabilities: tuple[str, ...] = Field(
        default=(), max_length=_MAX_NEGOTIATED_CAPABILITIES
    )
    required_capabilities: tuple[str, ...] = Field(
        default=(), max_length=_MAX_NEGOTIATED_CAPABILITIES
    )

    @field_validator("supported_versions")
    @classmethod
    def normalize_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("supported protocol versions must be unique")
        if any(not _matches_version(version) for version in value):
            raise ValueError("invalid protocol version")
        return tuple(sorted(value, key=_version_key, reverse=True))

    @field_validator("offered_capabilities", "required_capabilities")
    @classmethod
    def normalize_hello_capabilities(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("protocol capabilities must be unique")
        if any(not _matches_capability(capability) for capability in value):
            raise ValueError("invalid protocol capability")
        return tuple(sorted(value))

    @model_validator(mode="after")
    def require_client_consistency(self) -> Self:
        if not set(self.required_capabilities).issubset(self.offered_capabilities):
            raise ValueError("required capabilities must also be offered")
        if not any(
            _version_key(version) >= _version_key(self.minimum_version)
            for version in self.supported_versions
        ):
            raise ValueError("minimum version exceeds every supported version")
        return self


class ProtocolNegotiation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    server_node_id: str = Field(pattern=_IDENTIFIER_PATTERN)
    profile: TopologyProfile
    topology_epoch: int = Field(ge=1)
    topology_digest: str = Field(pattern=_DIGEST_PATTERN)
    selected_version: str = Field(pattern=_VERSION_PATTERN)
    assigned_roles: tuple[TopologyNodeRole, ...]
    granted_capabilities: tuple[str, ...]
    denied_capabilities: tuple[str, ...]
    owned_domains: tuple[OwnershipDomain, ...]
    offline_capabilities: tuple[str, ...]
    network_loss_behavior: NetworkLossBehavior
    valid_until: datetime


class TopologyNegotiationError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__("topology protocol negotiation failed")
        self.code = code


class TopologyNegotiator:
    """Negotiate only what authenticated identity and static topology both allow."""

    def __init__(
        self,
        manifest: TopologyManifest,
        *,
        server_node_id: str,
        supported_versions: tuple[str, ...] = (TOPOLOGY_PROTOCOL_VERSION,),
        capability_registry: Iterable[str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.manifest = manifest
        self.server_node_id = server_node_id
        self._nodes = {node.id: node for node in manifest.nodes}
        server = self._nodes.get(server_node_id)
        if server is None or TopologyNodeRole.CORE_PRIMARY not in server.roles:
            raise ValueError("server node must be the manifest primary core")
        if not supported_versions or len(supported_versions) != len(set(supported_versions)):
            raise ValueError("supported protocol versions must be non-empty and unique")
        if any(not _matches_version(version) for version in supported_versions):
            raise ValueError("invalid supported protocol version")
        self._supported_versions = tuple(sorted(supported_versions, key=_version_key, reverse=True))
        registry = set(
            _all_manifest_capabilities(manifest)
            if capability_registry is None
            else capability_registry
        )
        if len(registry) > _MAX_NEGOTIATED_CAPABILITIES or any(
            not _matches_capability(capability) for capability in registry
        ):
            raise ValueError("invalid capability registry")
        self._capability_registry = frozenset(registry)
        self._clock = clock or (lambda: datetime.now(UTC))

    def negotiate(
        self, *, context: RemoteIdentityContext, hello: ProtocolHello
    ) -> ProtocolNegotiation:
        now = self._now()
        if RemoteScope.TOPOLOGY_NEGOTIATE not in context.scopes:
            self._deny("scope_denied")
        if context.audience != REQUEST_AUDIENCE or hello.audience != context.audience:
            self._deny("audience_mismatch")
        if hello.host_id != context.host_id or hello.host_id != self.manifest.host_id:
            self._deny("host_mismatch")
        if hello.node_id != context.device_id:
            self._deny("device_mismatch")
        if hello.session_id != context.session_id:
            self._deny("session_mismatch")
        if context.expires_at is None or context.expires_at <= now:
            self._deny("session_expired")
        if hello.profile is not self.manifest.profile:
            self._deny("topology_profile_mismatch")
        if hello.topology_epoch != self.manifest.epoch:
            self._deny("topology_epoch_mismatch")
        if hello.topology_digest != self.manifest.digest:
            self._deny("topology_digest_mismatch")
        node = self._nodes.get(hello.node_id)
        if node is None or hello.node_id == self.server_node_id:
            self._deny("node_not_allowed")

        selected_version = self._select_version(hello)
        allowed = set(node.capabilities).intersection(self._capability_registry)
        granted = tuple(sorted(set(hello.offered_capabilities).intersection(allowed)))
        denied = tuple(sorted(set(hello.offered_capabilities).difference(granted)))
        if not set(hello.required_capabilities).issubset(granted):
            self._deny("required_capability_unavailable")
        owned_domains = tuple(
            sorted(
                (item.domain for item in self.manifest.ownership if item.owner_node_id == node.id),
                key=str,
            )
        )
        valid_until = context.expires_at
        return ProtocolNegotiation(
            node_id=node.id,
            server_node_id=self.server_node_id,
            profile=self.manifest.profile,
            topology_epoch=self.manifest.epoch,
            topology_digest=self.manifest.digest,
            selected_version=selected_version,
            assigned_roles=node.roles,
            granted_capabilities=granted,
            denied_capabilities=denied,
            owned_domains=owned_domains,
            offline_capabilities=node.offline_capabilities,
            network_loss_behavior=self.manifest.network_loss_behavior,
            valid_until=valid_until,
        )

    def offline_fallback(self, node_id: str) -> tuple[str, ...]:
        node = self._nodes.get(node_id)
        if node is None:
            self._deny("node_not_allowed")
        if self.manifest.network_loss_behavior is NetworkLossBehavior.FAIL_CLOSED:
            return ()
        return node.offline_capabilities

    def _select_version(self, hello: ProtocolHello) -> str:
        minimum = _version_key(hello.minimum_version)
        client_versions = set(hello.supported_versions)
        for version in self._supported_versions:
            if version in client_versions and _version_key(version) >= minimum:
                return version
        self._deny("protocol_version_mismatch")

    @staticmethod
    def _deny(code: str) -> Never:
        raise TopologyNegotiationError(code)

    def _now(self) -> datetime:
        value = self._clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise RuntimeError("topology clock returned a naive datetime")
        return value.astimezone(UTC)


def build_local_only_manifest(
    *, host_id: str, node_id: str, capabilities: tuple[str, ...], epoch: int = 1
) -> TopologyManifest:
    node = TopologyNode(
        id=node_id,
        roles=tuple(TopologyNodeRole),
        capabilities=capabilities,
        offline_capabilities=capabilities,
    )
    return TopologyManifest(
        profile=TopologyProfile.LOCAL_ONLY,
        host_id=host_id,
        epoch=epoch,
        nodes=(node,),
        ownership=tuple(
            OwnershipAssignment(domain=domain, owner_node_id=node_id) for domain in OwnershipDomain
        ),
        network_loss_behavior=NetworkLossBehavior.KEEP_LOCAL_OWNER,
    )


def build_remote_manifest(
    *,
    profile: TopologyProfile,
    host_id: str,
    server_node_id: str,
    laptop_node_id: str,
    server_capabilities: tuple[str, ...],
    laptop_capabilities: tuple[str, ...],
    laptop_offline_capabilities: tuple[str, ...] = (),
    epoch: int = 1,
) -> TopologyManifest:
    if profile is TopologyProfile.LOCAL_ONLY:
        raise ValueError("remote manifest requires split or server-primary profile")
    laptop_roles = [TopologyNodeRole.DEVICE_NODE]
    if laptop_offline_capabilities:
        laptop_roles.append(TopologyNodeRole.OFFLINE_CORE)
    server = TopologyNode(
        id=server_node_id,
        roles=(TopologyNodeRole.CORE_PRIMARY, TopologyNodeRole.GATEWAY),
        capabilities=server_capabilities,
    )
    laptop = TopologyNode(
        id=laptop_node_id,
        roles=tuple(laptop_roles),
        capabilities=laptop_capabilities,
        offline_capabilities=laptop_offline_capabilities,
    )
    laptop_domains = {
        OwnershipDomain.DEVICE_SETTINGS,
        OwnershipDomain.COMPUTER_EFFECTS,
        OwnershipDomain.MEDIA_CAPTURE,
    }
    return TopologyManifest(
        profile=profile,
        host_id=host_id,
        epoch=epoch,
        nodes=(server, laptop),
        ownership=tuple(
            OwnershipAssignment(
                domain=domain,
                owner_node_id=laptop_node_id if domain in laptop_domains else server_node_id,
            )
            for domain in OwnershipDomain
        ),
        network_loss_behavior=(
            NetworkLossBehavior.USE_DECLARED_OFFLINE_CAPABILITIES
            if laptop_offline_capabilities
            else NetworkLossBehavior.FAIL_CLOSED
        ),
    )


def _all_manifest_capabilities(manifest: TopologyManifest) -> set[str]:
    return {capability for node in manifest.nodes for capability in node.capabilities}


def _matches_capability(value: str) -> bool:
    return re.fullmatch(_CAPABILITY_PATTERN, value) is not None


def _matches_version(value: str) -> bool:
    return re.fullmatch(_VERSION_PATTERN, value) is not None


def _version_key(value: str) -> tuple[int, int]:
    major, minor = value.split(".", maxsplit=1)
    return int(major), int(minor)
