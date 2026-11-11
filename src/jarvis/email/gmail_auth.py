"""Explicit desktop OAuth and foreground renewal. No project creation or automatic login."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from .exports import _local_volume
from .gmail import GMAIL_READ_SCOPE, GmailAccessToken, GmailReadProvider, _account, _unique_object
from .models import EmailError

AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"


class CredentialStore(Protocol):
    def read(self) -> bytes | None: ...
    def create(self, value: bytes) -> None: ...
    def delete(self) -> None: ...


def _ascii(value: object, maximum: int, *, token: bool = False) -> str:
    pattern = r"[A-Za-z0-9._~+/-]+=*" if token else r"[!-~]+"
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= maximum
        or not re.fullmatch(pattern, value)
    ):
        raise EmailError("gmail_auth_invalid")
    return value


def _json(raw: bytes) -> dict[str, Any]:
    def invalid_constant(_: str) -> None:
        raise EmailError("gmail_auth_invalid")

    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=invalid_constant
        )
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (ValueError, UnicodeError, RecursionError, EmailError):
        raise EmailError("gmail_auth_invalid") from None


@dataclass(frozen=True, repr=False)
class DesktopClient:
    client_id: str
    client_secret: str = field(repr=False)

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,200}\.apps\.googleusercontent\.com", self.client_id):
            raise EmailError("gmail_client_invalid")
        _ascii(self.client_secret, 512)


def load_desktop_client(path: Path) -> DesktopClient:
    """Only the owner's explicit local file; no search, discovery or generated token.json."""
    try:
        if not path.is_absolute() or str(path).startswith(("\\\\", "//")):
            raise EmailError("gmail_client_path")
        _local_volume(path)
        for component in (path, *path.parents):
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise EmailError("gmail_client_path")
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > 16384:
            raise EmailError("gmail_client_path")
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            raw = stream.read(16385)
        after = path.stat()

        def identity(s: os.stat_result) -> tuple[int, int, int, int]:
            return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)

        if (
            len(raw) > 16384
            or identity(before) != identity(opened)
            or identity(before) != identity(after)
        ):
            raise EmailError("gmail_client_path")
        data = _json(raw)
        if set(data) != {"installed"} or not isinstance(data["installed"], dict):
            raise EmailError("gmail_client_invalid")
        client = data["installed"]
        if client.get("auth_uri") != AUTH_URI or client.get("token_uri") != TOKEN_URI:
            raise EmailError("gmail_client_invalid")
        uris = client.get("redirect_uris")
        if (
            not isinstance(uris, list)
            or not uris
            or len(uris) > 8
            or any(uri not in {"http://localhost", "http://127.0.0.1"} for uri in uris)
        ):
            raise EmailError("gmail_client_invalid")
        return DesktopClient(
            _ascii(client.get("client_id"), 240), _ascii(client.get("client_secret"), 512)
        )
    except EmailError:
        raise
    except Exception:
        raise EmailError("gmail_client_invalid") from None


async def _exchange(
    client: DesktopClient, fields: dict[str, str], transport: httpx.AsyncBaseTransport | None
) -> dict[str, Any]:
    try:
        async with (
            asyncio.timeout(5),
            httpx.AsyncClient(
                transport=transport,
                timeout=5,
                trust_env=False,
                follow_redirects=False,
                headers={"Accept": "application/json", "Accept-Encoding": "identity"},
            ) as session,
            session.stream(
                "POST",
                TOKEN_URI,
                data={
                    "client_id": client.client_id,
                    "client_secret": client.client_secret,
                    **fields,
                },
            ) as response,
        ):
            if response.status_code != 200:
                raise EmailError("gmail_credentials_denied")
            if (
                response.headers.get("content-type", "").split(";", 1)[0].lower()
                != "application/json"
                or response.headers.get("content-encoding", "identity").lower() != "identity"
            ):
                raise EmailError("gmail_auth_invalid")
            length = response.headers.get("content-length")
            if length is not None and (
                not re.fullmatch(r"[0-9]{1,8}", length) or int(length) > 16384
            ):
                raise EmailError("gmail_auth_invalid")
            raw = bytearray()
            async for chunk in response.aiter_raw(chunk_size=4096):
                if len(raw) + len(chunk) > 16384:
                    raise EmailError("gmail_auth_invalid")
                raw.extend(chunk)
            if length is not None and len(raw) != int(length):
                raise EmailError("gmail_auth_invalid")
            return _json(bytes(raw))
    except EmailError:
        raise
    except (TimeoutError, httpx.HTTPError):
        raise EmailError("gmail_auth_unavailable") from None
    except Exception:
        raise EmailError("gmail_auth_invalid") from None


def _access(account: str, data: dict[str, Any]) -> GmailAccessToken:
    seconds = data.get("expires_in")
    if (
        data.get("token_type") != "Bearer"
        or data.get("scope") != GMAIL_READ_SCOPE
        or type(seconds) is not int
        or not 60 <= seconds <= 86400
    ):
        raise EmailError("gmail_auth_invalid")
    return GmailAccessToken(
        account,
        _ascii(data.get("access_token"), 8192, token=True),
        datetime.now(UTC) + timedelta(seconds=seconds),
    )


class ProtectedGmailTokenSource:
    def __init__(
        self,
        account: str,
        client: DesktopClient,
        store: CredentialStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.account = _account(account)
        self.client = client
        self.store = store
        self.transport = transport
        self._lock = asyncio.Lock()
        self._cached: GmailAccessToken | None = None

    def _grant(self) -> str:
        raw = self.store.read()
        if raw is None:
            raise EmailError("gmail_login_required")
        if len(raw) > 2560:
            raise EmailError("gmail_store_invalid")
        data = _json(raw)
        if (
            set(data) != {"version", "account", "client_id", "scope", "refresh_token"}
            or type(data["version"]) is not int
            or data["version"] != 1
            or data["account"] != self.account
            or data["client_id"] != self.client.client_id
            or data["scope"] != GMAIL_READ_SCOPE
        ):
            raise EmailError("gmail_store_invalid")
        return _ascii(data["refresh_token"], 2048, token=True)

    async def acquire(self) -> GmailAccessToken:
        try:
            async with self._lock:
                # Recheck local deletion on every acquisition, even with a live process token.
                refresh = self._grant()
                if self._cached and self._cached.expires_at > datetime.now(UTC) + timedelta(
                    seconds=30
                ):
                    return self._cached
                data = await _exchange(
                    self.client,
                    {"grant_type": "refresh_token", "refresh_token": refresh},
                    self.transport,
                )
                if data.get("refresh_token", refresh) != refresh:
                    raise EmailError("gmail_token_replacement_required")
                token = _access(self.account, data)
                if self._grant() != refresh:
                    raise EmailError("gmail_credentials_denied")
                self._cached = token
                return token
        except EmailError:
            self._cached = None
            raise
        except Exception:
            self._cached = None
            raise EmailError("gmail_credentials_denied") from None


def open_system_browser(url: str) -> None:
    if os.name != "nt":
        raise EmailError("gmail_windows_required")
    os.startfile(url)


class _InitialToken:
    def __init__(self, value: GmailAccessToken) -> None:
        self.value = value

    async def acquire(self) -> GmailAccessToken:
        return self.value


async def authorize_desktop(
    account: str,
    client: DesktopClient,
    store: CredentialStore,
    *,
    open_browser: Callable[[str], None] = open_system_browser,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Explicit trusted-local consent only. Stores a new grant after exact profile verification."""
    account = _account(account)
    if store.read() is not None:
        raise EmailError("gmail_credential_exists")
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    loop = asyncio.get_running_loop()
    result: asyncio.Future[tuple[bool, str]] = loop.create_future()
    tasks: set[asyncio.Task[None]] = set()
    attempts = 0
    host = ""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal attempts
        attempts += 1
        try:
            if attempts > 8 or len(tasks) > 4:
                if not result.done():
                    result.set_result((False, ""))
                return
            async with asyncio.timeout(2):
                raw = await reader.readuntil(b"\r\n\r\n")
                if len(raw) > 8192:
                    raise ValueError
                lines = raw.decode("ascii").split("\r\n")
                method, target, version = lines[0].split(" ")
                if method != "GET" or version != "HTTP/1.1" or not target.startswith("/"):
                    raise ValueError
                headers: dict[str, str] = {}
                for line in lines[1:-2]:
                    key, value = line.split(":", 1)
                    key = key.lower()
                    if key in headers:
                        raise ValueError
                    headers[key] = value.strip()
                if (
                    headers.get("host") != host
                    or "origin" in headers
                    or "transfer-encoding" in headers
                ):
                    raise ValueError
                if headers.get("content-length", "0") != "0":
                    raise ValueError
                parsed = urlsplit(target)
                if (
                    parsed.path != "/oauth2/callback"
                    or parsed.scheme
                    or parsed.netloc
                    or parsed.fragment
                ):
                    raise ValueError
                query = parse_qs(
                    parsed.query, keep_blank_values=True, strict_parsing=True, max_num_fields=8
                )
                if any(len(v) != 1 for v in query.values()) or set(query) - {
                    "state",
                    "code",
                    "error",
                    "scope",
                    "authuser",
                    "prompt",
                    "iss",
                }:
                    raise ValueError
                supplied_state = query.get("state", [""])[0]
                if not supplied_state.isascii() or not secrets.compare_digest(
                    supplied_state, state
                ):
                    raise ValueError
                if "iss" in query and query["iss"] != ["https://accounts.google.com"]:
                    raise ValueError
                if "error" in query:
                    if not result.done():
                        result.set_result((False, ""))
                elif not result.done():
                    code = _ascii(query.get("code", [None])[0], 2048)
                    result.set_result((True, code))
                body = b"JARVIS authorization response received. Return to the local terminal."
                writer.write(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nCache-Control: no-store\r\n"
                    b"Content-Security-Policy: default-src 'none'; frame-ancestors 'none'\r\n"
                    b"Connection: close\r\nContent-Length: "
                    + str(len(body)).encode()
                    + b"\r\n\r\n"
                    + body
                )
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            with suppress(OSError):
                await writer.wait_closed()

    def connected(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        task = asyncio.create_task(handle(reader, writer))
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    server = await asyncio.start_server(connected, "127.0.0.1", 0, limit=8192, backlog=4)
    try:
        async with asyncio.timeout(180):
            port = server.sockets[0].getsockname()[1]
            host = f"127.0.0.1:{port}"
            redirect = f"http://{host}/oauth2/callback"
            open_browser(
                AUTH_URI
                + "?"
                + urlencode(
                    {
                        "client_id": client.client_id,
                        "redirect_uri": redirect,
                        "response_type": "code",
                        "scope": GMAIL_READ_SCOPE,
                        "state": state,
                        "code_challenge": challenge,
                        "code_challenge_method": "S256",
                        "access_type": "offline",
                        "prompt": "consent",
                        "login_hint": account,
                        "include_granted_scopes": "false",
                    }
                )
            )
            accepted, code = await result
            server.close()
            await server.wait_closed()
            if not accepted:
                raise EmailError("gmail_consent_denied")
            data = await _exchange(
                client,
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "code_verifier": verifier,
                    "redirect_uri": redirect,
                },
                transport,
            )
            token = _access(account, data)
            refresh = _ascii(data.get("refresh_token"), 2048, token=True)
            provider = GmailReadProvider(
                account, _InitialToken(token), enabled=True, transport=transport
            )
            await provider.verify_account()
            blob = json.dumps(
                {
                    "version": 1,
                    "account": account,
                    "client_id": client.client_id,
                    "scope": GMAIL_READ_SCOPE,
                    "refresh_token": refresh,
                }
            ).encode()
            if len(blob) > 2560:
                raise EmailError("gmail_store_invalid")
            store.create(blob)
    except EmailError:
        raise
    except TimeoutError:
        raise EmailError("gmail_auth_timeout") from None
    except Exception:
        raise EmailError("gmail_auth_unavailable") from None
    finally:
        server.close()
        await server.wait_closed()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tuple(tasks), return_exceptions=True)
