from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from rich.console import Console
from typer.testing import CliRunner

import jarvis.computer.windows as windows
from jarvis import cli
from jarvis.computer.config import (
    AppGroupPolicy,
    ApplicationPolicy,
    BrowserTargetPolicy,
    ComputerAccessConfigStore,
    ComputerAccessPolicy,
    HandsFreeMappingsPolicy,
    PrinterPolicy,
)
from jarvis.computer.identity import LocalActorFactory
from jarvis.computer.registry import build_computer_registry
from jarvis.computer.review import render_local_action_preview
from jarvis.computer.runtime import build_computer_runtime
from jarvis.config import Settings
from jarvis.permissions import (
    ActionCoordinatorStatus,
    ActorContext,
    ApprovalSource,
    AuthenticationAssurance,
    InteractionInterface,
    LocalCliApprovalSurface,
)


@pytest.fixture(autouse=True)
def no_native_media_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    async def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("automated matrix must never dispatch native media input")

    monkeypatch.setattr("jarvis.computer.actions.MediaControlHandler.execute", forbidden)


@pytest.fixture
def policy_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Policy/store integration uses a synthetic identity; native admission is tested separately."""

    def create(
        _factory: LocalActorFactory,
        *,
        interface: InteractionInterface,
        capabilities: Iterable[str],
    ) -> ActorContext:
        return ActorContext(
            host_id="synthetic-host",
            session_id="synthetic-session",
            device_id="synthetic-device",
            interface=interface,
            assurance=AuthenticationAssurance.LOCAL_SESSION,
            authenticated_at=datetime.now(UTC),
            capabilities=tuple(capabilities),
        )

    monkeypatch.setattr(LocalActorFactory, "create", create)


def _setup(tmp_path: Path) -> tuple[Settings, ComputerAccessPolicy]:
    root = tmp_path / "controlled-files"
    root.mkdir()
    policy = ComputerAccessPolicy(
        enabled=True, action_set="controlled-windows", controlled_root=root
    )
    ComputerAccessConfigStore(tmp_path).save(policy)
    return Settings(data_dir=tmp_path, computer_access_enabled=True, _env_file=None), policy


def test_policy_epoch_preserves_exact_fixed_argv_unicode(tmp_path: Path) -> None:
    _, policy = _setup(tmp_path)
    application = ApplicationPolicy(
        executable=tmp_path / "fixture.exe", sha256="a" * 64, arguments=("caf\u00e9.txt",)
    )
    original = policy.model_copy(update={"applications": {"fixture": application}})
    changed = original.model_copy(
        update={
            "applications": {
                "fixture": application.model_copy(update={"arguments": ("cafe\u0301.txt",)})
            }
        }
    )
    assert original.authority_version != changed.authority_version


def test_selected_set_excludes_stale_optional_actions(tmp_path: Path) -> None:
    _, policy = _setup(tmp_path)
    executable = tmp_path / "editor.exe"
    executable.write_bytes(b"synthetic enrollment identity; never executable")
    policy = policy.model_copy(
        update={
            "applications": {
                "editor": ApplicationPolicy(
                    executable=executable,
                    sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                )
            },
            "app_groups": {"work": AppGroupPolicy(applications=("editor",))},
            "browser_application": "editor",
            "browser_targets": {"docs": BrowserTargetPolicy(url="https://example.com")},
            "printers": {"office": PrinterPolicy(system_name="Synthetic")},
        }
    )
    registry = build_computer_registry(policy)
    assert {a.definition.action_id for a in registry.actions} == {
        "launch_application",
        "control_media",
        "set_master_volume",
        "move_controlled_file",
    }
    assert {t.definition.name for t in registry.read_tools} == {"search_controlled_files"}
    assert registry.action("set_clipboard_text") is None
    for mapping in HandsFreeMappingsPolicy.model_fields:
        with pytest.raises(ValueError, match="hands-free"):
            ComputerAccessPolicy.model_validate(
                {**policy.model_dump(), "hands_free_mappings": {mapping: True}}
            )
    with pytest.raises(ValueError, match="hands-free"):
        ComputerAccessPolicy.model_validate({**policy.model_dump(), "hands_free_app_group": "work"})


def test_catalog_has_typed_limits_and_creates_no_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, _ = _setup(tmp_path)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    output = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=output, width=1000, color_system=None))
    assert CliRunner().invoke(cli.app, ["computer", "catalog"]).exit_code == 0
    catalog = json.loads(output.getvalue())
    assert catalog["action_set"] == "controlled-windows"
    assert len(catalog["actions"]) == 3
    for action in catalog["actions"]:
        assert action["tool"]["input_schema"]["type"] == "object"
        assert action["tool"]["timeout_seconds"] <= 30
        assert action["tool"]["recovery"]
    assert not settings.database_path.exists()
    assert not (tmp_path / "computer-identity.key").exists()
    settings.computer_access_enabled = False
    assert CliRunner().invoke(cli.app, ["computer", "catalog"]).exit_code == 1


async def _approve_media(settings: Settings) -> str:
    async with await build_computer_runtime(settings) as runtime:
        handler = runtime.registry.action("control_media")
        assert handler is not None
        proposal = await runtime.coordinator.propose(
            handler,
            handler.input_model.model_validate({"operation": "stop"}),
            actor=runtime.actor,
            source=ApprovalSource.LOCAL_CLI,
        )
        assert proposal.approval_id is not None
        approved = await runtime.coordinator.review(
            proposal.approval_id,
            LocalCliApprovalSurface(approver=runtime.actor, prompt=lambda _r, _p: True),
        )
        assert approved.grant_id is not None
        return approved.grant_id


@pytest.mark.parametrize("restart", [False, True])
async def test_unicode_policy_edit_invalidates_existing_grant(
    tmp_path: Path, policy_identity: None, restart: bool
) -> None:
    settings, policy = _setup(tmp_path)
    executable = policy.controlled_root / "fixture.exe"
    executable.write_bytes(b"synthetic; never launched")
    application = ApplicationPolicy(
        executable=executable,
        sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
        arguments=("caf\u00e9.txt",),
    )
    policy = policy.model_copy(update={"applications": {"fixture": application}})
    store = ComputerAccessConfigStore(tmp_path)
    store.save(policy)
    grant_id = await _approve_media(settings)
    runtime = await build_computer_runtime(settings)
    try:
        store.save(
            policy.model_copy(
                update={
                    "applications": {
                        "fixture": application.model_copy(update={"arguments": ("cafe\u0301.txt",)})
                    }
                }
            )
        )
        if restart:
            await runtime.close()
            runtime = await build_computer_runtime(settings)
        result = await runtime.coordinator.execute(grant_id, actor=runtime.actor)
        assert result.status is ActionCoordinatorStatus.DENIED
        assert result.code == ("policy_version_mismatch" if restart else "authority_disabled")
    finally:
        await runtime.close()


async def test_exact_app_preview_reads_bound_policy_without_persisting_argv(
    tmp_path: Path, policy_identity: None
) -> None:
    settings, policy = _setup(tmp_path)
    executable = policy.controlled_root / "fixture.exe"
    executable.write_bytes(b"synthetic; never launched")
    fixed_argument = "[conceal]--fixed\x1b[2J\u202e cafe\u0301.txt"
    policy = policy.model_copy(
        update={
            "applications": {
                "fixture": ApplicationPolicy(
                    executable=executable,
                    sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                    arguments=(fixed_argument,),
                )
            }
        }
    )
    ComputerAccessConfigStore(tmp_path).save(policy)
    async with await build_computer_runtime(settings) as runtime:
        handler = runtime.registry.action("launch_application")
        assert handler is not None
        proposal = await runtime.coordinator.propose(
            handler,
            handler.input_model.model_validate({"application_id": "fixture"}),
            actor=runtime.actor,
            source=ApprovalSource.LOCAL_CLI,
        )
        assert proposal.request is not None
        preview = render_local_action_preview(proposal.request, policy)
        assert "fixed_argv" in preview and "[conceal]--fixed" in preview
        assert "\\u001b" in preview and "\\u202e" in preview
        assert "cafe\\u0301.txt" in preview and "caf\\u00e9.txt" not in preview
        assert "\x1b" not in preview and "\u202e" not in preview
        assert "--fixed" not in proposal.request.model_dump_json()
        with pytest.raises(ValueError, match="exact current"):
            render_local_action_preview(
                proposal.request, policy.model_copy(update={"max_file_bytes": 1024})
            )


async def test_obsolete_pending_policy_is_denied_before_approval_prompt(
    tmp_path: Path, policy_identity: None
) -> None:
    settings, policy = _setup(tmp_path)
    async with await build_computer_runtime(settings) as runtime:
        handler = runtime.registry.action("control_media")
        assert handler is not None
        proposal = await runtime.coordinator.propose(
            handler,
            handler.input_model.model_validate({"operation": "stop"}),
            actor=runtime.actor,
            source=ApprovalSource.LOCAL_CLI,
        )
    ComputerAccessConfigStore(tmp_path).save(policy.model_copy(update={"max_file_bytes": 1024}))
    prompted = []
    async with await build_computer_runtime(settings) as restarted:
        assert proposal.approval_id is not None
        result = await restarted.coordinator.review(
            proposal.approval_id,
            LocalCliApprovalSurface(
                approver=restarted.actor, prompt=lambda r, p: prompted.append(r) is None
            ),
        )
        assert result.code == "policy_version_mismatch"
        assert not prompted


async def test_restart_policy_edit_without_epoch_rotation_denies_old_grant(
    tmp_path: Path, policy_identity: None
) -> None:
    settings, policy = _setup(tmp_path)
    grant_id = await _approve_media(settings)  # Preparation only; no media input.
    ComputerAccessConfigStore(tmp_path).save(policy.model_copy(update={"max_file_bytes": 1024}))
    async with await build_computer_runtime(settings) as restarted:
        denied = await restarted.coordinator.execute(grant_id, actor=restarted.actor)
        assert denied.status is ActionCoordinatorStatus.DENIED
        assert denied.code == "policy_version_mismatch"
        assert denied.receipt is not None
        assert denied.receipt.outcome.value == "denied"


async def test_cancel_revokes_only_unclaimed_owned_grant_across_restart(
    tmp_path: Path, policy_identity: None
) -> None:
    settings, _ = _setup(tmp_path)
    grant_id = await _approve_media(settings)
    assert await cli._computer_cancel(settings, grant_id="unknown") == 1
    assert await cli._computer_cancel(settings, grant_id=grant_id) == 0
    assert await cli._computer_cancel(settings, grant_id=grant_id) == 1
    async with await build_computer_runtime(settings) as runtime:
        denied = await runtime.coordinator.execute(grant_id, actor=runtime.actor)
        assert denied.status is ActionCoordinatorStatus.DENIED
        assert denied.code == "grant_revoked"
        assert not await runtime.store.list_receipt_summaries()


async def test_concurrent_cancel_has_one_atomic_winner(
    tmp_path: Path, policy_identity: None
) -> None:
    settings, _ = _setup(tmp_path)
    grant_id = await _approve_media(settings)
    results = await asyncio.gather(
        cli._computer_cancel(settings, grant_id=grant_id),
        cli._computer_cancel(settings, grant_id=grant_id),
    )
    assert sorted(results) == [0, 1]


async def test_cancel_rejects_foreign_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, policy_identity: None
) -> None:

    settings, _ = _setup(tmp_path)
    grant_id = await _approve_media(settings)
    original = LocalActorFactory.create

    def other_session(self: LocalActorFactory, **kwargs: object) -> object:
        actor = original(self, **kwargs)  # type: ignore[arg-type]
        return actor.model_copy(update={"session_id": "foreign-session"})

    with monkeypatch.context() as patch:
        patch.setattr(LocalActorFactory, "create", other_session)
        assert await cli._computer_cancel(settings, grant_id=grant_id) == 1
    assert await cli._computer_cancel(settings, grant_id=grant_id) == 0


@pytest.mark.skipif(os.name != "nt", reason="real guarded Windows file identity/rename")
def test_native_cli_respects_current_token_and_one_use_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings, policy = _setup(tmp_path)
    monkeypatch.setattr(cli, "_load_settings", lambda: settings)
    output = io.StringIO()
    console = Console(file=output, width=1000, color_system=None)
    monkeypatch.setattr(cli, "console", console)
    runner = CliRunner()
    source = policy.controlled_root / "[conceal]report.txt"
    source.write_text("Disposable Phase 13 synthetic fixture.", encoding="utf-8")
    result = runner.invoke(
        cli.app,
        [
            "computer",
            "propose",
            "move_controlled_file",
            "--arguments",
            json.dumps({"source": source.name, "destination": "archive.txt"}),
        ],
    )
    assert source.exists() and not (policy.controlled_root / "archive.txt").exists()
    preview = output.getvalue()

    if windows._read_token_state()[0]:
        assert result.exit_code == 1
        assert "runtime is unavailable" in preview
        assert source.exists() and not settings.database_path.exists()
        return
    assert result.exit_code == 0, result.exception
    assert "[conceal]report.txt" in preview
    assert "controlled_root" in preview and "file_bytes" in preview
    approval_id = preview.split("Approval ID: ")[1].splitlines()[0]
    monkeypatch.setattr(console, "input", lambda prompt: prompt.split("[bold]")[1].split("[/]")[0])
    assert runner.invoke(cli.app, ["computer", "approve", approval_id]).exit_code == 0
    grant_id = output.getvalue().split("One-use grant issued: ")[1].splitlines()[0]
    assert source.exists()  # Exact approval alone has no effect.
    assert runner.invoke(cli.app, ["computer", "execute", grant_id]).exit_code == 0
    destination = policy.controlled_root / "archive.txt"
    assert destination.read_text() == "Disposable Phase 13 synthetic fixture."
    # A new runtime rejects consumed authority; inspect audit rather than re-executing.
    assert runner.invoke(cli.app, ["computer", "execute", grant_id]).exit_code == 1
    assert not source.exists() and destination.exists()
    assert output.getvalue().count("succeeded receipt=") == 1
    assert runner.invoke(cli.app, ["computer", "cancel", grant_id]).exit_code == 1
    assert runner.invoke(cli.app, ["computer", "audit", "--kind", "receipts"]).exit_code == 0
    assert "Sanitized computer action receipts" in output.getvalue()


async def test_elevated_native_runtime_denied_before_authority_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from jarvis.computer.windows import ElevatedProcessError

    settings, _ = _setup(tmp_path)
    monkeypatch.setattr("jarvis.computer.windows._read_token_state", lambda: (True, b"synthetic"))
    with pytest.raises(ElevatedProcessError):
        await build_computer_runtime(settings)
    assert (
        await cli._computer_propose(settings, action="control_media", raw={"operation": "stop"})
        == 1
    )
    assert not settings.database_path.exists()
