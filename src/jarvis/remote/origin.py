"""Canonical server-origin handling for authority-bound mobile identities."""

from __future__ import annotations

import ipaddress
import re
from contextlib import suppress
from urllib.parse import urlsplit

_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def normalize_server_origin(value: str, *, allow_insecure_loopback: bool = False) -> str:
    """Return one unambiguous origin or reject unsafe/non-origin URLs."""
    if value != value.strip() or len(value) > 255:
        raise ValueError("server origin must be trimmed and at most 255 characters")
    parsed = urlsplit(value)
    scheme = parsed.scheme.casefold()
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("server origin cannot contain user information")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("server origin cannot contain a path, query, or fragment")
    hostname = parsed.hostname
    if hostname is None or not hostname.isascii() or hostname.endswith("."):
        raise ValueError("server origin requires an ASCII host without a trailing dot")
    hostname = hostname.casefold()
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.split(".")
        if any(_DNS_LABEL.fullmatch(label) is None for label in labels):
            raise ValueError("server origin contains an invalid host") from None
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("server origin contains an invalid port") from exc
    if port == 0:
        raise ValueError("server origin contains an invalid port")
    loopback = hostname == "localhost"
    with suppress(ValueError):
        loopback = loopback or ipaddress.ip_address(hostname).is_loopback
    if scheme != "https" and not (scheme == "http" and allow_insecure_loopback and loopback):
        raise ValueError("server origin must use HTTPS")
    default_port = 443 if scheme == "https" else 80
    rendered_host = f"[{hostname}]" if ":" in hostname else hostname
    authority = rendered_host if port in {None, default_port} else f"{rendered_host}:{port}"
    return f"{scheme}://{authority}"


def authority_from_origin(origin: str) -> str:
    """Extract canonical authority from an already-normalized server origin."""
    parsed = urlsplit(normalize_server_origin(origin, allow_insecure_loopback=True))
    return parsed.netloc
