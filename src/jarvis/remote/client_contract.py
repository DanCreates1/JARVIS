"""Stable capability metadata shared by PWA and native clients."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Final

CLIENT_API_PROTOCOL_VERSION: Final = "1"
CLIENT_CAPABILITIES: Final = (
    "client.chat",
    "client.events",
    "client.proactivity",
    "client.status",
    "client.tasks",
    "enrollment.v1",
    "enrollment.v2.authority-bound",
    "identity.read",
    "sessions.browser-cookie",
    "sessions.signed-bearer",
    "signed-request.v1",
    "topology.negotiate",
)
CLIENT_COMPATIBILITY_FLAGS: Final = {
    "pwa_v1": True,
    "enrollment_v1": True,
    "enrollment_v2_authority_binding": True,
    "signed_request_v1": True,
}


def client_contract_metadata(*, server_time: datetime | None = None) -> dict[str, object]:
    now = server_time or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("server time must be timezone-aware")
    return {
        "protocol_version": CLIENT_API_PROTOCOL_VERSION,
        "server_time": now.astimezone(UTC),
        "capabilities": CLIENT_CAPABILITIES,
        "compatibility": CLIENT_COMPATIBILITY_FLAGS,
    }
