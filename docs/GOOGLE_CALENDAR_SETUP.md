# Phase 16 Google Calendar decision and setup review

Owner selected **Google Calendar**, **primary calendar**, **same personal Google account as
Phase 15**, on 2026-11-01. Selection is not consent to a new OAuth scope, account read or setup
commitment. No calendar, Google profile, credential, console project or client has been accessed.
Current implementation includes an inactive read adapter, explicit default-off service factory,
protected foreground auth/renewal and an aggregate-only proof CLI. Setup approval, actual login
and live proof remain pending. Connected-chat Calendar credentials are
not Windows Core credentials. No Gmail grant is reused or expanded.

## Concrete proposed decision

Review and approve together before external setup/access:

1. Add **Google Calendar API** to the owner-controlled personal project prepared for Phase 15,
   or identify the exact approved replacement project if that project still does not exist.
   Existing email setup approval remains within its original scope. No billing linkage,
   public publishing, paid verification, new account or unreviewed legal commitment.
2. Create a separate **Desktop app** OAuth client, proposed name **JARVIS Windows Calendar**,
   distinct from Gmail's client. Same exact personal account, External/Testing audience and
   owner test user. Owner reviews actual consent/terms and performs Google login/MFA.
3. Request exactly:
   - `https://www.googleapis.com/auth/calendar.events.owned.readonly`
   - `https://www.googleapis.com/auth/userinfo.email`

   Include offline access for **explicit foreground same-account renewal**, not background
   polling. Store the exact account/client/primary/scope-bound refresh grant in a distinct
   per-user Windows Credential Manager entry; access tokens remain volatile. Refuse existing
   entry replacement, refresh-token rotation, account changes or scope expansion. This grants
   no unattended acquisition authority. Existing Gmail credentials remain separate.

4. Grant one explicit foreground primary-calendar acceptance read: owner-selected whole-second interval
   **<=7 days**, **<=100 expanded entries**, one verified-email identity GET and one event-page
   GET, five-second read deadline, zero retries/pagination. Inspect only bounded basic event
   evidence and prepare an unsent local proposal; evidence output must contain counts/booleans,
   never titles, account, event IDs, timestamps, tokens or client-file contents.

The owned-events scope can read **all Google calendars the account owns**. JARVIS's selected
target is only the primary calendar; the trusted token port binds account **and calendar** and
rejects a substituted selector. The identity scope reveals the primary email solely to verify
the chosen exact account before calendar acquisition. No contacts, broad profile, shared-calendar
read, calendar list/settings, Drive, Gmail, write, attendee response or invitation scope.
No background polling, notification sender, provider writes, PWA scope or model disclosure.
Initial-read approval does not authorize unattended future acquisition or broadened targets.

Sources reviewed before implementation: [scope definitions](https://developers.google.com/workspace/calendar/api/auth),
[event-list authorization/parameters](https://developers.google.com/workspace/calendar/api/v3/reference/events/list),
[event resource](https://developers.google.com/workspace/calendar/api/v3/reference/events),
[Google identity API contract](https://www.googleapis.com/discovery/v1/apis/oauth2/v2/rest),
[Desktop OAuth](https://developers.google.com/identity/protocols/oauth2/native-app),
[API terms](https://developers.google.com/terms) and
[user-data policy](https://developers.google.com/terms/api-services-user-data-policy).
Review actual console requirements at setup; stop if it demands billing or a different commitment.

## Current executable preparation

```powershell
rtk proxy uv run --locked jarvis calendar google-plan
```

This prints the selected target, proposed scopes, limits and explicit disabled/unapproved state.
It reads no account, client file, token or calendar and opens no browser. Following commands
are prepared for use **only after the concrete decision above is approved**. No real invocation
has occurred. Do not substitute Gmail auth or paste tokens into chat/command arguments.

```powershell
rtk proxy uv run --locked jarvis calendar google-auth `
  --account <exact-lowercase-account> --client-file C:\private\calendar-desktop.json

rtk proxy uv run --locked jarvis calendar google-proof `
  <owner-selected-whole-second-start-with-offset> <owner-selected-whole-second-end-with-offset> `
  --account <exact-lowercase-account> --client-file C:\private\calendar-desktop.json
```

Keep actual account/client paths in the private local terminal, outside Git/chat evidence.
Each consequential CLI prompt defaults to No and precedes client-file/protected-store access.
This application confirmation enforces a local invocation boundary; it does not supply missing
owner setup, scope or private-read authorization. After owner approval covering an exact
invocation, automation may answer its matching prompt without requesting the same approval again.
Wrong/expired/missing grants fail closed; commands never silently start a new login or replace one.

`google-auth` requests only the two listed scopes with PKCE S256, random state and ephemeral
127.0.0.1 callback. Total login timeout is 180 seconds; callback requests are bounded to eight,
four active handlers, 8 KiB/request and two seconds/handler. Host/path/state/issuer/header/body
checks reject hostile callbacks. One bounded token POST and verified-email GET precede exact
create in Windows Credential Manager. Login never reads calendar events. Client JSON must be an
explicit absolute local regular single-link file <=16 KiB, without reparse/network/alternate-stream
paths. Known Google client-metadata endpoint spellings are accepted; live endpoints stay fixed.

`google-proof` validates the <=7-day whole-second window before client or store access. One
foreground operation acquires/renews the exact protected grant, verifies email and reads one
<=100-entry primary-calendar page within five seconds. No login, retry or pagination.
An unsent cancellation proposal binds the exact volatile observed event without another network
read. No event cancellation is performed or approved. Empty calendars honestly return
`read_pass=true`, `proposal_prepared=false`, `preparation_pass=false`; they cannot satisfy the
read/prepare live gate alone. Output contains counts/booleans only, never timestamps, titles,
account/client/event IDs, revision digests, private file content or tokens.

`build_google_calendar_service(account, tokens, enabled=False, calendar_id="primary")` consumes
the existing provider-neutral service. Only trusted host composition may supply already-authorized
`GoogleCalendarAccessToken` values with exact account/calendar/scopes and live expiry. Normal
runtime/bootstrap never constructs the provider. The library's explicit owned-secondary-selector
support grants no secondary-calendar authority; selected acceptance remains primary only.

## Acquisition, normalization and freshness

One operation includes token acquisition and exactly two GETs to fixed Google HTTPS endpoints.
Exact verified-email identity precedes all event reads. Request projection includes event IDs,
ETags, status, title, start/end, transparency and recurrence instance metadata. Descriptions,
attendees, locations, attachments, links and conference data are not requested. No calendar/list
or account discovery. Redirects, ambient proxies, cross-request cookies, compressed bodies,
malformed/duplicate JSON, invalid account/scopes/expiry and non-owner access fail closed.

Normal library ceiling: one **1 MiB**, **512-entry** event page, **31-day** window. The initial
proof must configure `max_events=100` and <=7 days; over-cap inventories or any nextPageToken
fail the entire operation. No partial availability claim. Recurrence is expanded by Google using
`singleEvents=true`; unexpanded rules are rejected. All event types are requested; unknown types
fail closed. Cancelled tombstones are not busy and may lack time/title. Moved instances retain
identity through originalStartTime. Date-only end is exclusive and uses calendar timezone.
Timed values require explicit offsets; a supplied IANA timezone must agree with that offset.
Exact subsecond windows are filtered locally after a conservative whole-second server query;
the rounded query must also fit 31 days, or fail before token acquisition. Initial proof uses
whole-second endpoints and a seven-day ceiling.
Cancelled/transparent events do not conflict; adjacent intervals do not overlap.

ETags, normalized source/window and stable ordered response metadata bind revisions. Changes
invalidate prepare; volatile sync tokens are ignored, never stored or followed. Current observation
is `observed-provider`, stale after five minutes/clock rollback. Upstream freshness remains
`unknown`, and missing calendars/hidden provider state never prove availability.

Service disable propagates to the provider; every asynchronous boundary checks generation.
Disable/re-enable cannot revive old results or proceed to event acquisition after a stale identity
response. Cancellation closes the response/client; there is no automatic retry/login/account swap.
Provider bodies, exceptions and credentials remain outside logs, models, client storage and Git.

## Protected-auth storage and recovery

Calendar auth adapts the published reviewed Gmail client-validation/PKCE/loopback/token-transport
and Windows protected-secret protocol into Calendar-owned modules. Held Gmail edits stay preserved;
no Gmail token source/store is imported, read or expanded. No new dependency or credential backend.
Namespace: `JARVIS/Calendar/Google/v1/<sha256-binding>`; binding includes exact account,
client, `primary` and sorted scopes. Entry contains only version/binding and refresh grant, <=2,560
bytes, current Windows user/host persistence, no enumeration/roaming/plaintext fallback.
Access tokens remain volatile. Exact create refuses replacement under a cooperative per-target
mutex. Renewal has a five-second deadline including lock wait and refuses changed scopes,
missing/invalid expiry and refresh-token rotation. Local deletion is rechecked even before cached
use and after network renewal; cancellation discards pending results.

Stop explicit callers or disable the service/provider to end acquisition. Stop other Calendar/Core
processes before the separately confirmed exact local deletion command:

```powershell
rtk proxy uv run --locked jarvis calendar google-disconnect `
  --account <exact-lowercase-account> --client-file C:\private\calendar-desktop.json
```

Deletion affects only this local Calendar grant; it does not revoke Google consent or delete events,
Gmail grants or history. Provider revocation stays an explicit owner operation in Google Account
settings. No automatic remote revocation/token replacement. New consent after expiration or
revocation requires applicable approval. Google's External/Testing refresh grants can expire after
seven days for these scopes; expiry is unavailable evidence, not authority to log in again. See
[Google token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
Current official desktop/scopes/expiration/Windows CredWrite contracts rechecked 2026-11-04;
[Windows storage contract](https://learn.microsoft.com/en-us/windows/win32/api/wincred/nf-wincred-credwritew).

No calendar cache, database migration or provider mutation to roll back. Existing `.ics` and
reminder controls remain as [documented](CALENDAR.md). No real Google grant or private source
access exists from this work. Synthetic protocol/Windows-storage verification is distinct from
pending real protected-auth and live acceptance. Physical phone checks: **skipped by owner; unverified**.
