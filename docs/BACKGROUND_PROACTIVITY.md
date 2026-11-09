# Bounded background suggestions

Current Phase 17 extends [legacy foreground policy](PROACTIVITY.md) inside the
[single Windows Core](JARVIS_ARCHITECTURE.md#current-core-decision--2026-10-26). Core/PWA startup
never launches the worker. Production activation is excluded from development acceptance.

## Scope

An explicitly activated owner-authored one-time/daily rule creates one generic local inbox item
when due. `proactive inbox`, `explain` and `show` expose the suggestion and exact rule to the local
owner. Existing snooze/dismiss/cancel/disable/delete controls remain. The worker reuses existing
policy, runner and canonical SQLite state; it is not a second task scheduler.

No DAG execution, task handoff, source acquisition, model/tool/broker invocation, approval creation,
OS/browser notification, event subscription or external destination exists in this worker. No
email/calendar/Garmin polling or Phase 18 briefing. An independently scoped existing PWA adapter
gets no new authority and remains separately gated. Private titles stay in the existing local
rule store; candidate/inbox/worker metadata never contains a private notification preview.

## Opt-in and lifetime

Existing global, feature allowlist and runner gates all default off. Installation changes no
production setting. Worker consent additionally binds exact host, policy hash, feature subset,
control generation, poll interval, tick budget and absolute UTC expiry. Local review input is
capped at 16 KiB, output refuses overwrite, and private errors are suppressed. Activation requires
a <=5-minute review, full SHA-256 digest and exact phrase. The eight-character phrase suffix is
only a typing check; it never substitutes for the full digest. Stop/re-enable invalidates old
reviews and leases.

For a separately authorized session, use the same explicit data/profile as its approved rules:

```powershell
rtk proxy uv run --locked jarvis proactive background status
rtk proxy uv run --locked jarvis proactive background preview <new-review.json> `
  --feature task.checkin --seconds 300 --poll-seconds 5 --max-ticks 60
# Inspect exact review and printed limits before using its exact phrase.
rtk proxy uv run --locked jarvis proactive background enable <review.json> `
  --expected-digest <printed-full-sha256> `
  --confirm "ENABLE BACKGROUND <printed-eight-hex>"
rtk proxy uv run --locked jarvis proactive background run
# Separate local terminal, same data/profile:
rtk proxy uv run --locked jarvis proactive background stop
```

Preview/enable start no process. `run` owns one bounded process; Ctrl+C cancels and drains it.
Persistent `stop` revokes consent. No detach, service, scheduled task, startup registration, remote
mutation route or automatic restart. Explicit restart can use only original unexpired consent
and remaining budget. Every new consent needs another review. Laptop must remain awake.

## Enforced bounds

| Boundary | Limit |
| --- | --- |
| Session | Positive lifetime <=3,600 s; absolute UTC expiry, hard monotonic cap and rejection of startup before consent creation |
| Polling | Integer 1–60 s; <=3,600 durable reservations/consent, including failed ticks |
| Tick | <=500 active rule scans, one existing dispatch, 5 s timeout |
| Owner | One host lease, random token, generation fence; renewed <=90 s and within consent expiry |
| Stop/config | Fresh persistent authority and global/runner/feature policy checked <=1 s apart while idle; target <=2 s with unlocked store |
| Clock | >5 s wall/monotonic drift stops at next evaluation; no catch-up burst |
| Existing policy | <=6 candidates/hour, <=24/day, <=300 attention seconds/day, one active candidate, <=30-day rule, cost $0 |

Worker SQLite busy waits are <=1 s. Polling waits after each completed tick. Storage/config/
corruption failure exits without hidden retry. >500 active rules retain the existing bounded
newest-first list behavior; rules outside that window are omitted from that tick.

Existing IANA zones, DST gap/fold, quiet hours, expiry and occurrence keys remain authoritative.
Background creation and dispatch never happen early. Late occurrences are eligible only within
the configured existing grace/skew ceiling (<=300 s); older occurrences are skipped. Quiet hours
are checked at schedule time and actual inbox completion, including a boundary crossed mid-tick.
A daily explicit fold on a nonambiguous date retains existing fail-closed behavior; preview the
exact next occurrence before activation.

## Recovery and removal

Additive migration 021 creates inert `proactivity_worker_controls` in the canonical database.
Candidate, claim and inbox transactions check current host, generation, owner token and fresh
lease/consent expiry. Stop/re-enable serializes against those writes. Earlier committed suggestions
remain inert. Stopping does not delete existing inbox items; cancel/dismiss or disable/delete their
exact rules separately. Candidate/inbox uniqueness and durable polling reservations survive restart.

After a crash, wait for the original lease to expire (<=90 s) or explicitly stop/review a new
consent. Old owners cannot reserve, deliver or clear a newer lease. Cancellation drains owned
work and releases ownership. No task replay exists because no task is executed.

Removal: stop, inspect/cancel inbox, disable/delete exact rules, leave feature/runner/global gates
off. Stop erases the stored plan and lease, retaining a content-free generation/counter against
replay. The explicit review file remains owner-controlled. Never remove migration 021 from an
existing store or downgrade its schema in place. Natural expiry retains only the bounded control
metadata until explicit stop; no automatic purge is installed. Ordinary conversations remain independent.

Implementation uses Python 3.11 [cancellation/timeouts](https://docs.python.org/3.11/library/asyncio-task.html)
and SQLite [IMMEDIATE transactions](https://www.sqlite.org/lang_transaction.html), checked
2026-11-08. No new dependency or OS API.

## Synthetic verification

```powershell
rtk proxy uv run --locked python scripts/phase17-background-benchmark.py --enforce `
  --output runtime/phase17/background-soak.json
```

Fresh temporary state stays under ignored `runtime/`. The harness reuses the fixed 30-day/
1,000-decision policy oracle, runs 100 worker incidents and >=1,800 real ticks for >=1,800 s;
tick p95 <=50 ms, CPU <=5% of one logical core, RSS growth <=50 MiB. It checks duplicate/private
exclusion, removes rule/worker-plan state, proves a synthetic ordinary Core turn still works,
then removes temporary state. Shortened runs cannot pass `--enforce`. This is a synthetic oracle,
not a human usefulness study or production acceptance. See [current evidence](phase-reports/current/PHASE_17_COMPLETION.md).
Phone checks remain **skipped by owner; unverified**.
