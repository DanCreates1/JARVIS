"""Synthetic full foreground auth/read/prepare composition. Never owner data."""

from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from urllib.parse import parse_qs

import httpx
import pytest
from typer.testing import CliRunner

from jarvis.calendar.google import GoogleCalendarReadProvider
from jarvis.calendar.google_auth import ProtectedGoogleCalendarTokenSource, authorize_desktop
from jarvis.calendar.google_proof import proof_window, selected_calendar_proof
from jarvis.calendar.models import CalendarError, CalendarWindow
from jarvis.cli import app
from tests.unit.test_google_calendar import WINDOW, event, listing
from tests.unit.test_google_calendar_auth import (
    ACCOUNT,
    CLIENT,
    TOKEN_URI,
    Browser,
    Store,
    client_file,
    grant,
    response,
    token,
)


@pytest.mark.parametrize("count", [0, 1, 2, 100])
async def test_auth_restart_renewal_and_single_read_aggregate_proof(count, caplog):
    store, browser, calls = Store(), Browser(), []

    def endpoint(request):
        calls.append(request)
        assert "cookie" not in request.headers
        if request.url == TOKEN_URI:
            return response(token(), headers={"set-cookie": "private=forbidden"})
        if request.url.path == "/oauth2/v2/userinfo":
            return response({"email": ACCOUNT, "verified_email": True})
        assert request.url.path == "/calendar/v3/calendars/primary/events"
        assert request.url.params["maxResults"] == "100"
        assert request.url.params["singleEvents"] == "true"
        return response(listing(*(event(f"fixture{n}") for n in range(count))))

    transport = httpx.MockTransport(endpoint)
    await authorize_desktop(ACCOUNT, CLIENT, store, open_browser=browser, transport=transport)
    await browser.close()
    assert len(calls) == 2 and store.writes == 1  # No event read during login.
    assert json.loads(store.value) == json.loads(grant())
    calls.clear()
    provider = GoogleCalendarReadProvider(
        ACCOUNT,
        ProtectedGoogleCalendarTokenSource(ACCOUNT, CLIENT, store, transport=transport),
        enabled=True,
        max_events=100,
        transport=transport,
    )
    result = await selected_calendar_proof(provider, WINDOW)
    assert len(calls) == 3  # One renewal POST, identity GET, event GET; no reacquisition.
    assert result["read_pass"] and result["events"] == count
    assert result["preparation_pass"] is bool(count)
    assert result["proposal_prepared"] is bool(count)
    assert result["conflict_pairs"] == count * (count - 1) // 2
    assert not provider.enabled and store.writes == 1
    output = json.dumps(result)
    for sentinel in [ACCOUNT, "fixture", "Synthetic", "2026", "sentinel", CLIENT.client_id]:
        assert sentinel not in output and sentinel not in caplog.text
    assert all(type(v) in {int, bool} for v in result.values())
    assert not result["provider_freshness_known"] and not result["availability_proven"]


@pytest.mark.parametrize("change", ["long", "fraction-start", "fraction-end"])
async def test_invalid_window_before_tokens(change):
    start, end = WINDOW.start, WINDOW.end
    if change == "long":
        end += timedelta(seconds=1)
    elif change == "fraction-start":
        start += timedelta(microseconds=1)
    else:
        end -= timedelta(microseconds=1)
    window = CalendarWindow(start=start, end=end)
    with pytest.raises(CalendarError, match="calendar_proof_configuration"):
        proof_window(window)
    from tests.unit.test_google_calendar import Tokens

    tokens = Tokens()
    provider = GoogleCalendarReadProvider(ACCOUNT, tokens, enabled=True, max_events=100)
    with pytest.raises(CalendarError, match="calendar_proof_configuration"):
        await selected_calendar_proof(provider, window)
    assert tokens.calls == 0


@pytest.mark.parametrize("max_events,calendar_id", [(512, "primary"), (100, "other@gmail.com")])
async def test_proof_refuses_broader_configuration(max_events, calendar_id):
    from tests.unit.test_google_calendar import Tokens

    tokens = Tokens()
    provider = GoogleCalendarReadProvider(
        ACCOUNT, tokens, enabled=True, max_events=max_events, calendar_id=calendar_id
    )
    with pytest.raises(CalendarError, match="calendar_proof_configuration"):
        await selected_calendar_proof(provider, WINDOW)
    assert tokens.calls == 0


@pytest.mark.parametrize("mode", ["page", "limit", "denied", "network", "protocol"])
async def test_proof_failure_has_no_partial_evidence_and_disables_provider(mode):
    calls = []

    def endpoint(request):
        calls.append(request)
        if request.url.path == "/oauth2/v2/userinfo":
            return response({"email": ACCOUNT, "verified_email": True})
        if mode == "network":
            raise httpx.ConnectError("private-sentinel")
        data = listing(event())
        if mode == "page":
            data["nextPageToken"] = "private-sentinel"
        if mode == "limit":
            data = listing(*(event(f"fixture{n}") for n in range(101)))
        return response(
            data,
            status=401 if mode == "denied" else 200,
            raw=b"private-sentinel" if mode == "protocol" else None,
        )

    from tests.unit.test_google_calendar import Tokens

    provider = GoogleCalendarReadProvider(
        ACCOUNT, Tokens(), enabled=True, max_events=100, transport=httpx.MockTransport(endpoint)
    )
    with pytest.raises(CalendarError) as caught:
        await selected_calendar_proof(provider, WINDOW)
    assert not provider.enabled and len(calls) == 2
    assert "private-sentinel" not in str(caught.value)


async def test_cancel_proof_discards_token_and_closes_transport():
    entered = asyncio.Event()

    async def endpoint(request):
        entered.set()
        await asyncio.Event().wait()

    provider = GoogleCalendarReadProvider(
        ACCOUNT,
        ProtectedGoogleCalendarTokenSource(
            ACCOUNT, CLIENT, Store(grant()), transport=httpx.MockTransport(endpoint)
        ),
        enabled=True,
        max_events=100,
    )
    task = asyncio.create_task(selected_calendar_proof(provider, WINDOW))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not provider.enabled and provider._tokens._cached is None


@pytest.mark.parametrize("command", ["google-auth", "google-disconnect", "google-proof"])
def test_decline_before_private_file_or_credentials(tmp_path, monkeypatch, command):
    import jarvis.calendar.google_auth as auth
    import jarvis.calendar.google_credentials as credentials

    monkeypatch.setattr(auth, "load_desktop_client", lambda _: pytest.fail("no private input"))
    monkeypatch.setattr(
        credentials,
        "WindowsGoogleCalendarCredentials",
        lambda *_: pytest.fail("no credential access"),
    )
    args = ["calendar", command, "--account", ACCOUNT, "--client-file", str(tmp_path / "missing")]
    if command == "google-proof":
        args.extend([WINDOW.start.isoformat(), WINDOW.end.isoformat()])
    result = CliRunner().invoke(app, args, input="n\n")
    assert result.exit_code == 0, result.output


def test_cli_proof_real_composition_and_sanitized_failures(tmp_path, monkeypatch):
    import jarvis.calendar.google as google
    import jarvis.calendar.google_auth as auth
    import jarvis.calendar.google_credentials as credentials

    path = client_file(tmp_path)
    store, calls = Store(grant()), []
    failed = False

    def endpoint(request):
        calls.append(request)
        if failed:
            raise httpx.ConnectError("private-sentinel")
        if request.url == TOKEN_URI:
            assert parse_qs(request.content.decode())["grant_type"] == ["refresh_token"]
            return response(token())
        if request.url.path == "/oauth2/v2/userinfo":
            return response({"email": ACCOUNT, "verified_email": True})
        return response(listing(event()))

    transport = httpx.MockTransport(endpoint)
    original_source, original_provider = (
        auth.ProtectedGoogleCalendarTokenSource,
        google.GoogleCalendarReadProvider,
    )
    monkeypatch.setattr(credentials, "WindowsGoogleCalendarCredentials", lambda *_: store)
    monkeypatch.setattr(
        auth,
        "ProtectedGoogleCalendarTokenSource",
        lambda *a, **k: original_source(*a, **k, transport=transport),
    )
    monkeypatch.setattr(
        google,
        "GoogleCalendarReadProvider",
        lambda *a, **k: original_provider(*a, **k, transport=transport),
    )
    args = [
        "calendar",
        "google-proof",
        WINDOW.start.isoformat(),
        WINDOW.end.isoformat(),
        "--account",
        ACCOUNT,
        "--client-file",
        str(path),
    ]
    result = CliRunner().invoke(app, args, input="y\n")
    assert result.exit_code == 0, result.output
    evidence = json.loads(result.output.splitlines()[-1])
    assert evidence["read_pass"] and evidence["preparation_pass"] and len(calls) == 3
    for value in [ACCOUNT, "sentinel", "Synthetic", CLIENT.client_id]:
        assert value not in result.output
    failed = True
    result = CliRunner().invoke(app, args, input="y\n")
    assert result.exit_code == 1 and "private-sentinel" not in result.output


def test_bad_cli_window_before_private_inputs(tmp_path, monkeypatch):
    import jarvis.calendar.google_auth as auth

    monkeypatch.setattr(auth, "load_desktop_client", lambda _: pytest.fail("no private file"))
    result = CliRunner().invoke(
        app,
        [
            "calendar",
            "google-proof",
            WINDOW.start.isoformat(),
            (WINDOW.end + timedelta(seconds=1)).isoformat(),
            "--account",
            ACCOUNT,
            "--client-file",
            str(tmp_path / "missing"),
        ],
    )
    assert result.exit_code == 1 and "calendar_proof_configuration" in result.output
