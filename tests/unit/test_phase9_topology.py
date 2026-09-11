from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jarvis.remote import (
    NetworkLossBehavior,
    OwnershipAssignment,
    OwnershipDomain,
    ProtocolHello,
    RemoteIdentityContext,
    RemoteScope,
    TopologyManifest,
    TopologyNegotiationError,
    TopologyNegotiator,
    TopologyNode,
    TopologyNodeRole,
    TopologyProfile,
    build_local_only_manifest,
    build_remote_manifest,
)

NOW = datetime(2026, 9, 10, 20, 0, tzinfo=UTC)
HOST_ID = "host:test"
SERVER_ID = "node:server"
LAPTOP_ID = "device:laptop"
SERVER_CAPABILITIES = (
    "core.chat",
    "core.identity",
    "core.memory",
    "core.tasks",
    "transport.events",
)
LAPTOP_CAPABILITIES = (
    "node.computer",
    "node.vision",
    "node.voice",
    "transport.events",
)


def _split_manifest() -> TopologyManifest:
    return build_remote_manifest(
        profile=TopologyProfile.SPLIT,
        host_id=HOST_ID,
        server_node_id=SERVER_ID,
        laptop_node_id=LAPTOP_ID,
        server_capabilities=SERVER_CAPABILITIES,
        laptop_capabilities=LAPTOP_CAPABILITIES,
        laptop_offline_capabilities=("node.voice",),
        epoch=7,
    )


def _context(**changes: object) -> RemoteIdentityContext:
    values: dict[str, object] = {
        "host_id": HOST_ID,
        "device_id": LAPTOP_ID,
        "session_id": "session:test",
        "key_version": 1,
        "audience": "jarvis-api",
        "scopes": frozenset({RemoteScope.TOPOLOGY_NEGOTIATE}),
        "expires_at": NOW + timedelta(minutes=10),
    }
    values.update(changes)
    return RemoteIdentityContext.model_validate(values)


def _hello(manifest: TopologyManifest, **changes: object) -> ProtocolHello:
    values: dict[str, object] = {
        "host_id": HOST_ID,
        "node_id": LAPTOP_ID,
        "session_id": "session:test",
        "profile": manifest.profile,
        "topology_epoch": manifest.epoch,
        "topology_digest": manifest.digest,
        "supported_versions": ("1.0",),
        "minimum_version": "1.0",
        "offered_capabilities": (*LAPTOP_CAPABILITIES, "node.unapproved"),
        "required_capabilities": ("node.voice",),
    }
    values.update(changes)
    return ProtocolHello.model_validate(values)


def test_local_only_manifest_assigns_every_domain_to_one_node() -> None:
    manifest = build_local_only_manifest(
        host_id=HOST_ID,
        node_id="node:local",
        capabilities=("core.chat", "node.voice"),
        epoch=3,
    )

    assert manifest.profile is TopologyProfile.LOCAL_ONLY
    assert manifest.epoch == 3
    assert set(item.domain for item in manifest.ownership) == set(OwnershipDomain)
    assert {item.owner_node_id for item in manifest.ownership} == {"node:local"}
    assert manifest.network_loss_behavior is NetworkLossBehavior.KEEP_LOCAL_OWNER
    assert (
        manifest.digest == TopologyManifest.model_validate(manifest.model_dump(mode="json")).digest
    )


def test_split_manifest_assigns_shared_state_to_server_and_effects_to_laptop() -> None:
    manifest = _split_manifest()

    assert manifest.owner_for(OwnershipDomain.IDENTITY) == SERVER_ID
    assert manifest.owner_for(OwnershipDomain.CONVERSATIONS) == SERVER_ID
    assert manifest.owner_for(OwnershipDomain.COMPUTER_EFFECTS) == LAPTOP_ID
    assert manifest.owner_for(OwnershipDomain.MEDIA_CAPTURE) == LAPTOP_ID
    assert manifest.network_loss_behavior is NetworkLossBehavior.USE_DECLARED_OFFLINE_CAPABILITIES


def test_server_primary_without_offline_core_fails_closed_on_network_loss() -> None:
    manifest = build_remote_manifest(
        profile=TopologyProfile.SERVER_PRIMARY,
        host_id=HOST_ID,
        server_node_id=SERVER_ID,
        laptop_node_id=LAPTOP_ID,
        server_capabilities=SERVER_CAPABILITIES,
        laptop_capabilities=LAPTOP_CAPABILITIES,
    )
    negotiator = TopologyNegotiator(manifest, server_node_id=SERVER_ID, clock=lambda: NOW)

    assert manifest.network_loss_behavior is NetworkLossBehavior.FAIL_CLOSED
    assert negotiator.offline_fallback(LAPTOP_ID) == ()


def test_manifest_rejects_duplicate_or_unknown_ownership() -> None:
    local = build_local_only_manifest(
        host_id=HOST_ID,
        node_id="node:local",
        capabilities=("core.chat",),
    )
    duplicated = list(local.ownership)
    duplicated[-1] = duplicated[0]
    with pytest.raises(ValidationError, match="exactly one owner"):
        TopologyManifest.model_validate({**local.model_dump(mode="json"), "ownership": duplicated})

    unknown = list(local.ownership)
    unknown[0] = OwnershipAssignment(
        domain=unknown[0].domain,
        owner_node_id="node:unknown",
    )
    with pytest.raises(ValidationError, match="unknown node"):
        TopologyManifest.model_validate({**local.model_dump(mode="json"), "ownership": unknown})


def test_manifest_rejects_offline_capability_without_offline_role() -> None:
    with pytest.raises(ValidationError, match="offline-core"):
        TopologyNode(
            id=LAPTOP_ID,
            roles=(TopologyNodeRole.DEVICE_NODE,),
            capabilities=("node.voice",),
            offline_capabilities=("node.voice",),
        )


def test_remote_manifest_rejects_shared_state_owned_by_device_node() -> None:
    manifest = _split_manifest()
    ownership = [
        (
            OwnershipAssignment(domain=item.domain, owner_node_id=LAPTOP_ID)
            if item.domain is OwnershipDomain.IDENTITY
            else item
        )
        for item in manifest.ownership
    ]

    with pytest.raises(ValidationError, match="shared state domains"):
        TopologyManifest.model_validate(
            {**manifest.model_dump(mode="json"), "ownership": ownership}
        )


def test_negotiation_selects_highest_non_downgraded_version_and_intersects_capabilities() -> None:
    manifest = _split_manifest()
    negotiator = TopologyNegotiator(
        manifest,
        server_node_id=SERVER_ID,
        supported_versions=("1.0", "1.1"),
        clock=lambda: NOW,
    )
    hello = _hello(
        manifest,
        supported_versions=("1.0", "1.1"),
        minimum_version="1.0",
    )

    result = negotiator.negotiate(context=_context(), hello=hello)

    assert result.selected_version == "1.1"
    assert result.granted_capabilities == LAPTOP_CAPABILITIES
    assert result.denied_capabilities == ("node.unapproved",)
    assert result.offline_capabilities == ("node.voice",)
    assert set(result.owned_domains) == {
        OwnershipDomain.DEVICE_SETTINGS,
        OwnershipDomain.COMPUTER_EFFECTS,
        OwnershipDomain.MEDIA_CAPTURE,
    }
    assert result.valid_until == NOW + timedelta(minutes=10)


@pytest.mark.parametrize(
    ("hello_changes", "context_changes", "code"),
    [
        ({"host_id": "host:other"}, {}, "host_mismatch"),
        ({"node_id": "device:other"}, {}, "device_mismatch"),
        ({"session_id": "session:other"}, {}, "session_mismatch"),
        ({"topology_epoch": 8}, {}, "topology_epoch_mismatch"),
        ({"topology_digest": "0" * 64}, {}, "topology_digest_mismatch"),
        ({"profile": TopologyProfile.SERVER_PRIMARY}, {}, "topology_profile_mismatch"),
        ({}, {"expires_at": NOW}, "session_expired"),
        ({}, {"scopes": frozenset()}, "scope_denied"),
    ],
)
def test_negotiation_rejects_identity_and_topology_mismatch(
    hello_changes: dict[str, object],
    context_changes: dict[str, object],
    code: str,
) -> None:
    manifest = _split_manifest()
    negotiator = TopologyNegotiator(manifest, server_node_id=SERVER_ID, clock=lambda: NOW)

    with pytest.raises(TopologyNegotiationError) as error:
        negotiator.negotiate(
            context=_context(**context_changes),
            hello=_hello(manifest, **hello_changes),
        )

    assert error.value.code == code


def test_negotiation_rejects_version_downgrade_and_required_capability_escalation() -> None:
    manifest = _split_manifest()
    negotiator = TopologyNegotiator(manifest, server_node_id=SERVER_ID, clock=lambda: NOW)

    with pytest.raises(TopologyNegotiationError) as version_error:
        negotiator.negotiate(
            context=_context(),
            hello=_hello(
                manifest,
                supported_versions=("1.0", "1.1"),
                minimum_version="1.1",
            ),
        )
    assert version_error.value.code == "protocol_version_mismatch"

    with pytest.raises(TopologyNegotiationError) as capability_error:
        negotiator.negotiate(
            context=_context(),
            hello=_hello(
                manifest,
                required_capabilities=("node.unapproved",),
            ),
        )
    assert capability_error.value.code == "required_capability_unavailable"


def test_protocol_hello_rejects_duplicate_and_incoherent_claims() -> None:
    manifest = _split_manifest()
    with pytest.raises(ValidationError, match="versions must be unique"):
        _hello(manifest, supported_versions=("1.0", "1.0"))
    with pytest.raises(ValidationError, match="must also be offered"):
        _hello(manifest, required_capabilities=("core.chat",))
    with pytest.raises(ValidationError, match="minimum version exceeds"):
        _hello(manifest, supported_versions=("1.0",), minimum_version="1.1")


def test_unknown_node_has_no_offline_fallback() -> None:
    negotiator = TopologyNegotiator(_split_manifest(), server_node_id=SERVER_ID, clock=lambda: NOW)

    with pytest.raises(TopologyNegotiationError) as error:
        negotiator.offline_fallback("device:unknown")

    assert error.value.code == "node_not_allowed"


def test_explicit_empty_server_registry_grants_nothing() -> None:
    manifest = _split_manifest()
    negotiator = TopologyNegotiator(
        manifest,
        server_node_id=SERVER_ID,
        capability_registry=(),
        clock=lambda: NOW,
    )

    with pytest.raises(TopologyNegotiationError) as error:
        negotiator.negotiate(context=_context(), hello=_hello(manifest))

    assert error.value.code == "required_capability_unavailable"
