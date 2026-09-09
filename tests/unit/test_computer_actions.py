from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from jarvis.computer.actions import (
    ActionCanonicalizer,
    ActionPreparationError,
    AppGroupLaunchHandler,
    ApplicationLaunchArguments,
    ApplicationLaunchHandler,
    LocalPrinterStatusArguments,
    LocalPrinterStatusTool,
    MediaControlArguments,
    MediaControlHandler,
    MediaOperation,
    PreparedAction,
    ReversibleMoveArguments,
    ReversibleMoveHandler,
    SearchControlledFilesArguments,
    SearchControlledFilesTool,
    prepare_action,
)
from jarvis.computer.config import (
    AppGroupPolicy,
    ApplicationPolicy,
    ComputerAccessPolicy,
    PrinterPolicy,
)
from jarvis.computer.windows import (
    AllowedRootGuard,
    DestinationExistsError,
    ExecutableEnrollment,
    FileIdentity,
    IdentityMismatchError,
    MediaInputResult,
    MediaKey,
    PrinterStatus,
    RenamePostconditionError,
    RenameReceipt,
    rollback_rename,
)
from jarvis.core import (
    AssistantService,
    PermissionLevel,
    ProviderResponse,
    RuntimeStatus,
    ToolIdempotency,
    ToolRetryPolicy,
    count_json_leaf_items,
)
from jarvis.permissions import (
    ActionDefinition,
    CanonicalAction,
    PostconditionStatus,
    RollbackStatus,
)
from tests.fakes import FakeChatProvider, FakeToolPolicy, InMemoryConversationStore
from tests.fakes.phase3 import FIXED_NOW, actor

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="requires guarded Win32 paths")


@dataclass(frozen=True)
class FakeLaunchObservation:
    pid: int
    image_verified: bool = True


def policy(
    root: Path,
    *,
    applications: dict[str, ApplicationPolicy] | None = None,
    groups: dict[str, AppGroupPolicy] | None = None,
    printers: dict[str, PrinterPolicy] | None = None,
    enabled: bool = True,
    maximum_level: PermissionLevel = PermissionLevel.LEVEL_2,
    max_search_results: int = 50,
) -> ComputerAccessPolicy:
    return ComputerAccessPolicy(
        enabled=enabled,
        controlled_root=root,
        applications=applications or {},
        app_groups=groups or {},
        printers=printers or {},
        maximum_permission_level=maximum_level,
        max_search_results=max_search_results,
    )


def application(path: Path, digest: str, *arguments: str) -> ApplicationPolicy:
    return ApplicationPolicy(executable=path, sha256=digest, arguments=arguments)


def fake_enrollment(path: Path, digest: str, *, index: int = 1) -> ExecutableEnrollment:
    identity = FileIdentity(
        path=path,
        final_path=rf"\\?\Volume{{test}}\apps\{path.name}",
        volume_serial=100,
        file_id=f"{index:032x}",
        size=10_000 + index,
        modified_100ns=1_000 + index,
        link_count=1,
        attributes=0,
        sha256=digest,
    )
    return ExecutableEnrollment(path=path, identity=identity, sha256=digest)


def canonical_action(
    definition: ActionDefinition,
    prepared: PreparedAction,
    *,
    key: str = "computer-action-1",
) -> CanonicalAction:
    return CanonicalAction.create(
        request_id=f"request-{key}",
        conversation_id="conversation-1",
        tool_call_id="tool-call-1",
        action_id=definition.action_id,
        action_version=definition.version,
        actor=actor(capabilities=definition.tool.required_capabilities),
        normalized_arguments=prepared.normalized_arguments,
        permission_level=definition.tool.permission_level,
        approval_rule=definition.tool.approval_rule,
        policy_version="phase3-v1",
        idempotency_key=key,
        human_effect=prepared.human_effect,
        recovery_limits=prepared.recovery_limits,
        precondition=prepared.precondition,
        created_at=FIXED_NOW,
        expires_at=FIXED_NOW + timedelta(minutes=2),
    )


def test_prepared_action_contains_only_coordinator_authority_fields(tmp_path: Path) -> None:
    digest = "a" * 64
    app_path = tmp_path / "apps" / "alpha.exe"
    configured = policy(
        tmp_path,
        applications={"alpha": application(app_path, digest, "--fixed")},
    )
    handler = ApplicationLaunchHandler(
        configured,
        capture_enrollment=lambda path: fake_enrollment(path, digest),
        launch_application=lambda _enrollment, _arguments: FakeLaunchObservation(100),
    )

    assert isinstance(handler, ActionCanonicalizer)
    prepared = prepare_action(handler, {"application_id": "alpha"})
    assert set(type(prepared).model_fields) == {
        "normalized_arguments",
        "human_effect",
        "recovery_limits",
        "precondition",
    }
    assert prepared.normalized_arguments == {"application_id": "alpha"}
    serialized = json.dumps(prepared.model_dump(mode="json"))
    assert str(app_path) not in serialized
    assert "--fixed" not in serialized
    assert handler.definition.tool.input_schema["properties"]["application_id"]["enum"] == ["alpha"]
    with pytest.raises(ValidationError, match="extra_forbidden"):
        prepare_action(handler, {"application_id": "alpha", "arguments": ["injected"]})
    with pytest.raises(ActionPreparationError, match="not configured"):
        prepare_action(handler, {"application_id": "unknown"})


@pytest.mark.asyncio
async def test_application_handler_uses_only_enrolled_fixed_arguments_and_verifies_image(
    tmp_path: Path,
) -> None:
    digest = "a" * 64
    app_path = tmp_path / "apps" / "alpha.exe"
    configured = policy(
        tmp_path,
        applications={"alpha": application(app_path, digest, "--mode", "safe")},
    )
    launches: list[tuple[ExecutableEnrollment, tuple[str, ...]]] = []

    def launch(
        enrollment: ExecutableEnrollment,
        arguments: tuple[str, ...],
    ) -> FakeLaunchObservation:
        launches.append((enrollment, arguments))
        return FakeLaunchObservation(pid=4242)

    handler = ApplicationLaunchHandler(
        configured,
        capture_enrollment=lambda path: fake_enrollment(path, digest),
        launch_application=launch,
    )
    prepared = handler.prepare(ApplicationLaunchArguments(application_id="alpha"))
    action = canonical_action(handler.definition, prepared)

    effect = await handler.execute(action)
    evidence = await handler.verify(action, effect)
    rollback = await handler.rollback(action, effect, reason="test")

    assert launches == [(fake_enrollment(app_path, digest), ("--mode", "safe"))]
    assert effect.result == {"application_id": "alpha", "pid": 4242, "image_verified": True}
    assert evidence.status is PostconditionStatus.PASSED
    assert rollback.status is RollbackStatus.UNAVAILABLE
    assert handler.definition.supports_rollback is False


def test_application_enrollment_sha_mismatch_and_disabled_policy_fail_closed(
    tmp_path: Path,
) -> None:
    configured = policy(
        tmp_path,
        applications={"alpha": application(tmp_path / "alpha.exe", "a" * 64)},
    )
    with pytest.raises(IdentityMismatchError, match="SHA-256"):
        ApplicationLaunchHandler(
            configured,
            capture_enrollment=lambda path: fake_enrollment(path, "b" * 64),
        )
    with pytest.raises(ValueError, match="disabled"):
        ApplicationLaunchHandler(
            configured.model_copy(update={"enabled": False}),
            capture_enrollment=lambda path: fake_enrollment(path, "a" * 64),
        )


@pytest.mark.asyncio
async def test_app_group_reports_partial_launch_without_retry_or_auto_termination(
    tmp_path: Path,
) -> None:
    digests = {"alpha.exe": "a" * 64, "beta.exe": "b" * 64}
    applications = {
        "alpha": application(tmp_path / "alpha.exe", digests["alpha.exe"], "--alpha"),
        "beta": application(tmp_path / "beta.exe", digests["beta.exe"], "--beta"),
    }
    configured = policy(
        tmp_path,
        applications=applications,
        groups={"work": AppGroupPolicy(applications=("alpha", "beta"))},
    )
    launches: list[str] = []

    def capture(path: Path) -> ExecutableEnrollment:
        return fake_enrollment(path, digests[path.name], index=1 if path.name == "alpha.exe" else 2)

    def launch(
        enrollment: ExecutableEnrollment,
        _arguments: tuple[str, ...],
    ) -> FakeLaunchObservation:
        launches.append(enrollment.path.name)
        if enrollment.path.name == "beta.exe":
            raise OSError("injected launch failure")
        return FakeLaunchObservation(pid=101)

    handler = AppGroupLaunchHandler(
        configured,
        capture_enrollment=capture,
        launch_application=launch,
    )
    prepared = prepare_action(handler, {"group_id": "work"})
    action = canonical_action(handler.definition, prepared)

    effect = await handler.execute(action)
    evidence = await handler.verify(action, effect)
    rollback = await handler.rollback(action, effect, reason="partial")

    assert launches == ["alpha.exe", "beta.exe"]
    assert effect.result == {
        "group_id": "work",
        "launched": [{"application_id": "alpha", "pid": 101, "image_verified": True}],
        "complete": False,
        "failed_application_id": "beta",
    }
    assert evidence.status is PostconditionStatus.MISMATCH
    assert evidence.detail["launched_application_ids"] == ["alpha"]
    assert rollback.status is RollbackStatus.UNAVAILABLE
    assert handler.definition.tool.permission_level is PermissionLevel.LEVEL_1


@pytest.mark.asyncio
async def test_app_group_full_verified_result_passes(tmp_path: Path) -> None:
    digest = "c" * 64
    applications = {
        "alpha": application(tmp_path / "alpha.exe", digest),
        "beta": application(tmp_path / "beta.exe", digest),
    }
    configured = policy(
        tmp_path,
        applications=applications,
        groups={"work": AppGroupPolicy(applications=("alpha", "beta"))},
    )
    next_pid = iter((101, 102))
    handler = AppGroupLaunchHandler(
        configured,
        capture_enrollment=lambda path: fake_enrollment(path, digest),
        launch_application=lambda _enrollment, _arguments: FakeLaunchObservation(next(next_pid)),
    )
    prepared = prepare_action(handler, {"group_id": "work"})
    action = canonical_action(handler.definition, prepared, key="group-full")
    effect = await handler.execute(action)

    assert (await handler.verify(action, effect)).status is PostconditionStatus.PASSED


@pytest.mark.asyncio
async def test_media_handler_uses_fixed_enum_once_and_scopes_postcondition() -> None:
    keys: list[MediaKey] = []

    def send(key: MediaKey) -> MediaInputResult:
        keys.append(key)
        return MediaInputResult(
            key=key,
            requested_count=2,
            accepted_count=2,
            last_error=None,
        )

    handler = MediaControlHandler(send_input=send)
    prepared = prepare_action(handler, {"operation": "play_pause"})
    action = canonical_action(handler.definition, prepared, key="media")
    effect = await handler.execute(action)
    evidence = await handler.verify(action, effect)

    assert keys == [MediaKey.PLAY_PAUSE]
    assert evidence.status is PostconditionStatus.PASSED
    assert evidence.detail == {
        "operation": "play_pause",
        "scope": "input_acceptance_only",
        "playback_state_verified": False,
    }
    assert handler.definition.tool.idempotency is ToolIdempotency.NON_IDEMPOTENT
    assert handler.definition.tool.retry_policy is ToolRetryPolicy.NEVER
    assert (
        await handler.rollback(action, effect, reason="test")
    ).status is RollbackStatus.UNAVAILABLE
    with pytest.raises(ValidationError):
        prepare_action(handler, {"operation": "arbitrary_virtual_key"})


@pytest.mark.asyncio
async def test_media_partial_input_is_postcondition_mismatch() -> None:
    handler = MediaControlHandler(
        send_input=lambda key: MediaInputResult(
            key=key,
            requested_count=2,
            accepted_count=1,
            last_error=5,
        )
    )
    prepared = handler.prepare(MediaControlArguments(operation=MediaOperation.NEXT_TRACK))
    action = canonical_action(handler.definition, prepared, key="media-partial")
    effect = await handler.execute(action)

    assert (await handler.verify(action, effect)).status is PostconditionStatus.MISMATCH


@pytest.mark.asyncio
async def test_media_mute_toggle_uses_only_fixed_volume_mute_key() -> None:
    keys: list[MediaKey] = []

    def send(key: MediaKey) -> MediaInputResult:
        keys.append(key)
        return MediaInputResult(
            key=key,
            requested_count=2,
            accepted_count=2,
            last_error=None,
        )

    handler = MediaControlHandler(send_input=send)
    prepared = handler.prepare(MediaControlArguments(operation=MediaOperation.MUTE_TOGGLE))
    action = canonical_action(handler.definition, prepared, key="media-mute-toggle")
    effect = await handler.execute(action)

    assert keys == [MediaKey.VOLUME_MUTE]
    assert effect.result["operation"] == "mute_toggle"


@WINDOWS_ONLY
@pytest.mark.asyncio
async def test_reversible_move_binds_precondition_verifies_and_rolls_back(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    source_dir = controlled / "inbox"
    destination_dir = controlled / "archive"
    source_dir.mkdir(parents=True)
    destination_dir.mkdir()
    source = source_dir / "note.txt"
    source.write_text("approved content", encoding="utf-8")
    handler = ReversibleMoveHandler(policy(controlled))

    prepared = prepare_action(
        handler,
        {"source": "inbox/note.txt", "destination": "archive/note.txt"},
    )
    assert str(controlled) not in json.dumps(prepared.model_dump(mode="json"))
    action = canonical_action(handler.definition, prepared, key="move")
    effect = await handler.execute(action)
    assert not source.exists()
    assert (destination_dir / "note.txt").read_text(encoding="utf-8") == "approved content"
    assert (await handler.verify(action, effect)).status is PostconditionStatus.PASSED

    rollback = await handler.rollback(action, effect, reason="test rollback")
    assert rollback.status is RollbackStatus.SUCCEEDED
    assert source.read_text(encoding="utf-8") == "approved content"
    assert not (destination_dir / "note.txt").exists()


@WINDOWS_ONLY
@pytest.mark.asyncio
async def test_move_rollback_preserves_sanitized_uncertain_recovery_state(
    tmp_path: Path,
) -> None:
    controlled = tmp_path / "controlled"
    source_dir = controlled / "inbox"
    destination_dir = controlled / "archive"
    source_dir.mkdir(parents=True)
    destination_dir.mkdir()
    source = source_dir / "note.txt"
    destination = destination_dir / "note.txt"
    source.write_text("approved content", encoding="utf-8")

    def complete_then_report_uncertain(
        guard: AllowedRootGuard,
        receipt: RenameReceipt,
    ) -> FileIdentity:
        restored = rollback_rename(guard, receipt)
        recovery = RenameReceipt(
            source=receipt.destination,
            destination=receipt.source,
            identity=restored,
            postcondition_verified=False,
            postcondition_error="postcondition_probe_failed",
        )
        raise RenamePostconditionError("private primitive detail", recovery)

    handler = ReversibleMoveHandler(
        policy(controlled),
        rollback_operation=complete_then_report_uncertain,
    )
    prepared = prepare_action(
        handler,
        {"source": "inbox/note.txt", "destination": "archive/note.txt"},
    )
    action = canonical_action(handler.definition, prepared, key="move-uncertain-rollback")
    effect = await handler.execute(action)
    rollback = await handler.rollback(action, effect, reason="postcondition mismatch")

    assert rollback.status is RollbackStatus.FAILED
    assert "uncertain" in rollback.summary
    assert "private primitive detail" not in json.dumps(rollback.model_dump(mode="json"))
    assert rollback.detail == {
        "source": "inbox/note.txt",
        "destination": "archive/note.txt",
        "effect_may_have_completed": True,
        "reconciliation_required": True,
        "recovery_evidence_bound": True,
        "primitive_postcondition_verified": False,
    }
    assert source.read_text(encoding="utf-8") == "approved content"
    assert not destination.exists()


@WINDOWS_ONLY
@pytest.mark.asyncio
async def test_move_refuses_changed_source_collision_and_traversal(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    inbox = controlled / "inbox"
    archive = controlled / "archive"
    inbox.mkdir(parents=True)
    archive.mkdir()
    source = inbox / "note.txt"
    source.write_text("before", encoding="utf-8")
    handler = ReversibleMoveHandler(policy(controlled))
    prepared = prepare_action(
        handler,
        {"source": "inbox/note.txt", "destination": "archive/note.txt"},
    )
    action = canonical_action(handler.definition, prepared, key="move-changed")
    source.write_text("after approval", encoding="utf-8")
    with pytest.raises(IdentityMismatchError, match="precondition"):
        await handler.execute(action)

    (archive / "occupied.txt").write_text("occupied", encoding="utf-8")
    with pytest.raises(DestinationExistsError):
        prepare_action(
            handler,
            {"source": "inbox/note.txt", "destination": "archive/occupied.txt"},
        )
    for bad in ("../outside.txt", "/absolute.txt", r"inbox\note.txt", "file.txt:stream"):
        with pytest.raises(ValidationError):
            ReversibleMoveArguments(source=bad, destination="archive/safe.txt")


@WINDOWS_ONLY
@pytest.mark.asyncio
async def test_filename_search_is_bounded_relative_and_does_not_follow_links(
    tmp_path: Path,
) -> None:
    controlled = tmp_path / "controlled"
    notes = controlled / "notes"
    notes.mkdir(parents=True)
    (notes / "report-one.txt").write_text("content is never searched", encoding="utf-8")
    (notes / "other.txt").write_text("report only in content", encoding="utf-8")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "report-secret.txt").write_text("secret", encoding="utf-8")
    link = controlled / "linked"
    link_created = True
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        link_created = False

    tool = SearchControlledFilesTool(policy(controlled, max_search_results=2))
    result = await tool.invoke(SearchControlledFilesArguments(query="report", limit=2))

    assert result.is_error is False
    assert result.data is not None
    assert result.data["matches"] == ["notes/report-one.txt"]
    assert count_json_leaf_items(result.data) <= tool.definition.max_result_items
    serialized = json.dumps(result.data)
    assert str(controlled) not in serialized
    assert "report-secret" not in serialized
    if link_created:
        assert "linked" not in serialized

    limited = await tool.invoke(SearchControlledFilesArguments(query=".txt", limit=1))
    assert limited.data is not None
    assert limited.data["count"] == 1
    assert limited.data["truncated"] is True
    with pytest.raises(ValidationError, match="filename text"):
        SearchControlledFilesArguments(query="notes/report", limit=1)

    runtime = AssistantService(
        provider=FakeChatProvider(
            [
                {
                    "tool_calls": [
                        {
                            "id": "search-runtime",
                            "name": tool.definition.name,
                            "arguments": {"query": ".txt", "limit": 2},
                        }
                    ]
                },
                ProviderResponse(content="Search complete."),
            ]
        ),
        store=InMemoryConversationStore(),
        tools=[tool],
        policy=FakeToolPolicy(),
    )
    runtime_result = await runtime.respond("Find controlled text files.")
    assert runtime_result.status is RuntimeStatus.COMPLETED
    assert runtime_result.tool_iterations == 1


@WINDOWS_ONLY
@pytest.mark.asyncio
async def test_filename_search_maximum_shape_fits_declared_runtime_byte_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controlled = tmp_path / "controlled"
    controlled.mkdir()
    tool = SearchControlledFilesTool(policy(controlled, max_search_results=200))
    matches = [f"{index:03d}-" + "a" * 396 for index in range(200)]
    assert all(len(item.encode("utf-8")) == 400 for item in matches)
    monkeypatch.setattr(
        tool,
        "_search",
        lambda _query, _limit: (matches, 1_000_000, True),
    )

    direct = await tool.invoke(SearchControlledFilesArguments(query="a", limit=200))

    assert len(direct.model_dump_json().encode("utf-8")) <= tool.definition.max_result_bytes
    assert tool.definition.max_result_bytes <= 100 * 1_024
    assert count_json_leaf_items(direct.data) == tool.definition.max_result_items

    runtime = AssistantService(
        provider=FakeChatProvider(
            [
                {
                    "tool_calls": [
                        {
                            "id": "search-max-shape",
                            "name": tool.definition.name,
                            "arguments": {"query": "a", "limit": 200},
                        }
                    ]
                },
                ProviderResponse(content="Maximum search shape accepted."),
            ]
        ),
        store=InMemoryConversationStore(),
        tools=[tool],
        policy=FakeToolPolicy(),
    )

    runtime_result = await runtime.respond("Find the maximum bounded result set.")

    assert runtime_result.status is RuntimeStatus.COMPLETED
    assert runtime_result.tool_iterations == 1


@WINDOWS_ONLY
@pytest.mark.asyncio
async def test_filename_search_fails_closed_if_root_identity_changes(tmp_path: Path) -> None:
    controlled = tmp_path / "controlled"
    controlled.mkdir()
    tool = SearchControlledFilesTool(policy(controlled))
    moved = tmp_path / "moved"
    controlled.rename(moved)
    controlled.mkdir()

    result = await tool.invoke(SearchControlledFilesArguments(query="anything"))
    assert result.is_error is True
    assert result.data == {"code": "controlled_search_failed"}


@pytest.mark.asyncio
async def test_printer_status_returns_only_configured_aliases_from_worker_thread(
    tmp_path: Path,
) -> None:
    configured = policy(
        tmp_path,
        printers={
            "office": PrinterPolicy(system_name="Private Office Queue"),
            "pdf": PrinterPolicy(system_name="Configured PDF Queue"),
        },
    )
    main_thread = threading.get_ident()
    discovery_threads: list[int] = []

    def discover(*, max_printers: int = 64) -> tuple[PrinterStatus, ...]:
        discovery_threads.append(threading.get_ident())
        assert max_printers == 256
        return (
            PrinterStatus(name="Private Office Queue", attributes=0, status=0),
            PrinterStatus(name="Unconfigured Secret Queue", attributes=0, status=128),
        )

    tool = LocalPrinterStatusTool(configured, discover=discover)
    result = await tool.invoke(LocalPrinterStatusArguments())

    assert discovery_threads and discovery_threads[0] != main_thread
    assert result.is_error is False
    assert result.data == {
        "printers": [
            {
                "printer_id": "office",
                "installed": True,
                "status_available": True,
                "status_flags": 0,
            },
            {
                "printer_id": "pdf",
                "installed": False,
                "status_available": False,
                "status_flags": None,
            },
        ],
        "count": 2,
    }
    assert count_json_leaf_items(result.data) <= tool.definition.max_result_items
    serialized = json.dumps(result.data)
    assert "Private Office Queue" not in serialized
    assert "Unconfigured Secret Queue" not in serialized

    unknown = await tool.invoke(LocalPrinterStatusArguments(printer_id="unknown"))
    assert unknown.is_error is True
    assert unknown.data == {"code": "unknown_printer_alias"}
    assert len(discovery_threads) == 1

    runtime = AssistantService(
        provider=FakeChatProvider(
            [
                {
                    "tool_calls": [
                        {
                            "id": "printer-runtime",
                            "name": tool.definition.name,
                            "arguments": {},
                        }
                    ]
                },
                ProviderResponse(content="Printer status complete."),
            ]
        ),
        store=InMemoryConversationStore(),
        tools=[tool],
        policy=FakeToolPolicy(),
    )
    runtime_result = await runtime.respond("Check configured printers.")
    assert runtime_result.status is RuntimeStatus.COMPLETED
    assert runtime_result.tool_iterations == 1


@pytest.mark.asyncio
async def test_printer_discovery_failure_is_safe_and_never_prints(tmp_path: Path) -> None:
    configured = policy(
        tmp_path,
        printers={"office": PrinterPolicy(system_name="Private Office Queue")},
    )

    def fail(*, max_printers: int = 64) -> tuple[PrinterStatus, ...]:
        del max_printers
        raise OSError("Private Office Queue spooler detail")

    tool = LocalPrinterStatusTool(configured, discover=fail)
    result = await tool.invoke(LocalPrinterStatusArguments(printer_id="office"))

    assert result.is_error is True
    assert result.data == {"code": "printer_status_failed"}
    assert "Private Office Queue" not in result.content


@WINDOWS_ONLY
def test_all_definitions_declare_bounded_security_and_recovery(tmp_path: Path) -> None:
    digest = "a" * 64
    configured = policy(
        tmp_path,
        applications={"alpha": application(tmp_path / "alpha.exe", digest)},
        groups={"work": AppGroupPolicy(applications=("alpha",))},
        printers={"office": PrinterPolicy(system_name="Office")},
    )
    app = ApplicationLaunchHandler(
        configured,
        capture_enrollment=lambda path: fake_enrollment(path, digest),
    )
    group = AppGroupLaunchHandler(
        configured,
        capture_enrollment=lambda path: fake_enrollment(path, digest),
    )
    media = MediaControlHandler()
    printer = LocalPrinterStatusTool(configured, discover=lambda **_kwargs: ())
    move = ReversibleMoveHandler(configured)
    search = SearchControlledFilesTool(configured)

    for definition in (
        app.definition.tool,
        group.definition.tool,
        media.definition.tool,
        move.definition.tool,
        search.definition,
        printer.definition,
    ):
        assert definition.version == "1"
        assert definition.required_capabilities
        assert 0 < definition.timeout_seconds <= 30
        assert definition.max_result_bytes > 0
        assert definition.max_result_items > 0
        assert definition.postcondition
        assert definition.recovery

    assert [
        app.definition.tool.max_result_items,
        group.definition.tool.max_result_items,
        media.definition.tool.max_result_items,
        move.definition.tool.max_result_items,
        search.definition.max_result_items,
        printer.definition.max_result_items,
    ] == [3, 6, 4, 4, 53, 5]
    assert all(
        definition.effect_may_outlive_cancellation
        for definition in (
            app.definition,
            group.definition,
            media.definition,
            move.definition,
        )
    )
