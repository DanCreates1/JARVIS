from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.computer.actions import MediaControlArguments, MediaOperation
from jarvis.computer.config import ComputerAccessConfigStore, ComputerAccessPolicy
from jarvis.computer.runtime import ComputerAccessDisabledError, build_computer_runtime
from jarvis.config import Settings
from jarvis.core import PermissionLevel
from jarvis.permissions import (
    ActionCoordinatorStatus,
    ApprovalSource,
    LocalCliApprovalSurface,
)


async def test_runtime_requires_both_enablement_gates_without_creating_identity(
    tmp_path: Path,
) -> None:
    settings = Settings(data_dir=tmp_path, _env_file=None)
    with pytest.raises(ComputerAccessDisabledError, match="master switch"):
        await build_computer_runtime(settings)
    assert not (tmp_path / "computer-identity.key").exists()

    enabled_settings = Settings(
        data_dir=tmp_path,
        computer_access_enabled=True,
        _env_file=None,
    )
    with pytest.raises(ComputerAccessDisabledError, match="policy file"):
        await build_computer_runtime(enabled_settings)
    assert not (tmp_path / "computer-identity.key").exists()


async def test_runtime_builds_fixed_level_one_registry_and_closes_store(tmp_path: Path) -> None:
    root = tmp_path / "controlled-files"
    root.mkdir()
    policy_store = ComputerAccessConfigStore(tmp_path)
    policy_store.save(
        ComputerAccessPolicy(
            enabled=True,
            maximum_permission_level=PermissionLevel.LEVEL_1,
            controlled_root=root,
        )
    )
    settings = Settings(
        data_dir=tmp_path,
        computer_access_enabled=True,
        _env_file=None,
    )

    components = await build_computer_runtime(settings)

    assert {action.definition.action_id for action in components.registry.actions} == {
        "control_media",
        "set_master_volume",
    }
    assert components.actor.capabilities == components.registry.required_capabilities
    assert components.coordinator.policy_version == "phase3-v1"
    async with components as entered:
        assert entered is components


async def test_runtime_level_two_adds_bounded_clipboard_and_move(tmp_path: Path) -> None:
    root = tmp_path / "controlled-files"
    root.mkdir()
    ComputerAccessConfigStore(tmp_path).save(
        ComputerAccessPolicy(
            enabled=True,
            maximum_permission_level=PermissionLevel.LEVEL_2,
            controlled_root=root,
        )
    )
    settings = Settings(
        data_dir=tmp_path,
        computer_access_enabled=True,
        _env_file=None,
    )

    components = await build_computer_runtime(settings)
    try:
        assert {action.definition.action_id for action in components.registry.actions} == {
            "control_media",
            "set_clipboard_text",
            "set_master_volume",
            "move_controlled_file",
        }
        assert {tool.definition.name for tool in components.registry.read_tools} == {
            "get_local_printer_status",
            "search_controlled_files",
        }
    finally:
        await components.close()


async def test_policy_file_change_kills_approved_action_before_claim(tmp_path: Path) -> None:
    root = tmp_path / "controlled-files"
    root.mkdir()
    policy_store = ComputerAccessConfigStore(tmp_path)
    policy = ComputerAccessPolicy(
        enabled=True,
        maximum_permission_level=PermissionLevel.LEVEL_1,
        controlled_root=root,
    )
    policy_store.save(policy)
    settings = Settings(
        data_dir=tmp_path,
        computer_access_enabled=True,
        _env_file=None,
    )
    components = await build_computer_runtime(settings)
    try:
        handler = components.registry.action("control_media")
        assert handler is not None
        proposal = await components.coordinator.propose(
            handler,
            MediaControlArguments(operation=MediaOperation.STOP),
            actor=components.actor,
            source=ApprovalSource.LOCAL_CLI,
            idempotency_key="kill-switch-test",
        )
        assert proposal.approval_id is not None
        surface = LocalCliApprovalSurface(
            approver=components.actor,
            prompt=lambda _request, _phrase: True,
        )
        approved = await components.coordinator.review(proposal.approval_id, surface)
        assert approved.status is ActionCoordinatorStatus.APPROVED
        assert approved.grant_id is not None

        policy_store.save(policy.model_copy(update={"enabled": False}))
        denied = await components.coordinator.execute(
            approved.grant_id,
            actor=components.actor,
        )

        assert denied.status is ActionCoordinatorStatus.DENIED
        assert denied.code == "authority_disabled"
    finally:
        await components.close()
