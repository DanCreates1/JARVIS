from __future__ import annotations

import ctypes
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest
from pydantic import ValidationError

import jarvis.computer.printing as printing
from jarvis.computer.actions import ActionCanonicalizer, ActionPreparationError, PreparedAction
from jarvis.computer.config import ComputerAccessPolicy, PrinterPolicy
from jarvis.computer.printing import (
    PrintControlledTextArguments,
    PrintControlledTextHandler,
    PrintSpoolError,
    PrintSubmissionReceipt,
)
from jarvis.computer.windows import (
    AllowedRootGuard,
    FileIdentity,
    IdentityMismatchError,
    UnsafePathError,
    UnsupportedPlatformError,
)
from jarvis.core import (
    PermissionLevel,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolSideEffect,
)
from jarvis.permissions import (
    ActionDefinition,
    ActionHandler,
    CanonicalAction,
    PostconditionStatus,
    RollbackStatus,
)
from tests.fakes.phase3 import FIXED_NOW, actor


class FakeSpoolApi:
    def __init__(self, *, partial_write: bool = False, fail_at: str | None = None) -> None:
        self.partial_write = partial_write
        self.fail_at = fail_at
        self.calls: list[tuple[object, ...]] = []

    def _fail(self, stage: str) -> None:
        if self.fail_at == stage:
            raise PrintSpoolError(f"fake {stage} failure")

    def open_printer(self, system_name: str) -> int:
        self.calls.append(("open", system_name))
        self._fail("open")
        return 41

    def start_doc(self, handle: int) -> int:
        self.calls.append(("start_doc", handle))
        self._fail("start_doc")
        return 731

    def start_page(self, handle: int) -> None:
        self.calls.append(("start_page", handle))
        self._fail("start_page")

    def write(self, handle: int, payload: bytes) -> int:
        self.calls.append(("write", handle, payload))
        self._fail("write")
        return max(0, len(payload) - 1) if self.partial_write else len(payload)

    def end_page(self, handle: int) -> None:
        self.calls.append(("end_page", handle))
        self._fail("end_page")

    def end_doc(self, handle: int) -> None:
        self.calls.append(("end_doc", handle))
        self._fail("end_doc")

    def abort(self, handle: int) -> None:
        self.calls.append(("abort", handle))

    def close(self, handle: int) -> None:
        self.calls.append(("close", handle))


class FakeGuard:
    def __init__(
        self,
        root: Path,
        *,
        link_count: int = 1,
        attributes: int = 0,
    ) -> None:
        self.root = root
        self.link_count = link_count
        self.attributes = attributes
        self.probed: list[Path] = []
        self.revalidated: list[FileIdentity] = []
        self.probe_mutation_modes: list[bool] = []
        self.revalidate_mutation_modes: list[bool] = []

    def _identity(self, path: Path, *, compute_sha256: bool) -> FileIdentity:
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest() if compute_sha256 else None
        return FileIdentity(
            path=path,
            final_path=rf"\\?\Volume{{fake}}\controlled\{path.name}",
            volume_serial=901,
            file_id="ab" * 16,
            size=len(payload),
            modified_100ns=1_234_567,
            link_count=self.link_count,
            attributes=self.attributes,
            sha256=digest,
        )

    @staticmethod
    def _require_safe_effect_source(identity: FileIdentity, *, enabled: bool) -> None:
        if not enabled:
            return
        if identity.link_count != 1:
            raise UnsafePathError("mutation of multiply-linked files is not accepted")
        if identity.attributes & (0x00001000 | 0x00040000 | 0x00400000):
            raise UnsafePathError("mutation of offline or recall-on-access files is not accepted")

    def probe_existing_file(
        self,
        path: str | os.PathLike[str],
        *,
        compute_sha256: bool = False,
        for_mutation: bool = False,
    ) -> FileIdentity:
        candidate = Path(path)
        assert candidate.is_relative_to(self.root)
        self.probed.append(candidate)
        self.probe_mutation_modes.append(for_mutation)
        identity = self._identity(candidate, compute_sha256=compute_sha256)
        self._require_safe_effect_source(identity, enabled=for_mutation)
        return identity

    def revalidate(
        self,
        expected: FileIdentity,
        *,
        for_mutation: bool = False,
    ) -> FileIdentity:
        self.revalidated.append(expected)
        self.revalidate_mutation_modes.append(for_mutation)
        current = self._identity(expected.path, compute_sha256=expected.sha256 is not None)
        self._require_safe_effect_source(current, enabled=for_mutation)
        if not expected.unchanged(current):
            raise IdentityMismatchError("fake identity changed")
        return current


def policy(
    root: Path,
    *,
    max_bytes: int = 1_024,
    max_copies: int = 2,
    enabled: bool = True,
    maximum_level: PermissionLevel = PermissionLevel.LEVEL_2,
) -> ComputerAccessPolicy:
    return ComputerAccessPolicy(
        enabled=enabled,
        maximum_permission_level=maximum_level,
        controlled_root=root,
        printers={"office": PrinterPolicy(system_name="Exact Office Queue")},
        max_print_bytes=max_bytes,
        max_print_copies=max_copies,
    )


def canonical_action(
    definition: ActionDefinition,
    prepared: PreparedAction,
    *,
    key: str = "print-action-1",
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


def handler(
    root: Path,
    submit: printing.PrintSubmitter,
    *,
    configured: ComputerAccessPolicy | None = None,
) -> tuple[PrintControlledTextHandler, FakeGuard]:
    guard = FakeGuard(root)
    return (
        PrintControlledTextHandler(
            configured or policy(root),
            guard=cast(AllowedRootGuard, guard),
            submit=submit,
        ),
        guard,
    )


def test_text_spool_engine_writes_each_complete_copy_in_one_job() -> None:
    api = FakeSpoolApi()

    receipt = printing._submit_with_api(api, "Exact Office Queue", b"hello\n", copies=2)

    assert receipt == PrintSubmissionReceipt(
        job_id=731,
        document_bytes=6,
        spooled_bytes=12,
        copies=2,
    )
    assert api.calls == [
        ("open", "Exact Office Queue"),
        ("start_doc", 41),
        ("start_page", 41),
        ("write", 41, b"hello\n"),
        ("end_page", 41),
        ("start_page", 41),
        ("write", 41, b"hello\n"),
        ("end_page", 41),
        ("end_doc", 41),
        ("close", 41),
    ]


def test_text_spool_engine_aborts_and_never_completes_after_partial_write() -> None:
    api = FakeSpoolApi(partial_write=True)

    with pytest.raises(PrintSpoolError, match="complete controlled document"):
        printing._submit_with_api(api, "Exact Office Queue", b"unsafe to truncate", copies=1)

    assert ("abort", 41) in api.calls
    assert api.calls[-1] == ("close", 41)
    assert not any(call[0] in {"end_page", "end_doc"} for call in api.calls)


@pytest.mark.parametrize("stage", ["start_page", "write", "end_page", "end_doc"])
def test_text_spool_engine_aborts_every_failure_after_start_doc(stage: str) -> None:
    api = FakeSpoolApi(fail_at=stage)

    with pytest.raises(PrintSpoolError, match=f"fake {stage} failure"):
        printing._submit_with_api(api, "Exact Office Queue", b"text", copies=1)

    assert ("abort", 41) in api.calls
    assert api.calls[-1] == ("close", 41)


def test_text_spool_engine_does_not_abort_when_start_doc_never_created_job() -> None:
    api = FakeSpoolApi(fail_at="start_doc")

    with pytest.raises(PrintSpoolError, match="fake start_doc failure"):
        printing._submit_with_api(api, "Exact Office Queue", b"text", copies=1)

    assert not any(call[0] == "abort" for call in api.calls)
    assert api.calls[-1] == ("close", 41)


@pytest.mark.parametrize(
    ("system_name", "payload", "copies", "error"),
    [
        (" queue", b"text", 1, ValueError),
        ("queue\x00escape", b"text", 1, ValueError),
        ("queue", b"text", 0, ValueError),
        ("queue", b"text", 21, ValueError),
        ("queue", b"text", True, TypeError),
        ("queue", bytearray(b"text"), 1, TypeError),
    ],
)
def test_text_spool_engine_rejects_ambiguous_or_unbounded_inputs(
    system_name: object,
    payload: object,
    copies: object,
    error: type[Exception],
) -> None:
    api = FakeSpoolApi()

    with pytest.raises(error):
        printing._submit_with_api(
            api,
            cast(str, system_name),
            cast(bytes, payload),
            copies=cast(int, copies),
        )

    assert api.calls == []


def test_public_primitive_fails_closed_off_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(printing, "_IS_WINDOWS", False)

    with pytest.raises(UnsupportedPlatformError):
        printing.submit_text_job("Exact Office Queue", "text")


def test_public_primitive_enforces_elevation_guard_before_spooling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = FakeSpoolApi()
    guarded: list[bool] = []
    monkeypatch.setattr(printing, "_IS_WINDOWS", True)
    monkeypatch.setattr(printing, "_require_non_elevated", lambda: guarded.append(True))
    monkeypatch.setattr(printing, "_Win32TextSpoolApi", lambda: api)

    receipt = printing.submit_text_job("Exact Office Queue", "text")

    assert guarded == [True]
    assert receipt.job_id == 731
    assert ("write", 41, b"text") in api.calls


def test_text_encoding_is_strict_and_rejects_printer_control_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(printing, "_IS_WINDOWS", True)
    monkeypatch.setattr(printing, "_WINDOWS_ANSI_CODEC", "ascii")

    assert printing._encode_windows_text("plain\ttext\r\n", subject="text") == b"plain\ttext\r\n"
    with pytest.raises(ValueError, match="unsupported control characters"):
        printing._encode_windows_text("plain\x1bcommand", subject="text")
    with pytest.raises(ValueError, match="not representable"):
        printing._encode_windows_text("caf\u00e9", subject="text")


def test_win32_adapter_fixes_document_name_and_text_datatype(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[object, ...]] = []

    class FakeWinspool:
        @staticmethod
        def OpenPrinterW(system_name: str, raw_handle: object, defaults: object) -> bool:
            handle = ctypes.cast(raw_handle, ctypes.POINTER(printing.wintypes.HANDLE))
            handle.contents.value = 41
            captured.append(("open", system_name, defaults))
            return True

        @staticmethod
        def StartDocPrinterW(handle: int, level: int, raw_info: object) -> int:
            info = ctypes.cast(
                raw_info,
                ctypes.POINTER(printing._DOC_INFO_1W),
            ).contents
            captured.append(
                ("start_doc", handle, level, info.document_name, info.output_file, info.datatype)
            )
            return 55

        @staticmethod
        def StartPagePrinter(handle: int) -> bool:
            captured.append(("start_page", handle))
            return True

        @staticmethod
        def WritePrinter(
            handle: int,
            buffer: object,
            size: int,
            raw_written: object,
        ) -> bool:
            written = ctypes.cast(raw_written, ctypes.POINTER(printing.wintypes.DWORD))
            written.contents.value = size
            captured.append(("write", handle, ctypes.string_at(buffer, size)))
            return True

        @staticmethod
        def EndPagePrinter(handle: int) -> bool:
            captured.append(("end_page", handle))
            return True

        @staticmethod
        def EndDocPrinter(handle: int) -> bool:
            captured.append(("end_doc", handle))
            return True

        @staticmethod
        def AbortPrinter(handle: int) -> bool:
            captured.append(("abort", handle))
            return True

        @staticmethod
        def ClosePrinter(handle: int) -> bool:
            captured.append(("close", handle))
            return True

    monkeypatch.setattr(printing, "_IS_WINDOWS", True)
    monkeypatch.setattr(printing, "_winspool", FakeWinspool())

    api = printing._Win32TextSpoolApi()
    handle = api.open_printer("Exact Office Queue")
    assert handle == 41
    assert api.start_doc(handle) == 55
    api.start_page(handle)
    assert api.write(handle, b"text\x00payload") == 12
    api.end_page(handle)
    api.end_doc(handle)
    api.abort(handle)
    api.close(handle)
    assert captured == [
        ("open", "Exact Office Queue", None),
        ("start_doc", 41, 1, "JARVIS controlled text", None, "TEXT"),
        ("start_page", 41),
        ("write", 41, b"text\x00payload"),
        ("end_page", 41),
        ("end_doc", 41),
        ("abort", 41),
        ("close", 41),
    ]


def test_prepare_exposes_only_alias_relative_file_and_full_document_scope(tmp_path: Path) -> None:
    document = tmp_path / "notes" / "agenda.txt"
    document.parent.mkdir()
    document.write_bytes(b"hello, printer\n")
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler, guard = handler(tmp_path, submit)

    prepared = action_handler.prepare(
        PrintControlledTextArguments(file="notes/agenda.txt", printer_id="office", copies=2)
    )

    assert isinstance(action_handler, ActionCanonicalizer)
    assert isinstance(action_handler, ActionHandler)
    assert prepared.normalized_arguments == {
        "file": "notes/agenda.txt",
        "printer_id": "office",
        "copies": 2,
    }
    assert prepared.precondition["document_scope"] == "full"
    assert prepared.precondition["spool_encoding"] == "windows-ansi-strict"
    assert prepared.precondition["spool_bytes_per_copy"] == len(b"hello, printer\n")
    assert prepared.precondition["spool_sha256"] == hashlib.sha256(b"hello, printer\n").hexdigest()
    assert prepared.precondition["file_identity"] == {
        "volume_serial": 901,
        "file_id": "ab" * 16,
        "size": len(b"hello, printer\n"),
        "modified_100ns": 1_234_567,
        "sha256": hashlib.sha256(b"hello, printer\n").hexdigest(),
    }
    serialized = json.dumps(prepared.model_dump(mode="json"))
    assert "Exact Office Queue" not in serialized
    assert guard.probed == [document]
    assert len(guard.revalidated) == 1
    assert guard.probe_mutation_modes == [True]
    assert guard.revalidate_mutation_modes == [True]
    schema = action_handler.definition.tool.input_schema.get("properties")
    assert isinstance(schema, dict)
    printer_schema = schema.get("printer_id")
    copy_schema = schema.get("copies")
    assert isinstance(printer_schema, dict)
    assert isinstance(copy_schema, dict)
    assert printer_schema.get("enum") == ["office"]
    assert copy_schema.get("maximum") == 2
    assert "pages" not in schema


@pytest.mark.parametrize(
    ("link_count", "attributes", "match"),
    [
        (2, 0, "multiply-linked"),
        (1, 0x00001000, "offline or recall"),
        (1, 0x00040000, "offline or recall"),
        (1, 0x00400000, "offline or recall"),
    ],
)
def test_print_source_rejects_fake_hardlink_offline_and_recall_files(
    tmp_path: Path,
    link_count: int,
    attributes: int,
    match: str,
) -> None:
    document = tmp_path / "document.txt"
    document.write_text("safe", encoding="utf-8")
    guard = FakeGuard(tmp_path, link_count=link_count, attributes=attributes)
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler = PrintControlledTextHandler(
        policy(tmp_path),
        guard=cast(AllowedRootGuard, guard),
        submit=submit,
    )

    with pytest.raises(UnsafePathError, match=match):
        action_handler.prepare(
            PrintControlledTextArguments(file="document.txt", printer_id="office")
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows hardlink identity regression")
def test_real_windows_print_source_hardlink_is_rejected(tmp_path: Path) -> None:
    document = tmp_path / "document.txt"
    alias = tmp_path / "alias.txt"
    document.write_text("safe", encoding="utf-8")
    os.link(document, alias)
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler = PrintControlledTextHandler(policy(tmp_path), submit=submit)

    with pytest.raises(UnsafePathError, match="multiply-linked"):
        action_handler.prepare(
            PrintControlledTextArguments(file="document.txt", printer_id="office")
        )


@pytest.mark.parametrize(
    "arguments",
    [
        {"file": "../outside.txt", "printer_id": "office", "copies": 1},
        {"file": "notes\\agenda.txt", "printer_id": "office", "copies": 1},
        {"file": "notes/agenda.pdf", "printer_id": "office", "copies": 1},
        {"file": "notes/agenda.txt", "printer_id": "unknown", "copies": 1},
        {"file": "notes/agenda.txt", "printer_id": "office", "copies": 3},
        {
            "file": "notes/agenda.txt",
            "printer_id": "office",
            "copies": 1,
            "pages": "1-2",
        },
    ],
)
def test_prepare_rejects_paths_aliases_copy_overrides_and_page_claims(
    tmp_path: Path,
    arguments: dict[str, object],
) -> None:
    document = tmp_path / "notes" / "agenda.txt"
    document.parent.mkdir()
    document.write_text("safe", encoding="utf-8")
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler, _guard = handler(tmp_path, submit)

    with pytest.raises((ActionPreparationError, ValidationError, ValueError)):
        parsed = action_handler.input_model.model_validate(arguments)
        action_handler.prepare(parsed)


@pytest.mark.parametrize(
    ("payload", "max_bytes", "match"),
    [
        (b"\xff\xfe", 10, "not valid UTF-8"),
        (b"text\x1bprinter-command", 100, "unsupported control characters"),
        (b"too many bytes", 4, "exceeds configured print byte limit"),
    ],
)
def test_prepare_rejects_invalid_utf8_and_oversized_documents(
    tmp_path: Path,
    payload: bytes,
    max_bytes: int,
    match: str,
) -> None:
    document = tmp_path / "document.txt"
    document.write_bytes(payload)
    configured = policy(tmp_path, max_bytes=max_bytes)
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler, _guard = handler(tmp_path, submit, configured=configured)

    with pytest.raises(ActionPreparationError, match=match):
        action_handler.prepare(
            PrintControlledTextArguments(file="document.txt", printer_id="office")
        )


def test_prepare_rejects_text_not_representable_in_windows_ansi(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "document.txt"
    document.write_text("caf\u00e9", encoding="utf-8")
    monkeypatch.setattr(printing, "_WINDOWS_ANSI_CODEC", "ascii")
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler, _guard = handler(tmp_path, submit)

    with pytest.raises(ActionPreparationError, match="not representable"):
        action_handler.prepare(
            PrintControlledTextArguments(file="document.txt", printer_id="office")
        )


def test_prepare_applies_policy_byte_limit_after_text_encoding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = tmp_path / "document.txt"
    document.write_bytes(b"four")
    monkeypatch.setattr(printing, "_WINDOWS_ANSI_CODEC", "utf-16-le")
    configured = policy(tmp_path, max_bytes=4)
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler, _guard = handler(tmp_path, submit, configured=configured)

    with pytest.raises(ActionPreparationError, match="encoded controlled text exceeds"):
        action_handler.prepare(
            PrintControlledTextArguments(file="document.txt", printer_id="office")
        )


@pytest.mark.asyncio
async def test_handler_submits_exact_configured_name_and_verifies_spool_scope(
    tmp_path: Path,
) -> None:
    document = tmp_path / "document.txt"
    source_bytes = b"full document\nsecond line\n"
    text = "full document\nsecond line\n"
    document.write_bytes(source_bytes)
    submissions: list[tuple[str, str, int]] = []

    def submit(system_name: str, submitted: str, *, copies: int) -> PrintSubmissionReceipt:
        submissions.append((system_name, submitted, copies))
        encoded = submitted.encode("mbcs", errors="strict")
        return PrintSubmissionReceipt(
            job_id=93,
            document_bytes=len(encoded),
            spooled_bytes=len(encoded) * copies,
            copies=copies,
        )

    action_handler, _guard = handler(tmp_path, cast(printing.PrintSubmitter, submit))
    prepared = action_handler.prepare(
        PrintControlledTextArguments(file="document.txt", printer_id="office", copies=2)
    )
    action = canonical_action(action_handler.definition, prepared)

    effect = await action_handler.execute(action)
    evidence = await action_handler.verify(action, effect)
    rollback = await action_handler.rollback(action, effect, reason="test")

    assert submissions == [("Exact Office Queue", text, 2)]
    assert effect.result == {
        "printer_id": "office",
        "job_id": 93,
        "document_bytes": len(source_bytes),
        "spooled_bytes": len(source_bytes) * 2,
        "copies": 2,
    }
    assert "Exact Office Queue" not in json.dumps(effect.model_dump(mode="json"))
    assert evidence.status is PostconditionStatus.PASSED
    assert evidence.detail == {
        "printer_id": "office",
        "scope": "spool_acceptance_only",
        "physical_output_verified": False,
        "rendering_verified": False,
    }
    assert rollback.status is RollbackStatus.UNAVAILABLE


@pytest.mark.asyncio
async def test_handler_refuses_stale_file_identity_before_submission(tmp_path: Path) -> None:
    document = tmp_path / "document.txt"
    document.write_text("approved", encoding="utf-8")
    submissions: list[str] = []

    def submit(_system_name: str, text: str, *, copies: int) -> PrintSubmissionReceipt:
        submissions.append(text)
        encoded = text.encode("mbcs", errors="strict")
        return PrintSubmissionReceipt(1, len(encoded), len(encoded) * copies, copies)

    action_handler, _guard = handler(tmp_path, cast(printing.PrintSubmitter, submit))
    prepared = action_handler.prepare(
        PrintControlledTextArguments(file="document.txt", printer_id="office")
    )
    action = canonical_action(action_handler.definition, prepared)
    document.write_text("changed!", encoding="utf-8")

    with pytest.raises(IdentityMismatchError, match="precondition no longer matches"):
        await action_handler.execute(action)

    assert submissions == []


@pytest.mark.asyncio
async def test_handler_reports_mismatch_for_incomplete_fake_receipt(tmp_path: Path) -> None:
    document = tmp_path / "document.txt"
    document.write_text("approved", encoding="utf-8")

    def submit(_system_name: str, text: str, *, copies: int) -> PrintSubmissionReceipt:
        encoded = text.encode("mbcs", errors="strict")
        return PrintSubmissionReceipt(1, len(encoded), len(encoded) * copies - 1, copies)

    action_handler, _guard = handler(tmp_path, cast(printing.PrintSubmitter, submit))
    prepared = action_handler.prepare(
        PrintControlledTextArguments(file="document.txt", printer_id="office", copies=2)
    )
    action = canonical_action(action_handler.definition, prepared)

    evidence = await action_handler.verify(action, await action_handler.execute(action))

    assert evidence.status is PostconditionStatus.MISMATCH


def test_handler_definition_declares_level2_external_exact_no_retry_no_rollback(
    tmp_path: Path,
) -> None:
    submit = cast(printing.PrintSubmitter, lambda *_args, **_kwargs: None)
    action_handler, _guard = handler(tmp_path, submit)
    definition = action_handler.definition

    assert definition.tool.permission_level is PermissionLevel.LEVEL_2
    assert definition.tool.side_effect is ToolSideEffect.EXTERNAL
    assert definition.tool.idempotency is ToolIdempotency.NON_IDEMPOTENT
    assert definition.tool.retry_policy is ToolRetryPolicy.NEVER
    assert definition.tool.max_result_items == 5
    assert definition.supports_rollback is False
    assert definition.effect_may_outlive_cancellation is True
    assert "physical output" in definition.tool.postcondition
    assert "Never retry" in definition.tool.recovery


@pytest.mark.parametrize(
    ("enabled", "maximum_level", "match"),
    [
        (False, PermissionLevel.LEVEL_2, "disabled"),
        (True, PermissionLevel.LEVEL_1, "Level 2"),
    ],
)
def test_handler_requires_enabled_level2_policy(
    tmp_path: Path,
    enabled: bool,
    maximum_level: PermissionLevel,
    match: str,
) -> None:
    configured = policy(tmp_path, enabled=enabled, maximum_level=maximum_level)

    with pytest.raises(ValueError, match=match):
        PrintControlledTextHandler(
            configured,
            guard=cast(AllowedRootGuard, FakeGuard(tmp_path)),
        )
