# Private Garmin workspace

Current Phase 8 capability on the existing Windows Core and PWA. Launch explicitly:

```powershell
rtk proxy .\scripts\open-garmin.cmd
```

First identify the existing Core/process owner. Stop an existing writer normally before starting
another against the same store. Launcher selects `private-garmin`, installed `qwen3:1.7b`, local
daily text and read-only Garmin. It changes no private route, credential, device or scope. Core
remains one process/store/router; laptop must be on/reachable. No model download or cloud role.

Open the existing private HTTPS `/app/`, then Settings → Connect existing device. Garmin requires
an already approved `client.health.read` device **and session** scope for the current Core owner.
Existing enrollments gain nothing automatically. If scope is absent, view remains unavailable;
any production enrollment/scope change needs its separate concrete approval. No phone check is
requested. `prototype-text` and `daily-text` remain text only, including at the health API.

Select Garmin, then **Refresh Garmin**. In this profile connecting, navigation, chat and browser
resume perform no health read. Refresh uses the existing protected saved session, with normal
same-account renewal and required authentication profile/settings reads. Startup never reimports
the old file or falls back to interactive login/MFA. Keep Core as sole session reader; do not run
the standalone reporter against the independent original copy.

| View | Meaning and bound |
| --- | --- |
| Steps / resting heart rate / sleep / stress / Body Battery | Explicit mapped values; unsupported or absent fields say Unavailable, never invented zero. |
| Recent activities | At most three generic activity types/dates; no original names, IDs, GPS or raw responses. Empty successful endpoint differs from unavailable endpoint. |
| Data date and last checked | Core fetch time, **not device sync time**. Wearable sync time is unavailable through this six-read contract. |
| Freshness | Stale after five minutes, day rollover, invalid/future time or network/refresh failure. Different laptop/client calendar days can conservatively mark data stale. |
| Refresh | Memory-only Core cache <=300 seconds; upstream attempt no more than once per 60 seconds per running Core. Refresh inside that window can return the same timestamp. |
| Failure | Retained tab values are explicitly stale/uncertain. Failed server refresh clears server cache; throttled retries cannot turn that failure into old-data success. |

The bridge uses its locked Python 3.12 environment, fixed six read methods, no library retry,
90-second total child deadline and 8,192-byte normalized output limit enforced during reading.
Overflow/timeout/cancellation kill the child, discard remaining pipe output in fixed chunks, then
reap it without a full-pipe deadlock. Concurrent refreshes share the existing
Core lock/cache/throttle. Process restart drops health/cache/throttle; it does not reimport tokens.
Cached summaries are immutable. Duplicate JSON fields, invalid dates, naive fetch timestamps,
coerced numeric values, extra private fields and oversized activity lists fail closed.

Garmin responses remain private, untrusted data. No automatic health input to chat, model prompts,
memory, history, notifications, diagnostics or browser persistence. Only normalized view crosses
the authenticated Core API with `Cache-Control: no-store`; service worker caches fixed shell
assets only. Browser identity still uses existing dedicated IndexedDB, never health storage.
Other optional features remain disabled in this profile: files/research/email/voice/camera/actions/
task execution/proactivity. Daily text quality has [bounded Phase 7 limits](DAILY_TEXT.md).

Logout clears displayed Garmin and identity immediately, aborts obsolete fetches and rejects late
results. Health-access denial clears values; reconnect requires current authentication and scope.
Offline logout proves local erase only, not server revocation. Provider disconnect requires
trusted-host operation; no remote disconnect or provider-write API exists. After approved local
disconnect, a running Core may retain its memory cache for at most five minutes; stop/restart its
owned process to clear immediately. Another tab's displayed memory cannot be remotely erased;
its freshness/next protected request remains the boundary. Local deletion does not revoke the
Garmin-side session or delete old standalone report/source files. Those actions remain separate.

For current flags-only Core diagnostics, first ensure no competing Core/standalone reader:

```powershell
rtk proxy uv run --locked python scripts/garmin_core_check.py --read
```

One read, no report files; only schema/freshness/activity-bound and category-presence booleans.
No health values, dates, account identifiers, tokens or provider errors appear. Unavailable result
requires trusted-local diagnosis; new login/MFA remains consequential and has no automatic fallback.
Disconnect and renewal are tested with synthetic vaults; no live deletion is acceptance work.

Recovery without data migration: stop the owned Core normally and launch `open-daily.cmd` or
original `open-local.cmd`. Protected session remains in Windows Credential Locker. Native dependency
publication stays held; phone checks **skipped by owner; unverified**. No medical interpretation,
physical/mobile MVP/production acceptance or deployment follows from this workspace.

Evidence: [Phase 8 report](phase-reports/current/PHASE_8_COMPLETION.md),
[protected connector contract](PWA_GARMIN.md). Rechecked primary implementation references:
[pinned Garmin client](https://github.com/cyberjunky/python-garminconnect/blob/c3c1c0d66579696e3843cba20f985c66069140b9/garminconnect/client.py),
[Windows keyring backend](https://keyring.readthedocs.io/en/latest/),
[bounded asyncio streams](https://docs.python.org/3.11/library/asyncio-subprocess.html),
[Requests environment authentication](https://requests.readthedocs.io/en/latest/user/authentication/#netrc-authentication).
