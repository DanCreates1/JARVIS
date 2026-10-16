# F11 — physical phone acceptance

Status: `in-progress`; initiated 2026-10-15 at `4fa75e3`, shell **v8**.
No new physical result recorded. Aggregate MVP 4 remains incomplete.

Readiness gate found and repaired concurrent immediate-cancellation settlement on 2026-10-15.
The initial Core process predated that Python fix. At the owner's return on 2026-10-15, Core was
already stopped; patched Core was started using the verified existing configuration. Readiness
rechecked at `2026-10-15T22:15:54-04:00`: one loopback listener and private v8 assets HTTP 200.
This does not change shell v8 assets and is not the observed in-flight restart required by F11-P6.
Owner confirms phone available. A bundled metadata/non-health/status prompt received **no**;
its referent is unconfirmed. Requested Garmin status wording only, without health values.
Phone metadata, retained identity/runtime and connection status remain unverified; Connect stays
paused. Subsequent read-only Core evidence establishes the non-health boundary below.
Availability alone accepts no physical row.

## Execution boundary

Use compact owner-operated batches on the existing iPhone Home Screen PWA and approved private
HTTPS route. Record date/time with offset, phone/iOS, surface, connection type, orientation,
text/zoom, VoiceOver and keyboard availability. Use public synthetic prompts only; retain row
results, counts, durations and sanitized symptoms, never transcripts, origin, identifiers or keys.

Before Connect, establish the existing identity's non-health boundary from previously connected
guidance with same-identity continuity, or a current trusted Core metadata check showing every
active browser enrollment has exactly the prior seven scopes and no `client.health.read`.
Fresh disconnected startup displays **Connect JARVIS to see Garmin data.**; the new-enrollment
guidance is assigned only after Connect and cannot be required before a fresh connection.
If neither evidence path is established, stop authenticated checks; do not connect to discover
scope. Enrollment, erasure, revocation and Garmin acceptance remain
in [MVP 3](phase-reports/PWA_MVP3_PROGRESS.md); its pending grouped decision stays pending.

2026-10-15 continuation: owner reports the generic disconnected Garmin text and privacy hint.
Read-only Core metadata inventory finds one active browser enrollment, exactly the prior seven
scopes, no health scope and risk ceiling at most 1. No IDs, names, keys or tokens emitted, no
state changed. This establishes the Core non-health boundary; retained phone identity/runtime
and physical connection still need observation. The generic text is not a scope/asset pass.
Owner subsequently reports different Device access wording from the expected enrolled-key startup
sentence. Exact public wording requested; no missing-key, wrong-surface or stale-script diagnosis
inferred from that answer alone.

Reload online and close/reopen twice without clearing website data. Inspect the new controls and
record their behavior as a v8 runtime fingerprint. This supports current execution; it does not
close the separate loaded script/CSS/worker/cache verification in
[M4A](PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md). No Mac inspection surface is currently established.

Run in order. Stop after a failure; capture only the row and public symptom. If a reply finishes
before cancellation/interruption, record the attempt as unobserved and use another public request.
Do not repeatedly tap Send or manually resend an uncertain request. Retry request owns recovery.

## Functional and accessibility ledger

| ID | Compact batch and fixed pass criterion | Result |
| --- | --- | --- |
| F11-P0 | Confirm metadata, non-health guidance and retained identity; reload/reopen twice. Saved conversations, New conversation and Refresh history appear. Record version method separately from full asset proof. | pending: owner observations |
| F11-P1 | Connect existing device once if needed. With VoiceOver, inspect Saved conversations, New conversation, Refresh history, Load earlier messages, Cancel reply and Retry request when available. Names, order, unavailable/busy states and focus usable; Send waits authenticated readiness. | pending |
| F11-P2 | Send once: `Write 40 numbered sentences about a fictional blue cube. Do not use tools or save memories.` During generation activate Cancel reply once. Observe confirmed cancellation, no later completion replacing it, usable focus and a subsequent new public request succeeding. If completion wins the race, cancellation remains untested. | pending |
| F11-P3 | During a separate public request, briefly disconnect/reconnect phone Tailscale. When Retry request is offered, activate it once. Recover the original outcome with one user turn and at most one answer; no replacement submission or false completion. Record whether running/completed/cancelled/failed/interrupted. If Retry never appears, its physical gate remains pending. | pending |
| F11-P4 | Finish public turns in two new conversations; Refresh history, switch saved conversations and reopen the app. Correct owned history restores without duplicate turns or replayed completion speech. Use Load earlier messages only when real bounded pagination exists; otherwise keep pagination pending. Do not create 50+ turns merely to expose it. | pending |
| F11-P5 | Three app close/reopen cycles, including one during a public generation. Reconnect with the same retained key as needed. Reconcile original outcome/history without automatic resubmission or duplicate speech. Background/resume is not process eviction; label actual mechanism. | pending: 0/3 |
| F11-P6 | Three interruptions: idle phone-network loss, in-flight phone-network loss, then one coordinated loopback Core restart during a public generation. Preserve route and identity. Same-device reconnect restores history; unresolved Core work is explicitly interrupted, never silently replayed. Coordinate restart while owner observes; do not disrupt Core before that batch. | pending: 0/3 |
| F11-P7 | Thirty-minute foreground soak, including at least ten public turns and P2–P6 where feasible. Zero duplicate turns, unexpected private content, false readiness/completion, unrecoverable controls or app eviction. Record Wi-Fi/cellular separately; an unavailable network remains blocked. | pending |

Retest M4A A1/A3–A5/A9/A11 for the new controls where applicable; historical v7 observations
remain dated. A2 requires an already identity-free surface; A6 requires observed spoken failure
and draft recovery; A10 requires an available external keyboard. Logout focus requires separate
M3C exact-device authority. No unexecuted row becomes passing from a synthetic test.

## Phone performance targets frozen before measurement

Frozen 2026-10-15, before any new phone samples. These are product acceptance budgets chosen for
this phone client, not measured capabilities or replacements for Phase 1 provider thresholds.
Keep failures and slow samples; do not tune thresholds after seeing results.

| Metric | Start → finish; sample requirement | Fixed target | Result |
| --- | --- | --- | --- |
| Cached startup | Home Screen activation after close → usable shell controls, excluding explicit Connect; 20 reopenings, no cache deletion | p50 ≤3s; p95 ≤5s; zero failed loads | pending |
| Saved-history navigation | Select saved conversation → corresponding latest page rendered and controls usable; 20 selections | p50 ≤1s; p95 ≤2s; zero wrong-conversation renders | pending |
| First visible delta | Send activation → first answer text on screen; 20 completed public requests, record route/model and Core cold/warm state without content | p50 ≤3s; p95 ≤7s; zero failed requests | pending |
| Confirmed cancellation | Cancel activation → authoritative cancelled state; 5 observed in-flight cancellations | all ≤5s; zero late completion replacements | pending |
| Memory during soak | Phone web-content process resident-memory samples after warm-up and at end of the 30-minute soak, same measurement method | growth ≤50MiB; zero eviction/crash | blocked: no established phone memory instrumentation |

Twenty samples are required per timing series and per network being accepted; never pool Wi-Fi
and cellular. Sort all durations; nearest-rank p50 is sample 10 and p95 sample 19 for n=20. Record
sample count, errors and min/max. Stopwatch timing is allowed with declared resolution/reaction
uncertainty; a value whose uncertainty crosses its budget cannot establish a pass. Avoid screenshots
and recordings. First-delta timing includes provider/network delay; report a miss even if provider
latency explains it. Cached startup does not claim cold-install or authenticated-ready performance.

Desktop RSS, JavaScript heap estimates and absence of eviction do not measure phone process memory.
Keep memory blocked until suitable existing instrumentation is available; enabling new device
trust/debugging or installing a proxy needs separate consideration. No substitute metric closes it.

## Supporting evidence and closure

2026-10-15 local checks at the baseline: **63/63** real-script lifecycle tests and **24/24**
desktop geometry cases pass. Existing owned route/backend/origin and online tailnet match; Funnel
disabled. One Python-owned loopback listener, no non-loopback Core listener. Loopback/private
shell, script, CSS and worker return HTTP 200 and byte-match current source. Unauthenticated
chat-status/history/Garmin calls return 401. This is host readiness only, with no health read.

Complete each row from dated actual observations, resolve failures, run applicable release/security
gates and synchronize [MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md), M4A, overview and roadmap.
Held native package files and their existing audit publication hold remain untouched.
