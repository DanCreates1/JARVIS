"""Pinned, bounded HTTP acquisition for untrusted Phase 5 source documents."""

from __future__ import annotations

import asyncio
import ipaddress
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from jarvis.research.models import FetchedDocument, FetchRequest, ResearchErrorCode
from jarvis.research.security import (
    DnsResolver,
    PublicResearchUrlPolicy,
    ResearchUrlDenied,
    ValidatedResearchUrl,
)

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ALLOWED_ENCODINGS = frozenset({"ascii", "iso-8859-1", "utf-8", "utf-16", "windows-1252"})


class ResearchFetchError(RuntimeError):
    """Bounded metadata-only acquisition failure."""

    def __init__(self, code: ResearchErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class HttpDocumentFetcher:
    """Fetch public HTTPS documents without DNS rebinding or automatic redirects."""

    def __init__(
        self,
        *,
        policy: PublicResearchUrlPolicy | None = None,
        resolver: DnsResolver | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._policy = policy or PublicResearchUrlPolicy()
        self._resolver = resolver
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            follow_redirects=False,
            trust_env=False,
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=0),
            headers={
                "Accept": "text/html, text/plain, application/pdf;q=0.8",
                "User-Agent": "JARVIS-Research/0.1",
            },
        )
        self._closed = False

    async def fetch(self, request: FetchRequest) -> FetchedDocument:
        if self._closed:
            raise RuntimeError("HttpDocumentFetcher is closed")
        try:
            async with asyncio.timeout(request.limits.timeout_seconds):
                return await self._fetch_bounded(request)
        except asyncio.CancelledError:
            raise
        except ResearchFetchError:
            raise
        except ResearchUrlDenied as exc:
            raise ResearchFetchError(exc.code, str(exc)) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ResearchFetchError(
                ResearchErrorCode.TIMEOUT, "research fetch exceeded its total deadline"
            ) from exc
        except (httpx.NetworkError, httpx.ProtocolError) as exc:
            raise ResearchFetchError(
                ResearchErrorCode.UNAVAILABLE,
                f"research source unavailable: {type(exc).__name__}",
            ) from exc

    async def _fetch_bounded(self, request: FetchRequest) -> FetchedDocument:
        current = await self._policy.validate(
            request.url,
            allowed_domains=request.allowed_domains,
            resolver=self._resolver,
        )
        redirect_domains = request.allowed_domains or (current.hostname,)
        redirect_chain: list[str] = []
        for redirect_count in range(request.limits.max_redirects + 1):
            response = await self._request_pinned(
                current, request_timeout_seconds=request.limits.timeout_seconds
            )
            try:
                if response.status_code in _REDIRECT_STATUSES:
                    if redirect_count >= request.limits.max_redirects:
                        raise ResearchFetchError(
                            ResearchErrorCode.REDIRECT_LIMIT,
                            "research source exceeded redirect limit",
                        )
                    location = response.headers.get("location")
                    if not location:
                        raise ResearchFetchError(
                            ResearchErrorCode.PROTOCOL_ERROR,
                            "research redirect omitted Location",
                        )
                    next_url = urljoin(current.url, location)
                    current = await self._policy.validate(
                        next_url,
                        allowed_domains=redirect_domains,
                        resolver=self._resolver,
                    )
                    redirect_chain.append(current.url)
                    continue
                self._raise_for_status(response)
                media_type, encoding = _content_type(response)
                if media_type not in request.limits.accepted_media_types:
                    raise ResearchFetchError(
                        ResearchErrorCode.UNSUPPORTED_CONTENT,
                        f"research content type is unsupported: {media_type}",
                    )
                content_length = _content_length(response)
                if content_length is not None and content_length > request.limits.max_bytes:
                    raise ResearchFetchError(
                        ResearchErrorCode.RESPONSE_TOO_LARGE,
                        "research response exceeds configured byte limit",
                    )
                body = await _read_bounded(response, request.limits.max_bytes)
                return FetchedDocument(
                    requested_url=request.url,
                    final_url=current.url,
                    media_type=media_type,
                    encoding=encoding,
                    body=body,
                    retrieved_at=datetime.now(UTC),
                    status_code=response.status_code,
                    redirect_chain=tuple(redirect_chain),
                    etag=_validator_header(response, "etag"),
                    last_modified=_validator_header(response, "last-modified"),
                )
            finally:
                await response.aclose()
        raise AssertionError("redirect loop must return or raise")

    async def _request_pinned(
        self, target: ValidatedResearchUrl, *, request_timeout_seconds: float
    ) -> httpx.Response:
        self._client.cookies.clear()
        address = target.resolved_addresses[0]
        request_url = _pinned_url(target.url, address)
        request = self._client.build_request(
            "GET",
            request_url,
            headers={
                "Host": target.hostname,
                "Accept": "text/html, text/plain, application/pdf;q=0.8",
                "User-Agent": "JARVIS-Research/0.1",
            },
            extensions={
                "sni_hostname": target.hostname,
                "timeout": {
                    "connect": request_timeout_seconds,
                    "read": request_timeout_seconds,
                    "write": request_timeout_seconds,
                    "pool": request_timeout_seconds,
                },
            },
        )
        return await self._client.send(request, stream=True, follow_redirects=False)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> HttpDocumentFetcher:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise ResearchFetchError(
                ResearchErrorCode.AUTHENTICATION_REQUIRED,
                "research source requires authentication",
            )
        if response.status_code == 402:
            raise ResearchFetchError(ResearchErrorCode.PAYWALL, "research source requires payment")
        if response.status_code == 429 or response.status_code >= 500:
            raise ResearchFetchError(
                ResearchErrorCode.UNAVAILABLE, "research source is temporarily unavailable"
            )
        if response.status_code != 200:
            raise ResearchFetchError(
                ResearchErrorCode.PROTOCOL_ERROR,
                f"research source returned HTTP {response.status_code}",
            )


def _pinned_url(url: str, address: str) -> str:
    parsed = urlsplit(url)
    ip = ipaddress.ip_address(address)
    netloc = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, ""))


def _content_type(response: httpx.Response) -> tuple[str, str]:
    raw = response.headers.get("content-type", "")
    parts = [part.strip() for part in raw.split(";")]
    media_type = parts[0].lower()
    if not media_type or "/" not in media_type:
        raise ResearchFetchError(
            ResearchErrorCode.UNSUPPORTED_CONTENT,
            "research response omitted a supported Content-Type",
        )
    encoding = "utf-8"
    for parameter in parts[1:]:
        name, separator, value = parameter.partition("=")
        if separator and name.strip().lower() == "charset":
            candidate = value.strip().strip('"').lower()
            if candidate not in _ALLOWED_ENCODINGS:
                raise ResearchFetchError(
                    ResearchErrorCode.UNSUPPORTED_CONTENT,
                    "research response declared an unsupported character encoding",
                )
            encoding = candidate
    return media_type, encoding


def _content_length(response: httpx.Response) -> int | None:
    raw = response.headers.get("content-length")
    if raw is None:
        return None
    try:
        length = int(raw)
    except ValueError as exc:
        raise ResearchFetchError(
            ResearchErrorCode.PROTOCOL_ERROR, "research Content-Length is invalid"
        ) from exc
    if length < 0:
        raise ResearchFetchError(
            ResearchErrorCode.PROTOCOL_ERROR, "research Content-Length is invalid"
        )
    return length


def _validator_header(response: httpx.Response, name: str) -> str | None:
    raw = response.headers.get(name)
    if raw is None:
        return None
    value = str(raw).strip()
    if not value or len(value) > 500:
        raise ResearchFetchError(
            ResearchErrorCode.PROTOCOL_ERROR,
            f"research {name} header is invalid",
        )
    return value


async def _read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    content = bytearray()
    async for chunk in response.aiter_bytes():
        content.extend(chunk)
        if len(content) > max_bytes:
            raise ResearchFetchError(
                ResearchErrorCode.RESPONSE_TOO_LARGE,
                "research response exceeds configured byte limit",
            )
    if not content:
        raise ResearchFetchError(
            ResearchErrorCode.PROTOCOL_ERROR, "research response body is empty"
        )
    return bytes(content)
