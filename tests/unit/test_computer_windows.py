from __future__ import annotations

import os
import sys
from ctypes import sizeof
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import jarvis.computer.windows as windows
from jarvis.computer.windows import (
    AllowedRootGuard,
    DestinationExistsError,
    ExecutableEnrollment,
    FixedExecutableLauncher,
    IdentityMismatchError,
    MediaKey,
    UnsafePathError,
    UnsupportedPlatformError,
    WindowsIdentityProbe,
    discover_local_printers,
    rename_file_same_volume,
    rollback_rename,
    send_media_key,
)

WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="requires Win32")


def test_non_windows_calls_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows, "_IS_WINDOWS", False)
    with pytest.raises(UnsupportedPlatformError):
        windows._require_windows()
    with pytest.raises(UnsupportedPlatformError):
        WindowsIdentityProbe(b"k" * 32).probe()


def test_identity_probe_rejects_short_key() -> None:
    with pytest.raises(ValueError, match="16 bytes"):
        WindowsIdentityProbe(b"short")


@WINDOWS_ONLY
def test_input_layout_matches_win32_abi() -> None:
    expected = 40 if sizeof(windows.ctypes.c_void_p) == 8 else 28
    assert sizeof(windows._INPUT) == expected


@WINDOWS_ONLY
def test_elevation_check_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(windows, "_read_token_state", lambda: (True, b"sid"))
    monkeypatch.setattr(windows, "_read_machine_guid", lambda: b"device")

    with pytest.raises(windows.ElevatedProcessError):
        WindowsIdentityProbe(b"a" * 32).probe()
    elevated = WindowsIdentityProbe(b"a" * 32).probe(require_non_elevated=False)
    assert elevated.is_elevated is True
    with pytest.raises(windows.ElevatedProcessError):
        windows._require_non_elevated()


@WINDOWS_ONLY
@pytest.mark.parametrize(
    "path",
    [
        "",
        "relative.txt",
        "C:drive-relative.txt",
        r"\\server\share\file.txt",
        r"\\?\C:\file.txt",
        "C:\\folder\\..\\file.txt",
        "C:\\folder\\file.txt.",
        "C:\\folder\\file.txt ",
        "C:\\folder\\file.txt:stream",
        "C:\\folder\\CON.txt",
        "C:\\folder\\*.txt",
        "C:\\folder\\bad\x00name.txt",
    ],
)
def test_path_validator_rejects_unsafe_namespaces_and_names(path: str) -> None:
    with pytest.raises(UnsafePathError):
        windows._validate_local_absolute_path(path)


@WINDOWS_ONLY
def test_path_validator_rejects_unbounded_and_non_fixed_paths(tmp_path: Path) -> None:
    with pytest.raises(UnsafePathError, match="too long"):
        windows._validate_local_absolute_path("C:\\" + "x" * 32_001)
    with pytest.raises(UnsafePathError, match="fixed"):
        windows._validate_local_absolute_path("A:\\not-present.txt")
    assert windows._validate_local_absolute_path(tmp_path) == tmp_path


@WINDOWS_ONLY
def test_identity_probe_returns_stable_keyed_hashes() -> None:
    first = WindowsIdentityProbe(b"a" * 32).probe()
    repeated = WindowsIdentityProbe(b"a" * 32).probe()
    other_key = WindowsIdentityProbe(b"b" * 32).probe()

    assert first.is_elevated is False
    assert first == repeated
    assert len(first.user_id_hash) == len(first.device_id_hash) == 64
    assert first.user_id_hash != other_key.user_id_hash
    assert first.device_id_hash != other_key.device_id_hash


@WINDOWS_ONLY
def test_allowed_root_identity_hash_and_revalidation(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    file = allowed / "note.txt"
    file.write_text("approved", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))

    identity = guard.probe_existing_file(file, compute_sha256=True)
    assert identity.path == file.resolve()
    assert identity.size == len(b"approved")
    assert identity.link_count == 1
    assert identity.sha256 is not None and len(identity.sha256) == 64
    assert identity.same_object(guard.revalidate(identity))

    file.write_text("changed", encoding="utf-8")
    with pytest.raises(IdentityMismatchError):
        guard.revalidate(identity)
    with pytest.raises(UnsafePathError, match="outside"):
        guard.probe_existing_file(outside)
    with pytest.raises(UnsafePathError):
        guard.probe_existing_file(Path("relative.txt"))


@WINDOWS_ONLY
def test_guard_requires_directory_root_and_regular_existing_file(tmp_path: Path) -> None:
    file = tmp_path / "file.txt"
    file.write_text("data", encoding="utf-8")
    directory = tmp_path / "directory"
    directory.mkdir()

    with pytest.raises(ValueError, match="root"):
        AllowedRootGuard(())
    with pytest.raises(UnsafePathError, match="directory"):
        AllowedRootGuard((file,))

    guard = AllowedRootGuard((tmp_path,))
    assert guard.roots == (tmp_path.resolve(),)
    with pytest.raises(UnsafePathError, match="regular file"):
        guard.probe_existing_file(directory)
    with pytest.raises(UnsafePathError, match="does not exist"):
        guard.probe_existing_file(tmp_path / "missing.txt")


@WINDOWS_ONLY
def test_guard_detects_replaced_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    approved = allowed / "approved.txt"
    approved.write_text("approved", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))
    moved = tmp_path / "moved-root"
    allowed.rename(moved)
    allowed.mkdir()
    replacement = allowed / "replacement.txt"
    replacement.write_text("replacement", encoding="utf-8")

    with pytest.raises(IdentityMismatchError, match="root identity"):
        guard.probe_existing_file(replacement)


@WINDOWS_ONLY
def test_allowed_root_rejects_name_surrogate_component(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    target = allowed / "target"
    target.mkdir(parents=True)
    (target / "note.txt").write_text("text", encoding="utf-8")
    link = allowed / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable: {exc}")

    guard = AllowedRootGuard((allowed,))
    with pytest.raises(UnsafePathError, match="reparse"):
        guard.probe_existing_file(link / "note.txt")


@WINDOWS_ONLY
def test_component_walker_rejects_name_surrogate_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_lstat(_path: Path) -> SimpleNamespace:
        nonlocal calls
        calls += 1
        if calls == 2:
            return SimpleNamespace(
                st_file_attributes=windows._FILE_ATTRIBUTE_REPARSE_POINT,
                st_reparse_tag=windows._IO_REPARSE_TAG_NAME_SURROGATE,
            )
        return SimpleNamespace(st_file_attributes=0, st_reparse_tag=0)

    monkeypatch.setattr(windows.os, "lstat", fake_lstat)
    with pytest.raises(UnsafePathError, match="reparse"):
        windows._reject_name_surrogate_components(Path(r"C:\root\link"))


@WINDOWS_ONLY
def test_mutation_rejects_hard_link(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    source.write_text("data", encoding="utf-8")
    alias = allowed / "alias.txt"
    os.link(source, alias)
    guard = AllowedRootGuard((allowed,))

    with pytest.raises(UnsafePathError, match="multiply-linked"):
        rename_file_same_volume(guard, source, allowed / "renamed.txt")


@WINDOWS_ONLY
def test_same_volume_rename_and_rollback_are_identity_bound(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    source.write_text("data", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))

    receipt = rename_file_same_volume(guard, source, allowed / "renamed.txt")
    assert not source.exists()
    assert receipt.postcondition_verified is True
    assert receipt.postcondition_error is None
    assert receipt.destination.read_text(encoding="utf-8") == "data"
    assert receipt.identity.same_object(guard.probe_existing_file(receipt.destination))

    restored = rollback_rename(guard, receipt)
    assert source.read_text(encoding="utf-8") == "data"
    assert not receipt.destination.exists()
    assert receipt.identity.same_object(restored)


@WINDOWS_ONLY
def test_handle_bound_rename_blocks_source_swap_at_dispatch(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    replacement = allowed / "replacement.txt"
    destination = allowed / "destination.txt"
    source.write_text("approved", encoding="utf-8")
    replacement.write_text("attacker", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))
    blocked = False

    def try_source_swap() -> None:
        nonlocal blocked
        try:
            os.replace(replacement, source)
        except PermissionError:
            blocked = True
        else:
            pytest.fail("source replacement succeeded while DELETE handle was pinned")

    receipt = rename_file_same_volume(
        guard,
        source,
        destination,
        _before_dispatch=try_source_swap,
    )

    assert blocked is True
    assert receipt.postcondition_verified is True
    assert destination.read_text(encoding="utf-8") == "approved"
    assert replacement.read_text(encoding="utf-8") == "attacker"


@WINDOWS_ONLY
def test_handle_bound_rename_blocks_destination_parent_swap_at_dispatch(
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    incoming = allowed / "incoming"
    archive = allowed / "archive"
    incoming.mkdir(parents=True)
    archive.mkdir()
    source = incoming / "source.txt"
    destination = archive / "destination.txt"
    parked = allowed / "parked-archive"
    source.write_text("approved", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))
    blocked = False

    def try_parent_swap() -> None:
        nonlocal blocked
        try:
            archive.rename(parked)
        except PermissionError:
            blocked = True
        else:
            pytest.fail("destination parent replacement succeeded while parent handle was pinned")

    receipt = rename_file_same_volume(
        guard,
        source,
        destination,
        _before_dispatch=try_parent_swap,
    )

    assert blocked is True
    assert receipt.postcondition_verified is True
    assert archive.is_dir()
    assert not parked.exists()
    assert destination.read_text(encoding="utf-8") == "approved"


@WINDOWS_ONLY
def test_handle_bound_rename_blocks_allowed_root_swap_at_dispatch(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    destination = allowed / "destination.txt"
    parked = tmp_path / "parked-root"
    source.write_text("approved", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))
    blocked = False

    def try_root_swap() -> None:
        nonlocal blocked
        try:
            allowed.rename(parked)
        except PermissionError:
            blocked = True
        else:
            pytest.fail("allowed root replacement succeeded while root handle was pinned")

    receipt = rename_file_same_volume(
        guard,
        source,
        destination,
        _before_dispatch=try_root_swap,
    )

    assert blocked is True
    assert receipt.postcondition_verified is True
    assert allowed.is_dir()
    assert not parked.exists()
    assert destination.read_text(encoding="utf-8") == "approved"


@WINDOWS_ONLY
def test_handle_bound_rename_collision_race_never_overwrites(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    destination = allowed / "destination.txt"
    source.write_text("approved", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))

    def create_collision() -> None:
        destination.write_text("collision", encoding="utf-8")

    with pytest.raises(DestinationExistsError):
        rename_file_same_volume(
            guard,
            source,
            destination,
            _before_dispatch=create_collision,
        )
    assert source.read_text(encoding="utf-8") == "approved"
    assert destination.read_text(encoding="utf-8") == "collision"


@WINDOWS_ONLY
def test_completed_rename_preserves_recovery_evidence_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    destination = allowed / "destination.txt"
    source.write_text("approved", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))
    real_set_name = windows._set_handle_name
    real_identity_for_handle = windows._identity_for_handle
    dispatched = False

    def set_name(handle: int, target: Path) -> None:
        nonlocal dispatched
        real_set_name(handle, target)
        dispatched = True

    def fail_post_dispatch_probe(
        path: Path,
        handle: int,
        *,
        compute_sha256: bool,
    ) -> windows.FileIdentity:
        if dispatched:
            raise OSError("deterministic post-dispatch probe failure")
        return real_identity_for_handle(path, handle, compute_sha256=compute_sha256)

    monkeypatch.setattr(windows, "_set_handle_name", set_name)
    monkeypatch.setattr(windows, "_identity_for_handle", fail_post_dispatch_probe)
    receipt = rename_file_same_volume(guard, source, destination)

    assert not source.exists()
    assert destination.read_text(encoding="utf-8") == "approved"
    assert receipt.postcondition_verified is False
    assert receipt.postcondition_error == "postcondition_probe_failed"
    assert receipt.identity.path == destination
    assert receipt.identity.file_id

    monkeypatch.setattr(windows, "_identity_for_handle", real_identity_for_handle)
    restored = rollback_rename(guard, receipt)
    assert restored.same_object(receipt.identity)
    assert source.read_text(encoding="utf-8") == "approved"
    assert not destination.exists()


@WINDOWS_ONLY
def test_completed_rollback_raises_typed_recovery_state_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    destination = allowed / "destination.txt"
    source.write_text("approved", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))
    receipt = rename_file_same_volume(guard, source, destination)
    real_set_name = windows._set_handle_name
    real_identity_for_handle = windows._identity_for_handle
    dispatched = False

    def set_name(handle: int, target: Path) -> None:
        nonlocal dispatched
        real_set_name(handle, target)
        dispatched = True

    def fail_post_dispatch_probe(
        path: Path,
        handle: int,
        *,
        compute_sha256: bool,
    ) -> windows.FileIdentity:
        if dispatched:
            raise OSError("deterministic rollback post-dispatch probe failure")
        return real_identity_for_handle(path, handle, compute_sha256=compute_sha256)

    monkeypatch.setattr(windows, "_set_handle_name", set_name)
    monkeypatch.setattr(windows, "_identity_for_handle", fail_post_dispatch_probe)
    with pytest.raises(windows.RenamePostconditionError) as raised:
        rollback_rename(guard, receipt)

    recovery = raised.value.recovery
    assert recovery.postcondition_verified is False
    assert recovery.postcondition_error == "postcondition_probe_failed"
    assert recovery.source == destination
    assert recovery.destination == source
    assert source.read_text(encoding="utf-8") == "approved"
    assert not destination.exists()


@WINDOWS_ONLY
def test_rename_and_rollback_require_allowed_collision_free_destinations(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    source.write_text("data", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    guard = AllowedRootGuard((allowed,))

    with pytest.raises(UnsafePathError, match="outside"):
        rename_file_same_volume(guard, source, outside)

    receipt = rename_file_same_volume(guard, source, allowed / "renamed.txt")
    source.write_text("collision", encoding="utf-8")
    with pytest.raises(DestinationExistsError):
        rollback_rename(guard, receipt)


@WINDOWS_ONLY
def test_rename_never_overwrites_and_tamper_blocks_rollback(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    source = allowed / "source.txt"
    destination = allowed / "destination.txt"
    source.write_text("source", encoding="utf-8")
    destination.write_text("existing", encoding="utf-8")
    guard = AllowedRootGuard((allowed,))

    with pytest.raises(DestinationExistsError):
        rename_file_same_volume(guard, source, destination)
    assert source.read_text(encoding="utf-8") == "source"
    assert destination.read_text(encoding="utf-8") == "existing"

    destination.unlink()
    receipt = rename_file_same_volume(guard, source, destination)
    destination.write_text("tampered", encoding="utf-8")
    with pytest.raises(IdentityMismatchError):
        rollback_rename(guard, receipt)


@WINDOWS_ONLY
def test_executable_launcher_pins_hash_identity_environment_and_image() -> None:
    enrollment = ExecutableEnrollment.capture(Path(sys.executable))
    launcher = FixedExecutableLauncher(
        enrollment,
        ("-c", "import time; time.sleep(30)"),
    )
    receipt = launcher.launch()
    try:
        assert receipt.pid > 0
        assert receipt.image_verified is True
        assert receipt.image_path is not None
        assert "PATH" not in windows._sanitized_environment()
        assert launcher.argv == ("-c", "import time; time.sleep(30)")
        assert launcher.enrollment == enrollment
    finally:
        receipt.process.terminate()
        receipt.process.wait(timeout=5)

    altered = replace(enrollment, sha256="0" * 64)
    with pytest.raises(IdentityMismatchError, match="SHA-256"):
        FixedExecutableLauncher(altered).launch()


@WINDOWS_ONLY
def test_executable_enrollment_and_fixed_arguments_validate(tmp_path: Path) -> None:
    text = tmp_path / "not-an-app.txt"
    text.write_text("x", encoding="utf-8")
    with pytest.raises(UnsafePathError, match=r"\.exe"):
        ExecutableEnrollment.capture(text)

    enrollment = ExecutableEnrollment.capture(Path(sys.executable))
    with pytest.raises(ValueError, match="NUL"):
        FixedExecutableLauncher(enrollment, ("bad\x00argument",))
    with pytest.raises(ValueError, match="too long"):
        FixedExecutableLauncher(enrollment, ("x" * 30_001,))


@WINDOWS_ONLY
def test_launcher_terminates_when_live_image_cannot_be_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    enrollment = ExecutableEnrollment.capture(Path(sys.executable))
    launcher = FixedExecutableLauncher(
        enrollment,
        ("-c", "import time; time.sleep(30)"),
    )
    monkeypatch.setattr(windows, "_query_process_image", lambda _pid: None)

    with pytest.raises(IdentityMismatchError, match="could not be verified"):
        launcher.launch()


def test_sanitized_environment_is_case_insensitive_and_excludes_path() -> None:
    sanitized = windows._sanitized_environment(
        {
            "systemroot": r"C:\Windows",
            "PaTh": r"C:\untrusted",
            "TEMP": r"C:\Temp",
            "JARVIS_SECRET": "secret",
        }
    )
    assert sanitized == {"SystemRoot": r"C:\Windows", "TEMP": r"C:\Temp"}
    with pytest.raises(windows.WindowsPrimitiveError, match="SystemRoot"):
        windows._sanitized_environment({"PATH": r"C:\untrusted"})
    with pytest.raises(windows.WindowsPrimitiveError, match="NUL"):
        windows._sanitized_environment({"SystemRoot": "bad\x00value"})


@WINDOWS_ONLY
def test_printer_discovery_is_bounded_and_read_only() -> None:
    printers = discover_local_printers(max_printers=256)
    assert isinstance(printers, tuple)
    assert all(printer.name and not printer.name.startswith("\\\\") for printer in printers)
    with pytest.raises(ValueError, match="between"):
        discover_local_printers(max_printers=0)
    with pytest.raises(ValueError, match="between"):
        discover_local_printers(max_printers=257)


@WINDOWS_ONLY
def test_media_input_reports_accepted_count_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[MediaKey] = []

    def fake_send(key: MediaKey) -> tuple[int, int | None]:
        calls.append(key)
        return 1, 5

    monkeypatch.setattr(windows, "_send_media_input", fake_send)
    result = send_media_key(MediaKey.PLAY_PAUSE)
    assert calls == [MediaKey.PLAY_PAUSE]
    assert result.requested_count == 2
    assert result.accepted_count == 1
    assert result.accepted is False
    assert result.last_error == 5

    with pytest.raises(TypeError, match="MediaKey"):
        send_media_key(0xB3)  # type: ignore[arg-type]

    monkeypatch.setattr(windows, "_send_media_input", lambda _key: (2, None))
    assert send_media_key(MediaKey.NEXT_TRACK).accepted is True


@WINDOWS_ONLY
def test_send_input_builds_one_keydown_keyup_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[int, int, int, int, int]] = []

    class FakeUser32:
        @staticmethod
        def SendInput(count: int, inputs: object, structure_size: int) -> int:
            typed = windows.ctypes.cast(inputs, windows.ctypes.POINTER(windows._INPUT))
            captured.append(
                (
                    count,
                    structure_size,
                    int(typed[0].keyboard.virtual_key),
                    int(typed[0].keyboard.flags),
                    int(typed[1].keyboard.flags),
                )
            )
            return 2

    monkeypatch.setattr(windows, "_user32", FakeUser32())
    accepted, error = windows._send_media_input(MediaKey.PLAY_PAUSE)
    assert accepted == 2 and error is None
    assert captured == [
        (
            2,
            sizeof(windows._INPUT),
            MediaKey.PLAY_PAUSE.value,
            0,
            windows._KEYEVENTF_KEYUP,
        )
    ]


def test_identity_comparison_and_component_safe_containment(tmp_path: Path) -> None:
    base = windows.FileIdentity(
        path=tmp_path / "file",
        final_path=r"\\?\Volume{one}\root\file",
        volume_serial=1,
        file_id="01",
        size=4,
        modified_100ns=10,
        link_count=1,
        attributes=0,
        sha256="a" * 64,
    )
    assert base.same_object(replace(base, path=tmp_path / "alias"))
    assert base.unchanged(replace(base, path=tmp_path / "alias"))
    assert not base.unchanged(replace(base, size=5))
    assert not base.unchanged(replace(base, sha256=None))
    assert windows._path_is_within(r"\\?\Volume{one}\root\child", r"\\?\Volume{one}\root")
    assert not windows._path_is_within(r"\\?\Volume{one}\rooted\child", r"\\?\Volume{one}\root")
