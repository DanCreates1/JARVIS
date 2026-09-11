import asyncio
import hashlib
import json
import shutil
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import jarvis.remote.resilience as resilience_module
from jarvis.bootstrap import build_runtime
from jarvis.config import Settings
from jarvis.core.models import Message, MessageRole
from jarvis.memory import SQLiteConversationStore, local_memory_host_id
from jarvis.remote.migration import (
    analyze_database,
    create_cutover_receipt,
    create_rollback_receipt,
)
from jarvis.remote.resilience import (
    AvailabilityMode,
    DeploymentError,
    DeploymentErrorCode,
    DeploymentHealthMonitor,
    DeploymentManifest,
    DeploymentRole,
    DeploymentStateReceipt,
    DeploymentTransition,
    HealthReason,
    ServiceHardening,
    build_deployment_manifest,
    create_deployment_state,
    decide_availability,
    load_deployment_manifest,
    load_deployment_state,
    promote_release,
    rollback_release,
    stage_release,
    verify_runtime_deployment,
    write_deployment_manifest,
)
from jarvis.remote.topology import build_local_only_manifest, build_remote_manifest


def _database(path: Path) -> Path:
    async def initialize() -> None:
        store = SQLiteConversationStore(path)
        await store.initialize()
        await store.close()

    asyncio.run(initialize())
    return path


def _artifact(path: Path, content: bytes = b"pinned-wheel") -> Path:
    path.write_bytes(content)
    return path


def _remote_fixture(tmp_path: Path):  # type: ignore[no-untyped-def]
    topology = build_remote_manifest(
        profile="split",
        host_id=local_memory_host_id(),
        server_node_id="node:server",
        laptop_node_id="node:laptop",
        server_capabilities=("core.chat", "core.identity", "transport.events"),
        laptop_capabilities=("node.computer", "node.voice", "transport.events"),
        laptop_offline_capabilities=("node.voice",),
        epoch=2,
    )
    source = _database(tmp_path / "source.db")
    target = tmp_path / "target.db"
    shutil.copyfile(source, target)
    accepted = analyze_database(source).content_sha256
    receipt_path = tmp_path / "cutover.json"
    receipt = create_cutover_receipt(
        source,
        target,
        receipt_path,
        topology=topology,
        source_owner_node_id="node:laptop",
        accepted_state_sha256=accepted,
    )
    artifact = _artifact(tmp_path / "jarvis_assistant-0.1.0-py3-none-any.whl")
    deployment = build_deployment_manifest(
        topology=topology,
        role=DeploymentRole.SERVER_CORE,
        node_id="node:server",
        release_artifact=artifact,
        python_version="3.11.9",
        database_path=target,
        ownership_receipt=receipt,
    )
    return topology, source, target, receipt, artifact, deployment


def test_service_hardening_cannot_be_relaxed() -> None:
    secure = ServiceHardening()
    assert secure.replica_count == 1
    assert secure.bind_host == "127.0.0.1"
    assert secure.capability_bounding_set == ()

    for field, value in (
        ("root_filesystem_read_only", False),
        ("no_new_privileges", False),
        ("private_devices", False),
        ("capability_bounding_set", ("CAP_SYS_ADMIN",)),
    ):
        with pytest.raises(ValidationError, match="cannot be relaxed"):
            ServiceHardening(**{field: value})


def test_deployment_document_role_and_chain_shapes_fail_closed(tmp_path: Path) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    manifest = deployment.model_dump(mode="python")
    manifest_cases = (
        {"created_at": datetime.now(UTC).replace(tzinfo=None)},
        {"database_path": "relative.db"},
        {"offline_capabilities": ("node.voice", "node.voice")},
        {"offline_capabilities": ("INVALID",)},
        {"database_path": None},
        {"role": DeploymentRole.LOCAL_CORE},
        {
            "role": DeploymentRole.LOCAL_CORE,
            "topology_profile": "local-only",
            "topology_epoch": 1,
        },
        {
            "role": DeploymentRole.LOCAL_CORE,
            "topology_profile": "local-only",
            "topology_epoch": 3,
            "ownership_receipt_sha256": None,
        },
        {
            "role": DeploymentRole.LAPTOP_DEVICE,
            "topology_profile": "local-only",
            "database_path": None,
            "ownership_receipt_sha256": None,
        },
        {"ownership_receipt_sha256": None},
        {"role": DeploymentRole.LAPTOP_DEVICE, "database_path": None},
    )
    for changes in manifest_cases:
        with pytest.raises(ValidationError):
            DeploymentManifest.model_validate({**manifest, **changes})

    state = create_deployment_state(
        tmp_path / "state.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    ).model_dump(mode="python")
    state_cases = (
        {"created_at": datetime.now(UTC).replace(tzinfo=None)},
        {"transition": DeploymentTransition.UPDATE},
        {"previous_state_sha256": "a" * 64},
        {"sequence": 2},
    )
    for changes in state_cases:
        with pytest.raises(ValidationError):
            DeploymentStateReceipt.model_validate({**state, **changes})


def test_server_core_activation_binds_release_topology_receipt_and_database(tmp_path: Path) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    state_path = tmp_path / "deployment-state.json"
    state = create_deployment_state(
        state_path,
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    loaded = load_deployment_state(state_path)

    activation = verify_runtime_deployment(
        deployment=deployment,
        expected_deployment_sha256=deployment.digest,
        state=loaded,
        expected_state_sha256=state.digest,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )

    assert activation.role is DeploymentRole.SERVER_CORE
    assert activation.active_owner_node_id == "node:server"
    assert activation.deployment_state_sha256 == state.digest
    assert state.accepted_migration_state_sha256 == analyze_database(target).content_sha256


def test_composition_root_activates_only_complete_pinned_server_state(tmp_path: Path) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    topology_path = tmp_path / "topology.json"
    topology_path.write_text(topology.model_dump_json(indent=2), encoding="utf-8")
    deployment_path = tmp_path / "deployment.json"
    write_deployment_manifest(deployment_path, deployment)
    state_path = tmp_path / "deployment-state.json"
    state = create_deployment_state(
        state_path,
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    settings = Settings(
        data_dir=target.parent,
        database_filename=target.name,
        topology_profile="split",
        topology_node_id="node:server",
        topology_epoch=2,
        deployment_enforced=True,
        deployment_role="server-core",
        topology_manifest_path=topology_path,
        deployment_manifest_path=deployment_path,
        deployment_manifest_sha256=deployment.digest,
        deployment_state_path=state_path,
        deployment_state_sha256=state.digest,
        ownership_receipt_path=tmp_path / "cutover.json",
        release_artifact_path=artifact,
        _env_file=None,
    )

    async def run() -> None:
        runtime = await build_runtime(settings)
        try:
            assert runtime.deployment is not None
            assert runtime.deployment.role is DeploymentRole.SERVER_CORE
            assert runtime.deployment_health is not None
            assert runtime.deployment_health.snapshot().ready
        finally:
            await runtime.close()

    asyncio.run(run())


def test_runtime_restart_allows_authorized_database_growth(tmp_path: Path) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    state = create_deployment_state(
        tmp_path / "state.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )

    async def add_state() -> None:
        store = SQLiteConversationStore(target)
        await store.initialize()
        conversation = await store.create_conversation(metadata={"title": "post-cutover"})
        await store.append_message(
            Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content="private growth",
            )
        )
        await store.close()

    asyncio.run(add_state())
    activation = verify_runtime_deployment(
        deployment=deployment,
        expected_deployment_sha256=deployment.digest,
        state=state,
        expected_state_sha256=state.digest,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    assert activation.active_owner_node_id == "node:server"


def test_runtime_restart_skips_unused_content_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    state = create_deployment_state(
        tmp_path / "state.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )

    def reject_full_fingerprint(_path: Path) -> None:
        raise AssertionError("runtime restart must not fingerprint unused logical content")

    monkeypatch.setattr(resilience_module, "analyze_database", reject_full_fingerprint)
    activation = verify_runtime_deployment(
        deployment=deployment,
        expected_deployment_sha256=deployment.digest,
        state=state,
        expected_state_sha256=state.digest,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    assert activation.active_owner_node_id == "node:server"


def test_runtime_restart_rejects_schema_drift_after_activation(tmp_path: Path) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    state = create_deployment_state(
        tmp_path / "state.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    connection = sqlite3.connect(target)
    try:
        connection.execute("CREATE TABLE unreviewed_schema (value TEXT)")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(DeploymentError) as caught:
        verify_runtime_deployment(
            deployment=deployment,
            expected_deployment_sha256=deployment.digest,
            state=state,
            expected_state_sha256=state.digest,
            topology=topology,
            release_artifact=artifact,
            database=target,
            ownership_receipt=receipt,
        )
    assert caught.value.code is DeploymentErrorCode.DATABASE_MISMATCH


@pytest.mark.parametrize("failure", ["release", "manifest", "state", "database", "receipt"])
def test_activation_rejects_tamper_and_mismatch(tmp_path: Path, failure: str) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    state = create_deployment_state(
        tmp_path / "state.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    expected_deployment = deployment.digest
    expected_state = state.digest
    supplied_receipt = receipt
    if failure == "release":
        artifact.write_bytes(b"changed")
        expected_code = DeploymentErrorCode.RELEASE_MISMATCH
    elif failure == "manifest":
        expected_deployment = "0" * 64
        expected_code = DeploymentErrorCode.RELEASE_MISMATCH
    elif failure == "state":
        expected_state = "0" * 64
        expected_code = DeploymentErrorCode.RECEIPT_MISMATCH
    elif failure == "database":
        target.write_bytes(b"not sqlite")
        expected_code = DeploymentErrorCode.DATABASE_MISMATCH
    else:
        supplied_receipt = receipt.model_copy(update={"active_owner_node_id": "node:laptop"})
        expected_code = DeploymentErrorCode.RECEIPT_MISMATCH

    with pytest.raises(DeploymentError) as caught:
        verify_runtime_deployment(
            deployment=deployment,
            expected_deployment_sha256=expected_deployment,
            state=state,
            expected_state_sha256=expected_state,
            topology=topology,
            release_artifact=artifact,
            database=target,
            ownership_receipt=supplied_receipt,
        )
    assert caught.value.code is expected_code


def test_low_disk_capacity_blocks_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    state = create_deployment_state(
        tmp_path / "state.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    monkeypatch.setattr(shutil, "disk_usage", lambda _path: SimpleNamespace(free=0))
    with pytest.raises(DeploymentError) as caught:
        verify_runtime_deployment(
            deployment=deployment,
            expected_deployment_sha256=deployment.digest,
            state=state,
            expected_state_sha256=state.digest,
            topology=topology,
            release_artifact=artifact,
            database=target,
            ownership_receipt=receipt,
        )
    assert caught.value.code is DeploymentErrorCode.IO_FAILED
    assert "private growth" not in str(caught.value)


def test_release_update_chains_state_without_requiring_old_snapshot(tmp_path: Path) -> None:
    topology, _, target, receipt, artifact, deployment = _remote_fixture(tmp_path)
    first = create_deployment_state(
        tmp_path / "state-1.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=target,
        ownership_receipt=receipt,
    )
    replacement = _artifact(
        tmp_path / "jarvis_assistant-0.1.1-py3-none-any.whl", b"replacement-wheel"
    )
    updated = build_deployment_manifest(
        topology=topology,
        role=DeploymentRole.SERVER_CORE,
        node_id="node:server",
        release_artifact=replacement,
        python_version="3.11.9",
        database_path=target,
        ownership_receipt=receipt,
    )
    second = create_deployment_state(
        tmp_path / "state-2.json",
        deployment=updated,
        topology=topology,
        release_artifact=replacement,
        database=target,
        ownership_receipt=receipt,
        previous_state=first,
        transition=DeploymentTransition.UPDATE,
    )

    assert second.sequence == 2
    assert second.previous_state_sha256 == first.digest
    assert second.release_sha256 != first.release_sha256


def test_deployment_state_chains_remote_to_local_rollback(tmp_path: Path) -> None:
    remote, _, active, cutover, artifact, remote_deployment = _remote_fixture(tmp_path)
    remote_state = create_deployment_state(
        tmp_path / "remote-state.json",
        deployment=remote_deployment,
        topology=remote,
        release_artifact=artifact,
        database=active,
        ownership_receipt=cutover,
    )
    restored_local = tmp_path / "restored-local.db"
    shutil.copyfile(active, restored_local)
    local = build_local_only_manifest(
        host_id=remote.host_id,
        node_id="node:laptop",
        capabilities=("core.chat", "core.identity", "transport.events"),
        epoch=3,
    )
    rollback = create_rollback_receipt(
        active,
        restored_local,
        tmp_path / "rollback.json",
        topology=local,
        previous_receipt=tmp_path / "cutover.json",
        accepted_state_sha256=analyze_database(active).content_sha256,
    )
    local_deployment = build_deployment_manifest(
        topology=local,
        role=DeploymentRole.LOCAL_CORE,
        node_id="node:laptop",
        release_artifact=artifact,
        python_version="3.11.9",
        database_path=restored_local,
        ownership_receipt=rollback,
    )
    local_state = create_deployment_state(
        tmp_path / "local-state.json",
        deployment=local_deployment,
        topology=local,
        release_artifact=artifact,
        database=restored_local,
        ownership_receipt=rollback,
        previous_state=remote_state,
        transition=DeploymentTransition.ROLLBACK,
    )
    assert local_state.sequence == remote_state.sequence + 1
    assert local_state.previous_state_sha256 == remote_state.digest
    assert local_state.active_owner_node_id == "node:laptop"


def test_laptop_device_offline_policy_never_changes_owner_or_effects(tmp_path: Path) -> None:
    topology, _, _, _, artifact, _ = _remote_fixture(tmp_path)
    deployment = build_deployment_manifest(
        topology=topology,
        role=DeploymentRole.LAPTOP_DEVICE,
        node_id="node:laptop",
        release_artifact=artifact,
        python_version="3.11.9",
    )
    activation = verify_runtime_deployment(
        deployment=deployment,
        expected_deployment_sha256=deployment.digest,
        state=None,
        expected_state_sha256=None,
        topology=topology,
        release_artifact=artifact,
        database=None,
        ownership_receipt=None,
    )

    offline_voice = decide_availability(activation, capability="node.voice", connected=False)
    shared_write = decide_availability(
        activation,
        capability="node.voice",
        connected=False,
        mutates_shared_state=True,
    )
    effect = decide_availability(
        activation,
        capability="node.computer",
        connected=False,
        causes_device_effect=True,
    )
    unknown = decide_availability(activation, capability="core.chat", connected=False)
    online = decide_availability(activation, capability="core.chat", connected=True)

    assert offline_voice.allowed and offline_voice.mode is AvailabilityMode.OFFLINE
    assert not shared_write.allowed and shared_write.reason == "shared_write_denied"
    assert not effect.allowed and effect.reason == "effect_denied"
    assert not unknown.allowed and unknown.reason == "capability_unavailable"
    assert online.allowed and online.mode is AvailabilityMode.REMOTE
    assert activation.active_owner_node_id == "node:server"


def test_local_owner_remains_available_without_network(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path / "jarvis_assistant-0.1.0-py3-none-any.whl")
    database = _database(tmp_path / "local.db")
    topology = build_local_only_manifest(
        host_id=local_memory_host_id(),
        node_id="node:laptop",
        capabilities=("core.chat",),
        epoch=1,
    )
    deployment = build_deployment_manifest(
        topology=topology,
        role=DeploymentRole.LOCAL_CORE,
        node_id="node:laptop",
        release_artifact=artifact,
        python_version="3.11.9",
        database_path=database,
    )
    state = create_deployment_state(
        tmp_path / "state.json",
        deployment=deployment,
        topology=topology,
        release_artifact=artifact,
        database=database,
        ownership_receipt=None,
    )
    activation = verify_runtime_deployment(
        deployment=deployment,
        expected_deployment_sha256=deployment.digest,
        state=state,
        expected_state_sha256=state.digest,
        topology=topology,
        release_artifact=artifact,
        database=database,
        ownership_receipt=None,
    )
    decision = decide_availability(
        activation,
        capability="core.chat",
        connected=False,
        mutates_shared_state=True,
    )
    assert decision.allowed and decision.mode is AvailabilityMode.LOCAL


def test_health_telemetry_is_bounded_typed_and_recovers() -> None:
    monitor = DeploymentHealthMonitor(max_events=16)
    start = datetime(2026, 9, 11, tzinfo=UTC)
    monitor.observe(HealthReason.READY, healthy=True, latency_ms=1, observed_at=start)
    for index in range(20):
        monitor.observe(
            HealthReason.NETWORK_PARTITION,
            healthy=True,
            latency_ms=float(index + 1),
            observed_at=start + timedelta(seconds=index + 1),
        )
    snapshot = monitor.snapshot()
    assert snapshot.live and snapshot.ready
    assert snapshot.samples == 16
    assert snapshot.p50_ms == 12
    assert snapshot.p95_ms == 20
    assert set(snapshot.model_dump()) == {
        "live",
        "ready",
        "reason",
        "samples",
        "p50_ms",
        "p95_ms",
        "counters",
    }

    failed = monitor.observe(HealthReason.DISK_FULL, healthy=False)
    assert not failed.ready and failed.reason is HealthReason.DISK_FULL
    recovered = monitor.observe(HealthReason.READY, healthy=True)
    assert recovered.ready and recovered.reason is HealthReason.READY
    stopped = monitor.observe(HealthReason.SHUTTING_DOWN, healthy=False)
    assert not stopped.live and not stopped.ready


def test_stage_promote_failed_update_and_rollback_are_atomic(tmp_path: Path) -> None:
    root = tmp_path / "releases"
    root.mkdir()
    first_source = _artifact(tmp_path / "first.whl", b"first")
    second_source = _artifact(tmp_path / "second.whl", b"second")
    first_digest = hashlib.sha256(b"first").hexdigest()
    second_digest = hashlib.sha256(b"second").hexdigest()

    first = stage_release(first_source, root, expected_sha256=first_digest)
    second = stage_release(second_source, root, expected_sha256=second_digest)
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    with pytest.raises(DeploymentError) as duplicate:
        stage_release(first_source, root, expected_sha256=first_digest)
    assert duplicate.value.code is DeploymentErrorCode.DESTINATION_EXISTS

    state_path = tmp_path / "release-state.json"
    state1 = promote_release(
        state_path,
        candidate_sha256=first_digest,
        expected_current_sha256=None,
        probe=lambda value: value == first_digest,
    )
    before = state_path.read_bytes()
    with pytest.raises(DeploymentError) as failed:
        promote_release(
            state_path,
            candidate_sha256=second_digest,
            expected_current_sha256=first_digest,
            probe=lambda _value: False,
        )
    assert failed.value.code is DeploymentErrorCode.HEALTH_CHECK_FAILED
    assert state_path.read_bytes() == before

    state2 = promote_release(
        state_path,
        candidate_sha256=second_digest,
        expected_current_sha256=first_digest,
        probe=lambda value: value == second_digest,
    )
    rolled_back = rollback_release(
        state_path,
        expected_current_sha256=second_digest,
        probe=lambda value: value == first_digest,
    )
    assert state1.generation == 1
    assert state2.generation == 2
    assert rolled_back.generation == 3
    assert rolled_back.current_release_sha256 == first_digest
    assert rolled_back.previous_release_sha256 == second_digest


def test_release_update_lock_refuses_concurrent_writer_without_removing_lock(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "release-state.json"
    lock_path = tmp_path / ".release-state.json.lock"
    lock_path.write_bytes(b"")
    with pytest.raises(DeploymentError) as caught:
        promote_release(
            state_path,
            candidate_sha256="a" * 64,
            expected_current_sha256=None,
            probe=lambda _digest: True,
        )
    assert caught.value.code is DeploymentErrorCode.STATE_CONFLICT
    assert lock_path.exists()
    assert not state_path.exists()


def test_load_manifest_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "deployment.json"
    path.write_text('{"format":"jarvis-deployment-v1","format":"changed"}', encoding="utf-8")
    with pytest.raises(DeploymentError) as caught:
        load_deployment_manifest(path)
    assert caught.value.code is DeploymentErrorCode.DOCUMENT_INVALID


def test_manifest_json_has_no_database_content(tmp_path: Path) -> None:
    topology, _, _, receipt, _artifact_path, deployment = _remote_fixture(tmp_path)
    rendered = deployment.model_dump_json()
    assert topology.digest in rendered
    assert receipt.accepted_state_sha256 not in rendered
    assert "pinned-wheel" not in rendered
    assert "private growth" not in rendered
    assert json.loads(rendered)["hardening"]["capability_bounding_set"] == []
