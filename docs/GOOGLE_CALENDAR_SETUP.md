# Phase 16 Google Calendar decision and setup review

Owner selected **Google Calendar**, **primary calendar**, **same personal Google account as
Phase 15**, on 2026-11-01. Selection is not consent to a new OAuth scope, account read or setup
commitment. No calendar, Google profile, credential, console project or client has been accessed.
Current implementation is an inactive read adapter with a trusted-host token port, explicit
default-off service factory and an inert `jarvis calendar google-plan` CLI. Protected calendar
login/storage/renewal and live proof remain pending. Connected-chat Calendar credentials are
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

4. Grant one explicit foreground primary-calendar acceptance read: owner-selected interval
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
It reads no account, client file, token or calendar and opens no browser. There is currently no
calendar login/disconnect/read CLI with credentials. Do not substitute Gmail auth, paste tokens
into chat/command arguments or use an ambient token file to bypass this boundary.

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
Exact subsecond windows are filtered locally after a conservative whole-second server query.
Cancelled/transparent events do not conflict; adjacent intervals do not overlap.

ETags, normalized source/window and stable ordered response metadata bind revisions. Changes
invalidate prepare; volatile sync tokens are ignored, never stored or followed. Current observation
is `observed-provider`, stale after five minutes/clock rollback. Upstream freshness remains
`unknown`, and missing calendars/hidden provider state never prove availability.

Service disable propagates to the provider; every asynchronous boundary checks generation.
Disable/re-enable cannot revive old results or proceed to event acquisition after a stale identity
response. Cancellation closes the response/client; there is no automatic retry/login/account swap.
Provider bodies, exceptions and credentials remain outside logs, models, client storage and Git.

## Later protected-auth implementation and recovery boundary

Reuse existing Google desktop client-validation/PKCE/loopback and Windows protected-secret
boundaries through reviewed shared primitives. Do not silently widen or replace Gmail credentials.
Calendar refresh grants require a distinct namespace and exact account/client/primary/scope binding;
access tokens must stay volatile. Exact create refuses replacement; same-account renewal remains
foreground, bounded, no scope expansion or token rotation. Implement and verify these contracts
before any authorized live invocation; the current read adapter is not production auth acceptance.

Until then, no activation steps are executable. Stopping the explicit caller or disabling its
service/provider ends acquisition. There is no calendar cache, database migration or provider
mutation to roll back. Existing `.ics` and reminder controls remain as [documented](CALENDAR.md).
No Google grant exists from this work; any future local deletion/provider revocation needs its
exact reviewed recovery path. Physical phone checks: **skipped by owner; unverified**.
