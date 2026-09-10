"""Deterministic request and enrollment signature profile for Phase 8A."""

from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final

REQUEST_AUDIENCE: Final = "jarvis-api"
SIGNATURE_HEADERS: Final = frozenset(
    {
        "authorization",
        "x-jarvis-audience",
        "x-jarvis-date",
        "x-jarvis-device",
        "x-jarvis-key-version",
        "x-jarvis-nonce",
        "x-jarvis-signature",
    }
)
_BASE64URL_RE: Final = re.compile(r"^[A-Za-z0-9_-]+$")
_AUTHORITY_RE: Final = re.compile(r"^(?:[a-z0-9.-]+|\[[0-9a-f:]+\])(?::[0-9]{1,5})?$")
_NONCE_RE: Final = re.compile(r"^[A-Za-z0-9_-]{22,128}$")


@dataclass(frozen=True, slots=True)
class SignedRequest:
    method: str
    authority: str
    path: str
    query: str
    body: bytes
    device_id: str
    key_version: int
    audience: str
    timestamp: datetime
    nonce: str
    session_token: str | None


def encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode_base64url(value: str, *, expected_bytes: int | None = None) -> bytes:
    if not value or "=" in value or _BASE64URL_RE.fullmatch(value) is None:
        raise ValueError("value is not canonical unpadded base64url")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("value is not valid base64url") from exc
    if encode_base64url(decoded) != value:
        raise ValueError("value is not canonical base64url")
    if expected_bytes is not None and len(decoded) != expected_bytes:
        raise ValueError(f"decoded value must be {expected_bytes} bytes")
    return decoded


def canonical_request(request: SignedRequest) -> bytes:
    method = request.method.upper()
    authority = request.authority.casefold()
    if not method.isascii() or not method.isalpha() or not (1 <= len(method) <= 16):
        raise ValueError("invalid HTTP method")
    if _AUTHORITY_RE.fullmatch(authority) is None:
        raise ValueError("invalid HTTP authority")
    port = authority.rpartition(":")[2]
    if port.isdecimal() and int(port) > 65_535:
        raise ValueError("invalid HTTP authority port")
    if not request.path.startswith("/") or "#" in request.path or "\n" in request.path:
        raise ValueError("invalid raw request path")
    if "#" in request.query or "\n" in request.query:
        raise ValueError("invalid raw query")
    if not request.device_id or "\n" in request.device_id:
        raise ValueError("invalid device ID")
    if request.key_version < 1:
        raise ValueError("invalid key version")
    if request.audience != REQUEST_AUDIENCE:
        raise ValueError("invalid audience")
    if request.timestamp.tzinfo is None or request.timestamp.utcoffset() is None:
        raise ValueError("request timestamp must be timezone-aware")
    if _NONCE_RE.fullmatch(request.nonce) is None:
        raise ValueError("invalid nonce")
    timestamp = request.timestamp.isoformat(timespec="microseconds").replace("+00:00", "Z")
    body_digest = encode_base64url(hashlib.sha256(request.body).digest())
    token_digest = (
        encode_base64url(hashlib.sha256(request.session_token.encode("ascii")).digest())
        if request.session_token is not None
        else "-"
    )
    components = (
        ("@method", method),
        ("@authority", authority),
        ("@path", request.path),
        ("@query", request.query),
        ("content-digest", f"sha-256=:{body_digest}:"),
        ("x-jarvis-date", timestamp),
        ("x-jarvis-nonce", request.nonce),
        ("x-jarvis-audience", request.audience),
        ("x-jarvis-device", request.device_id),
        ("x-jarvis-key-version", str(request.key_version)),
        ("authorization-digest", token_digest),
    )
    output = bytearray(b"jarvis-http-signature-v1\n")
    for name, value in components:
        encoded = value.encode("utf-8")
        output.extend(f"{name}:{len(encoded)}:".encode("ascii"))
        output.extend(encoded)
        output.extend(b"\n")
    return bytes(output)


def build_enrollment_proof(
    *, enrollment_id: str, challenge: str, public_key: str, protocol_version: str
) -> bytes:
    return _proof(
        "jarvis-enrollment-v1",
        enrollment_id,
        challenge,
        public_key,
        protocol_version,
    )


def build_rotation_proof(*, device_id: str, current_key_version: int, new_public_key: str) -> bytes:
    return _proof(
        "jarvis-key-rotation-v1",
        device_id,
        str(current_key_version),
        new_public_key,
    )


def _proof(profile: str, *values: str) -> bytes:
    output = bytearray((profile + "\n").encode("ascii"))
    for value in values:
        encoded = value.encode("utf-8")
        output.extend(f"{len(encoded)}:".encode("ascii"))
        output.extend(encoded)
        output.extend(b"\n")
    return bytes(output)
