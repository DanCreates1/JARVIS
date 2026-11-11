"""Inactive, foreground Gmail read adapter. No login, token store, writes or startup wiring.

Only a trusted host composition may supply the account-bound access-token port. Mail and
provider errors remain volatile. The ordinary export factory never constructs this adapter.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

import httpx

from .models import MAX_MESSAGE_BYTES, EmailError, EmailMessage, EmailThread, validate_id
from .processing import IsolatedEmailParser

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_API = "https://gmail.googleapis.com/gmail/v1/users/me"
_INVENTORY_FIELDS = "id,historyId,messages(id,threadId,historyId)"


def _account(value: str) -> str:
    # No alias equivalence or Workspace account discovery. Exact owner-selected address only.
    if not isinstance(value, str) or not re.fullmatch(
        r"[a-z0-9][a-z0-9.+_-]{0,63}@gmail\.com", value
    ):
        raise EmailError("gmail_account_required")
    return value


def _provider_id(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,28}", value):
        raise EmailError("gmail_protocol")
    return value


def _history(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,32}", value):
        raise EmailError("gmail_protocol")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EmailError("gmail_protocol")
    return value


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EmailError("gmail_protocol")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise EmailError("gmail_protocol")


@dataclass(frozen=True, repr=False)
class GmailAccessToken:
    """Host-only credential result. Never stringify this value or project it to a client/model."""

    account: str
    access_token: str = field(repr=False)
    expires_at: datetime
    scopes: frozenset[str] = frozenset({GMAIL_READ_SCOPE})


class GmailTokenSource(Protocol):
    async def acquire(self) -> GmailAccessToken:
        """Obtain an already-authorized same-account token; never prompt or expand scopes."""
        ...


class GmailReadProvider:
    def __init__(
        self,
        account: str,
        tokens: GmailTokenSource,
        *,
        enabled: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
        parser: IsolatedEmailParser | None = None,
    ) -> None:
        self._account = _account(account)
        self._tag = hashlib.sha256(self._account.encode("ascii")).hexdigest()[:16]
        self._tokens = tokens
        self._transport = transport
        self._parser = parser or IsolatedEmailParser()
        if type(enabled) is not bool:
            raise EmailError("gmail_configuration")
        self._enabled = enabled
        self._generation = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        if type(value) is not bool:
            raise EmailError("gmail_configuration")
        self._generation += 1
        self._enabled = value

    def _check(self, generation: int) -> None:
        if not self._enabled or generation != self._generation:
            raise EmailError("email_disabled")

    def canonical_id(self, provider_id: str, *, kind: Literal["t", "m"]) -> str:
        encoded = base64.b32encode(_provider_id(provider_id).encode("ascii"))
        return validate_id(f"g{self._tag}{kind}{encoded.decode('ascii').lower().rstrip('=')}")

    def _decode_id(self, value: str, kind: Literal["t", "m"]) -> str:
        validate_id(value)
        prefix = f"g{self._tag}{kind}"
        if not value.startswith(prefix):
            raise EmailError("gmail_provenance")
        encoded = value[len(prefix) :]
        try:
            provider_id = base64.b32decode(encoded.upper() + "=" * (-len(encoded) % 8)).decode(
                "ascii"
            )
            if self.canonical_id(provider_id, kind=kind) != value:
                raise EmailError("gmail_provenance")
            return provider_id
        except (ValueError, UnicodeError):
            raise EmailError("gmail_provenance") from None

    @asynccontextmanager
    async def _operation(self, seconds: float) -> AsyncIterator[tuple[httpx.AsyncClient, int]]:
        generation = self._generation
        self._check(generation)
        try:
            async with asyncio.timeout(seconds):
                try:
                    token = await self._tokens.acquire()
                except EmailError:
                    raise EmailError("gmail_credentials_denied") from None
                self._check(generation)
                if (
                    not isinstance(token, GmailAccessToken)
                    or token.account != self._account
                    or token.scopes != frozenset({GMAIL_READ_SCOPE})
                    or not isinstance(token.access_token, str)
                    or len(token.access_token) > 8192
                    or not re.fullmatch(r"[A-Za-z0-9._~+/-]{1,8192}=*", token.access_token)
                    or not isinstance(token.expires_at, datetime)
                    or token.expires_at.tzinfo is None
                    or token.expires_at <= datetime.now(UTC)
                ):
                    raise EmailError("gmail_credentials_denied")
                async with httpx.AsyncClient(
                    transport=self._transport,
                    timeout=5,
                    follow_redirects=False,
                    trust_env=False,
                    headers={
                        "Authorization": f"Bearer {token.access_token}",
                        "Accept": "application/json",
                        "Accept-Encoding": "identity",
                    },
                ) as client:
                    profile = await self._get(
                        client, generation, "/profile", {"fields": "emailAddress"}, 16_384
                    )
                    if profile.get("emailAddress") != self._account:
                        raise EmailError("gmail_account_mismatch")
                    yield client, generation
                    self._check(generation)
        except EmailError:
            raise
        except (TimeoutError, httpx.TimeoutException):
            raise EmailError("email_timeout") from None
        except httpx.HTTPError:
            raise EmailError("gmail_unavailable") from None
        except Exception:
            # Credential-source/parser/transport exceptions must not reveal private content.
            raise EmailError("gmail_unavailable") from None

    async def _get(
        self,
        client: httpx.AsyncClient,
        generation: int,
        path: str,
        params: dict[str, str],
        limit: int,
    ) -> dict[str, Any]:
        self._check(generation)
        client.cookies.clear()
        async with asyncio.timeout(5):
            async with client.stream("GET", _API + path, params=params) as response:
                self._check(generation)
                if response.status_code in {401, 403}:
                    raise EmailError("gmail_credentials_denied")
                if response.status_code == 429:
                    raise EmailError("gmail_rate_limited")
                if response.status_code == 404:
                    raise EmailError("gmail_source_unavailable")
                if response.status_code != 200:
                    raise EmailError("gmail_unavailable")
                if (
                    response.headers.get("content-type", "").split(";", 1)[0].lower()
                    != "application/json"
                    or response.headers.get("content-encoding", "identity").lower() != "identity"
                ):
                    raise EmailError("gmail_protocol")
                length = response.headers.get("content-length")
                if length is not None and (not length.isascii() or not length.isdigit()):
                    raise EmailError("gmail_protocol")
                if length is not None and int(length) > limit:
                    raise EmailError("gmail_response_limit")
                output = bytearray()
                async for chunk in response.aiter_raw(chunk_size=16_384):
                    self._check(generation)
                    if len(output) + len(chunk) > limit:
                        raise EmailError("gmail_response_limit")
                    output.extend(chunk)
                if length is not None and len(output) != int(length):
                    raise EmailError("gmail_protocol")
        self._check(generation)
        try:
            return _object(
                json.loads(
                    output.decode("utf-8"),
                    object_pairs_hook=_unique_object,
                    parse_constant=_invalid_constant,
                )
            )
        except (ValueError, UnicodeError, RecursionError):
            raise EmailError("gmail_protocol") from None

    async def list_threads(self) -> tuple[str, ...]:
        async with self._operation(5) as (client, generation):
            data = await self._get(
                client,
                generation,
                "/threads",
                {"maxResults": "100", "fields": "threads(id),nextPageToken"},
                32_768,
            )
            items = data.get("threads", [])
            if not isinstance(items, list) or len(items) > 100:
                raise EmailError("gmail_protocol")
            page = data.get("nextPageToken", "")
            if not isinstance(page, str) or len(page) > 4096:
                raise EmailError("gmail_protocol")
            ids = tuple(
                self.canonical_id(_provider_id(_object(item).get("id")), kind="t") for item in items
            )
            if len(set(ids)) != len(ids):
                raise EmailError("gmail_provenance")
            return ids

    async def _inventory(
        self, client: httpx.AsyncClient, generation: int, provider_thread: str
    ) -> tuple[str, tuple[tuple[str, str | None], ...]]:
        data = await self._get(
            client,
            generation,
            f"/threads/{provider_thread}",
            {"format": "minimal", "fields": _INVENTORY_FIELDS},
            16_384,
        )
        if data.get("id") != provider_thread:
            raise EmailError("gmail_provenance")
        history = _history(data.get("historyId"))
        items = data.get("messages")
        if not isinstance(items, list) or not 1 <= len(items) <= 16:
            raise EmailError("gmail_thread_limit")
        references: list[tuple[str, str | None]] = []
        for item in items:
            message = _object(item)
            if message.get("threadId") != provider_thread:
                raise EmailError("gmail_provenance")
            references.append(
                (
                    _provider_id(message.get("id")),
                    _history(message["historyId"]) if "historyId" in message else None,
                )
            )
        if len({item[0] for item in references}) != len(references):
            raise EmailError("gmail_provenance")
        return history, tuple(references)

    async def read_thread(self, thread_id: str) -> EmailThread:
        provider_thread = self._decode_id(thread_id, "t")
        async with self._operation(30) as (client, generation):
            initial = await self._inventory(client, generation, provider_thread)
            messages: list[EmailMessage] = []
            for identifier, history in initial[1]:
                data = await self._get(
                    client,
                    generation,
                    f"/messages/{identifier}",
                    {"format": "raw", "fields": "id,threadId,historyId,sizeEstimate,raw"},
                    196_608,
                )
                if data.get("id") != identifier or data.get("threadId") != provider_thread:
                    raise EmailError("gmail_provenance")
                observed_history = _history(data.get("historyId"))
                if history is not None and history != observed_history:
                    raise EmailError("gmail_thread_changed")
                size = data.get("sizeEstimate")
                if type(size) is not int or not 0 < size <= MAX_MESSAGE_BYTES:
                    raise EmailError("message_size")
                raw = self._raw(data.get("raw"))
                message_id = self.canonical_id(identifier, kind="m")
                message = EmailMessage.model_validate(
                    await self._parser.parse(raw, thread_id=thread_id, message_id=message_id)
                )
                self._check(generation)
                if (
                    message.id != message_id
                    or message.thread_id != thread_id
                    or message.sha256 != hashlib.sha256(raw).hexdigest()
                ):
                    raise EmailError("parser_provenance")
                messages.append(message)
            if initial != await self._inventory(client, generation, provider_thread):
                raise EmailError("gmail_thread_changed")
            return EmailThread(id=thread_id, messages=tuple(messages))

    @staticmethod
    def _raw(value: object) -> bytes:
        if (
            not isinstance(value, str)
            or len(value) > 174_764
            or not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value)
        ):
            raise EmailError("gmail_protocol")
        try:
            raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        except (ValueError, binascii.Error):
            raise EmailError("gmail_protocol") from None
        canonical = base64.urlsafe_b64encode(raw).decode("ascii")
        if value not in {canonical, canonical.rstrip("=")}:
            raise EmailError("gmail_protocol")
        if not raw or len(raw) > MAX_MESSAGE_BYTES:
            raise EmailError("message_size")
        return raw

    async def read_message(self, thread_id: str, message_id: str) -> EmailMessage:
        self._decode_id(message_id, "m")
        for message in (await self.read_thread(thread_id)).messages:
            if message.id == message_id:
                return message
        raise EmailError("message_not_found")
