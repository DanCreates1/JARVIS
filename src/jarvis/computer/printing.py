"""Bounded Windows TEXT printing for an approved controlled UTF-8 text file.

The Win32 primitive accepts only an exact printer name, fixed ``TEXT`` datatype,
and validated text encoded strictly to the current Windows ANSI code page. Policy,
canonicalization, and broker approval stay in :class:`PrintControlledTextHandler`.
Import is safe away from Windows.
"""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import hmac
import os
from contextlib import suppress
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Final, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    ValidationError,
    field_validator,
)

from jarvis.core import (
    ApprovalRule,
    PermissionLevel,
    SensitivityClass,
    ToolConcurrency,
    ToolDefinition,
    ToolIdempotency,
    ToolRetryPolicy,
    ToolRisk,
    ToolSideEffect,
)
from jarvis.permissions import (
    ActionDefinition,
    ActionEffect,
    CanonicalAction,
    PostconditionEvidence,
    PostconditionStatus,
    RollbackReceipt,
    RollbackStatus,
    canonicalize,
    sha256_fingerprint,
)

from .actions import ActionPreparationError, ComputerActionError, PreparedAction
from .config import ComputerAccessPolicy
from .windows import (
    AllowedRootGuard,
    FileIdentity,
    IdentityMismatchError,
    UnsupportedPlatformError,
    WindowsPrimitiveError,
    _require_non_elevated,
)

_IS_WINDOWS: Final = os.name == "nt"
_TEXT_DATATYPE: Final = "TEXT"
_FIXED_DOCUMENT_NAME: Final = "JARVIS controlled text"
_WINDOWS_ANSI_CODEC: Final = "mbcs"
_MAX_TEXT_BYTES: Final = 10 * 1024 * 1024
_MAX_TEXT_COPIES: Final = 20

_IDENTIFIER = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_-]{0,63}$",
    ),
]
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class PrintSpoolError(WindowsPrimitiveError):
    """A TEXT job was not accepted completely by the Windows spooler."""


@dataclass(frozen=True, slots=True)
class PrintSubmissionReceipt:
    """Narrow evidence of spool acceptance, never physical print evidence."""

    job_id: int
    document_bytes: int
    spooled_bytes: int
    copies: int


class _DOC_INFO_1W(ctypes.Structure):
    _fields_ = [
        ("document_name", wintypes.LPWSTR),
        ("output_file", wintypes.LPWSTR),
        ("datatype", wintypes.LPWSTR),
    ]


_winspool: Any | None = None
if _IS_WINDOWS:
    _winspool = ctypes.WinDLL("winspool.drv", use_last_error=True)


def _configure_winspool() -> None:
    if not _IS_WINDOWS:
        return
    assert _winspool is not None
    _winspool.OpenPrinterW.argtypes = [
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.HANDLE),
        wintypes.LPVOID,
    ]
    _winspool.OpenPrinterW.restype = wintypes.BOOL
    _winspool.ClosePrinter.argtypes = [wintypes.HANDLE]
    _winspool.ClosePrinter.restype = wintypes.BOOL
    _winspool.StartDocPrinterW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPBYTE,
    ]
    _winspool.StartDocPrinterW.restype = wintypes.DWORD
    _winspool.StartPagePrinter.argtypes = [wintypes.HANDLE]
    _winspool.StartPagePrinter.restype = wintypes.BOOL
    _winspool.WritePrinter.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _winspool.WritePrinter.restype = wintypes.BOOL
    _winspool.EndPagePrinter.argtypes = [wintypes.HANDLE]
    _winspool.EndPagePrinter.restype = wintypes.BOOL
    _winspool.EndDocPrinter.argtypes = [wintypes.HANDLE]
    _winspool.EndDocPrinter.restype = wintypes.BOOL
    _winspool.AbortPrinter.argtypes = [wintypes.HANDLE]
    _winspool.AbortPrinter.restype = wintypes.BOOL


_configure_winspool()


def _spool_error(operation: str) -> PrintSpoolError:
    error = ctypes.get_last_error()
    return PrintSpoolError(f"{operation} failed with Win32 error {error}")


class _TextSpoolApi(Protocol):
    def open_printer(self, system_name: str) -> int: ...

    def start_doc(self, handle: int) -> int: ...

    def start_page(self, handle: int) -> None: ...

    def write(self, handle: int, payload: bytes) -> int: ...

    def end_page(self, handle: int) -> None: ...

    def end_doc(self, handle: int) -> None: ...

    def abort(self, handle: int) -> None: ...

    def close(self, handle: int) -> None: ...


class _Win32TextSpoolApi:
    def __init__(self) -> None:
        if not _IS_WINDOWS or _winspool is None:
            raise UnsupportedPlatformError("Windows printer APIs are unavailable")
        self._api = _winspool

    def open_printer(self, system_name: str) -> int:
        handle = wintypes.HANDLE()
        ctypes.set_last_error(0)
        if not self._api.OpenPrinterW(system_name, ctypes.byref(handle), None):
            raise _spool_error("OpenPrinterW")
        if handle.value is None:
            raise PrintSpoolError("OpenPrinterW returned a null handle")
        return int(handle.value)

    def start_doc(self, handle: int) -> int:
        info = _DOC_INFO_1W(_FIXED_DOCUMENT_NAME, None, _TEXT_DATATYPE)
        ctypes.set_last_error(0)
        job_id = int(
            self._api.StartDocPrinterW(
                handle,
                1,
                ctypes.cast(ctypes.byref(info), wintypes.LPBYTE),
            )
        )
        if job_id <= 0:
            raise _spool_error("StartDocPrinterW")
        return job_id

    def start_page(self, handle: int) -> None:
        ctypes.set_last_error(0)
        if not self._api.StartPagePrinter(handle):
            raise _spool_error("StartPagePrinter")

    def write(self, handle: int, payload: bytes) -> int:
        buffer = ctypes.create_string_buffer(payload, max(1, len(payload)))
        written = wintypes.DWORD()
        ctypes.set_last_error(0)
        if not self._api.WritePrinter(
            handle,
            ctypes.cast(buffer, wintypes.LPVOID),
            len(payload),
            ctypes.byref(written),
        ):
            raise _spool_error("WritePrinter")
        return int(written.value)

    def end_page(self, handle: int) -> None:
        ctypes.set_last_error(0)
        if not self._api.EndPagePrinter(handle):
            raise _spool_error("EndPagePrinter")

    def end_doc(self, handle: int) -> None:
        ctypes.set_last_error(0)
        if not self._api.EndDocPrinter(handle):
            raise _spool_error("EndDocPrinter")

    def abort(self, handle: int) -> None:
        ctypes.set_last_error(0)
        self._api.AbortPrinter(handle)

    def close(self, handle: int) -> None:
        ctypes.set_last_error(0)
        self._api.ClosePrinter(handle)


def _validate_spool_request(system_name: str, payload: bytes, copies: int) -> None:
    if not isinstance(system_name, str):
        raise TypeError("system_name must be a string")
    if (
        not system_name
        or system_name != system_name.strip()
        or len(system_name) > 256
        or any(ord(character) < 32 for character in system_name)
    ):
        raise ValueError("system_name must be one exact bounded configured printer name")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if len(payload) > _MAX_TEXT_BYTES:
        raise ValueError("payload exceeds the TEXT print primitive byte limit")
    if isinstance(copies, bool) or not isinstance(copies, int):
        raise TypeError("copies must be an integer")
    if not 1 <= copies <= _MAX_TEXT_COPIES:
        raise ValueError("copies must be between 1 and 20")


def _validate_text_characters(text: str, *, subject: str) -> None:
    for character in text:
        if character in {"\t", "\n", "\r"}:
            continue
        if not character.isprintable():
            raise ValueError(f"{subject} contains unsupported control characters")


def _decode_utf8_text(payload: bytes, *, subject: str) -> str:
    try:
        text = payload.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{subject} is not valid UTF-8") from exc
    _validate_text_characters(text, subject=subject)
    return text


def _encode_windows_text(text: str, *, subject: str) -> bytes:
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if not _IS_WINDOWS:
        raise UnsupportedPlatformError("Windows ANSI text encoding is unavailable")
    _validate_text_characters(text, subject=subject)
    try:
        encoded = text.encode(_WINDOWS_ANSI_CODEC, errors="strict")
    except UnicodeEncodeError as exc:
        raise ValueError(f"{subject} is not representable in the Windows ANSI code page") from exc
    if len(encoded) > _MAX_TEXT_BYTES:
        raise ValueError(f"{subject} exceeds the TEXT print primitive byte limit")
    return encoded


def _submit_with_api(
    api: _TextSpoolApi,
    system_name: str,
    payload: bytes,
    *,
    copies: int,
) -> PrintSubmissionReceipt:
    _validate_spool_request(system_name, payload, copies)
    handle = api.open_printer(system_name)
    document_started = False
    spooled_bytes = 0
    try:
        job_id = api.start_doc(handle)
        if job_id <= 0:
            raise PrintSpoolError("StartDocPrinterW returned an invalid job ID")
        document_started = True
        for _copy in range(copies):
            api.start_page(handle)
            written = api.write(handle, payload)
            if written != len(payload):
                raise PrintSpoolError(
                    "WritePrinter did not accept the complete controlled document"
                )
            spooled_bytes += written
            api.end_page(handle)
        api.end_doc(handle)
        document_started = False
        return PrintSubmissionReceipt(
            job_id=job_id,
            document_bytes=len(payload),
            spooled_bytes=spooled_bytes,
            copies=copies,
        )
    except BaseException:
        if document_started:
            with suppress(Exception):
                api.abort(handle)
        raise
    finally:
        api.close(handle)


def submit_text_job(
    system_name: str,
    text: str,
    *,
    copies: int = 1,
) -> PrintSubmissionReceipt:
    """Submit one fixed-TEXT job; success proves only complete spool acceptance.

    Each requested copy is a full StartPage/WritePrinter/EndPage sequence in the
    same job. WinPrint TEXT rendering and physical output remain spooler, driver,
    and printer dependent.
    """

    if not _IS_WINDOWS:
        raise UnsupportedPlatformError("Windows printer APIs are unavailable")
    _require_non_elevated()
    payload = _encode_windows_text(text, subject="text")
    return _submit_with_api(_Win32TextSpoolApi(), system_name, payload, copies=copies)


class _ArgumentsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _controlled_text_path(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or "\\" in value
        or "\x00" in value
        or any(ord(character) < 32 for character in value)
    ):
        raise ValueError("file must be a normalized forward-slash controlled path")
    candidate = PurePosixPath(value)
    if (
        candidate.is_absolute()
        or len(candidate.parts) > 16
        or any(component in {"", ".", ".."} for component in candidate.parts)
        or candidate.as_posix() != value
    ):
        raise ValueError("file must remain beneath the configured controlled root")
    for component in candidate.parts:
        if (
            component.endswith((" ", "."))
            or any(character in '<>:"|?*' for character in component)
            or component.split(".", maxsplit=1)[0].upper() in _WINDOWS_RESERVED_NAMES
        ):
            raise ValueError("file contains a forbidden Windows path component")
    if candidate.suffix.casefold() != ".txt":
        raise ValueError("only controlled .txt files can be printed")
    return value


class PrintControlledTextArguments(_ArgumentsModel):
    """Model-facing print selection: alias, whole text file, and bounded copies."""

    file: Annotated[str, Field(min_length=1, max_length=1_000)]
    printer_id: _IDENTIFIER
    copies: Annotated[int, Field(strict=True, ge=1, le=_MAX_TEXT_COPIES)] = 1

    @field_validator("file")
    @classmethod
    def validate_file(cls, value: str) -> str:
        return _controlled_text_path(value)


class _PrintEffect(_ArgumentsModel):
    printer_id: _IDENTIFIER
    job_id: Annotated[int, Field(strict=True, gt=0)]
    document_bytes: Annotated[int, Field(strict=True, ge=0)]
    spooled_bytes: Annotated[int, Field(strict=True, ge=0)]
    copies: Annotated[int, Field(strict=True, ge=1, le=_MAX_TEXT_COPIES)]


class PrintSubmitter(Protocol):
    def __call__(
        self,
        system_name: str,
        text: str,
        *,
        copies: int,
    ) -> PrintSubmissionReceipt: ...


def _identity_precondition(identity: FileIdentity) -> dict[str, JsonValue]:
    if identity.sha256 is None:
        raise ActionPreparationError("controlled text content hash was not captured")
    return {
        "volume_serial": identity.volume_serial,
        "file_id": identity.file_id,
        "size": identity.size,
        "modified_100ns": identity.modified_100ns,
        "sha256": identity.sha256,
    }


def _schema(policy: ComputerAccessPolicy) -> dict[str, JsonValue]:
    schema = PrintControlledTextArguments.model_json_schema()
    properties = schema.get("properties")
    if isinstance(properties, dict):
        printer = properties.get("printer_id")
        if isinstance(printer, dict):
            printer["enum"] = sorted(policy.printers)
        copies = properties.get("copies")
        if isinstance(copies, dict):
            copies["maximum"] = policy.max_print_copies
    return schema


class PrintControlledTextHandler:
    """Canonicalize and execute one exactly approved controlled text print."""

    def __init__(
        self,
        policy: ComputerAccessPolicy,
        *,
        guard: AllowedRootGuard | None = None,
        submit: PrintSubmitter = submit_text_job,
    ) -> None:
        if not policy.enabled:
            raise ValueError("computer access policy is disabled")
        if policy.maximum_permission_level < PermissionLevel.LEVEL_2:
            raise ValueError("printing requires permission Level 2")
        if not policy.printers:
            raise ValueError("printing requires at least one configured printer alias")
        self._root = policy.controlled_root
        self._printers = dict(policy.printers)
        self._max_bytes = policy.max_print_bytes
        self._max_copies = policy.max_print_copies
        self._guard = guard or AllowedRootGuard((self._root,))
        self._submit = submit
        tool = ToolDefinition(
            name="print_controlled_text",
            version="1",
            description=(
                "Print one complete bounded UTF-8 .txt file beneath the controlled root to one "
                "host-configured printer alias."
            ),
            input_schema=_schema(policy),
            permission_level=PermissionLevel.LEVEL_2,
            approval_rule=ApprovalRule.POLICY_OR_EXPLICIT,
            risk=ToolRisk.REVERSIBLE,
            side_effect=ToolSideEffect.EXTERNAL,
            sensitivity=SensitivityClass.PRIVATE,
            required_capabilities=("computer.printer.print",),
            timeout_seconds=30,
            max_result_bytes=4_096,
            max_result_items=5,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
            retry_policy=ToolRetryPolicy.NEVER,
            concurrency=ToolConcurrency.SERIAL_GLOBAL,
            postcondition=(
                "Win32 accepted every strictly encoded byte of every requested full-document "
                "TEXT page into one spool job; rendering and physical output are not verified."
            ),
            recovery=(
                "Never retry or roll back automatically after spool acceptance; inspect or "
                "cancel the configured printer queue manually if needed."
            ),
        )
        self._definition = ActionDefinition(
            tool=tool,
            supports_rollback=False,
            effect_may_outlive_cancellation=True,
        )

    @property
    def definition(self) -> ActionDefinition:
        return self._definition

    @property
    def input_model(self) -> type[BaseModel]:
        return PrintControlledTextArguments

    def _absolute(self, relative: str) -> Path:
        return self._root.joinpath(*PurePosixPath(relative).parts)

    def _read_exact_utf8(self, relative: str) -> tuple[FileIdentity, str, bytes]:
        identity = self._guard.probe_existing_file(
            self._absolute(relative),
            compute_sha256=True,
            for_mutation=True,
        )
        if identity.size > self._max_bytes:
            raise ActionPreparationError("controlled text file exceeds configured print byte limit")
        if identity.sha256 is None:
            raise ActionPreparationError("controlled text content hash was not captured")
        try:
            source_bytes = identity.path.read_bytes()
        except OSError as exc:
            raise ActionPreparationError("controlled text file could not be read") from exc
        payload_digest = hashlib.sha256(source_bytes).hexdigest()
        if len(source_bytes) != identity.size or not hmac.compare_digest(
            payload_digest, identity.sha256
        ):
            raise IdentityMismatchError("controlled text changed while it was read")
        try:
            text = _decode_utf8_text(source_bytes, subject="controlled text file")
            encoded = _encode_windows_text(text, subject="controlled text file")
        except ValueError as exc:
            raise ActionPreparationError(str(exc)) from exc
        if len(encoded) > self._max_bytes:
            raise ActionPreparationError(
                "encoded controlled text exceeds configured print byte limit"
            )
        self._guard.revalidate(identity, for_mutation=True)
        return identity, text, encoded

    def _precondition(
        self,
        parsed: PrintControlledTextArguments,
        identity: FileIdentity,
        encoded: bytes,
    ) -> dict[str, JsonValue]:
        printer = self._printers[parsed.printer_id]
        return {
            "file": parsed.file,
            "printer_id": parsed.printer_id,
            "printer_binding": sha256_fingerprint({"system_name": printer.system_name}),
            "copies": parsed.copies,
            "document_scope": "full",
            "spool_encoding": "windows-ansi-strict",
            "spool_bytes_per_copy": len(encoded),
            "spool_sha256": hashlib.sha256(encoded).hexdigest(),
            "file_identity": _identity_precondition(identity),
        }

    def _parse_arguments(self, arguments: object) -> PrintControlledTextArguments:
        parsed = PrintControlledTextArguments.model_validate(arguments)
        if parsed.printer_id not in self._printers:
            raise ActionPreparationError("printer alias is not configured")
        if parsed.copies > self._max_copies:
            raise ActionPreparationError("copies exceed the configured print limit")
        return parsed

    def prepare(self, arguments: BaseModel) -> PreparedAction:
        parsed = self._parse_arguments(arguments)
        identity, _text, encoded = self._read_exact_utf8(parsed.file)
        copy_label = "copy" if parsed.copies == 1 else "copies"
        return PreparedAction(
            normalized_arguments={
                "file": parsed.file,
                "printer_id": parsed.printer_id,
                "copies": parsed.copies,
            },
            human_effect=(
                f"Print the complete controlled text file '{parsed.file}' as {parsed.copies} "
                f"{copy_label} using printer alias '{parsed.printer_id}'."
            ),
            recovery_limits=(
                "Spool acceptance cannot be safely undone or retried automatically; queue "
                "inspection or cancellation is manual and may be too late."
            ),
            precondition=self._precondition(parsed, identity, encoded),
        )

    def _action_arguments(self, action: CanonicalAction) -> PrintControlledTextArguments:
        definition = self._definition
        if (
            action.action_id != definition.action_id
            or action.action_version != definition.version
            or action.permission_level is not definition.tool.permission_level
            or action.approval_rule is not definition.tool.approval_rule
        ):
            raise ComputerActionError("canonical print action does not match its definition")
        return self._parse_arguments(action.normalized_arguments)

    async def execute(self, action: CanonicalAction) -> ActionEffect:
        parsed = self._action_arguments(action)
        identity, text, encoded = self._read_exact_utf8(parsed.file)
        expected = self._precondition(parsed, identity, encoded)
        if canonicalize(action.precondition) != canonicalize(expected):
            raise IdentityMismatchError("canonical print precondition no longer matches")
        printer = self._printers[parsed.printer_id]
        observed = await asyncio.to_thread(
            self._submit,
            printer.system_name,
            text,
            copies=parsed.copies,
        )
        result: dict[str, JsonValue] = {
            "printer_id": parsed.printer_id,
            "job_id": observed.job_id,
            "document_bytes": observed.document_bytes,
            "spooled_bytes": observed.spooled_bytes,
            "copies": observed.copies,
        }
        return ActionEffect(result=result)

    async def verify(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
    ) -> PostconditionEvidence:
        parsed = self._action_arguments(action)
        observed: _PrintEffect | None = None
        if effect is not None:
            try:
                observed = _PrintEffect.model_validate(effect.result)
            except (TypeError, ValidationError):
                observed = None
        expected_bytes = action.precondition.get("spool_bytes_per_copy")
        passed = (
            observed is not None
            and observed.printer_id == parsed.printer_id
            and observed.copies == parsed.copies
            and observed.document_bytes == expected_bytes
            and observed.spooled_bytes == observed.document_bytes * observed.copies
        )
        return PostconditionEvidence(
            status=PostconditionStatus.PASSED if passed else PostconditionStatus.MISMATCH,
            summary=(
                "Win32 accepted the complete configured TEXT spool job; rendering and physical "
                "output remain unverified."
                if passed
                else "Complete Win32 spool acceptance could not be verified."
            ),
            detail={
                "printer_id": parsed.printer_id,
                "scope": "spool_acceptance_only",
                "physical_output_verified": False,
                "rendering_verified": False,
            },
        )

    async def rollback(
        self,
        action: CanonicalAction,
        effect: ActionEffect | None,
        *,
        reason: str,
    ) -> RollbackReceipt:
        del action, effect, reason
        return RollbackReceipt(
            status=RollbackStatus.UNAVAILABLE,
            summary=(
                "An accepted print job cannot be safely rolled back; inspect or cancel the "
                "printer queue manually."
            ),
        )
