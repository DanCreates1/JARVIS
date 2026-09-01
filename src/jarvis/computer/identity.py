"""Trusted local Windows actor identity for Phase 3 approvals and grants."""

from __future__ import annotations

import ctypes
import hashlib
import hmac
import os
import secrets
import tempfile
from collections.abc import Callable, Iterable
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from jarvis.computer.windows import WindowsIdentityProbe
from jarvis.permissions import (
    ActorContext,
    AuthenticationAssurance,
    InteractionInterface,
)

_KEY_BYTES: Final = 32


class IdentityKeyStore:
    """Create/load one private pseudonymous-identity key outside the repository."""

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir.expanduser().resolve(strict=False)
        self._path = self._data_dir / "computer-identity.key"

    @property
    def path(self) -> Path:
        return self._path

    def load_or_create(self) -> bytes:
        if self._path.exists():
            return self._load()
        self._data_dir.mkdir(parents=True, exist_ok=True)
        key = secrets.token_bytes(_KEY_BYTES)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=self._data_dir,
                prefix=".computer-identity-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary_name = handle.name
                handle.write(key)
                handle.flush()
                os.fsync(handle.fileno())
            assert temporary_name is not None
            os.chmod(temporary_name, 0o600)
            try:
                os.link(temporary_name, self._path)
            except FileExistsError:
                return self._load()
            return key
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)

    def _load(self) -> bytes:
        if self._path.is_symlink() or not self._path.is_file():
            raise ValueError("computer identity key must be a regular non-link file")
        key = self._path.read_bytes()
        if len(key) != _KEY_BYTES:
            raise ValueError("computer identity key has an invalid size")
        return key


SessionProbe = Callable[[], int]
Now = Callable[[], datetime]
IdentityProbeFactory = Callable[[bytes], WindowsIdentityProbe]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _windows_session_id() -> int:
    if os.name != "nt":
        raise OSError("local computer identity requires Windows")
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    kernel32.ProcessIdToSessionId.restype = wintypes.BOOL
    session_id = wintypes.DWORD()
    if not kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session_id)):
        error = ctypes.get_last_error()
        raise OSError(error, "ProcessIdToSessionId failed")
    return int(session_id.value)


class LocalActorFactory:
    """Build authority context from native identity, never request metadata."""

    def __init__(
        self,
        key_store: IdentityKeyStore,
        *,
        session_probe: SessionProbe = _windows_session_id,
        identity_probe_factory: IdentityProbeFactory = WindowsIdentityProbe,
        now: Now = _utc_now,
    ) -> None:
        self._key_store = key_store
        self._session_probe = session_probe
        self._identity_probe_factory = identity_probe_factory
        self._now = now

    def create(
        self,
        *,
        interface: InteractionInterface,
        capabilities: Iterable[str],
    ) -> ActorContext:
        key = self._key_store.load_or_create()
        identity = self._identity_probe_factory(key).probe(require_non_elevated=True)
        native_session = self._session_probe()
        if not 0 <= native_session <= 0xFFFFFFFF:
            raise ValueError("Windows session ID is outside the expected range")
        session_hash = hmac.new(
            key,
            f"session\0{identity.user_id_hash}\0{native_session}".encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        authenticated_at = self._now()
        if authenticated_at.tzinfo is None or authenticated_at.utcoffset() is None:
            raise ValueError("identity clock must return a timezone-aware datetime")
        return ActorContext(
            host_id=f"host-{identity.user_id_hash}",
            session_id=f"session-{session_hash}",
            device_id=f"device-{identity.device_id_hash}",
            interface=interface,
            assurance=AuthenticationAssurance.LOCAL_SESSION,
            authenticated_at=authenticated_at.astimezone(UTC),
            capabilities=tuple(sorted(set(capabilities))),
        )
