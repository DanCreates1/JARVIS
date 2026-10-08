# JARVIS phone web app and Garmin

Status: M3A local compatibility/preparation; protected session and iPhone acceptance pending.
Updated: 2026-10-07

Local connector organization and one-command saved-session reports were verified on 2026-10-05;
see [Garmin connector and reports](GARMIN_CONNECTOR.md). That standalone report does not populate
the Core bridge's Windows Credential Locker or complete the phone acceptance below.

The existing private JARVIS PWA is the $0 iPhone app path. Safari can add it to the Home Screen.
Phase 8 already proved physical-iPhone install, enrollment, chat, and reconnect. Native M2C
acceptance remains deferred: the owner has no Mac or paid Apple Developer membership and permits
no project spending. No native-build result is claimed.

## What this adds

- A Garmin panel in the same PWA as JARVIS chat. It shows bounded daily steps, resting heart rate,
  sleep duration, stress, latest Body Battery reading, and up to three recent activities.
- A dedicated `client.health.read` scope. Existing PWA enrollments cannot read Garmin data. The
  owner must approve a fresh one-use browser ticket containing the prior PWA scopes plus this
  scope, log out/erase the old PWA key, and enroll again. Revoke the old device in Core when done.
- A Core-owned read-only API and memory-only five-minute summary cache. A refresh attempt is
  limited to once per minute. No raw Garmin response, precise activity location, Garmin token,
  password, or MFA code reaches the phone or model provider.
- An isolated Python 3.12 Garmin bridge. The main JARVIS runtime keeps its Python 3.11 default.
  Pinned `garminconnect` 0.3.16 and `keyring` 25.7.0 run under `garmin_sync/.venv`. The bridge
  explicitly uses Windows Credential Locker, splitting the token across small entries to stay
  within its size limit. It never uses the library's file token store.

## Saved-session compatibility — MVP 3 / M3A

Static review found the standalone 0.3.17 and pinned bridge 0.3.16 serialize the same three fields:
`di_token`, `di_refresh_token`, `di_client_id`. Their session loading/refresh code is compatible;
no bridge dependency upgrade is required. Their installed/locked `curl_cffi` 0.16.3, `requests`
2.34.2 and `ua-generator` 2.1.6 also match. This proves format compatibility, not validity of the
owner's current session. No real token file or Credential Locker entry was opened for review.
Evidence: [pinned 0.3.16 client](https://github.com/cyberjunky/python-garminconnect/blob/c3c1c0d66579696e3843cba20f985c66069140b9/garminconnect/client.py),
[0.3.17 client](https://github.com/cyberjunky/python-garminconnect/blob/218e72ca5459e014435fc2d94fd18bd601fa0c14/garminconnect/client.py).

The prepared `import-session` command performs an offline copy from one explicit absolute local
JSON file to Windows Credential Locker. It accepts only the complete three-field format, rejects
duplicate/unknown fields, control/whitespace/non-ASCII token characters, files over 65,536 bytes,
network/device/alternate-stream paths, and symlink/junction/reparse ancestry. It reads no implicit
`GARMINTOKENS` or default directory, imports no Garmin library, makes no network request, and
never writes the source file. Existing protected sessions are refused. Stop Core and the standalone
connector before authorized import; concurrent import/refresh is unsupported. Do not run two
independent copies of the saved session afterward: upstream refresh can rotate the token, and
Garmin's invalidation behavior has not been established.

**Do not execute yet. Fresh owner authority is required for the actual import and selected source.**
Then run in a trusted local terminal, replacing the placeholder with the selected existing file:

```powershell
rtk proxy garmin_sync\.venv\Scripts\python.exe -I src\jarvis\garmin\bridge.py import-session 'C:\ABSOLUTE\LOCAL\garmin_tokens.json'
```

The result reports only import success; live validity remains unverified. Legacy
`oauth1_token.json`/`oauth2_token.json` and incomplete JWT_WEB-only sessions are rejected. A new
login/MFA requires separate fresh authority, never an automatic fallback. The source remains
unchanged; deletion or revocation of it requires separate authority. Progress and pending gates:
[MVP 3 report](phase-reports/PWA_MVP3_PROGRESS.md).

## Trusted laptop setup

Run from repository root, after approving one live Garmin Connect login for that session:

```powershell
rtk uv python install 3.12
rtk uv sync --project garmin_sync --locked
rtk proxy garmin_sync\.venv\Scripts\python.exe -I src\jarvis\garmin\bridge.py login
```

Enter Garmin email, password, and MFA only in that local terminal. Do not put them in chat, an
environment variable, Git, a screenshot, or the phone. The bridge uses unofficial Garmin Connect
web services and may need repair if Garmin changes them. It exposes read methods only. `login`
sends credentials and MFA to Garmin over HTTPS and stores only the resulting access/refresh
session and client ID in Windows Credential Locker. It removes ambient `GARMINTOKENS` before
login. Upstream diagnostic logs are suppressed. Core launches the isolated interpreter with
`-I` and a minimal operating-system environment, excluding file-store/Python overrides, proxies,
and unrelated credentials. Renewed tokens are preserved even if later profile/category reads fail;
category reads stop on rate limiting. Activity names and unknown activity free text are discarded.
CLI authentication overrides `NETRC` with the null device; saved-session API sessions also set
`trust_env=False` to prevent unrelated `.netrc` credentials replacing Bearer headers
([Requests behavior](https://requests.readthedocs.io/en/latest/user/authentication/#netrc-authentication)).
These controls do not turn the unofficial client's authentication internals into a stable API.

Keep Core bound to loopback behind the existing private Tailscale HTTPS Serve route. Do not use
the Phase 8D launcher Run/Stop against an unowned route. After a separately approved fresh
browser ticket, open the existing Home Screen PWA, connect, and tap **Refresh Garmin**. Garmin
data requires the trusted laptop and tailnet to be online; offline data is labeled stale. Phone
storage and service-worker cache never hold Garmin API responses.

To remove the local Garmin token, run:

```powershell
rtk proxy garmin_sync\.venv\Scripts\python.exe -I src\jarvis\garmin\bridge.py disconnect
```

This clears the local token. If access may be exposed, revoke it separately in Garmin account
security settings. Revoke the JARVIS browser device in Core if the phone is lost.

## Acceptance still needed

- Owner-approved offline saved-session import or trusted-local Garmin login, with authority for
  bounded sanitized Core reads of only the listed categories.
- Owner-approved new browser enrollment ticket with `client.health.read` and risk ceiling 1.
- Physical iPhone PWA shows real bounded Garmin values and chat over private HTTPS; Wi-Fi and
  cellular, loss/reconnect, logout, revocation, and stale/error presentation pass.
- Full repository gate, sidecar dependency audit, secret scan, and CI pass. No private health
  values or account identifiers enter Git or test fixtures.

References: [Garmin library](https://github.com/cyberjunky/python-garminconnect),
[library package metadata](https://pypi.org/project/garminconnect/), and
[Windows Credential Locker backend](https://pypi.org/project/keyring/).
