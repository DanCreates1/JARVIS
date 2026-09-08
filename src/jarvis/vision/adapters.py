"""Killable subprocess adapter for native Windows camera and screen capture."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from asyncio.subprocess import Process
from collections.abc import Mapping
from contextlib import suppress
from typing import Any

from .models import (
    MAX_FRAME_BYTES,
    CaptureError,
    CaptureFailureCode,
    CaptureRequest,
    EphemeralFrame,
    FrameMetadata,
)

_MAX_HEADER_BYTES = 8 * 1_024
_SAFE_ENVIRONMENT_NAMES = frozenset(
    {
        "ALLUSERSPROFILE",
        "APPDATA",
        "COMSPEC",
        "HOMEDRIVE",
        "HOMEPATH",
        "LOCALAPPDATA",
        "PATH",
        "PATHEXT",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "SYSTEMDRIVE",
        "SYSTEMROOT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    }
)


class IsolatedWindowsFrameSource:
    """Own native libraries in a child process that can be killed on timeout/cancel."""

    def __init__(
        self,
        *,
        python_executable: str | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self.python_executable = python_executable or sys.executable
        self.environment = dict(environment or os.environ)
        self._process: Process | None = None
        self._request: CaptureRequest | None = None

    async def open(self, request: CaptureRequest) -> None:
        if self._process is not None:
            raise CaptureError(CaptureFailureCode.SOURCE_UNAVAILABLE, "capture source is busy")
        if os.name != "nt":
            raise CaptureError(
                CaptureFailureCode.SOURCE_UNAVAILABLE,
                "Phase 7A native capture adapter requires Windows",
            )
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            process = await asyncio.create_subprocess_exec(
                self.python_executable,
                "-m",
                "jarvis.vision._capture_worker",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                env=_sanitized_environment(self.environment),
                creationflags=creationflags,
                limit=max(_MAX_HEADER_BYTES, MAX_FRAME_BYTES + _MAX_HEADER_BYTES),
            )
            self._process = process
            self._request = request
            await self._write(
                {
                    "op": "open",
                    "protocol": 1,
                    "request": request.model_dump(mode="json"),
                }
            )
            header = await self._read_header()
            if header.get("type") != "ready" or header.get("protocol") != 1:
                self._raise_worker_error(header, opening=True)
        except asyncio.CancelledError:
            await self._abort()
            raise
        except CaptureError:
            await self._abort()
            raise
        except Exception as exc:
            await self._abort()
            raise CaptureError(
                CaptureFailureCode.SOURCE_UNAVAILABLE,
                "native capture worker could not start",
            ) from exc

    async def capture(self, *, session_id: str, sequence: int) -> EphemeralFrame:
        if self._process is None or self._request is None:
            raise CaptureError(CaptureFailureCode.SOURCE_LOST, "capture source is not open")
        try:
            await self._write({"op": "capture", "session_id": session_id, "sequence": sequence})
            header = await self._read_header()
            if header.get("type") != "frame":
                self._raise_worker_error(header, opening=False)
            metadata = FrameMetadata.model_validate(
                {name: value for name, value in header.items() if name != "type"}
            )
            stdout = self._require_stdout()
            pixels = bytearray(await stdout.readexactly(metadata.byte_count))
            return EphemeralFrame(metadata, pixels)
        except asyncio.CancelledError:
            await self._abort()
            raise
        except CaptureError:
            raise
        except (asyncio.IncompleteReadError, ValueError, TypeError) as exc:
            await self._abort()
            raise CaptureError(
                CaptureFailureCode.MALFORMED_FRAME,
                "native capture worker returned a malformed frame",
            ) from exc
        except Exception as exc:
            await self._abort()
            raise CaptureError(
                CaptureFailureCode.SOURCE_LOST,
                "native capture worker failed",
            ) from exc

    async def close(self) -> None:
        process = self._process
        self._process = None
        self._request = None
        if process is None:
            return
        if process.returncode is None:
            try:
                stdin = process.stdin
                if stdin is not None and not stdin.is_closing():
                    stdin.write(b'{"op":"close"}\n')
                    await stdin.drain()
                await asyncio.wait_for(process.wait(), 0.25)
            except (Exception, asyncio.CancelledError):
                if process.returncode is None:
                    process.kill()
                with suppress(Exception):
                    await asyncio.wait_for(process.wait(), 0.5)
        if process.stdin is not None:
            process.stdin.close()

    async def _abort(self) -> None:
        process = self._process
        self._process = None
        self._request = None
        if process is None:
            return
        if process.returncode is None:
            process.kill()
            with suppress(Exception):
                await asyncio.wait_for(process.wait(), 0.5)
        if process.stdin is not None:
            process.stdin.close()

    async def _write(self, payload: Mapping[str, object]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise CaptureError(CaptureFailureCode.SOURCE_LOST, "capture worker input is closed")
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > _MAX_HEADER_BYTES:
            raise CaptureError(
                CaptureFailureCode.MALFORMED_FRAME,
                "capture worker command exceeds protocol limit",
            )
        process.stdin.write(encoded)
        await process.stdin.drain()

    async def _read_header(self) -> dict[str, Any]:
        raw = await self._require_stdout().readline()
        if not raw or len(raw) > _MAX_HEADER_BYTES or not raw.endswith(b"\n"):
            raise CaptureError(
                CaptureFailureCode.MALFORMED_FRAME,
                "capture worker header is missing or oversized",
            )
        try:
            value = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise CaptureError(
                CaptureFailureCode.MALFORMED_FRAME,
                "capture worker header is invalid",
            ) from exc
        if not isinstance(value, dict):
            raise CaptureError(
                CaptureFailureCode.MALFORMED_FRAME,
                "capture worker header is not an object",
            )
        return value

    def _require_stdout(self) -> asyncio.StreamReader:
        process = self._process
        if process is None or process.stdout is None:
            raise CaptureError(CaptureFailureCode.SOURCE_LOST, "capture worker output is closed")
        return process.stdout

    @staticmethod
    def _raise_worker_error(header: Mapping[str, Any], *, opening: bool) -> None:
        code = header.get("code")
        mapping = {
            "dependency_unavailable": CaptureFailureCode.DEPENDENCY_UNAVAILABLE,
            "source_unavailable": CaptureFailureCode.SOURCE_UNAVAILABLE,
            "source_lost": CaptureFailureCode.SOURCE_LOST,
            "malformed_frame": CaptureFailureCode.MALFORMED_FRAME,
            "invalid_protocol": CaptureFailureCode.MALFORMED_FRAME,
        }
        failure = mapping.get(code) if isinstance(code, str) else None
        if failure is None:
            failure = (
                CaptureFailureCode.SOURCE_UNAVAILABLE if opening else CaptureFailureCode.SOURCE_LOST
            )
        raise CaptureError(failure, "native capture worker rejected the request")


def _sanitized_environment(source: Mapping[str, str]) -> dict[str, str]:
    """Pass only OS/runtime basics; never pass JARVIS/provider secrets to native workers."""
    safe = {
        name: value for name, value in source.items() if name.upper() in _SAFE_ENVIRONMENT_NAMES
    }
    safe["PYTHONIOENCODING"] = "utf-8"
    safe["PYTHONUTF8"] = "1"
    return safe
