"""Explicit local export adapter. Never discovers accounts or modifies source files."""

from __future__ import annotations

import asyncio
import ctypes
import hashlib
import os
import stat
from pathlib import Path

from .models import MAX_MESSAGE_BYTES, EmailError, EmailMessage, EmailThread, validate_id
from .processing import IsolatedEmailParser


def _local_volume(root: Path) -> None:
    if os.name != "nt":
        return
    query = ctypes.WinDLL("kernel32", use_last_error=True).GetDriveTypeW
    query.argtypes = [ctypes.c_wchar_p]
    query.restype = ctypes.c_uint
    if query(root.anchor) not in {2, 3, 6}:
        raise EmailError("local_volume_required")


class LocalEmailExports:
    def __init__(self, root: Path, *, parser: IsolatedEmailParser | None = None) -> None:
        if not root.is_absolute() or str(root).startswith(("\\\\", "//")):
            raise EmailError("local_absolute_root_required")
        self.root = root.absolute()
        _local_volume(self.root)
        self.parser = parser or IsolatedEmailParser()
        self._check(self.root, directory=True)

    def _check(self, path: Path, *, directory: bool = False) -> None:
        try:
            for component in (path, *path.parents):
                info = component.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise EmailError("export_link_denied")
            info = path.stat()
            if (directory and not stat.S_ISDIR(info.st_mode)) or (
                not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)
            ):
                raise EmailError("export_type_denied")
        except OSError:
            raise EmailError("export_unavailable") from None

    def _entries(self, directory: Path, limit: int) -> tuple[Path, ...]:
        self._check(directory, directory=True)
        entries: list[Path] = []
        try:
            with os.scandir(directory) as scan:
                for item in scan:
                    if len(entries) >= limit:
                        raise EmailError("export_capacity")
                    entries.append(Path(item.path))
        except OSError:
            raise EmailError("export_unavailable") from None
        return tuple(sorted(entries))

    async def list_threads(self) -> tuple[str, ...]:
        def snapshot() -> tuple[str, ...]:
            result = []
            for path in self._entries(self.root, 100):
                validate_id(path.name)
                self._check(path, directory=True)
                result.append(path.name)
            return tuple(result)

        return await asyncio.to_thread(snapshot)

    def _read(self, path: Path) -> bytes:
        self._check(path)
        try:
            before = path.stat()
            if before.st_size > MAX_MESSAGE_BYTES:
                raise EmailError("message_size")
            with path.open("rb") as stream:
                opened = os.fstat(stream.fileno())
                raw = stream.read(MAX_MESSAGE_BYTES + 1)
            after = path.stat()

            def identity(item: os.stat_result) -> tuple[int, int, int, int]:
                return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)

            if identity(before) != identity(opened) or identity(before) != identity(after):
                raise EmailError("export_changed")
            self._check(path)
            if not raw or len(raw) > MAX_MESSAGE_BYTES:
                raise EmailError("message_size")
            return raw
        except OSError:
            raise EmailError("export_unavailable") from None

    async def read_thread(self, thread_id: str) -> EmailThread:
        validate_id(thread_id)
        directory = self.root / thread_id
        paths = await asyncio.to_thread(self._entries, directory, 16)
        if not paths:
            raise EmailError("thread_empty")
        messages = []
        async with asyncio.timeout(30):
            for path in paths:
                if path.suffix != ".eml":
                    raise EmailError("export_type_denied")
                identifier = validate_id(path.stem)
                raw = await asyncio.to_thread(self._read, path)
                parsed = await self.parser.parse(raw, thread_id=thread_id, message_id=identifier)
                # Treat provider/parser output as untrusted even behind a typed contract.
                parsed = EmailMessage.model_validate(parsed)
                if (
                    parsed.id != identifier
                    or parsed.thread_id != thread_id
                    or parsed.sha256 != hashlib.sha256(raw).hexdigest()
                ):
                    raise EmailError("parser_provenance")
                messages.append(parsed)
        return EmailThread(id=thread_id, messages=tuple(messages))

    async def read_message(self, thread_id: str, message_id: str) -> EmailMessage:
        validate_id(message_id)
        for message in (await self.read_thread(thread_id)).messages:
            if message.id == message_id:
                return message
        raise EmailError("message_not_found")
