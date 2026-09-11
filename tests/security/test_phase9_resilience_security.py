from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.remote import (
    DeploymentError,
    DeploymentErrorCode,
    DeploymentHealthMonitor,
    HealthReason,
    ServiceHardening,
    load_deployment_manifest,
    load_topology_manifest,
    stage_release,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_service_identity_and_public_bind_cannot_be_relaxed() -> None:
    with pytest.raises(ValidationError, match="non-root"):
        ServiceHardening(run_as_user="root")
    with pytest.raises(ValidationError):
        ServiceHardening(bind_host="0.0.0.0")
    with pytest.raises(ValidationError, match="cannot be relaxed"):
        ServiceHardening(capability_bounding_set=("CAP_SYS_ADMIN",))


def test_oversized_deployment_document_fails_closed(tmp_path: Path) -> None:
    document = tmp_path / "deployment.json"
    document.write_bytes(b"{" + b" " * 1_048_576)
    with pytest.raises(DeploymentError) as caught:
        load_deployment_manifest(document)
    assert caught.value.code is DeploymentErrorCode.DOCUMENT_INVALID


def test_duplicate_topology_keys_fail_closed(tmp_path: Path) -> None:
    document = tmp_path / "topology.json"
    document.write_text('{"profile":"split","profile":"local-only"}', encoding="utf-8")
    with pytest.raises(DeploymentError) as caught:
        load_topology_manifest(document)
    assert caught.value.code is DeploymentErrorCode.DOCUMENT_INVALID


def test_symlinked_control_document_and_release_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_text("{}", encoding="utf-8")
    link = tmp_path / "link.json"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(DeploymentError) as document_error:
        load_deployment_manifest(link)
    assert document_error.value.code is DeploymentErrorCode.DOCUMENT_INVALID

    releases = tmp_path / "releases"
    releases.mkdir()
    with pytest.raises(DeploymentError) as release_error:
        stage_release(link, releases, expected_sha256="0" * 64)
    assert release_error.value.code is DeploymentErrorCode.INVALID_INPUT


def test_invalid_pinned_topology_fails_before_database_creation(tmp_path: Path) -> None:
    topology = tmp_path / "topology.json"
    topology.write_text("not-json", encoding="utf-8")
    digest = "a" * 64
    settings = Settings(
        data_dir=tmp_path / "data",
        topology_profile="split",
        topology_node_id="node:server",
        topology_epoch=2,
        deployment_enforced=True,
        deployment_role="server-core",
        topology_manifest_path=topology,
        deployment_manifest_path=tmp_path / "deployment.json",
        deployment_manifest_sha256=digest,
        deployment_state_path=tmp_path / "state.json",
        deployment_state_sha256=digest,
        ownership_receipt_path=tmp_path / "cutover.json",
        release_artifact_path=tmp_path / "release.whl",
        _env_file=None,
    )
    with pytest.raises(DeploymentError) as caught:
        asyncio.run(build_runtime(settings))
    assert caught.value.code is DeploymentErrorCode.DOCUMENT_INVALID
    assert not settings.database_path.exists()


def test_health_telemetry_schema_cannot_accept_private_labels() -> None:
    monitor = DeploymentHealthMonitor(max_events=16)
    snapshot = monitor.observe(HealthReason.READY, healthy=True, latency_ms=1)
    rendered = snapshot.model_dump_json()
    assert set(snapshot.model_dump()) == {
        "live",
        "ready",
        "reason",
        "samples",
        "p50_ms",
        "p95_ms",
        "counters",
    }
    assert "private-user-prompt-marker" not in rendered


def test_checked_in_service_is_non_root_bounded_loopback_and_private_only() -> None:
    core = (REPOSITORY_ROOT / "deploy/phase9c/jarvis-core.service").read_text(encoding="utf-8")
    gateway = (REPOSITORY_ROOT / "deploy/phase9c/jarvis-tailscale-serve.service").read_text(
        encoding="utf-8"
    )
    for directive in (
        "User=jarvis",
        "Group=jarvis",
        "NoNewPrivileges=yes",
        "CapabilityBoundingSet=",
        "PrivateDevices=yes",
        "ProtectSystem=strict",
        "TasksMax=256",
        "MemoryMax=2G",
        "CPUQuota=200%",
    ):
        assert directive in core
    assert "http://127.0.0.1:8765" in gateway
    assert "tailscale serve" in gateway
    assert "funnel" not in gateway.casefold()
    assert "serve reset" not in gateway
    assert "http://127.0.0.1:8765 off" in gateway
    assert "0.0.0.0" not in core + gateway
    assert "DynamicUser=yes" not in core
