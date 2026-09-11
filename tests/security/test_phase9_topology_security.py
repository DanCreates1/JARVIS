from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from jarvis.remote import (
    OwnershipDomain,
    ProtocolHello,
    RemoteIdentityContext,
    RemoteScope,
    TopologyManifest,
    TopologyNegotiationError,
    TopologyNegotiator,
    TopologyProfile,
    build_local_only_manifest,
    build_remote_manifest,
)


def test_default_local_only_topology_has_no_remote_negotiable_peer() -> None:
    now = datetime.now(UTC)
    manifest = build_local_only_manifest(
        host_id="host:security",
        node_id="node:local-core",
        capabilities=("core.chat", "core.identity"),
    )
    negotiator = TopologyNegotiator(
        manifest,
        server_node_id="node:local-core",
        clock=lambda: now,
    )
    context = RemoteIdentityContext(
        host_id="host:security",
        device_id="device:hostile",
        session_id="session:hostile",
        key_version=1,
        audience="jarvis-api",
        scopes=frozenset({RemoteScope.TOPOLOGY_NEGOTIATE}),
        expires_at=now + timedelta(minutes=5),
    )
    hello = ProtocolHello(
        host_id=context.host_id,
        node_id=context.device_id,
        session_id=context.session_id,
        profile=manifest.profile,
        topology_epoch=manifest.epoch,
        topology_digest=manifest.digest,
        supported_versions=("1.0",),
        minimum_version="1.0",
        offered_capabilities=("core.chat",),
    )

    with pytest.raises(TopologyNegotiationError) as error:
        negotiator.negotiate(context=context, hello=hello)

    assert error.value.code == "node_not_allowed"


def test_protocol_rejects_caller_supplied_owner_or_role_claims() -> None:
    manifest = _manifest()
    payload = _hello_payload(manifest)

    with pytest.raises(ValidationError, match="Extra inputs"):
        ProtocolHello.model_validate({**payload, "owner_node_id": "device:laptop"})
    with pytest.raises(ValidationError, match="Extra inputs"):
        ProtocolHello.model_validate({**payload, "roles": ["core-primary"]})


def test_unknown_capability_is_denied_and_never_changes_owner_map() -> None:
    now = datetime.now(UTC)
    manifest = _manifest()
    negotiator = TopologyNegotiator(manifest, server_node_id="node:server", clock=lambda: now)
    context = RemoteIdentityContext(
        host_id="host:security",
        device_id="device:laptop",
        session_id="session:security",
        key_version=1,
        audience="jarvis-api",
        scopes=frozenset({RemoteScope.TOPOLOGY_NEGOTIATE}),
        expires_at=now + timedelta(minutes=5),
    )
    result = negotiator.negotiate(
        context=context,
        hello=ProtocolHello.model_validate(_hello_payload(manifest)),
    )

    assert result.granted_capabilities == ("node.voice",)
    assert result.denied_capabilities == ("admin.root", "core.identity")
    assert manifest.owner_for(OwnershipDomain.IDENTITY) == "node:server"
    assert "secret" not in result.model_dump_json().lower()


def _manifest() -> TopologyManifest:
    return build_remote_manifest(
        profile=TopologyProfile.SPLIT,
        host_id="host:security",
        server_node_id="node:server",
        laptop_node_id="device:laptop",
        server_capabilities=("core.chat", "core.identity"),
        laptop_capabilities=("node.voice",),
        laptop_offline_capabilities=("node.voice",),
    )


def _hello_payload(manifest: TopologyManifest) -> dict[str, object]:
    return {
        "host_id": "host:security",
        "node_id": "device:laptop",
        "session_id": "session:security",
        "profile": "split",
        "topology_epoch": manifest.epoch,
        "topology_digest": manifest.digest,
        "supported_versions": ("1.0",),
        "minimum_version": "1.0",
        "offered_capabilities": ("admin.root", "core.identity", "node.voice"),
        "required_capabilities": ("node.voice",),
    }
