# Private calendar and owner-authored reminders

Current Phase 16: trusted-local CLI read/prepare foundation. One Core, no calendar cache,
new scheduler, model tool, PWA scope or automatic feature activation. Live provider selection
and authorized owner-source acceptance remain pending; see [progress](phase-reports/current/PHASE_16_PROGRESS.md).

## Explicit source and inspection

Choose one local UTF-8 `.ics` file and its IANA calendar timezone. No recursive search,
account discovery, network URL fetch or source modification. Use an absolute local path;
UNC/network drives, links/reparse points, hard links, alternate streams and non-files fail closed.
Private exports are ignored by Git; keep them outside source directories.

```powershell
rtk proxy uv run --locked jarvis calendar inspect C:\private\calendar.ics `
  2026-11-01T00:00:00-04:00 2026-11-08T00:00:00-05:00 --timezone America/Toronto
```

Output is private ASCII JSON: hashed source/event/occurrence identifiers, exact source SHA-256
revision, observation timestamp, query window, occurrences and conflict pairs. Titles remain
untrusted data, never instructions. Terminal control/directional characters are escaped, and
errors expose fixed codes only. Do not post private output in chat, CI or Git.

`observed-export` means the explicit file was read within five minutes; `provider_freshness`
is always `unknown`. At five minutes, or after clock rollback, the snapshot is stale. No local
export proves current provider availability; omitted calendars remain unknown. No success is
retained after a failed refresh. Every command reads anew; cancellation never retries.

## Supported calendar semantics and bounds

RFC 5545 subset, reviewed against [official specification](https://www.rfc-editor.org/rfc/rfc5545):
one VCALENDAR with VERSION 2.0, PRODID and optional GREGORIAN CALSCALE; VEVENT fields UID,
UTC DTSTAMP, DTSTART, DTEND, SUMMARY, RRULE, EXDATE, STATUS, TRANSP and SEQUENCE. UTF-8
line folding and escaped summary text supported. Timed events require explicit UTC `Z` or
IANA TZID on start/end, same zone and positive duration. Floating times fail closed. All-day
dates use the explicitly selected calendar timezone; DTEND is exclusive, or defaults to next day.

Daily/weekly recurrence requires finite COUNT 1–366 and optional INTERVAL 1–52. EXDATE
removes matching occurrences. Local recurring start times retain wall time over DST;
nonexistent recurrence starts are skipped without consuming COUNT. Explicit nonexistent
starts fail. Repeated wall times choose first instant per RFC 5545. Timed duration is elapsed
duration from original DTSTART/DTEND; all-day duration uses local calendar days. ZoneInfo uses
installed timezone data; see [Python reference](https://docs.python.org/3.11/library/zoneinfo.html).
Cancelled and transparent events remain inspectable but do not block conflict checks.
Conflict uses half-open intervals; adjacent events do not overlap.

Unsupported data rejects the **whole snapshot**, never silently drops events: unbounded,
monthly/yearly/BYDAY/UNTIL/RDATE rules, exception overrides/RECURRENCE-ID, VTIMEZONE definitions,
alarms, attachments, descriptions, attendees, organizers and other properties/components.
This intentionally narrow adapter will reject many ordinary provider exports. It reports
unavailable evidence; it does not claim a general ICS importer. Use a deliberately compatible
export or select a reviewed provider adapter; do not edit exports to hide conflicting events.

Bounds: 256 KiB file, 8,192 characters/unfolded line, 100 source events, 366 instances/series,
512 returned occurrences and 31-day query. Overflow/unsupported input fails closed. The service
has one five-second deadline, no retries and generation checks across disable/re-enable. Local
file reads run in a thread; cancellation discards the result, and an already-started bounded
filesystem read may finish. No network provider, credentials, cloud, effects or spend.

## Prepare an event change

Copy exact revision and occurrence ID from inspection. Reacquisition must match revision and
source; replacements require a query covering their complete interval for conflict checks.

```powershell
rtk proxy uv run --locked jarvis calendar prepare C:\private\calendar.ics `
  2026-11-01T00:00:00-04:00 2026-11-08T00:00:00-05:00 `
  <revision-sha256> <occurrence-id> update --timezone America/Toronto `
  --replacement-start 2026-11-03T09:00:00-05:00 --replacement-end 2026-11-03T10:00:00-05:00
```

`cancel` prepares a cancellation without replacement fields. Both outputs are volatile proposals:
`written=false`, `approval_granted=false`. They grant no permission or provider scope. No create,
update, delete, invitation, attendee response or send adapter exists. A future write path needs
exact trusted approval, correct provider scope, version/idempotency and postcondition checks.

## Owner-authored reminders

Supply exact title, offset-bearing due instant and IANA timezone. Due must be in next 30 days.
This prints an existing `ProactivityProposal`, without storage or activation:

```powershell
rtk proxy uv run --locked jarvis calendar reminder "Review project" `
  2026-11-03T09:00:00-05:00 --timezone America/Toronto
```

If saving private JSON, choose a private explicit file outside Git. Feed it through existing
`jarvis proactive create`, inspect exact version/digest, then trusted-local `proactive activate`.
Feature is `calendar.reminder`; global, feature and runner gates remain independently off.
Only deliberate foreground ticks produce generic local inbox metadata. No private reminder
title is sent as a notification. No provider, task, cloud, effect or outbound message is authorized.
See [existing lifecycle and commands](PROACTIVITY.md#create-and-activate-a-rule) for show,
disable, cancellation, export, delete, replay prevention and restart recovery. No gate was enabled.

## Provider choice and recovery

Live calendar provider/account/calendar selection remains missing information. Gmail credentials
and `gmail.readonly` confer no calendar access. Connected chat integrations are not desktop Core
credentials. For Google, review [events list](https://developers.google.com/workspace/calendar/api/v3/reference/events/list)
and [narrow scopes](https://developers.google.com/workspace/calendar/api/auth) before a separate
exact account/calendar auth/read decision. No connected calendar/profile was read in this phase.

Stop invoking calendar commands to stop acquisition. There is no calendar state migration or
cache to restore/delete. Original export remains unchanged; private command output follows owner
file retention. Existing reminder data stays in canonical Core SQLite; use exact `proactive disable`
then cancellation/deletion controls. Do not delete an owner database as rollback. Revert calendar
source/CLI additions only if needed; preserve existing Core migrations and reminder evidence.
Physical phone checks: **skipped by owner; unverified**. No physical/MVP/production claim.
