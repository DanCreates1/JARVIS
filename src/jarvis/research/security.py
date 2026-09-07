"""Deterministic URL checks applied before every Phase 5 network hop."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

from jarvis.research.models import ResearchErrorCode

DnsResolver = Callable[[str, int], Awaitable[Sequence[str]]]


class ResearchUrlDenied(ValueError):
    """A URL failed deterministic research-network policy."""

    def __init__(self, message: str, *, code: ResearchErrorCode) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ValidatedResearchUrl:
    url: str
    hostname: str
    port: int
    resolved_addresses: tuple[str, ...]


class PublicResearchUrlPolicy:
    """Allow bounded public HTTPS destinations; deny local/private/special-use targets."""

    def __init__(self, *, allow_http: bool = False, max_url_length: int = 2_048) -> None:
        if not 1 <= max_url_length <= 8_192:
            raise ValueError("max_url_length must be between 1 and 8192")
        self._allow_http = allow_http
        self._max_url_length = max_url_length

    async def validate(
        self,
        url: str,
        *,
        allowed_domains: Sequence[str] = (),
        resolver: DnsResolver | None = None,
    ) -> ValidatedResearchUrl:
        normalized, hostname, port = self.validate_syntax(url, allowed_domains=allowed_domains)
        resolve = resolver or resolve_public_addresses
        addresses = tuple(dict.fromkeys(await resolve(hostname, port)))
        if not addresses:
            raise ResearchUrlDenied(
                "research hostname did not resolve", code=ResearchErrorCode.UNAVAILABLE
            )
        if len(addresses) > 16:
            raise ResearchUrlDenied(
                "research hostname returned too many addresses",
                code=ResearchErrorCode.PROTOCOL_ERROR,
            )
        for value in addresses:
            try:
                address = ipaddress.ip_address(value)
            except ValueError as exc:
                raise ResearchUrlDenied(
                    "resolver returned an invalid IP address",
                    code=ResearchErrorCode.PROTOCOL_ERROR,
                ) from exc
            if (
                not address.is_global
                or address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
            ):
                raise ResearchUrlDenied(
                    "research URL resolves to a non-public address",
                    code=ResearchErrorCode.PRIVATE_NETWORK_DENIED,
                )
        return ValidatedResearchUrl(
            url=normalized,
            hostname=hostname,
            port=port,
            resolved_addresses=addresses,
        )

    def validate_syntax(
        self, url: str, *, allowed_domains: Sequence[str] = ()
    ) -> tuple[str, str, int]:
        candidate = url.strip()
        if not candidate or len(candidate) > self._max_url_length:
            raise ResearchUrlDenied(
                "research URL is blank or exceeds configured length",
                code=ResearchErrorCode.INVALID_URL,
            )
        if any(ord(character) < 32 or ord(character) == 127 for character in candidate):
            raise ResearchUrlDenied(
                "research URL contains control characters",
                code=ResearchErrorCode.INVALID_URL,
            )
        try:
            parsed = urlsplit(candidate)
            port = parsed.port
        except ValueError as exc:
            raise ResearchUrlDenied(
                "research URL is malformed", code=ResearchErrorCode.INVALID_URL
            ) from exc
        allowed_schemes = {"https"} | ({"http"} if self._allow_http else set())
        if parsed.scheme.lower() not in allowed_schemes:
            raise ResearchUrlDenied(
                "research URL scheme is not allowed", code=ResearchErrorCode.INVALID_URL
            )
        if parsed.username is not None or parsed.password is not None:
            raise ResearchUrlDenied(
                "credential-bearing research URLs are denied",
                code=ResearchErrorCode.INVALID_URL,
            )
        if not parsed.hostname:
            raise ResearchUrlDenied(
                "research URL requires a hostname", code=ResearchErrorCode.INVALID_URL
            )
        hostname = _normalize_hostname(parsed.hostname)
        if _is_ip_literal(hostname):
            raise ResearchUrlDenied(
                "direct IP research URLs are denied",
                code=ResearchErrorCode.PRIVATE_NETWORK_DENIED,
            )
        if _is_special_hostname(hostname):
            raise ResearchUrlDenied(
                "local or special-use research hostname is denied",
                code=ResearchErrorCode.PRIVATE_NETWORK_DENIED,
            )
        effective_port = port or (443 if parsed.scheme.lower() == "https" else 80)
        expected_port = 443 if parsed.scheme.lower() == "https" else 80
        if effective_port != expected_port:
            raise ResearchUrlDenied(
                "non-default research URL ports are denied", code=ResearchErrorCode.INVALID_URL
            )
        normalized_allowlist = tuple(_normalize_hostname(value) for value in allowed_domains)
        if normalized_allowlist and not any(
            hostname == domain or hostname.endswith(f".{domain}") for domain in normalized_allowlist
        ):
            raise ResearchUrlDenied(
                "research URL hostname is outside allowed domains",
                code=ResearchErrorCode.DOMAIN_DENIED,
            )
        normalized = _normalize_url(parsed, hostname, effective_port)
        return normalized, hostname, effective_port


async def resolve_public_addresses(hostname: str, port: int) -> Sequence[str]:
    loop = asyncio.get_running_loop()
    records = await loop.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return tuple(str(record[4][0]) for record in records)


def _normalize_hostname(value: str) -> str:
    hostname = value.rstrip(".").lower()
    if not hostname:
        raise ResearchUrlDenied(
            "research URL hostname is blank", code=ResearchErrorCode.INVALID_URL
        )
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ResearchUrlDenied(
            "research URL hostname is invalid", code=ResearchErrorCode.INVALID_URL
        ) from exc
    if len(ascii_hostname) > 253 or any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or re.fullmatch(r"[a-z0-9-]+", label) is None
        for label in ascii_hostname.split(".")
    ):
        raise ResearchUrlDenied(
            "research URL hostname is invalid", code=ResearchErrorCode.INVALID_URL
        )
    return ascii_hostname


def _is_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True


def _is_special_hostname(hostname: str) -> bool:
    special_suffixes = (
        "localhost",
        ".localhost",
        ".local",
        ".internal",
        ".home.arpa",
        ".onion",
        ".invalid",
        ".test",
    )
    return hostname == "localhost" or hostname.endswith(special_suffixes)


def _normalize_url(parsed: SplitResult, hostname: str, port: int) -> str:
    scheme = parsed.scheme.lower()
    default_port = 443 if scheme == "https" else 80
    netloc = hostname if port == default_port else f"{hostname}:{port}"
    path = parsed.path or "/"
    return urlunsplit((scheme, netloc, path, parsed.query, ""))
