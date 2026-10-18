# PWA MVP 4 — accessibility and durable phone chat

- Status: `in-progress`; repository implementation verified; remaining manual phone checks **skipped by owner; unverified** (2026-10-16). Automated/release gates remain.
- Audit baseline: `ed4ee18`, shell v6; work started at `1f07d4c` after concurrent M3C evidence commit.
- Completed subphase: [F13 push-to-talk](PWA_F13_COMPLETION.md), F13A–F13D repository/automated scope, shell v10. Production voice stays off. No next phase queued. Phone-check track stays stopped by owner.
- Scope: owner authorized F11 implementation on 2026-10-14 while M3C/M4A physical gates remain open.
  Existing native candidates were reviewed and advanced through compatible SDK 57 patches; audit hold remains.
- M3C physical-phone acceptance remains separate. MVP 4 is not complete.

2026-10-10 resumption: `main` at `5384121`, shell `v7`; owner reports **phone available later**.
M4A physical acceptance is `blocked-external`; aggregate MVP 4 stays `in-progress`. Preparation:
freeze separate Safari/Home Screen steps and sanitized results in
[M4A acceptance](../PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md), refresh local supporting checks, run
applicable publication gates, preserve native edits and MVP 3 report. No new application change
or physical pass is planned without observed device evidence.

2026-10-12 resumption: `main` at `2cb1f96`, shell `v7`; owner confirmed **phone available now**.
M4A physical acceptance is `in-progress`; owner reports **iPhone 15 Pro, iOS 27.0.1** and a connected
Home Screen app. Preliminary label observations are recorded; settings, phone-loaded version and
complete Safari/Home Screen accessibility acceptance remain pending. Availability closes the phone-unavailable blocker, not an acceptance
row. Use the existing matrix; M3C acceptance stays separate.

## Acceptance

- [x] Authenticated transport readiness and one stream owner through synthetic offline/recovery/restart.
- [x] Desktop enlarged text, long identifiers, text spacing and 320–430 CSS px reflow.
- [x] Measured enabled text/boundary/focus contrast and 44px product touch targets.
- [x] Named keyboard-focusable chat history; retain earlier reading position and selection.
- [x] Deliberate completed/failed reply status; persistent recovery guidance. Spoken acceptance open.
- [x] Focused synthetic tests and Core repository gate; unrelated native audit hold isolated below.
- [x] Separate actual desktop browser 400% zoom gate on the bounded synthetic shell.
- [ ] Physical Safari/Home Screen VoiceOver, larger text, zoom, external keyboard and touch.
- [x] F11 code and automated cancel/retry/history/restart/isolation regressions.
- [ ] Physical F11 soak and measured phone performance thresholds.

## Evidence

### 2026-10-17 — F13 implementation from `b6fd3fd`

F13A–F13D complete within repository/automated scope. Core-owned transcription-only service,
authenticated bounded PCM upload, default-off host gate/readiness/software kill, one actual native
worker slot, scoped identity revalidation and metadata-only audit are implemented. Shell v10 adds
deliberate foreground microphone controls, cleanup on lifecycle changes and editable transcript
draft; existing Send remains explicit. Worklet resampling, late ownership, privacy/failure/auth
and desktop accessibility are verified. Real CPU/int8 `base.en` STT recognizes synthetic SAPI audio;
browser fixture responses remain separate fake evidence. Full gate counts and limitations live in
[F13 completion](PWA_F13_COMPLETION.md). Native manifests remain held and unpublished.

Active PWA estimate stays **94%** on existing MVP milestones: F13 is optional input capability,
not physical acceptance. Manual phone checks **skipped by owner; unverified**. Aggregate MVP 4
remains incomplete. No deployment, production enablement, enrollment, scope or credential change.

### 2026-10-17 — proposed F13 planning at `7517e6a`

Owner requests a bounded PWA push-to-talk plan reusing local speech and Core controls. Inspecting
v9 confirms existing remote identity/origin/CSRF/scope and 1 MiB body ceiling, a microphone-denying
Permissions Policy, and reusable Phase 2 STT/VAD/software kill contracts. Root Python **3.11.9**
has NumPy but no faster-whisper/Silero/sounddevice; model readiness was not exercised. Plan:
explicit foreground capture, at most 30 seconds of canonical PCM, authenticated local-only
transcription, editable memory-only draft, then existing explicit Send. No capture or chat auto-send.

[F13 plan](../PWA_F13_PUSH_TO_TALK.md) freezes initial resource limits, lifecycle/privacy/authority
rules, four implementation milestones and automated acceptance gates. No application code,
dependency install/download, configuration change, enrollment, health read or deployment ran.
Held native hashes still match F12 and remain excluded from publication. Planning checks cover
documentation links, whitespace, safe-source secret scanning and hash preservation; no new F13
runtime or physical acceptance claimed. Manual phone checks remain **skipped by owner; unverified**.
Estimate stays **94%**, based on verified implementation milestones; planning adds no credit.
Aggregate MVP 4 remains incomplete. Next work is F13 implementation only when requested.

### 2026-10-16 — F12 navigation at `0d77f8c`

Shell **v9** separates Chat (conversation/tasks), Garmin and Settings (device access/status/logout)
with persistent links, visible shared connection status and accessible selection/focus/back/forward.
Navigation grants no authority and triggers no API action. Existing session, stream owner,
pending request, conversation and draft remain shared. Hidden replies retain reading position;
logout clears every view and does not focus a hidden ticket after later navigation.

Automated evidence: **73/73** lifecycle tests (63 original plus 10 navigation cases), **72** desktop
geometry/font/spacing cases across all views, six short-viewport focus cases, browser history,
keyboard and accessibility-tree checks. Full strict pytest: **1,464 passed / 3 existing optional
skips**, **85.67%** coverage; root/sidecar locks, bootstrap, Ruff, mypy, audits, Gitleaks and doctor
pass. Synthetic transport: **100 reconnects / 10,000 events**, zero duplicates/gaps/cross-session
deliveries/offline effects/private state retained. See [F12 completion](PWA_F12_COMPLETION.md).

Held mobile package/lock hashes match the previous checkpoint and remain unpublished. Native audit
hold and M3C authority stay separate. All manual phone checks remain **skipped by owner; unverified**.
No phone observation, real health read, enrollment, route change or deployment performed. PWA estimate
is now **94%**, milestone-based: F12 navigation adds verified capability; skipped physical checks
add no acceptance credit. Aggregate MVP 4 remains incomplete.

### 2026-10-16 — owner overrides manual phone gates

Owner explicitly directs skipping **all phone checks** and returning to development. Root
AGENTS/playbook now forbid further manual phone requests or using unfinished phone acceptance
as a development prerequisite unless the owner explicitly resumes that work. Remaining F11-P0–P7,
M4A/M3C/native physical, accessibility, reload, network/restart, soak and timing/memory checks are
**skipped by owner; unverified**. Historical results below remain unchanged. No new phone pass,
measurement, MVP completion or original-request terminal outcome inferred.

Next development queued: **F12 — Chat / Garmin / Settings navigation**, implementing the existing
three-surface product target over the current single-page PWA. See its bounded development plan.
No F12 application code started in this policy update. Automated checks, auth/privacy/approval,
health/device authority, $0 limits and held mobile publication restrictions remain enforced.
Completion estimate remains **92%**, milestone-based; waiving manual execution adds no capability.

### 2026-10-16 — Home Screen recovery reported at `473347e`

Owner reports **Connected; fixed the problem** in Home Screen, then answers **yes all good**
to the bundled original-request/status/Send/new-controls check. Record this as general recovery
confirmation only: exact original terminal status, Retry availability/activation and individual
control observations were not itemized. No specific original-request retry or full F11 row passes
from that shorthand response. Next owner batch stops if Retry/unconfirmed outcome remains;
otherwise performs two idle Home Screen close/reopen cycles, then VoiceOver inspection of the
three new history controls if both cycles pass. Owner answers **all good** to that ordered
pass/fail batch: record **2/2 idle reopenings passed**, Connected/Send usable, same saved
conversation, no duplicate answer, and VoiceOver names/order/unavailable states/focus passed for
Saved conversations, New conversation and Refresh history. No remaining Retry/unconfirmed blocker
reported. Current identity retained across those cycles; original pre-enrollment identity and
exact original terminal status remain unestablished. No measured timing, process eviction or
full phone asset inspection inferred. No new public request requested by Codex.

Owner subsequently answers **all good** to the final P1 batch: VoiceOver through one explicit
Connect/Checking/Connected transition, Message/Send unavailable until readiness, recoverable
focus/no trap/no repeated announcements. Record this reconnect/readiness batch as owner-reported
pass. The instruction included inspecting Load earlier messages, Cancel reply and Retry request
only if present; their presence/absence was not itemized. No specific conditional control's
availability or active-generation behavior inferred; retain that limitation rather than repeating
the completed reconnect check. Previous VoiceOver setting restoration was included in the batch.
Explicit online reload remains unobserved separately from the two reopenings.

Fresh read-only readiness passes existing private route/backend/origin, online Tailscale,
disabled Funnel, one Python-owned loopback listener and zero non-loopback listeners. All four
loopback/private assets byte-match v8 source; unauthenticated history/status return **401**.
Core metadata now finds **4 active unexpired browser enrollments**, all exact prior seven chat
scopes, no health scope, risk ceiling at most 1; compatibility columns/trigger intact. Separate
bounded host receipt metadata (maximum 100 rows, no content/IDs) finds **10 completed**, zero
running/failed/cancelled/interrupted receipts. Aggregate outcomes cannot identify the original
request, establish phone identity continuity or accept physical duplicate/retry behavior.

No ticket, enrollment mutation, service restart, route change, revocation, health read or request
submission performed by Codex. Held mobile package hashes still match their checkpoint. Source
unchanged; M3C separate; completion estimate stays **92%**, pending physical acceptance.

### 2026-10-16 — Home Screen connection failure after Safari enrollment

Owner distinguishes surfaces: Safari works, while Home Screen **Enroll device** is disabled.
Owner then reports Home Screen **Connect existing device → Connection failed**. Safari's
reported success does not establish an accepted chat turn or Home Screen recovery. Source disables
Enroll when an identity exists or an enrollment/connection is in progress; this control alone
does not prove missing/revoked credentials. No erasure, re-enrollment or original-request resend
requested. Exact secondary error in Device access/page notice is pending, without another Connect.

Current host checks still pass online Tailscale, exact existing private route/origin, disabled
Funnel, one loopback Python listener and v8 shell/script/worker markers. Bounded host-owned
read-only browser audit finds recent successful signature/session issuance, including earlier
enrollment identities; corresponding sessions show authenticated follow-up activity. No denial
appears in the bounded existing-browser audit window. This neither identifies Home Screen's
attempt nor excludes an unknown-device/pre-authentication or later connection failure. Public
secondary error is needed before selecting a repair; no authentication bypass or key loss inferred.
Application source and held native package files remain unchanged. F11-P0/P1 remain open;
M3C separate; milestone completion estimate remains **92%**.

### 2026-10-16 — chat-only enrollment reported at `5a5bed2`

Prior continuation ended with another **Connection failed** report while Core was running and
host Tailscale reported offline. A chat-only ticket command was supplied; issuance/enrollment
was unconfirmed at handoff. Owner now reports **Enrollment completed**. This is an enrollment
report, not a current Connected/Send, original-request recovery or retained-key-continuity pass.
Exact enrolled surface, original page/draft/Retry state and current connection remain requested.
Do not resubmit the original request through a new device identity or infer history transfer.

Read-only host checkpoint at `2026-10-16T20:33:01-04:00`: Tailscale **Running**, host online,
existing route/backend/origin exact, Funnel disabled, one Python-owned loopback Core listener,
zero non-loopback listeners. All four assets byte-match v8 source over loopback/private HTTPS;
unauthenticated history/status return **401**. Bounded read-only Core metadata finds **3 active
unexpired browser enrollments**, all exactly the prior seven chat scopes, no health scope and
risk ceiling at most 1. Repaired sequence columns/deletion trigger remain present; zero running
host receipts. Counts do not identify the phone or resolve the original request.

No service restart, route change, ticket issuance, enrollment mutation, revocation or health read
performed by Codex in this continuation. Held mobile package hashes match their checkpoint.
M3C grouped health/recovery decision remains separate. Application source unchanged; physical
F11-P0/P1 and later rows remain open. Completion estimate stays **92%**, milestone-based.

### 2026-10-16 — host recovery before F11-P0/P1 at `5ef5c36`

Owner reports **Connect existing device → Connection failed**. No original-request Retry result,
current Send state or exact phone surface observed. A generated one-use enrollment ticket is not
the saved credential: successful enrollment writes the browser's non-exportable device key.
No key loss, enrollment failure or schema regression inferred from the connection symptom.

Read-only diagnostics at `2026-10-16T17:11:39-04:00` find Tailscale **NoState**, host offline,
empty Serve configuration and zero Core listeners; Windows service is running. Starting the
existing Tailscale app restores its saved selected profile and prior exact private route/origin.
No login, profile switch, enrollment, security setting or route mutation. The reviewed existing
hidden Core launcher then restores the stopped local service. At `17:13:49-04:00`, exact route,
online host, Funnel disabled, one Python-owned loopback listener and zero non-loopback listeners
pass. Four process wrappers/children are not four listeners. All four loopback/private v8 assets
byte-match source; unauthenticated history/status return **401**. Bounded read-only metadata:
**2 active unexpired browser enrollments**, exact prior seven chat scopes, risk at most 1,
repaired sequence columns/deletion trigger and zero running host receipts.

Requested one same-surface Connect and, only after Connected if still offered, one original-request
Retry. Phone recovery and exact surface remain pending; two reopenings and VoiceOver await recovery.
No F11 row or restart-interruption result accepted. Application source unchanged; prior source
release gate remains historical evidence, no new application test run claimed. Held mobile package
hashes match the 2026-10-14 checkpoint and remain excluded; M3C unchanged. Completion estimate
stays **92%**, milestone-based; physical recovery/accessibility/performance gates remain open.

### 2026-10-15 — F11-P0/P1 metadata and legacy-schema repair at `55be543`

Owner reports **iPhone 15 Pro, iOS 27.0.1, Wi-Fi, portrait, normal text, VoiceOver off,
no external keyboard**. Follow-up confirms normal zoom and describes surface as **Safari as the
app**; exact Safari-tab versus Home Screen surface remains unresolved. Owner reports **cannot
send because outcome is unconfirmed**; requested one Retry request activation if available, then
public status and Send state. Reopen/VoiceOver batches paused for recovery; no resend, reload,
data clearing or cancellation requested. Visible controls were not confirmed.
Owner subsequently reports **still not working**. This establishes no recovered Send outcome;
Retry availability/activation and exact post-attempt public status were unconfirmed at that point.
Requested the status/error wording and Retry state without another activation. Physical acceptance stays
paused at recovery failure; no passing reopen or VoiceOver result inferred.
Two reopenings, retained identity and VoiceOver outcomes remain
unobserved; metadata alone accepts no complete F11 row. External-keyboard acceptance lacks
equipment. Historical connection/basic reply evidence remains intact.

Read-only host readiness at `2026-10-15T22:38:53-04:00` passes the existing owned route/backend/
origin, online tailnet, disabled Funnel, one Python-owned loopback listener and zero non-loopback
listeners. Loopback/private shell/script/CSS/worker byte-match current v8 source; unauthenticated
history/status return **401**. Bounded host-owned SQLite read (`mode=ro`, limit 101) finds **2
active unexpired browser enrollments**, exact prior seven scopes, no health scope and risk ceiling
at most 1. Aggregate count/booleans only; no identifier, transcript, token or health content.
Existing Core reused; no route/service/enrollment/credential mutation or Garmin call.

Bounded metadata-only receipt inventory found zero durable chat receipts for active host-owned
browser devices; phone request identity/cause was unestablished at that checkpoint. Existing real-script focused
recovery command (`rtk proxy node --test --test-name-pattern='safe Retry|Retry finds|unconfirmed
POST' tests/pwa/garmin-lifecycle.test.cjs`, one command) passes **4/4**. This synthetic evidence
does not accept the reported phone failure or a physical retry row.

Held native package/lock hashes match the 2026-10-14 checkpoint and remain excluded from
publication. At the metadata checkpoint application source was unchanged; subsequent repair follows.
Completion estimate stays **92%**, milestone-based; P0/P1 and later physical gates remain open.

Owner then reports the public **Send outcome unconfirmed. Retry request checks Core using the same
request ID. Your draft is kept.** and **Core has no accepted request. Retry request safely uses
the original request ID.** statuses. Running OpenAPI confirms current durable status/cancel routes
and request fields. Read-only production schema inspection reveals early already-applied migration
017 lacks `start_sequence`, `end_sequence` and `pwa_chat_conversation_deleted`. Current positional
12-value insertion therefore cannot create a receipt in its 10-column table. The synthetic legacy
regression fails before repair (**3 failed / 1 passed**; missing-both error: **table
pwa_chat_requests has 10 columns but 12 values were supplied**). Direct `uv run pytest` was blocked
by Windows Application Control (`os error 4551`); supported `uv run python -m pytest` executes.

Chat-store initialization now adds only missing columns and deletion trigger in one rollback-safe
transaction. Named insert columns avoid dependency on column order. No migration rewrite, row
replacement, receipt deletion, history backfill, scope expansion or phone-data clearing. Historical
sequence defaults do not authorize history; exact owner/request attribution still applies. Five
new regression cases cover modern/partial/early schemas, byte-preserved prior receipt fields,
terminal no-replay, new reservation, restart interruption, cancellation barrier, deletion privacy,
reopen idempotence and cancelled-upgrade rollback. Combined focused Core/API suite: **26 passed**.
SQLite official [ADD COLUMN](https://www.sqlite.org/lang_altertable.html#altertabaddcol) and
[transaction](https://www.sqlite.org/lang_transaction.html) documentation checked before repair.
Full release and repaired-host/phone recovery results follow; P0/P1 remain unaccepted.

Idle Core restart used the exact verified existing Python listener, checked zero running
host receipts, then reused reviewed `runtime/mvp4-fixes/f11-start.ps1` through supported bundled
`pwsh` with a hidden window. Existing route/enrollment unchanged. Read-only check at
`2026-10-15T22:51:01-04:00` confirms both columns and deletion trigger present, still zero receipts.
One loopback listener, zero non-loopback listeners, private route/tailnet/Funnel boundary and v8
HTTP markers pass. At `22:51:45-04:00` private/loopback shell/script/CSS/worker byte-match source,
unauthenticated history/status remain **401**, and Doctor passes with UTF-8 console environment.
Requested one original-request Retry after Connected, with Connect existing device only if needed.
No phone replacement submission, credential change, route mutation, Garmin read or F11-P6
in-flight-interruption acceptance. Actual recovery result remains pending.

Final repair release gate (after deletion-safeguard hardening):

| Check | Result |
| --- | --- |
| Root lock check / locked sync | pass; 119 resolved / 69 checked |
| Ruff format / lint / Mypy | pass; 415 formatted files / 166 source files |
| Full strict pytest | **1,464 passed / 3 existing optional skips**, **85.67% coverage**, **124.33s**; existing Starlette warning |
| Focused Core/API | **26 passed**, including five new compatibility/rollback cases |
| PWA real-script lifecycle | **63 passed**; assets unchanged, geometry not rerun |
| Root dependency audit | no known vulnerabilities |
| Doctor / live host | pass; repaired columns/trigger, existing private boundary and unchanged v8 assets verified |
| History / staged secret scans | pass; 111 commits / approximately 21.52KB staged; no leaks |
| Documentation / whitespace | all **47 local links** across six edited documents resolve; diff check passes |
| Held native candidates | original hashes unchanged; publication hold retained; no native gate rerun |

Full command: `rtk proxy uv run python -m pytest -q --tb=short --cov-report=
--basetemp runtime/f11-legacy-schema-release-final-20261015` (one command; configured **85%**
coverage gate retained). An earlier full repair run passed **1,464 / 3**, **85.51%**, **112.37s**;
final run above follows the added deletion safeguard. Runtime test artifacts and local service
helpers stay ignored. Publication includes only repair source/tests and six acceptance/status
documents. No full physical row, phone performance sample or MVP completion claimed.

### 2026-10-15 — F11 phone connection confirmed at `22d50db`

Checkpoint `2026-10-15T22:34:16-04:00`; shell **v8** source unchanged. Previous chat supplied
the owner the trusted-host chat-only ticket command. Owner reports **Connected**, followed by
**Send enabled; one reply** after a single public synthetic request in this continuation. No ticket,
key, device ID or transcript retained in repository evidence. Enrollment/connection outcome is
supported by the phone report and fresh Core metadata: **2 active browser enrollments**, both exactly the prior seven
scopes, no health scope and risk ceiling at most 1. The earlier inventory had one active browser;
aggregate metadata does not map the phone identity or prove retained-key continuity.

Read-only readiness passes existing owned route/backend/origin, online tailnet, disabled Funnel,
one Python-owned **127.0.0.1:8765** listener and zero non-loopback listeners. Loopback/private
shell, script and worker return **200**, shell/worker v8 markers match. No service restart, route
change, ticket/enrollment mutation, revocation or Garmin read performed here. Held mobile package
and lock hashes match the 2026-10-14 checkpoint; MVP 3 report and application assets remain untouched.

This accepts only the reported connection/basic one-turn outcome. F11-P0 metadata, current phone
surface/runtime/controls and two reopenings remain pending. F11-P1 VoiceOver/readiness ordering,
P2–P7, frozen timing/memory targets and remaining M4A cases stay open. No performance sample or
full physical row accepted. M3C Garmin enrollment decision/acceptance remains separate. Completion
estimate stays **92%**, milestone-based; connection checkpoint alone closes no full milestone.
Publication scope is these four acceptance/status documents only. All **41 relative links** resolve;
Whitespace, preservation hashes and staged Gitleaks pass; no leaks found in approximately **6KB**.
Existing source release evidence below remains applicable;
no application or native test rerun is claimed for this documentation-only continuation.

### 2026-10-15 — F11 physical acceptance initiated

Baseline `main` at `4fa75e3`, shell **v8**; exact-SHA
[baseline CI 38652127469](https://github.com/DanCreates1/JARVIS/actions/runs/38652127469) independently
verified **passed**. Resume scope is
physical F11 acceptance, with M3C decision, remaining M4A rows and phone performance still open.
Execution sequence: verify unchanged host readiness; collect phone metadata/non-health prerequisite;
run compact F11 functional/accessibility batches; coordinate reopen/network/Core interruptions;
measure against frozen targets; record only observed results and run applicable publication gates.
See [F11 physical acceptance](../PWA_F11_PHYSICAL_ACCEPTANCE.md) for the ledger and fixed budgets.

Fresh supporting checks: `rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs` **63/63 pass**;
`rtk proxy node scripts/pwa-accessibility-check.cjs` **24/24 pass**. Read-only readiness reused
existing validators with v8 markers: exact owned private route/backend/origin, online tailnet,
Funnel disabled, one Python-owned `127.0.0.1:8765` listener and zero non-loopback Core listeners.
Both loopback/private shell, script, CSS and worker return **200** and byte-match current source;
unauthenticated chat-status/history/Garmin requests return **401**. This makes no authenticated
health call and cannot prove phone-loaded assets.
The process-command inventory matches four wrapper/child entries; it is not four listeners.
Existing Core reused; no service restart, route change, enrollment, ticket or Garmin read.

Held `mobile/package.json` and `mobile/package-lock.json` hashes still match the 2026-10-14
checkpoint below; files remain excluded from publication. Owner phone metadata/status requested;
no new physical observation received at this preparation checkpoint. All F11 phone rows remain
pending; memory measurement lacks established phone instrumentation. Historical v7 M4A passes
are preserved. Estimated completion stays **92%**, milestone-based; preparation accepts no gate.

Baseline full gate exposed a real immediate-cancellation race: **1 failed / 1,456 passed /
3 skipped**, **85.60% coverage**, **131.30s**. Concurrent callers could observe `settled=True`
before terminal storage/audit/event completion and return the stale `running` receipt. A delayed-
storage regression reproduced the defect before the fix. `_settle_unstarted` now retains the
coordinator lock through terminal persistence/audit/publication and active-turn removal, so a
concurrent cancellation waits for settlement. No API, schema, scope, shell version or provider
behavior changes. The strengthened existing test verifies no early return, no provider generation,
one terminal audit and one terminal event. Focused Core/API/transport checks: **28 passed**.
This is targeted development evidence (`--no-cov`); the unchanged full **85%** coverage gate is
rerun separately. Lock semantics checked against
[Python 3.11 synchronization documentation](https://docs.python.org/3.11/library/asyncio-sync.html#asyncio.Lock).

The next full run exposed two further baseline cancellation issues: **2 failed / 1,455 passed /
3 skipped**, **85.65% coverage**, **107.38s**. Interrupted initial audit insertion could leave a
transaction open, blocking terminal writes on the separate chat connection. Audit insertion now
rolls back on `BaseException`, including cancellation, under its existing operation lock, matching
message-write recovery. Two injected commit-failure/cancellation regressions failed before the
fix and pass afterward; no orphan audit survives and the next write remains usable. The provider-
cleanup test now checks the exact two audit records without assuming distinct Windows timestamps;
SQL ordering is unspecified when their timestamps tie. Combined focused storage/Core/API/transport:
**34 passed**. Earlier failed full runs remain failures; final full-gate evidence follows.

Final stable local release gate on 2026-10-15:

| Check | Result |
| --- | --- |
| Root / Garmin lock checks and locked sync | pass; 119/69 and 20/16 resolved/checked |
| Windows bootstrap / Doctor | pass; supported bundled `pwsh`; Doctor requires `PYTHONIOENCODING=utf-8` on this console |
| Ruff format / lint / Mypy | pass; 415 formatted files, 166 typed source files |
| Full strict pytest | **1,459 passed / 3 existing optional skips**, **85.65% coverage**, **105.67s**; existing Starlette warning |
| Focused storage/Core/API/transport | **34 passed**; regression reproductions failed before their fixes |
| PWA lifecycle / desktop geometry | **63 / 24 passed**; Edge 155.0.4283.45; application assets unchanged |
| Root / Garmin dependency audits | no known vulnerabilities |
| Gitleaks history / staged | pass; 107 baseline commits / approximately 18.51KB staged at initial scan; final scan before commit |
| Relative documentation links / whitespace | 46 links across six documentation files resolve; diff checks pass |
| Native package candidates | unchanged; existing production-audit hold retained, native verification not rerun |

Full command: `rtk proxy uv run python -m pytest -q --tb=short --cov-report=
--basetemp runtime/pwa-f11-physical-20261015-quality3` (one command; standard configured coverage
and **85%** threshold retained). The two earlier full runs are documented above, not hidden by
the passing final run. Pytest targets were fresh verified workspace-local ignored runtime paths.
No application source changed after this passing gate. Publication includes the two bounded
cancellation fixes, regression tests and six acceptance/status documents; excludes both held
mobile files and every runtime artifact. Published source `a0b60fb055de932202a37119b9471d0dc4962559`:
[exact-SHA CI 38814848115](https://github.com/DanCreates1/JARVIS/actions/runs/38814848115) **passed**,
verified during the owner's phone-ready resumption. Local/tracking/live upstream matched at publication.

At the initial preparation checkpoint, the running Core predated this source fix. Coordinate an idle restart using its verified
existing loopback/private configuration before physical testing of the patched cancellation path;
that preparation is not physical Core-restart acceptance. No live restart was performed here.

Phone-ready resumption, 2026-10-15: owner replied **yes good to go**. This confirms availability,
not phone version, tailnet status, retained non-health scope, loaded assets or an acceptance row.
Requested the existing Home Screen connection status/non-health guidance and whether previously
reported iPhone 15 Pro/iOS 27.0.1 remains current. No Connect/enrollment/logout/health action queued.

Core was found stopped: zero backend listeners and zero matching Core commands. Existing owned
Serve route/backend/origin, online tailnet and disabled Funnel all validated. Reviewed existing
`runtime/mvp4-fixes/f11-start.ps1` started patched Core through supported `pwsh` and the locked
Python module entry point; no route or identity changes. Settled verification at
`2026-10-15T22:15:54-04:00`: one Python-owned **127.0.0.1:8765** listener, no non-loopback listener;
loopback/private shell/script/worker **200**, v8 markers match. This is readiness, not F11-P6
physical interruption or M3C acceptance. Held mobile files remain the only pre-existing changes.
No application source changed; source CI/local release evidence above remains applicable.

Owner answered **no** to the bundled metadata/non-health/status prompt. Its referent is ambiguous;
do not infer missing scope, an enrolled health identity, a different phone or a connection failure.
Requested only the Garmin panel's public status wording, omitting health numbers. Connect and
authenticated F11 steps remain paused until the non-health prerequisite is established. No new
physical row accepted; progress remains the **92%** milestone estimate.

Subsequent owner wording matches disconnected shell **Connect JARVIS to see Garmin data.** and
its standard privacy hint; no health values reported. Code review found the previous procedural
precheck circular on fresh startup: the non-health new-enrollment sentence is set only after
successful Connect. Corrected F11/M4A procedure to accept equivalent trusted current Core metadata
before connection, without changing application scopes, authentication or Garmin-read behavior.

Bounded read-only SQLite query (`mode=ro`, host-bound, active browser rows only, limit 101) emitted
only count/booleans: **1 active browser**, exact prior seven scopes, **no health scope**, risk
ceiling at most 1; bounded inventory true. No IDs/names/keys/tokens or private content emitted;
no migrations, authentication, tickets, enrollment, scope changes or health reads. This proves
the Core-enforced non-health boundary for any accepted existing browser session; a request for
additional health scope fails existing subset validation. Generic phone guidance proves neither
current scripts nor retained identity. Requested the public **Enrolled key found. Connect existing
device to start a fresh session.** startup wording; physical F11-P0/Connect still pending.
Owner reports **different wording**. Requested exact public Device access sentence, without
tickets/keys/device IDs. No identity absence, wrong surface or old loaded script is inferred.

2026-10-09 changes, shell `v7`:

- F1: network availability cannot enable protected controls. First successful authenticated poll
  establishes readiness. One generation-bound owner resumes offline/stalled polling, retries with
  bounded backoff and resubscribes on Core 404/409. Queued Web Locks cancel on logout/replacement.
  Session rejection clears volatile credentials/private views; enrolled key survives for renewal.
- F2/F3/F10: user-relative root font and inherited button fonts; wrapping headings/actions/device
  identifiers; adaptive metrics; visible focus; 44px minimum button dimensions. Logout text computes
  **5.7947:1**; enrollment boundary **4.9248:1** against input fill and **4.6004:1** against panel
  RGB. Focus outline exceeds 3:1 against tested fill/button colors. Panel alpha does not bring the
  measured input boundary below 3:1 over either dark background endpoint.
- F4/F5: named, explicitly focusable history; no forced scroll while reading earlier text or
  selecting history; append deltas retain a selection inside the active reply's text node. Named
  Jump to latest returns focus to history. Deltas do not trigger repeated
  speech; a polite completed answer status is deduplicated across HTTP/SSE completion. Failed and
  cancelled events have deliberate status. Steady keepalives do not rewrite live connection
  status. Real screen-reader speech remains unverified.
- F6: local five-minute freshness timer and resume evaluation; last-checked context stays visible
  during refresh/error. Logout clears timers/snapshot. Freshness evaluation alone makes no reads.
- F7/F8/F9: durable ticket-associated error/recovery and local/remote logout result; logout focuses
  ticket after local cleanup. Busy controls/regions and whole-connect failure handling. Headers
  and bodies are bounded: bootstrap/revocation 5s, normal/enrollment 10s, event poll 30s, Garmin 95s
  (Core child deadline 90s). No automatic login, enrollment, scope expansion or chat retry.
- Failed-send draft remains in page memory. An unconfirmed POST does not suppress a later
  authoritative streamed answer. A confirmed reply clears only its unchanged submitted draft;
  newer user edits survive. F11 cancel/retry/history controls remain separate work.

Verification:

- `rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs`: 43/43 pass. Covers success/rejected/
  stalled offline polls, repeated online events, deadlines, 401/403, Core subscription restart,
  queued/cancelled ownership, partial connection failures, stale-result guards, chat completion/
  lost acknowledgement, retained reading/draft state, freshness and logout result/focus.
- `rtk proxy node scripts/pwa-accessibility-check.cjs`: 24/24 geometry cases pass in Windows Edge
  154.0.4258.62. Widths 320/375/390/430/844/1280 CSS px, browser default font 16/32px, with/without
  WCAG text-spacing overrides. No measured section/page overflow; buttons inherit enlarged font
  and meet 44px targets within 0.01px geometry tolerance. Named Conversation log, Tab/Shift+Tab,
  Page Down scrolling, selection/history retention, Jump focus, logout focus and reduced motion pass.
- Browser default-font resize is desktop evidence. 320px viewport at a 1280px reference is a reflow
  simulation; actual browser 400% zoom, Safari text zoom and iOS larger text remain physical checks.
- Full `rtk uv run pytest --basetemp runtime/mvp4-fixes/pytest-20261009a`: **1439 passed, 3 skipped**,
  **85.59% coverage**; existing Starlette/httpx deprecation warning. Final focused PWA tests pass.
- Lock check/sync, Ruff format/lint, mypy, root pip-audit, Garmin sidecar pip-audit via
  `--path garmin_sync/.venv/Lib/site-packages`, Gitleaks history and diff checks pass. Attempted
  transient sidecar auditor installation hit workstation cache hardlink/copy permissions; auditing
  its installed site-packages with the locked root auditor succeeds without sidecar edits.
- Existing synthetic Phase 8C transport benchmark passes 100 reconnects/10,000 events with no
  duplicates/gaps/cross-session deliveries/offline effects or retained private state. Its existing
  limits remain p95 <25ms, RSS growth <50MiB and shell <256,000 bytes. Measured p95 was
  0.1406ms and RSS growth 0.660MiB; shell remains below 47,000 bytes. This is a transport regression
  check, not phone startup/navigation/first-delta/memory acceptance.
- `rtk proxy npm run verify` in `mobile/`: formatting/lint/types, 38 Jest tests, Expo Doctor 21/21
  and 1,109 dependency license records pass. Existing production audit fails: **15 moderate,
  45 high, 0 critical**. Exports were not reached. Native packages remain under the existing audit
  hold, unchanged and excluded from PWA publication; no force upgrades or audit weakening.

All generated JSON, screenshots, browser profiles and pytest work directories stay under ignored
`runtime/mvp4-fixes/`. Browser script serves synthetic static files on an isolated loopback port;
test-only hooks are appended by that server, absent from production assets. No Core/real identity,
Garmin account, production route, enrollment, live revocation or private health data was used.
`PWA_MVP3_PROGRESS.md` remains untouched at its concurrent `1f07d4c` checkpoint. Native candidate
SHA256 remains `a9bb3741e6b3066deb4adf8091189e35a6837d57be3ba48460e056d75b7d8342` for package.json
and `d0da737979bc3f2ba193939f7d16a6889d934173bfe9a0f8180a4286c1433cf9` for package-lock.json.

Publication includes only PWA source/tests/harness and MVP 4 architecture/setup/progress docs.
Staged Gitleaks finds no leaks. Mobile package candidates, concurrent MVP 3 report and all runtime
artifacts are excluded. Standing commit/push authority applies. Implementation commit `e091930`
was pushed to `main`; [CI run 38013362174](https://github.com/DanCreates1/JARVIS/actions/runs/38013362174)
passed Windows quality (lock/sync, formatting/lint/types, full tests and both Python audits) and
secret scan. Final follow-up preserves text selection inside actively streaming replies and adds
its real-browser regression; 43 lifecycle tests and all 24 desktop cases pass after that change.

2026-10-09 verification checkpoint at `e4133b41ba4884d593b5a27f70fab9fa6a6b6398`:

- Local HEAD, tracking `origin/main`, and live upstream `main` match the final M4A implementation.
  [CI run 38013672136](https://github.com/DanCreates1/JARVIS/actions/runs/38013672136) passed
  both Windows quality and secret-scan jobs at that exact SHA, including the full test gate,
  root/sidecar locked setup and dependency audits. This closes the previously unrecorded CI
  result for the streamed-selection follow-up; physical MVP 4 acceptance remains open.
- Fresh local reruns pass all **43 lifecycle tests** and **24 desktop geometry cases**. Keyboard,
  named history, reading/selection retention, focus and reduced motion checks pass. Contrast
  remains 5.7947:1 for Logout text, 4.9248:1 for input boundary against fill, and 4.6004:1
  against panel RGB. Generated evidence remains under ignored `runtime/mvp4-fixes/`.
- No additional application change was needed for the requested F1-F5 priorities. This checkpoint
  updates only this report. Native package candidate hashes above remain unchanged; concurrent
  `PWA_MVP3_PROGRESS.md` content remains untouched. No physical-device evidence, enrollment,
  revocation, Garmin read or route change is claimed.

2026-10-10 M4A physical-acceptance preparation at baseline `5384121`:

- Owner reports **phone available later**. No physical-device check was run; iPhone/iOS, keyboard
  availability and phone-loaded shell version remain unknown. The new
  [M4A acceptance matrix](../PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md) freezes separate Safari/Home
  Screen steps and pending result rows for speech, enlarged text, zoom, focus, touch and recovery.
  Actual desktop browser 400% zoom stays separate from viewport emulation and phone magnification.
- Application assets remain shell `v7`, byte-for-byte unchanged. Fresh local evidence passes
  **43/43 lifecycle tests** and **24/24 desktop geometry cases**, now on Windows Edge
  **155.0.4283.45**. Named history, keyboard/focus, reading/selection retention and reduced motion
  checks pass. Contrast remains Logout text **5.7947:1**, input boundary/fill **4.9248:1**,
  input boundary/panel **4.6004:1**. These are desktop results, not spoken Safari acceptance.
- `rtk uv run pytest --basetemp runtime/mvp4-fixes/pytest-20261010-m4a`: **1,439 passed,
  3 skipped**, **85.59% coverage**, **105.43s**; one existing warning. Root and Garmin sidecar
  lock checks/locked sync pass; Ruff format/lint (410 files), mypy (164 source files), root
  pip-audit and sidecar audit through `--path garmin_sync/.venv/Lib/site-packages` pass.
  Gitleaks history scans 95 commits with no leaks; local documentation links and diff checks pass.
- Standard `jarvis doctor` initially hit console `OSError: [Errno 22] Invalid argument` using
  `cp1252` output. The same CLI succeeds through a Node subprocess with process-only
  `PYTHONIOENCODING=utf-8`; no repository/environment configuration changed. This is installation
  diagnostics under default settings, not private-route or phone readiness evidence.
- Baseline local HEAD, tracking ref and live upstream `main` match
  `53841218d616a6d09c172cec7ed29537afef023b`.
  [CI run 38016337629](https://github.com/DanCreates1/JARVIS/actions/runs/38016337629) succeeds
  at that exact SHA: Windows quality and secret scan, including both Python dependency audits.
  This is baseline CI; the documentation publication has its own subsequent run.
- Preservation SHA256 checks pass for both native package candidates (hashes above), all four
  inspected shell assets and `PWA_MVP3_PROGRESS.md`
  (`eddd4479a9ae1b11029f5436e01b81ccaa6ecdebbc5b7bfb1241b0d5a01e146b`). Native verification
  was not rerun for this documentation-only session; the existing native dependency-audit hold
  remains. Generated browser/pytest evidence stays ignored under `runtime/mvp4-fixes/`.
- Publication scope is four documentation files: M4A matrix, this report, phase overview and
  master roadmap. No application behavior, Core service, private route, enrollment/revocation,
  key erasure, Garmin read or M3C report changed. Physical M4A and aggregate MVP 4 stay open.

Official implementation references checked 2026-10-09: [network availability](https://developer.mozilla.org/en-US/docs/Web/API/Window/online_event),
[queued/abortable Web Locks](https://developer.mozilla.org/en-US/docs/Web/API/LockManager/request),
[scroll-container keyboard access](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/overflow),
[text resize](https://www.w3.org/WAI/WCAG22/Understanding/resize-text.html),
[reflow](https://www.w3.org/WAI/WCAG22/Understanding/reflow.html),
[text contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html),
[control contrast](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html),
[status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html).

2026-10-12 M4A resumption and desktop zoom checkpoint at baseline `2cb1f96`:

- Owner confirmed iPhone available and Home Screen JARVIS opens with **Offline shell**.
  One **Connect existing device** attempt returned **Connection failed**; owner subsequently
  reported connected. Recovery method/error detail unreported; no cause or spoken-failure pass
  inferred. Owner reports **iPhone 15 Pro, iOS 27.0.1**, metadata receipt recorded at
  `2026-10-12T13:26:59-04:00`. Settings, keyboard availability and phone-loaded version remain
  pending. Owner subsequently confirmed VoiceOver speaking, receipt recorded at
  `2026-10-12T13:32:22-04:00`; this is enablement preparation, not JARVIS speech acceptance.
  Owner then said the first Device access labels read their displayed text, receipt recorded at
  `2026-10-12T13:34:25-04:00`. This is partial A1 naming evidence; disabled-state announcement,
  remaining labels and complete reading order are unobserved. Owner subsequently reported
  **enroll device button** on single touch, without a dimmed/unavailable word (receipt
  `2026-10-12T13:35:40-04:00`), then **Connected; button looks normal** (receipt
  `2026-10-12T13:36:53-04:00`). This differs from the expected host v7 disabled enrollment state;
  phone assets/native disabled state remain unverified, so no screen-reader failure classification
  is inferred. Public access-status guidance below Connect is requested as supporting loaded-script
  evidence. Owner instead suspected an older website and requested the current link. The existing
  private route, one Python loopback listener and current static shell/script/worker were rechecked;
  HTTP 200 and host v7 references pass. Current `/app/?m4a=v7` HTML also passes; the query avoids
  the worker's exact cached navigation key, without website-data clearing or route changes. The
  private link was supplied only to its owner on request and remains absent from Git. Safari
  displays **enroll with an approved ticket, or connect an existing device key.** (receipt
  `2026-10-12T13:43:59-04:00`), the initial v7 HTML access-status paragraph absent in historical
  v6. This does not prove loaded script/worker execution or enrollment. Asked for Safari Enroll/Send
  VoiceOver names/state, owner said screen text is read with nothing special (receipt
  `2026-10-12T13:47:12-04:00`). Asked specifically whether Send includes dimmed/unavailable,
  owner answered **Yes**. This verifies that individual Safari state announcement only; full A1
  names/order and loaded assets remain pending. Owner confirmed Refresh Garmin, Refresh tasks
  and Logout and erase this device all clearly named during swiping, without activation. Owner
   then confirmed Message and the Conversation history area both clearly named. Owner subsequently
   confirmed Enrollment ticket JSON, Enroll device and Connect existing device names and sensible
   page reading order, then all remaining greyed-out controls announcing unavailable. Explicit
   heading traversal and test settings remain pending before closing A1. Cached/older Home Screen assets are a
  possible explanation, not a verified cause; full phone assets and Safari identity remain
  unverified. Instructions proceed in small phone steps.
  No complete physical A1-A11 pass is claimed. Safari observations remain preliminary. Before another
  A3 Connect activation, the matrix now requires public on-page non-health guidance: an existing
  health-enabled identity can automatically refresh Garmin after authenticated polling.
- Existing private Serve route passed ownership/backend/origin checks; tailnet online, Funnel
  disabled. Core was found stopped; resumed with its existing configuration: one Python-owned
  listener at `127.0.0.1:8765`, no non-loopback Core listener. Local/private shell, script and worker
  return HTTP 200 with host `v7` references. Route untouched. This is service readiness, not the
  M3C phone Core-restart row or proof of phone-loaded assets. No Garmin read or identity operation.
- Fresh **43/43 lifecycle tests** and **24/24 desktop geometry cases** pass on Edge
  **155.0.4283.45**. Contrast remains Logout text **5.7947:1**, input boundary/fill **4.9248:1**,
  input boundary/panel **4.6004:1**. Existing harness required normal local access after sandbox
  loopback `EACCES`; no application or Windows security setting changed.
- Separate actual desktop browser zoom gate passes in a fresh headless Edge profile with native
  `tabs.setZoom` in automatic/per-tab mode. At 100%, `innerWidth=1280`, scrollbar-adjusted
  `clientWidth=1265`; at 400%, `innerWidth=320`, `clientWidth=316`, visual width **316.25** and
  root/body scroll widths **316**. DPR **4**, visual scale **1**, CSS zoom **1**. Long public fixtures
  have no inspected horizontal overflow. Ten controls reachable/pointer-hit checks, history
  keyboard scrolling, reading/selection retention, Jump focus, text entry and mocked Send pass.
  Controls use test hooks; no authenticated Core action, phone, speech or WCAG conformance claim.
  Independent read-only review confirms actual zoom and these limits. Zoom restored; isolated
  processes closed. Final ignored evidence timestamp: `2026-10-12T17:02:09.614Z`.
- Root/sidecar lock checks and locked sync pass; Ruff format/lint (**410 files**), mypy
  (**164 source files**), root/sidecar audits and UTF-8 process-only `jarvis doctor` pass.
  Windows blocked the `pytest`/`pip-audit` console launchers with Application Control error **4551**;
  existing Python module entry points execute without changing policy. Full
  `rtk uv --cache-dir runtime/uv-cache-mvp3 run python -m pytest --basetemp runtime/mvp4-fixes/pytest-20261012-m4a`
  passes **1,439 tests, 3 existing skips**, **85.55% coverage**, **102.76s**, one existing warning.
  Both audits use `python -m pip_audit`; sidecar audit uses
  `--path garmin_sync/.venv/Lib/site-packages`. Gitleaks history scans **96 commits**, no leaks.
- Application assets remain unchanged, shell `v7`. Native package candidates and MVP 3 report
  retain their recorded preservation hashes. Runtime checkers, browser profiles, synthetic
  screenshots/JSON and pytest directories stay ignored. Publication scope remains the M4A matrix,
  MVP 4 report, overview and roadmap; physical M4A and aggregate MVP 4 remain open.
- Four-document checkpoint `843f916fc6df068e3164411ed6292ff71465dc3a` was pushed to `main`;
  local HEAD, tracking ref and live upstream matched. [CI run 38282189854](https://github.com/DanCreates1/JARVIS/actions/runs/38282189854)
  passed Windows quality and secret scan at that exact SHA. Follow-up documentation checkpoint
  `d6dd790e05ea685a1bcc8951028e02d8bcb7418c` also passed
  [CI run 38282852401](https://github.com/DanCreates1/JARVIS/actions/runs/38282852401): Windows
  quality and secret scan at that exact SHA. The later owner report of a recovered Home Screen
  connection and phone metadata is recorded above. No physical row is closed by these checkpoints.

2026-10-13 M4A continuation at `d6dd790`, shell `v7`:

- Owner confirms phone available; Safari context is **portrait, normal text/page zoom, VoiceOver
  on, no external keyboard**. Numeric text/zoom values uninspected; these settings do not establish
  the previous day's exact context. A10 is blocked for both surfaces by missing equipment.
  Owner then confirmed Device access, Conversation and Garmin announced as headings in order,
  with clear single-touch heading reading. **Safari A1 passes for the observed shell**: required
  names, reading order and unavailable-state announcements, combined with 2026-10-12 observations.
  This does not close script/worker verification, Home Screen A1, authenticated transitions or M4A.
  VoiceOver off was confirmed for visual checks. Largest-text setup was requested, then owner
  stopped remaining phone tests before confirming its setting or any webpage response (decision
  receipt `2026-10-13T20:13:50-04:00`). Physical acceptance was **owner-deferred** at that checkpoint;
  no questions queued until the subsequent owner request. No A7 pass had been observed then and
  skipping did not accept M4A/MVP 4.
- Core was found stopped; resumed the existing owned private route's loopback configuration.
  Settled check: one Python-owned `127.0.0.1:8765` listener, no non-loopback listener, tailnet online,
  origin/route/backend ownership intact, Funnel disabled. Current static shell/script/worker return
  HTTP 200 with host v7 references. No route/identity operation, ticket or Garmin read. Service
  readiness does not accept M3C restart or verify phone-loaded assets.
- Continuation started at `d6dd790`; all four PWA asset hashes match the prior checkpoint. Native
  package candidate hashes and MVP 3 report hash remain preserved. Two-document Safari A1
  checkpoint `345eb2453f5c7fab690726d9558777e895d92fbf` was committed/pushed after staged secret,
  diff and local-link checks. Owner-deferral publication also updates overview and roadmap; no
  application fix or new local test result claimed.

2026-10-13 owner resumption after the deferral checkpoint:

- Deferral checkpoint `21e60ac40bdf0d2ae9e6df16ba56ea3b7a966381` passed
  [CI run 38489374156](https://github.com/DanCreates1/JARVIS/actions/runs/38489374156): Windows
  quality gate and secret scan at that exact SHA, including the full tests and both Python audits.
  This verifies publication quality; it does not accept the deferred physical rows.
- Owner explicitly resumed phone checks (receipt `2026-10-13T20:20:26-04:00`); use compact batches
  and record working observations. Fixed acceptance criteria and existing scope remain intact.
- Safari visual batch at maximum accessibility text plus 200% Page Zoom: both orientations,
  empty-ticket keyboard show/dismiss, text/caret/control readability and scrolling reachability.
  Owner reports **all worked**, then explicitly confirms webpage text grew before website zoom.
  **Safari A7/A9 observed passes; A8 200% website zoom passes**, with its highest offered value and
  separate magnification still pending. No authenticated Message keyboard or Home Screen result
  claimed; script/worker gate remains open. Current step is original Home Screen public guidance
  and two online reopenings, no protected activation. Restore usual settings after the session.
- Owner then confirmed both Home Screen messages match: public non-health guidance before two
  online close/reopenings and exact v7 enrolled-key startup sentence afterward. This supports
  current Home Screen JavaScript execution and retained identity, with full script URL/CSS/worker
  gate open. Scope evidence comes from the pre-reopening guidance and unchanged identity, not
  the startup sentence alone. Current batch is bounded VoiceOver A1/A3 plus one existing non-health
  Connect and 30-second steady-state speech observation; no tickets/scopes/Garmin operation.
- Owner reported **all worked** for the updated Home Screen connection batch: clear headings/
  names/order/unavailable states, usable busy/ready focus, Message/Send unavailable until readiness
  and no repeated steady connection speech for 30 seconds. **Home Screen A3 passes** using the
  existing non-health identity. Explicit Message single-touch reading is requested with the public
  chat fixture before closing Home Screen A1; streamed speech/earlier-reading A4 remains pending.
- Owner then reported **ALL WORKED** for Message single-touch/activation, one public blue-cube
  fixture, earlier reading during streaming, no repeated delta interruptions or forced position
  loss and one spoken completion. **Home Screen A1 and A4 pass** for these observed cases. No
  transcript retained. A5 selection/reading retention and Jump to latest focus are the next batch;
  reply-too-quick/uncertain-submission limitations remain explicit.
- Owner reported **pass pass keep goin** for selection/earlier-reading retention during a further
  public reply and named Jump to latest content/Conversation focus. **Home Screen A5 passes** for
  the observed batch. Next batch covers Home Screen largest text/layout/keyboard/pinch, Reduce
  Motion and safe ordinary/VoiceOver Refresh tasks activation, plus Safari highest website zoom/
  pinch/empty-ticket touch. No health/enrollment/logout/notification activation requested.
- Resumption/visual-evidence checkpoint `bdaca5d3c5d1b75357b9f9691cc3d6f0c0eb1aa7` passed
  [CI run 38490869728](https://github.com/DanCreates1/JARVIS/actions/runs/38490869728): Windows
  quality and secret scan at that exact SHA. No application change or CI rerun.
- Owner reported **all worked** for the visual finish batch: actual Home Screen webpage text
  growth at largest accessibility size, readable/separate controls in both orientations,
  authenticated Message keyboard/caret/Send scrolling reachability, pinch/pan and no panel
  entrance motion with Reduce Motion. Ordinary and VoiceOver Refresh tasks each updated the
  intended panel. Safari highest offered website zoom, pinch/pan, ordinary/VoiceOver empty-ticket
  touch and Reduce Motion reload worked. **Home Screen A7/A9 and both surfaces' bounded A11 pass**.
  Safari maximum website percentage was requested but unreported; no protected Safari activation.
- Owner reported **all worked** for the final separate iOS Full Screen Zoom/restoration batch:
  usual text/website zoom restored first, VoiceOver off, magnified text/controls and panning usable
  in Safari and Home Screen. The aggregate response covers restoration of usual Zoom, text size,
  Safari Page Zoom, Reduce Motion and VoiceOver; exact restored values were not separately given.
  **Home Screen A8 passes for available mechanisms**; Safari's observed A8 mechanisms pass, with
  maximum website percentage still unreported. Screen Zoom level was not reported on either
  surface. No numeric 400% phone reflow claim. No further phone questions queued this session.
- Final evidence recorded `2026-10-13T21:35:15-04:00` (documentation checkpoint, not a timestamp
  for every phone action). Application shell remains v7 with no asset changes. Native candidate
  files and MVP 3 report retain their recorded hashes; only the four PWA documentation files are
  included in this publication. Existing Core is left running; M3C acceptance remains separate.

2026-10-13 resumption at baseline `114ab9a`, shell `v7`:

- Local HEAD, tracking `origin/main` and live upstream `main` match
  `114ab9a2a16eacc6a4508a7b958154cae7e75028`. Its
  [CI run 38496582097](https://github.com/DanCreates1/JARVIS/actions/runs/38496582097) passed
  Windows quality and secret scan, including full tests and both Python dependency audits.
- Existing Core was already running and was reused: one Python-owned `127.0.0.1:8765` listener,
  no non-loopback Core listener, exact owned private route/backend/origin, tailnet online and Funnel
  disabled. Loopback/private shell, script and worker HTTP 200; host v7 references unchanged.
  Windows refused the readiness helper's script-file entry point; reviewed code ran through
  the supported command entry point without changing execution/security policy. No restart,
  route/identity operation, ticket or Garmin read. This is readiness, not phone/M3C acceptance.
- Fresh supporting validation passes **43/43 lifecycle tests** and **24/24 desktop geometry
  cases**, Edge **155.0.4283.45**. Application assets match HEAD; native package candidates and
  MVP 3 report retain their recorded SHA256 hashes. Generated evidence and the reviewed local
  readiness runner stay ignored under `runtime/mvp4-fixes/`.
- Direct phone asset inspection is unavailable on this Windows host; official WebKit remote
  inspection requires connected macOS Safari. The matrix now states the public script/CSS/active
  worker/cache checks explicitly. Startup wording and host HTTP checks do not close that gate.
  Next owner batch requests Safari access guidance, maximum Page Zoom percentage and keyboard
  availability without protected activation. No new physical result; existing acceptance rows,
  M3C scope and **88%** milestone estimate remain unchanged. Publication updates only the matrix
  and this report; baseline CI is retained as evidence, not represented as a fresh local full gate.
- Documentation-only publication checks: five local links resolve, diff check passes and Gitleaks
  scans 102 commits with no leaks. Full local Python/native release gates were not rerun for this
  checkpoint; no milestone closure is claimed. Native packages remain excluded under their audit hold.

## 2026-10-14 F11 execution

Baseline `main` at `34b40105c695d70db5c8d92a1488e7a7e135f090`; only the two native package candidates
were dirty. Baseline [CI 38503620663](https://github.com/DanCreates1/JARVIS/actions/runs/38503620663)
passed at that exact SHA. Fresh initial PWA checks passed 43 lifecycle tests and 24 desktop geometry
cases. Historical phone observations remain dated v7 evidence; no physical v8 result is inferred.

Implemented shell **v8**:

- **Cancel reply** sends authenticated Core cancellation, waits for generation/provider cleanup,
  and updates the phone. Cancellation before POST prevents submission; cancellation overtaking POST
  creates a durable Core barrier so delayed submission cannot start generation. Lost cancellation
  acknowledgement retains recovery and triggers same-ID cancellation after a running acknowledgement.
- **Retry request** first reads authoritative status. Accepted requests are resumed/reconciled;
  unaccepted requests reuse the original frozen message/conversation and request ID. Repeated taps,
  new drafts, subscription replacement and lost HTTP acknowledgements cannot create duplicate turns.
  Cancelled/failed/interrupted requests never restart automatically.
- **Saved conversations**, **New conversation**, **Refresh history**, and **Load earlier messages**
  read bounded device-owned Core history. Same device/session renewal restores it after page/Core
  restart. Only an opaque device/request reference is stored on the phone; no transcript or draft
  is persisted. IndexedDB transaction completion precedes POST. Unknown references without a draft
  are closed on Core before allowing re-entry, protecting against a delayed original POST.
- Core reserves each host/device/request ID durably before starting background work. Changed
  payloads conflict; one active turn per device, 64 process-wide and a 300-second deadline. Status
  can attach an owned current subscription without resending text. Authority is revalidated during
  generation. Session expiry/revocation/logout stops bound work; session renewal can reattach it.
- Current session, history generation, conversation and request ownership reject obsolete results.
  Existing one-owner stream/Web Locks rules remain. Terminal replies reconcile missed deltas;
  completion during history restoration cannot disappear or announce twice. Internal tool/planning
  messages and conversations without provable device ownership are not exposed.
- Pre-F11 conversations have no reliable device binding and are not guessed/backfilled. New F11
  conversations persist in Core. Large replies/history pages retain explicit excerpt flags and
  existing output ceilings. Deleted conversation content cannot turn a delayed retry into new work.

### Mobile baseline repair and unresolved audit

Original candidates were preserved/reviewed before install. `rtk npm ci` reproduced their lock.
`rtk npm run verify` then exposed seven Expo SDK patch mismatches. Compatible patches advanced
Expo to `~57.0.29`, metro-runtime `~57.0.17`, crypto `~57.0.4`, linking `~57.0.13`, router
`~57.0.27`, jest-expo `~57.0.6`; constants retained `~57.0.21`, resolving `57.0.22`.
Another frozen install preserved the repaired package/lock hashes:

- package: `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`
- lock: `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`

Formatting/lint/types, **38/38 Jest tests**, unchanged coverage (91.63% statements, 86.69% branches,
93.75% functions, 93.81% lines), **Expo Doctor 21/21**, compatibility and **1,114 license records**
pass. Separate Android/iOS exports pass (1,288/1,152 modules, 3MB/2.6MB bundles). Exports do not
prove a native build, signing or physical-phone behavior. Generated outputs stay ignored.

Aggregate mobile verify still **fails** production audit: **60 findings, 15 moderate / 45 high /
0 critical**. Current reviewed advisories list no patched versions for
[braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm),
[node-forge](https://github.com/advisories/GHSA-86w9-cpqp-85rv), and
[sprintf-js](https://github.com/advisories/GHSA-hp3w-g68c-fv3c). Parent ranges also constrain
moderate decode-uri-component/uuid fixes. No forced major downgrade, audit exclusion or threshold
change was applied. Both local mobile candidates remain preserved under the existing publication
hold; the PWA has no dependency on their Expo runtime.

### Environment and verification

Windows Application Control error **4551** blocked console launchers, the old sidecar interpreter
and compiled mypy DLL. Supported Python module entry points run pytest/pip-audit; exact locked
mypy `1.20.2` was rebuilt from official source with
`rtk uv sync --locked --reinstall-package mypy --no-binary-package mypy --link-mode copy`.
Blocked Garmin environment was preserved under ignored runtime storage and rebuilt with supported
CPython **3.12.14** and locked copy installation. Root remains **3.11.9**, Node **24.20.0**, npm
**11.19.0**. No Windows policy changed. Root/sidecar lock/sync, audits, bootstrap and doctor passed.

Initial full pytest overlapped the new migration/source files: 1,437 passed / 3 skipped / 2 failures,
85.00% coverage. A stable targeted migration-manifest rerun passed; the PWA session/control failure
was repaired and all original lifecycle assertions now pass. Final stable gates are recorded below
before publication; this initial run is not represented as an acceptance pass.

Fresh v8 desktop evidence: 24 geometry/font/text-spacing cases pass with new controls. Actual
Edge **155.0.4283.45** page zoom through native `tabs.setZoom` passes: 100% `innerWidth=1280`,
400% `innerWidth=320`, root scroll width **316**, 14 controls pointer-reachable, new controls
keyboard-reachable, retained reading/selection and a mocked Send pass. No viewport/CSS zoom
substitute, phone speech or authenticated Core claim. Synthetic transport benchmark passes
**100 reconnects / 10,000 events** with zero duplicates/gaps/cross-session deliveries/offline
effects/private state retained; p95 **0.1378ms**, RSS growth **0.785MiB**, shell **62,249 bytes**,
within unchanged 25ms/50MiB/256,000-byte limits. This is transport evidence, not phone performance.
All browser profiles, screenshots and JSON remain ignored under `runtime/mvp4-fixes/`.

### Stable final gate

| Check | Actual 2026-10-14 result |
| --- | --- |
| Root lock check / locked sync | Pass; 119 resolved / 69 checked |
| Garmin sidecar lock check / locked sync | Pass; 20 resolved / 16 checked, supported Python 3.12.14 |
| Windows bootstrap | Pass through supported bundled `pwsh` |
| Ruff format / lint | Pass; 414 formatted files |
| Mypy | Pass; 166 source files |
| Full strict pytest | **1,457 passed / 3 existing optional skips**, **85.60% coverage**, **124.28s**; one existing Starlette deprecation warning |
| Focused Core/API/security/transport/migration | **54 passed**, including 17 new F11 Core cases; actual AssistantService provider cancellation cleanup, unknown-ID cancellation, rebind/restart, privacy/deletion and storage failures |
| Real PWA JavaScript lifecycle | **63 passed**; 43 original assertions retained plus 20 F11 cases |
| Desktop accessibility / actual 400% | **24 cases pass** / separate native zoom pass, 14 controls |
| Synthetic transport soak | **100 reconnects / 10,000 events pass**, unchanged ceilings |
| Root / sidecar dependency audits | No known vulnerabilities |
| Gitleaks required history scan | Pass; 103 baseline commits, no leaks; staged scan before commit |
| Whitespace | Pass |
| Mobile aggregate verify | **Fails production audit only**; repaired local tests/Doctor/licenses/exports pass as above |

Executed commands: `rtk uv lock --check`, `rtk uv sync --locked`, sidecar equivalents with
`--project garmin_sync`, `rtk proxy pwsh -NoProfile -File scripts/bootstrap.ps1`,
`rtk uv run ruff format --check .`, `rtk uv run ruff check .`, `rtk uv run mypy src`,
`rtk proxy uv run python -m pytest --basetemp runtime/pwa-f11-final-20261014-quality1`,
`rtk uv run python -m pip_audit`, sidecar audit with `--path garmin_sync/.venv/Lib/site-packages`,
`rtk proxy gitleaks detect --source . --redact --no-banner`, `rtk git diff --check`, both requested
Node commands and the synthetic benchmark. Fresh pytest target was verified under ignored runtime;
strict configuration/markers and **85%** coverage threshold remain unchanged. Final source stayed
stable during the full suite. Staged/private-data review and exact-SHA publication CI follow;
baseline CI is not substituted for that new run.

Local readiness after the gate: Core was not listening and was resumed with its verified existing
loopback/private configuration through supported `pwsh` and `python -m jarvis`. Owned Serve route,
exact backend/origin and disabled Funnel were validated; no launcher Run/Stop or route change.
Settled state has one Python-owned **127.0.0.1:8765** listener. Loopback/private HTTPS shell,
script and worker return **200** with matching v8 assets; unauthenticated chat-status, history and
Garmin requests return **401**. No credential, new ticket, health read or phone result was used.
An initial detached helper did not persist; the managed local service session succeeded. Staged
Gitleaks scanned approximately **156KB**, no leaks. Safe publication excludes both native package
files under their audit hold and all ignored runtime/generated artifacts.

Published implementation **83a95892a6d5309e60b36ac5158400aa18750ee8** to configured `origin/main`
under standing authorization; local/tracking/live upstream matched. Exact-SHA
[CI 38651530210](https://github.com/DanCreates1/JARVIS/actions/runs/38651530210) **passed** Windows
quality and secret scan: **1,459 passed / 1 skipped**, **85.52% coverage**, **218.90s**, one existing
Starlette warning, both locked dependency audits clear. Local optional skips differ by runtime;
the local result remains 1,457/3 and is not overwritten by CI. Native Mobile CI was not triggered
because held package candidates were excluded; their local aggregate audit failure remains open.
Ten current documentation files resolve **54 relative links**, no missing targets. A report-only
follow-up records this implementation CI result; no application source changes after the full gate.
Core remains running on the verified existing loopback/private route. No v8 physical acceptance,
M3C enrollment decision or native audit pass is claimed. Next milestone: physical F11 acceptance
alongside the remaining M4A matrix; M3C requires its separate pending grouped decision/evidence.

## Historical remaining phone gates — superseded for development on 2026-10-16

The phone execution directions in this historical section are superseded by the current owner
override at the top of this report. Do not resume or request them. Unverified evidence remains
unverified; next development is F12, independent of these skipped manual checks.

M4A local fixes are reviewable; **MVP 4 is not complete**. Owner resumed manual phone checks after
brief deferral on 2026-10-13. Bounded Safari A1/A7/A9/A11 and Home Screen
A1/A3/A4/A5/A7/A8/A9/A11 observations passed. Safari website zoom at 200% and highest offered value,
pinch and iOS screen magnification worked; the maximum website percentage remains unreported.
Full phone script URL/CSS/worker verification is open despite the Home Screen v7 runtime
fingerprint. Safari identity/script execution is unverified, so its authenticated A3-A5 remain
unexecuted; do not enroll it for M4A. A2 invalid-ticket acceptance remains unexecuted, blocked on
Home Screen by its retained identity. A6 failure/recovery/draft speech was not exercised; the
earlier plain connection failure is no substitute. A10 is blocked without an external keyboard.
Logout focus/cleanup stays blocked on separate M3C exact-device authority/evidence. Actual desktop
browser 400% zoom passed on the synthetic Edge shell 2026-10-12. Retain the dated
[M4A matrix](../PWA_M4A_ACCESSIBILITY_ACCEPTANCE.md). F11 implementation and automated regressions
are present; physical v8 cancel/retry/history/restart soak remains pending. Use the 2026-10-15 frozen
phone performance targets before measurements and milestone closure. M3C health-scoped phone
enrollment/revocation/Garmin recovery acceptance stays in its separate report and authority scope.

Estimated active PWA completion: **92%**; accepted phone chat/protected Core Garmin plus verified
M4A local accessibility fixes and bounded owner-reported phone accessibility passes. Health-scoped
physical acceptance, remaining accessibility prerequisites/failure cases,
physical F11 soak and performance/release gates remain open. Targets are now frozen in the
[F11 physical ledger](../PWA_F11_PHYSICAL_ACCEPTANCE.md); no phone sample accepted. Estimate is milestone-based,
not a measured test percentage.

## Current development handoff — 2026-10-17

**F13A–F13D complete** within bounded repository/automated scope; see [completion](PWA_F13_COMPLETION.md).
Current source is shell v10. No subsequent phase queued. Manual phone checks stay skipped by owner;
unverified. Preserve held mobile candidates and separate M3C authority. Current estimate **94%**
includes verified F12 navigation on the existing MVP milestone basis; no physical/MVP closure.
