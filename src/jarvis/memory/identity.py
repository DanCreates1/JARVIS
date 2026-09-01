"""Pseudonymous local memory scope; identity, not authentication authority."""

from __future__ import annotations

import getpass
import hashlib
import platform


def local_memory_host_id(*, user_name: str | None = None, device_name: str | None = None) -> str:
    """Derive a stable per-user/per-device scope without storing a new credential.

    This identifier only partitions local data. It must never authenticate remote clients or
    authorize tools. Later remote phases replace the caller with authenticated host identity.
    """
    user = (user_name if user_name is not None else getpass.getuser()).strip().casefold()
    device = (device_name if device_name is not None else platform.node()).strip().casefold()
    if not user or not device:
        raise RuntimeError("local memory identity requires user and device names")
    material = f"jarvis-memory-host-v1\0{user}\0{device}".encode()
    return f"host-memory-{hashlib.sha256(material).hexdigest()}"
