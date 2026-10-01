# JARVIS phone web app and Garmin

Status: local read-only implementation; live Garmin account and iPhone acceptance pending.
Updated: 2026-09-30

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

## Trusted laptop setup

Run from repository root, after approving one live Garmin Connect login for that session:

```powershell
rtk uv python install 3.12
rtk uv sync --project garmin_sync --locked
rtk proxy garmin_sync\.venv\Scripts\python.exe src\jarvis\garmin\bridge.py login
```

Enter Garmin email, password, and MFA only in that local terminal. Do not put them in chat, an
environment variable, Git, a screenshot, or the phone. The bridge uses unofficial Garmin Connect
web services and may need repair if Garmin changes them. It exposes read methods only. `login`
sends credentials and MFA to Garmin over HTTPS and stores only the resulting refresh token in
Windows Credential Locker.

Keep Core bound to loopback behind the existing private Tailscale HTTPS Serve route. Do not use
the Phase 8D launcher Run/Stop against an unowned route. After a separately approved fresh
browser ticket, open the existing Home Screen PWA, connect, and tap **Refresh Garmin**. Garmin
data requires the trusted laptop and tailnet to be online; offline data is labeled stale. Phone
storage and service-worker cache never hold Garmin API responses.

To remove the local Garmin token, run:

```powershell
rtk proxy garmin_sync\.venv\Scripts\python.exe src\jarvis\garmin\bridge.py disconnect
```

This clears the local token. If access may be exposed, revoke it separately in Garmin account
security settings. Revoke the JARVIS browser device in Core if the phone is lost.

## Acceptance still needed

- Owner-approved trusted-local Garmin login and sanitized read of only the listed categories.
- Owner-approved new browser enrollment ticket with `client.health.read` and risk ceiling 1.
- Physical iPhone PWA shows real bounded Garmin values and chat over private HTTPS; Wi-Fi and
  cellular, loss/reconnect, logout, revocation, and stale/error presentation pass.
- Full repository gate, sidecar dependency audit, secret scan, and CI pass. No private health
  values or account identifiers enter Git or test fixtures.

References: [Garmin library](https://github.com/cyberjunky/python-garminconnect),
[library package metadata](https://pypi.org/project/garminconnect/), and
[Windows Credential Locker backend](https://pypi.org/project/keyring/).
