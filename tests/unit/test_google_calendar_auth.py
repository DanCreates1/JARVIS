from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import secrets
from contextlib import suppress
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest
from typer.testing import CliRunner

from jarvis.calendar.google import GOOGLE_CALENDAR_SCOPES
from jarvis.calendar.google_auth import (
    AUTH_URI,
    TOKEN_URI,
    DesktopClient,
    ProtectedGoogleCalendarTokenSource,
    authorize_desktop,
    load_desktop_client,
)
from jarvis.calendar.google_credentials import WindowsGoogleCalendarCredentials
from jarvis.calendar.models import CalendarError
from jarvis.cli import app

SCOPE = " ".join(sorted(GOOGLE_CALENDAR_SCOPES))
ACCOUNT = "synthetic-owner@gmail.com"
CLIENT = DesktopClient("synthetic-client.apps.googleusercontent.com", "synthetic-client-sentinel")


class Store:
    def __init__(self, value=None):
        self.value = value
        self.writes = 0

    def read(self):
        return self.value

    def create(self, value):
        assert self.value is None
        self.value = value
        self.writes += 1

    def delete(self):
        self.value = None


def grant(**changes):
    return json.dumps(
        {
            "version": 1,
            "account": ACCOUNT,
            "client_id": CLIENT.client_id,
            "scopes": sorted(GOOGLE_CALENDAR_SCOPES),
            "calendar_id": "primary",
            "refresh_token": "synthetic-refresh-sentinel",
            **changes,
        }
    ).encode()


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for value in self.chunks:
            yield value

    async def aclose(self):
        self.closed = True


def response(data, *, status=200, headers=None, raw=None):
    return httpx.Response(
        status,
        headers={"content-type": "application/json", **(headers or {})},
        stream=Chunks([json.dumps(data).encode() if raw is None else raw]),
    )


def token(**changes):
    return {
        "access_token": "synthetic-access-sentinel",
        "refresh_token": "synthetic-refresh-sentinel",
        "token_type": "Bearer",
        "scope": SCOPE,
        "expires_in": 3600,
        **changes,
    }


def client_file(tmp_path, **changes):
    data = {
        "installed": {
            "client_id": CLIENT.client_id,
            "client_secret": CLIENT.client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": ["http://localhost"],
            **changes,
        }
    }
    path = tmp_path / "desktop.json"
    path.write_text(json.dumps(data))
    return path


class Browser:
    def __init__(self, *, mode="ok", requests=None):
        self.mode = mode
        self.url = None
        self.tasks = []
        self.replies = []
        self.requests = requests

    def __call__(self, url):
        self.url = url
        query = parse_qs(urlsplit(url).query)
        assert url.startswith(AUTH_URI + "?")
        assert query["scope"] == [SCOPE]
        assert query["access_type"] == ["offline"]
        assert query["include_granted_scopes"] == ["false"]
        assert query["code_challenge_method"] == ["S256"]
        redirect = urlsplit(query["redirect_uri"][0])
        assert redirect.hostname == "127.0.0.1"

        async def run():
            state = query["state"][0]
            callbacks = self.requests or [(state, "synthetic-code-sentinel")]
            for supplied, code in callbacks:
                reader, writer = await asyncio.open_connection(redirect.hostname, redirect.port)
                values = {
                    "state": state if supplied == "correct" else supplied,
                    "error" if self.mode == "denied" else "code": code,
                }
                target = redirect.path + "?" + urlencode(values)
                writer.write(f"GET {target} HTTP/1.1\r\nHost: {redirect.netloc}\r\n\r\n".encode())
                await writer.drain()
                try:
                    self.replies.append(await reader.read())
                except ConnectionResetError:
                    self.replies.append(b"")
                writer.close()
                with suppress(ConnectionResetError):
                    await writer.wait_closed()

        self.tasks.append(asyncio.create_task(run()))

    async def close(self):
        await asyncio.gather(*self.tasks)


async def test_auth_exact_pkce_profile_storage_and_renewal(caplog):
    store, browser, requests = Store(), Browser(), []

    def endpoint(request):
        requests.append(request)
        assert "cookie" not in request.headers
        if request.url == TOKEN_URI:
            assert request.method == "POST"
            data = parse_qs(request.content.decode())
            query = parse_qs(urlsplit(browser.url).query)
            verifier = data["code_verifier"][0]
            assert 43 <= len(verifier) <= 128
            assert query["code_challenge"] == [
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .decode()
                .rstrip("=")
            ]
            assert data["redirect_uri"] == query["redirect_uri"]
            return response(token(), headers={"set-cookie": "private=sentinel"})
        assert (
            str(request.url)
            == "https://www.googleapis.com/oauth2/v2/userinfo?fields=email%2Cverified_email"
        )
        assert request.headers["authorization"] == "Bearer synthetic-access-sentinel"
        return response({"email": ACCOUNT, "verified_email": True})

    await authorize_desktop(
        ACCOUNT, CLIENT, store, open_browser=browser, transport=httpx.MockTransport(endpoint)
    )
    await browser.close()
    assert len(requests) == 2 and store.writes == 1
    assert json.loads(store.value) == json.loads(grant())
    assert b"synthetic-access-sentinel" not in store.value
    assert all(b"synthetic-code-sentinel" not in reply for reply in browser.replies)
    assert "synthetic-code-sentinel" not in caplog.text
    assert "synthetic-refresh-sentinel" not in caplog.text
    assert CLIENT.client_secret not in repr(CLIENT)
    assert "access-sentinel" not in repr(token)


async def test_renewal_cached_restart_and_local_deletion():
    store, calls = Store(grant()), []

    def endpoint(request):
        calls.append(request)
        data = parse_qs(request.content.decode())
        assert str(request.url) == TOKEN_URI
        assert data["grant_type"] == ["refresh_token"]
        assert data["refresh_token"] == ["synthetic-refresh-sentinel"]
        return response(token())

    transport = httpx.MockTransport(endpoint)
    source = ProtectedGoogleCalendarTokenSource(ACCOUNT, CLIENT, store, transport=transport)
    first, second = await asyncio.gather(source.acquire(), source.acquire())
    assert first is second and len(calls) == 1
    source._cached = None
    await source.acquire()
    await ProtectedGoogleCalendarTokenSource(ACCOUNT, CLIENT, store, transport=transport).acquire()
    assert len(calls) == 3 and store.writes == 0
    store.delete()
    with pytest.raises(CalendarError, match="calendar_login_required"):
        await source.acquire()
    assert source._cached is None and len(calls) == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"account": "other@gmail.com"},
        {"client_id": "other"},
        {"calendar_id": "other@gmail.com"},
        {"scopes": []},
        {"scopes": [*sorted(GOOGLE_CALENDAR_SCOPES), "openid"]},
        {"scope": "gmail.modify"},
        {"version": True},
        {"version": 2},
        {"refresh_token": "a" * 2049},
        {"refresh_token": "line\nbreak"},
        {"extra": "value"},
    ],
)
async def test_bad_stored_binding_no_network(changes):
    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT,
        CLIENT,
        Store(grant(**changes)),
        transport=httpx.MockTransport(lambda _: pytest.fail("network denied")),
    )
    with pytest.raises(CalendarError):
        await source.acquire()


@pytest.mark.parametrize(
    "raw", [b"[]", b"{", b"{}", b"x" * 2561, b'{"version":1,"version":1}', b'"private-sentinel"']
)
async def test_malformed_store(raw):
    source = ProtectedGoogleCalendarTokenSource(ACCOUNT, CLIENT, Store(raw))
    with pytest.raises(CalendarError):
        await source.acquire()


@pytest.mark.parametrize(
    "changes",
    [
        {"scope": "gmail.modify"},
        {"scope": None},
        {"scope": SCOPE + " openid"},
        {"scope": SCOPE + " " + SCOPE},
        {"scope": SCOPE + " "},
        {"scope": "x" * 1025},
        {"token_type": "DPoP"},
        {"expires_in": True},
        {"expires_in": 0},
        {"expires_in": 86401},
        {"access_token": "a" * 8193},
        {"access_token": "a" + "=" * 8192},
        {"access_token": "bearer\nleak"},
        {"refresh_token": "replacement"},
    ],
)
async def test_renewal_denies_scope_expansion_invalid_and_replacement(changes):
    store = Store(grant())
    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT, CLIENT, store, transport=httpx.MockTransport(lambda _: response(token(**changes)))
    )
    with pytest.raises(CalendarError):
        await source.acquire()
    assert store.value == grant() and source._cached is None


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 429, 500, 503])
async def test_renewal_http_failures_fixed_no_retry(status):
    calls = []

    def endpoint(request):
        calls.append(request)
        return response(
            {"error": "private-sentinel"},
            status=status,
            headers={"location": "https://attacker.invalid"},
        )

    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT, CLIENT, Store(grant()), transport=httpx.MockTransport(endpoint)
    )
    with pytest.raises(CalendarError, match=r"^calendar_credentials_denied$"):
        await source.acquire()
    assert len(calls) == 1


@pytest.mark.parametrize(
    "headers,raw",
    [
        ({"content-type": "text/html"}, b"private"),
        ({"content-encoding": "gzip"}, b"private"),
        ({"content-length": "16385"}, b"{}"),
        ({"content-length": "broken"}, b"{}"),
        ({"content-length": "10"}, b"{}"),
        ({}, b"x" * 16385),
        ({}, b'{"scope":1,"scope":2}'),
        ({}, b"[]"),
        ({}, b"\xff"),
    ],
)
async def test_token_response_bounds(headers, raw):
    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT,
        CLIENT,
        Store(grant()),
        transport=httpx.MockTransport(lambda _: response(None, headers=headers, raw=raw)),
    )
    with pytest.raises(CalendarError):
        await source.acquire()


async def test_auth_refuses_existing_before_browser_or_network():
    with pytest.raises(CalendarError, match="calendar_credential_exists"):
        await authorize_desktop(
            ACCOUNT, CLIENT, Store(grant()), open_browser=lambda _: pytest.fail("must not open")
        )


@pytest.mark.parametrize("kind", ["denied", "wrong-account", "missing-refresh", "wrong-scope"])
async def test_auth_no_storage_on_failure(kind):
    store, browser = Store(), Browser(mode="denied" if kind == "denied" else "ok")

    def endpoint(request):
        if request.url == TOKEN_URI:
            data = token(scope="extra" if kind == "wrong-scope" else SCOPE)
            if kind == "missing-refresh":
                data.pop("refresh_token")
            return response(data)
        return response(
            {
                "email": "other@gmail.com" if kind == "wrong-account" else ACCOUNT,
                "verified_email": True,
            }
        )

    with pytest.raises(CalendarError):
        await authorize_desktop(
            ACCOUNT, CLIENT, store, open_browser=browser, transport=httpx.MockTransport(endpoint)
        )
    await browser.close()
    assert store.value is None


async def test_wrong_state_ignored_then_exact_callback():
    store, browser = Store(), Browser(requests=[("wrong-state", "private"), ("correct", "good")])

    def endpoint(request):
        return response(
            token() if request.url == TOKEN_URI else {"email": ACCOUNT, "verified_email": True}
        )

    await authorize_desktop(
        ACCOUNT, CLIENT, store, open_browser=browser, transport=httpx.MockTransport(endpoint)
    )
    await browser.close()
    assert browser.replies[0] == b"" and store.writes == 1


async def test_callback_request_limit_and_no_tokens():
    browser = Browser(requests=[("wrong-state", "private")] * 8)
    # Ninth callback exceeds the fixed cap and aborts the flow.
    browser.requests.append(("wrong-state", "private"))
    store = Store()
    with pytest.raises(CalendarError, match="calendar_consent_denied"):
        await authorize_desktop(
            ACCOUNT,
            CLIENT,
            store,
            open_browser=browser,
            transport=httpx.MockTransport(lambda _: pytest.fail("no network")),
        )
    await browser.close()
    assert store.value is None


async def test_cancel_closes_listener_without_storage():
    opened = asyncio.Event()
    urls = []

    def browser(url):
        urls.append(url)
        opened.set()

    store = Store()
    task = asyncio.create_task(authorize_desktop(ACCOUNT, CLIENT, store, open_browser=browser))
    await opened.wait()
    redirect = urlsplit(parse_qs(urlsplit(urls[0]).query)["redirect_uri"][0])
    reader, writer = await asyncio.open_connection(redirect.hostname, redirect.port)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.wait_for(reader.read(), 2) == b""
    writer.close()
    await writer.wait_closed()
    with pytest.raises(OSError):
        await asyncio.open_connection(redirect.hostname, redirect.port)
    assert store.value is None


async def test_cancel_renewal_drains_response_and_no_store_write():
    started = asyncio.Event()

    class Waiting(Chunks):
        async def __aiter__(self):
            started.set()
            await asyncio.Event().wait()
            yield b""

    stream = Waiting([])
    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT,
        CLIENT,
        Store(grant()),
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                200, headers={"content-type": "application/json"}, stream=stream
            )
        ),
    )
    task = asyncio.create_task(source.acquire())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert stream.closed and source._cached is None


@pytest.mark.parametrize("auth_uri", [AUTH_URI, "https://accounts.google.com/o/oauth2/auth"])
@pytest.mark.parametrize("token_uri", [TOKEN_URI, "https://accounts.google.com/o/oauth2/token"])
def test_desktop_file_is_explicit_and_bound(tmp_path, auth_uri, token_uri):
    path = client_file(tmp_path, auth_uri=auth_uri, token_uri=token_uri)
    assert load_desktop_client(path) == CLIENT
    with pytest.raises(CalendarError):
        load_desktop_client(path.relative_to(tmp_path))
    linked = tmp_path / "linked.json"
    os.link(path, linked)
    with pytest.raises(CalendarError):
        load_desktop_client(path)


@pytest.mark.parametrize(
    "changes",
    [
        {"token_uri": "https://attacker.invalid"},
        {"auth_uri": "https://attacker.invalid"},
        {"client_id": "bad"},
        {"client_secret": "bad\nsecret"},
        {"redirect_uris": ["https://attacker.invalid"]},
        {"redirect_uris": []},
        {"redirect_uris": "http://localhost"},
    ],
)
def test_desktop_registration_schema(tmp_path, changes):
    with pytest.raises(CalendarError):
        load_desktop_client(client_file(tmp_path, **changes))


@pytest.mark.parametrize(
    "raw",
    [
        b"x" * 16385,
        b"{}",
        b'{"web":{}}',
        b'{"installed":null}',
        b'{"installed":{},"installed":{}}',
        b"[]",
        b"\xff",
    ],
)
def test_desktop_file_malformed(tmp_path, raw):
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(CalendarError):
        load_desktop_client(path)


def test_cli_auth_and_disconnect_decline_has_no_effect(tmp_path, monkeypatch):
    import jarvis.calendar.google_credentials as credentials

    store = Store()
    monkeypatch.setattr(credentials, "WindowsGoogleCalendarCredentials", lambda *_: store)
    path = client_file(tmp_path)
    runner = CliRunner()
    for command in ["google-auth", "google-disconnect"]:
        result = runner.invoke(
            app,
            ["calendar", command, "--account", ACCOUNT, "--client-file", str(path)],
            input="n\n",
        )
        assert result.exit_code == 0, result.output
    assert store.value is None and store.writes == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows Credential Manager only")
def test_actual_windows_protected_storage_roundtrip_and_refuse_replacement():
    # Random synthetic-only target. Never enumerate or open an owner credential.
    client_id = f"synthetic-{secrets.token_hex(16)}.apps.googleusercontent.com"
    store = WindowsGoogleCalendarCredentials(ACCOUNT, client_id)
    assert store.read() is None
    try:
        store.create(b"synthetic-storage-sentinel")
        assert store.read() == b"synthetic-storage-sentinel"
        with pytest.raises(CalendarError, match="calendar_credential_exists"):
            store.create(b"replacement")
        assert store.read() == b"synthetic-storage-sentinel"
    finally:
        store.delete()
    assert store.read() is None


@pytest.mark.parametrize(
    "request_template",
    [
        "GET {path}?state=wrong&code=x HTTP/1.1\r\nHost: {host}\r\n\r\n",
        "GET {path}?state=%C3%A9&code=x HTTP/1.1\r\nHost: {host}\r\n\r\n",
        "GET {path}?state={state}&state=duplicate&code=x HTTP/1.1\r\nHost: {host}\r\n\r\n",
        "GET {path}?state={state}&code=x HTTP/1.1\r\nHost: attacker.invalid\r\n\r\n",
        "GET {path}?state={state}&code=x HTTP/1.1\r\nHost: {host}\r\nOrigin: https://attacker.invalid\r\n\r\n",
        "POST {path}?state={state}&code=x HTTP/1.1\r\nHost: {host}\r\n\r\n",
        "GET /wrong?state={state}&code=x HTTP/1.1\r\nHost: {host}\r\n\r\n",
        "GET {path}?state={state}&iss=https%3A%2F%2Fattacker.invalid&code=x HTTP/1.1\r\n"
        "Host: {host}\r\n\r\n",
        "GET {path}?state={state}&code=x HTTP/1.1\r\nHost: {host}\r\nHost: {host}\r\n\r\n",
        "GET {path}?state={state}&code=x HTTP/1.1\r\nHost: {host}\r\nContent-Length: 1\r\n\r\nx",
        "GET {path}?state={state}&code=x HTTP/1.1\r\nHost: {host}\r\n"
        "Transfer-Encoding: chunked\r\n\r\n",
        "GET {path}?state={state}&code=x&unexpected=field HTTP/1.1\r\nHost: {host}\r\n\r\n",
    ],
)
async def test_hostile_callback_no_token_exchange(request_template, caplog):
    urls, ready = [], asyncio.Event()

    def browser(url):
        urls.append(url)
        ready.set()

    store = Store()
    task = asyncio.create_task(
        authorize_desktop(
            ACCOUNT,
            CLIENT,
            store,
            open_browser=browser,
            transport=httpx.MockTransport(lambda _: pytest.fail("callback must not authorize")),
        )
    )
    await ready.wait()
    query = parse_qs(urlsplit(urls[0]).query)
    redirect = urlsplit(query["redirect_uri"][0])
    reader, writer = await asyncio.open_connection(redirect.hostname, redirect.port)
    writer.write(
        request_template.format(
            path=redirect.path, host=redirect.netloc, state=query["state"][0]
        ).encode()
    )
    await writer.drain()
    with suppress(ConnectionResetError):
        assert await asyncio.wait_for(reader.read(), 3) == b""
    assert not task.done() and store.value is None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    writer.close()
    with suppress(ConnectionResetError):
        await writer.wait_closed()
    assert "Task exception" not in caplog.text


async def test_auth_total_timeout_and_browser_failure(monkeypatch):
    import jarvis.calendar.google_auth as auth

    timeout = asyncio.timeout
    monkeypatch.setattr(
        auth.asyncio, "timeout", lambda seconds: timeout(0.03 if seconds == 180 else seconds)
    )
    store = Store()
    with pytest.raises(CalendarError, match="calendar_auth_timeout"):
        await authorize_desktop(ACCOUNT, CLIENT, store, open_browser=lambda _: None)

    def broken(_):
        raise RuntimeError("private-sentinel")

    with pytest.raises(CalendarError, match="calendar_auth_unavailable"):
        await authorize_desktop(ACCOUNT, CLIENT, store, open_browser=broken)
    assert store.value is None


async def test_real_five_second_renewal_deadline():
    async def endpoint(_):
        await asyncio.Event().wait()

    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT, CLIENT, Store(grant()), transport=httpx.MockTransport(endpoint)
    )
    loop = asyncio.get_running_loop()
    start = loop.time()
    with pytest.raises(CalendarError, match="calendar_auth_unavailable"):
        await source.acquire()
    assert 4.5 <= loop.time() - start < 7


async def test_renewal_local_deletion_during_network_discards_result():
    store = Store(grant())

    def endpoint(_):
        store.delete()
        return response(token())

    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT, CLIENT, store, transport=httpx.MockTransport(endpoint)
    )
    with pytest.raises(CalendarError):
        await source.acquire()
    assert source._cached is None and store.value is None


@pytest.mark.parametrize("kind", ["network", "private-store-error"])
async def test_renewal_sanitizes_unavailable_errors(kind):
    store = Store(grant())
    if kind == "private-store-error":
        store.read = lambda: (_ for _ in ()).throw(RuntimeError("private-sentinel"))

    def endpoint(_):
        raise httpx.ConnectError("private-sentinel")

    source = ProtectedGoogleCalendarTokenSource(
        ACCOUNT, CLIENT, store, transport=httpx.MockTransport(endpoint)
    )
    with pytest.raises(CalendarError) as caught:
        await source.acquire()
    assert "private-sentinel" not in str(caught.value)


def test_cli_auth_and_disconnect_explicit_success(tmp_path, monkeypatch):
    import jarvis.calendar.google_auth as auth
    import jarvis.calendar.google_credentials as credentials

    store, calls = Store(), []
    monkeypatch.setattr(credentials, "WindowsGoogleCalendarCredentials", lambda *_: store)

    async def authorize(account, client, selected):
        assert account == ACCOUNT and client == CLIENT and selected is store
        calls.append("auth")
        store.create(grant())

    monkeypatch.setattr(auth, "authorize_desktop", authorize)
    path = client_file(tmp_path)
    runner = CliRunner()
    for command in ["google-auth", "google-disconnect"]:
        result = runner.invoke(
            app,
            ["calendar", command, "--account", ACCOUNT, "--client-file", str(path)],
            input="y\n",
        )
        assert result.exit_code == 0, result.output
        assert ACCOUNT not in result.output and "synthetic-refresh-sentinel" not in result.output
    assert store.value is None and calls == ["auth"]
