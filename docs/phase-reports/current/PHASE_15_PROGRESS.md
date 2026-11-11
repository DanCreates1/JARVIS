# Phase 15 — Email

- Status: `implemented-closeout-pending`
- Started / updated: 2026-10-31 / 2026-11-10
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Resume checkpoint / conservative stop: 2026-11-04 22:49:01 UTC / 2026-11-05 03:30 UTC

## Current live acceptance — 2026-11-10

Owner supplied a different exact RFC Message-ID after the prior oversized-thread rejection.
The same explicit, exact-match ID-only lookup resolved one message without pagination or broad
listing. Existing protected same-account foreground acquisition/renewal succeeded without new
login, replacement or scope expansion. The unchanged selected-thread proof **passed** against
one actual thread containing **one message**, in **805.831 ms**. Provenance verified; summary,
extraction, bounded private projection and the fixed synthetic draft reused the volatile observed
thread. Draft remained **unsent and unstored**. Mailbox cache, cloud calls, research calls,
provider writes and cost were **zero**. No private source text or identifiers enter this report.

This closes the external source/live-proof blocker. Full current working/publication release
gates and reviewed documentation publication remain in progress; no phase completion is claimed
before they pass. Production configuration remains off; no send, worker, new remote email scope
or calendar access is enabled. Sanitized evidence is retained under ignored
`runtime/phase15/closeout-20261110/`. The 2026-11-08 failure below remains historical evidence.

Closeout environment repair: Windows Application Control denied coverage's native tracer.
The fallback on Python 3.11 produced synthetic request-body/cancellation failures; those runs
earn no acceptance credit. Verification uses the project's supported Python 3.12.14 and the
documented `COVERAGE_CORE=pytrace` implementation, retaining branch measurement and the 85%
floor. No OS/security control or blocked native module was bypassed. The original Python 3.11
environment and all 97 installed package versions remain unchanged; separate ignored environments
hold the locked Python 3.12 base/optional dependencies. Mypy still checks the configured Python
3.11 target using its compatible locked environment.

That run exposed two legacy deployment test modules deriving a synthetic pinned Python 3.11
deployment target from the test runner's version. Fixtures now explicitly simulate the reviewed
3.11.16 deployment target within the resilience module only, independent of the test interpreter.
Production deployment schema/runtime checks are unchanged. Added denial coverage for a 3.12
manifest and a mismatched runtime patch version. All 28 affected tests pass under both Python
3.11 and Python 3.12; final complete-source suites rerun after this test-only correction.
Application code, dependency locks, native manifests and existing held provider edits stay unchanged.

Final executable publication-source gates pass: **2,315 tests**, three existing skips,
**87.11% combined statement/branch coverage**, 350.68 s on Python 3.12.14 with pure-Python
coverage. Mypy passes all 191 source files against the configured Python 3.11 target; Ruff
format/lint, locked base sync/audit, PWA lifecycle/PCM 175 tests, desktop accessibility 72 cases,
prototype-text/private-email nine cases each and synthetic local-model privacy/recovery smoke pass.
The unchanged frozen local-export benchmark passes **100/100 cases**, 400 real parsers,
zero oracle/provenance failures, p50 **476.791 ms**, p95 **516.977 ms** <=1,000 ms, maximum
projection 490 characters, zero credentials/cloud/research/effects/cost. These synthetic benchmark
numbers are separate from actual Gmail read timing. A fresh installed wheel matches all 221
packaged source files and passes real isolated parsing/summary/extraction/projection/unsent-draft
checks without owner credentials. Current working-tree full checks and exact-commit CI remain
pending before phase closure. No executable source changes after this publication-source freeze.

## Earlier live checkpoint — 2026-11-08

Owner completed the approved Google project/Desktop-client setup and Google login/consent.
The selected registration passed the existing loader and was moved outside the checkout to
private local storage. Actual PKCE authorization and exact-account profile verification passed;
the CLI confirmed creation of the account/client-bound Windows Credential Manager refresh grant.
No credential, account, client identifier, callback, message identifier or private source text is
included in this report. No production environment file or background acquisition was enabled.

Initial Google consent was denied because tester access was unavailable. Owner corrected the
test-user configuration; a fresh explicit login succeeded. No Google denial was bypassed.
Owner then supplied one conversation and its exact RFC Message-ID for a narrowly scoped
identifier lookup. One exact `rfc822msgid` query, maximum two ID-only results, no pagination,
resolved one message. This explicit source-resolution step is separate from the unchanged
selected-thread proof, which performs no discovery. No generic mailbox listing was performed.

The selected-thread proof failed closed with `gmail_response_limit`. Subsequent bounded,
metadata-only diagnosis found three messages with size estimates 3,285 / 689,501 / 6,648 bytes;
the middle message exceeds the unchanged **131,072-byte/message** limit. No successful
read/prepare acceptance is claimed; messages were not silently omitted and no limit increased.
Requested another owner-selected, short single-message conversation without attachments.
Existing consent and same-account foreground renewal authority persist; no new login is needed
merely to select another source. Phase remains `blocked-external` on that source input and
subsequent live proof/closeout gates. Earlier milestones below remain historical evidence.

## Objective and scope

Approved-provider read/thread summaries and visibly unsent draft preparation with provenance.
Reuse `EmailReadProvider`, isolated MIME parsing, `EmailService`, trusted-local CLI and sticky
conversation privacy. Phase 7 prerequisite and Phase 14 receipt are complete. Owner selected
personal Gmail / desktop delegated OAuth / `gmail.readonly` on 2026-11-01. Current official
auth/API/data-policy review and frozen budgets precede the inactive adapter milestone below.
No provider write/draft/send, unattended polling, new remote scope or email PWA endpoint.

## Baseline and preservation

- Resume baseline: `ad474675d4c42a9e6f7cb5f3db763b592411e7f5`, matching tracking and live
  remote on resume. Prior initiation CI [41265754451](https://github.com/DanCreates1/JARVIS/actions/runs/41265754451)
  passed for that exact commit. All 28 held paths match the initiation byte/deletion snapshot.
- `main` at `74ebda4`, current Phase 14 complete. Captured hashes/deletion state for 28 existing
  held provider/native paths plus tracked patch under ignored `runtime/phase15/`. Preserve all.
- Current architecture, execution protocol, complete master roadmap, email contract, Legacy I
  report and security boundaries read. Legacy IA is local acceptance only; IB remains unaccepted.
- Existing local adapter: 100 threads, 16 messages/thread, 128 KiB/message, isolated text-only
  parser, 30 s read deadline, 8,000-character private projection; no credential or send port.
- Preserve prototype-text, locks, $0, privacy/auth/approval, native publication hold and original
  historical evidence. Volume acceptance remains unchanged 100% on built-in speakers only;
  earlier headphone failure and arbitrary-percentage/all-output limits remain documented.

## Acceptance checklist

Frozen before new provider implementation or live measurement:

- [x] Owner-selected personal Gmail / desktop delegated OAuth / exact `gmail.readonly` design;
  current official API/OAuth/data-policy sources and provider budgets reviewed/frozen before code.
- [x] Exact account/client ownership, applicable project terms/setup and private-read authority;
  actual owner-approved Google setup, consent, account verification and protected grant passed.
- [x] Inactive Gmail read-adapter milestone: synthetic account/scope/provenance/transport/lifecycle
  matrix and real parser/Core privacy checks; no runtime activation or production token source.
- [x] Explicit default-off configuration and exact account binding, verified synthetically. No startup login, mailbox
  discovery, automatic fallback to exports/another account, remote email endpoint or polling.
- [x] Synthetic foreground-read gates: bounded list of at most 100 thread references; explicitly selected
  thread at most 16 messages, each at most 128 KiB; reject over-limit/incomplete thread responses
  rather than silently summarizing an incomplete thread. Provider mapping must preserve canonical
  IDs/provenance without changing local export ID rules or inventing verified chronology.
- [x] Synthetic read/preparation data gates: selected text, bounded unverified From/To/Subject/Date metadata and
  source IDs/digests only. HTML rendering, attachment extraction, forwarded-body evidence and
  remote-resource fetching excluded; any MIME bytes remain inert within parser bounds.
  Summary excerpts <=512 characters; <=64 extraction candidates; projection <=8,000
  characters. Draft <=10 explicit bare recipients, subject <=512 and body <=8,000 characters;
  `sent=false`, `stored=false`; no provider draft API.
- [x] Credentials remain in protected Windows host storage, never browser/model/Git/diagnostics.
  Raw provider responses and email projections remain volatile; no mailbox cache/index/database.
  Existing private reply history retains normal conversation deletion/backup semantics. Sticky
  email privacy survives disable, restart, failed acquisition and selection removal; no automatic
  research, cloud override, memory capture, action or send authority.
- [x] Synthetic network gates: every operation bounded by time/bytes/request count; read/thread <=30 s and list
  <=5 s, zero automatic read retries. Freeze provider-specific request/response budgets before
  implementation. Redirects/unapproved origins denied; malformed schema, wrong ownership,
  over-size, rate limit and provider outage fail with content-free errors. Cancel drains work.
- [ ] Disable prevents new acquisition and discards in-flight results. Revoked/expired/denied
  credentials stop access; no automatic login, account switch or scope expansion. Any authorized
  same-account renewal stays bounded. Disconnect behavior and provider-side revocation instructions
  documented; token deletion/revocation never conflated with disabling reads or erasing history.
- [x] Synthetic hostile MIME/provider lifecycle matrix: injection, cross-account/ID mismatch,
  malformed/oversized/truncated responses, timeout/cancel, 401/403/429/5xx, network loss, duplicate
  IDs, restart, disable/revocation and no unexpected cloud/research/effects/private logging.
- [x] Existing frozen local benchmark: 100 single-message cases, four operations/case, 400 isolated
  parsers, 100% oracle/provenance correctness, p95 <=1,000 ms, no cache, exactly $0 and zero
  credentials/cloud/research/effects. Current synthetic Windows Core/CLI/model/restart proof.
- [x] Separate bounded live read/prepare proof after concrete authority: proposed one selected
  thread, <=3 messages, <=128 KiB/message, no attachment/write/send; sanitized evidence only.
  Live response time is reported, not substituted for synthetic benchmark performance.
- [ ] Full applicable working/publication quality, >=85% branch coverage, audits, privacy/security,
  secret/source/link checks and fresh exact-commit CI. No held provider/native publication.
- [x] Phone checks **skipped by owner; unverified**; physical/native/MVP acceptance unestablished.

## Milestone log

1. Audited baseline/contracts and froze scope/bounds. Requested provider/account selection before
   implementing live adapter or accessing any account. Read-only connector availability does not
   select the JARVIS provider or transfer credentials/scopes into Core.
2. Current local baseline: 56 focused unit/security/integration tests pass in 6.88 s; root lock
   check passes (119 packages). No provider credentials or owner store read.
3. Full working regression passes: 1,751 tests, three existing skips, 86.45% branch coverage,
   174.83 s. Existing Starlette TestClient deprecation retained. Ruff format/lint and Mypy pass
   (173 source files); installed optional dependency and Garmin audits clean. PWA lifecycle/PCM
   173 pass, desktop accessibility 72 cases and prototype-text nine cases pass.
4. Current Windows synthetic production smoke passes doctor, local-model email answer, cloud
   override denial, restart/delete and unsent volatile draft. Zero credentials, research/cloud
   calls, effects or spend. Existing smoke uses installed `qwen3:0.6b`, not a new model download.
5. Frozen local benchmark passes: 100/100 cases, 400 isolated parser processes, zero oracle
   failures; p50 499.650 ms, p95 540.213 ms against unchanged <=1,000 ms target. Maximum
   projection 490 characters; no cache, credentials, cloud/research/effects or spend. Run started
   after full working tests ended. Multi-message throughput is not measured by this benchmark.
6. Isolated publication regression passes: 1,752 tests, three existing skips, 86.40% branch
   coverage, 166.76 s; format/lint/Mypy and locked base audit pass. The published baseline retains
   one additional legacy provider test. Synthetic production email smoke/doctor/restart/delete
   passes; PWA lifecycle/PCM 173, desktop accessibility 72 and prototype-text nine cases pass.
   No application/configuration/test source changed during or after these suites.
7. Resume: selected personal Gmail and requested local account alias/client-registration status as
   missing information. No account profile, mailbox, credential file or owner store inspected.
   Resume baseline: 56 email tests pass in 4.68 s; 119-package lock check passes; 28 held paths exact.
8. Inactive `GmailReadProvider` implements the existing port with an injected trusted-host token
   source. Default-off; no production credential source/store, OAuth flow, Gmail CLI, settings or
   startup wiring. Exact profile/account/scope checks precede mail reads. List is one bounded page;
   selected reads require complete 1–16-message inventories, matching raw IDs/versions and identical
   final inventory/history. Existing isolated MIME parser, projection/draft bounds remain intact.
   Opaque IDs map reversibly into account/kind-bound canonical IDs; export validation is unchanged.
9. Fixed shared preparation lifecycle: disable/re-enable cannot resurrect a result begun under an
   earlier enabled generation. Provider-neutral projection labeling distinguishes acquired mail
   from exports while preserving sticky local privacy. No new Core, model tool or client scope.
10. Synthetic matrix passes: 150 focused email/Gmail tests in 11.55 s before final sanitization/
    labeling polish. Real parser and synthetic HTTP coverage includes maximum 16-message/19-request
    thread, 128 KiB boundary, stale/missing/duplicate inventories, account/ID/scope mismatch,
    malformed/oversized/compressed/truncated JSON, redirects/cookies, 401/403/404/429/5xx, revoked/
    expired tokens, real deadlines, disable/re-enable, network loss, cancellation and child reap.
    Core integration verifies private routing, restart/failure stickiness and no research, memory,
    cloud or persisted raw projection. Final complete-source verification is recorded below.
11. Prior work segment was interrupted before verification. Resumed complete-source working
    regression passes: 1,845 tests, three existing skips, 86.55% branch coverage, 241.03 s;
    Gmail adapter combined statement/branch coverage is 98%. Ruff format/lint and Mypy pass
    (174 source files). Root installed optional and Garmin audits pass; PWA lifecycle/PCM 173,
    desktop accessibility 72 and prototype-text nine cases pass. Source hashes were frozen before
    isolated publication verification. Final token-length hardening below supersedes these suites.
12. Resumed frozen local benchmark passes 100/100 cases, 400 parsers, zero oracle failures;
    p50 563.114 ms, p95 627.154 ms <=1,000 ms, maximum projection 490 characters. Synthetic
    production local-model email/doctor/cloud-denial/restart/delete/unsent-draft smoke passes.
    Zero credentials, cloud/research calls, effects or spend. These remain local-export proofs,
    not live Gmail performance or production auth acceptance.
13. Exact isolated publication regression passes: 1,846 tests, three existing skips, 86.50%
    branch coverage, 193.11 s. The one additional legacy provider test remains published;
    held provider removal stays local. Locked base/Garmin sync and audits pass; Ruff format/lint,
    Mypy, PWA lifecycle/PCM 173, desktop 72 and prototype-text nine cases pass. Built/installed
    wheel includes the Gmail module and real isolated MIME worker; default-off construction uses
    no credential source. Final token-length hardening below supersedes these suites.
14. Final source review found that token validation bounded non-padding characters but not trailing
    `=` padding. Added an 8,192-character total-token cap and a rejected oversize-padding case;
    also verified that token-source error codes cannot disclose private content. Final focused
    suite and complete working/publication regressions are rerun against this stronger boundary.
    Final focused suite: 152 tests pass in 12.14 s; Ruff/Mypy pass. Isolated local-export benchmark
    also passes 100/100 with p50 669.492 ms, p95 784.183 ms <=1,000 ms; production local-model
    smoke passes. The token-only hardening does not change the tested local export/service/smoke
    source. These numbers are not Gmail live latency or auth/storage acceptance.
15. Final exact-source regressions pass after token hardening: working 1,847 tests, three existing
    skips, 86.58% coverage, 246.61 s; isolated publication 1,848 tests, three existing skips,
    86.54% coverage, 231.84 s. Existing Starlette TestClient deprecation remains. Final Ruff
    format/lint/Mypy and focused checks pass. A fresh built/installed wheel matches the final
    Gmail source bytes and passes real isolated parser/default-off checks without credentials.
    All application/test/configuration/lock source remains unchanged after these final gates.
16. Resume at `17d93dda6679efec5bea216ccaba1ce9853591bb`: HEAD, tracking and live remote agree;
    exact-commit [CI 41329115610](https://github.com/DanCreates1/JARVIS/actions/runs/41329115610)
    completed successfully. Current focused email/Gmail unit/security/Core suite passes 152 tests
    in 10.35 s; root lock check and whitespace checks pass. All 28 held paths retain exact bytes/
    deletion state. Prior chat review confirms only personal Gmail/auth selection was supplied;
    no local account alias, exact mailbox or Desktop OAuth client-registration status/path exists
    in that handoff. Requested missing setup information; no credential discovery, account/profile
    read, login, project creation, scope change or live mailbox read attempted. Protected auth/
    activation and live acceptance remain blocked on these external inputs and applicable authority.
    No application/test/configuration/lock source changed; prior full-source gates remain the
    implementation evidence. This resumed checkpoint changes this report only.
17. Owner confirmed no project/client exists. Implemented bounded explicit local PKCE OAuth,
    Windows per-user Credential Manager create/read/exact disconnect, exact account/client/scope
    binding and foreground-only renewal. Existing credentials cannot be replaced automatically.
    Access tokens remain volatile; refresh grants never enter settings/model/client/diagnostics.
    A disposable random synthetic Windows credential target passes actual create/read/refuse-
    replacement/delete; native failures, capacity and handle cleanup pass synthetic checks.
18. Added explicit `private-email` with independent default-false email gate, lazy credential
    acquisition and provider choice without fallback. Reused one Core/service/CLI/private routing.
    Applied existing text-only model/tool/prompt and PWA exclusions; Garmin/files/voice stay denied.
    Shell v21 invalidates prior asset cache while preserving API/private-data cache exclusions.
    Added `gmail-auth`, `gmail-disconnect` and `gmail-proof` trusted-local commands, each with a
    default-No concrete confirmation. No production environment file or actual account touched.
19. Prepared selected-thread proof rejects >3-message inventories before raw reads, performs one
    network read and reuses the volatile observed thread for cited preparation plus a fixed synthetic
    unsent/unstored draft. Output contains sanitized counts/timing/booleans only. Synthetic tests
    cover 1/3/4-message bounds, hostile callback headers/state/replay, exact S256, wrong account,
    token scope/rotation denial, five-second renewal deadline, cancel/drain, restart/local deletion
    and real parser/Core privacy. Focused email/auth matrix passes 270 tests; final profile/auth/
    PWA transport subset passes 169 tests. Final exact-source full gate receipts follow below.
20. Final frozen working source passes **1,971 tests**, three existing skips, **86.60% combined
    statement/branch coverage**, 249.27 s. Exact isolated publication source passes **1,972 tests**,
    three existing skips, **86.56%**, 235.68 s; the extra legacy provider test remains published.
    Ruff format/lint and Mypy pass (177 source files). New Gmail adapter/auth/credential-module
    coverage is 98.53% / 93.64% / 100%. Existing Starlette TestClient deprecation remains.
    Full source hashes were frozen before these final runs and checked before publication.
21. Root/base optional and isolated locked base/Garmin audits pass without dependency/lock changes.
    Working and publication PWA lifecycle/PCM **175 tests**, standard desktop **72 cases**,
    prototype-text **9 cases** and private-email **9 cases** pass. Fresh built/installed wheel
    contains exact auth/read/proof/service source, shell v21 and the real isolated MIME worker;
    parser/default-off/lazy-source checks use zero owner credentials. Synthetic Windows local-model
    smoke passes doctor/private email/cloud denial/restart/delete/unsent draft in both environments.
22. Final local-export benchmark passes unchanged 100/100 cases, 400 real parser processes and zero
    oracle/provenance failures in each environment. Working p50/p95 **504.440/567.891 ms**;
    publication **611.562/666.529 ms**, against frozen p95 <=1,000 ms. Maximum projection 490
    characters; no cache, credentials, cloud/research calls, effects or spend. Runs followed full
    tests and model smokes without another benchmark/model workload. These are local-export
    performance proofs, not Google auth or Gmail live-read latency evidence.
23. Resumed 2026-11-04 at `57b0709c108e40d39a1b750485317ae9e198f7db` after independent
    Phase 16 commits. Existing bounded setup/consent/live-read approval persists. Owner is ready
    for Google console setup; requested exact account and selected Desktop client file path as
    information, not new authorization. No private account/file contents or credentials inferred.
    Finished review of the pending metadata compatibility correction: accept Google's documented
    legacy client-file OAuth URLs as metadata while keeping actual browser/token destinations
    pinned to current constants. Four metadata combinations retain hostile URL/schema denial;
    focused working auth/credential/provider/Core tests pass **215 tests in 15.71 s**.
    Root whole-repository checks also observed concurrent uncommitted Calendar auth work with
    format/type failures. Those files are outside this task and remain untouched. Isolated
    publication starts from committed `57b0709` and copies only four Phase 15 paths, preserving
    held provider/native and concurrent Calendar changes. Current complete-source gates follow.
24. Current isolated publication source passes **2,147 tests**, three existing skips,
    **86.81% coverage**, 242.64 s. Format/lint and Mypy pass (184 source files); locked root/base
    and Garmin sync/audits pass. Root installed optional-package audit also passes. PWA lifecycle/
    PCM **175 tests**, standard desktop **72 cases**, prototype-text and private-email **9 cases
    each** pass. Fresh installed wheel accepts all four allowlisted client metadata combinations,
    matches the tested auth module and runs the real isolated MIME parser; no owner credentials
    used. Published baseline `57b0709` has successful exact-commit CI. Source, local links, staged
    secret scan and final publication/CI receipts are checked separately for the compatibility patch.

## Decisions, authority and blockers

Owner approved the prepared project/client setup, `gmail.readonly` with offline renewal,
exact-account profile check and one owner-selected <=3-message/128-KiB-each live read/prepare.
Approval persists within that scope. Owner handles Google login/consent and reviews applicable
terms. No billing, public publishing, provider mutation/send or cloud email is authorized.
Actual account/client setup and live acceptance still need evidence; do not repeat this approval.

Owner clarified on resume: no Google project or Desktop OAuth client exists. Independent next
milestone is protected host credentials, explicit local OAuth command and default-off composition,
all verified synthetically before any consequential setup review. No project creation, terms
acceptance, login or new grant is authorized by that clarification. Local alias defaults to
`personal`; exact mailbox and downloaded Desktop client file are explicit local command inputs.
Frozen auth budgets: one system-browser launch, 180 s total OAuth flow, ephemeral IPv4 loopback
callback, at most eight inbound requests and four active handlers, 8 KiB request headers and 2 s
header deadline. S256 PKCE and constant-time random-state checks; no callback code in output/logs.
Exactly one token POST (5 s / 16 KiB JSON) and one exact-account profile GET before initial storage;
no mailbox body access during auth. Foreground renewal is at most one token POST per operation,
within existing 5/30 s operation deadlines, zero retries. Windows per-user local-machine Credential
Manager stores only exact account/client/scope-bound refresh grants, <=2,560 bytes serialized and
refresh token <=2,048 ASCII characters; access tokens remain volatile. Initial creation refuses an
existing credential; no automatic replacement, revocation, account switch or scope expansion.
Local token deletion requires an explicit trusted-local command confirmation; disable is separate.
No dependency/lock changes, ambient proxy, redirect, browser/client secret projection or polling.
Current primary OAuth/API/policy and Windows credential-storage documentation reviewed before code.

Provider/account/auth design selected; owner confirmed no existing project/client. Exact mailbox
and downloaded Desktop registration are explicit local inputs; no connected-chat account is
inferred. [Prepared setup/approval](../../GMAIL_SETUP.md) describes an owner-controlled personal
project, Gmail API only, Desktop client, External/Testing audience and only the owner as test user,
with no billing linkage/public publishing. Project/terms setup, new OAuth consent with offline
renewal, exact-account profile verification and one deliberately selected <=3-message read need
consequential authority. No actual Google credential, login, new scope, profile/mailbox access,
project/client creation or terms acceptance attempted. Synthetic protected storage grants no
production authority. No passwords, tokens or secret client contents belong in chat.

## Verification and measurements

Artifacts remain ignored under `runtime/phase15/`. Working environment: CPython 3.11.9,
uv 0.12.15, Node 24.20.0, Windows build 26300. Isolated publication environment: CPython 3.11.16;
locked root sync uses a new environment without changing the owner's optional environment.
Root lock/sync/base audit and Garmin lock/sync/audit pass. History and exact source secret scans
pass. Initiation evidence: five Phase 15 documentation paths were prepared independently from
`74ebda4`; application/configuration/tests/locks in that publication remained identical to its
baseline. All 28 held paths retained exact bytes/deletion state. Initial link review: 134 local
links/anchors, 591 source paths.
Legacy benchmark numbers remain historical, not current proof. Synthetic/local passes do not
satisfy the selected-provider live-read exit.

Resume source review: ten safe paths, 135 local links/anchors and 594 publication source paths;
history and exact publication-source secret scans pass. Locked root sync uses the separate ignored
`runtime/phase15/gmail-publication` worktree; original optional working environment stays intact.
All 28 held paths remain byte/deletion-identical. An initial isolated command used a wrong relative
preparation path; it was stopped and is not acceptance evidence. Preparation was corrected and
the exact source copied/frozen before applicable isolated checks were restarted. A later attempt
reused an interrupted-run basetemp and produced fixture setup errors; it was stopped. Fresh-directory
diagnostics passed, and the full coverage gate was restarted in a new verified ignored runtime
directory. Interrupted/diagnostic runs receive no full acceptance credit; no source or gate changed.

Commands used through RTK: root `uv lock --check`; isolated `uv sync --locked --link-mode copy`;
Ruff format/check, `python -m mypy src`, full strict `python -m pytest` with new ignored runtime
basetemp directories, `python -m pip_audit --strict`, Garmin lock/sync/audit; Node lifecycle/PCM,
desktop/prototype accessibility; `phase-i-email-benchmark.py --enforce` and
`phase-i-email-smoke.py`; Gitleaks history/exact-source/staged scans, local link/anchor checks and
`git diff --check`. Locked isolated execution uses `uv run --locked`; working checks use the
unchanged locked `.venv` with optional packages preserved.

Auth milestone final sources use ignored `auth-final-*-source-v2.json` hash receipts. Development
runs before this freeze receive no final-source acceptance credit: one changing-source run had
1,955 passing tests but 84.66% coverage; final source fixes and reruns above preserve the 85% gate.
An initial isolated run produced 169 fixture setup errors from `FileNotFoundError [WinError 3]`
creating its nested relative basetemp. A new-directory diagnostic passed. Both final full runs use
separate fresh absolute paths under the existing workspace `runtime/` parent, verified ignored and
absent before pytest. No gate, test or threshold was disabled. Final full runs contain no errors.

## Known limits, recovery and deferred scope

Explicit local `.eml` exports remain available. The Gmail adapter now has explicit protected-host
auth/renewal and lazy default-off bootstrap/CLI composition; actual Google setup/auth/live acceptance
remain pending. No production setting was activated. Existing source replies retain normal history
semantics; provider bytes/errors/projections remain volatile. Google profile/account binding proves
the authenticated mailbox match, not authentic senders or transactional thread chronology.
Disable `JARVIS_EMAIL_ENABLED`, remove selection and restart to stop local acquisition. Export
sources are never modified. Delete private derived replies using existing conversation lifecycle;
SQL deletion does not securely erase WAL, backups or storage. Preserve migration 016 on rollback.
Disable and disconnect follow [current runbook](../../GMAIL_SETUP.md#disable-disconnect-and-recovery).
No full email, provider, physical or production acceptance claimed.

## Publication and handoff

Prior initiation publication `ad47467` contains five documentation paths only: email contract,
provider decision,
current progress, master ledger and overview. All 28 held paths retain exact bytes/deletion state;
the original 97 package versions remain unchanged. No provider/native/application/configuration/
test/lock/private/runtime artifact is included. Exact staged/publication tree agreement and
HEAD/tracking/live-remote equality and fresh exact-commit CI passed for that initiation checkpoint.
Those gates did not validate a live email adapter or phase completion.
Inactive-adapter publication `17d93dd` has exact-commit successful CI linked in milestone 16.
Resumed verification-only report checkpoint `58de0f7` precedes the current auth implementation.
Current publication reviews 26 task paths: bounded auth/read/preparation, explicit settings/CLI,
text-only Core/PWA profile exclusion/cache update, tests and six email/status/setup documents.
Two held files (`config.py`, `bootstrap.py`) contain only separately isolated task additions;
reversing those additions reproduces the original held hashes. Other 26 held paths retain exact
bytes/deletion state. Held provider/native edits, locks, private client/account descriptors and
runtime artifacts are excluded from publication. Final working/isolated release evidence is
recorded in the verification section; exact tree/push/ref agreement and fresh exact-commit CI
are checked separately and recorded in the final handoff/ignored receipt. Repository auth code
and a passing synthetic proof do not close Phase 15 or enable an actual Google grant.
Progress remains **14/19 primary receipts closed (~74%)**, unweighted management count, not
code/effort or mobile MVP acceptance. Next current work: **Continue Phase 15 — Email** with exact
approved project/client setup, exact local inputs and actual auth/live proof. Phase 16 has independent
commits and remains governed by its own current report; this resumption does not change that scope.
