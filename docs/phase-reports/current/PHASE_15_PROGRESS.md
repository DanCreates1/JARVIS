# Phase 15 — Email

- Status: `blocked-external`
- Started / updated: 2026-10-31 / 2026-11-01
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Current verification checkpoint / conservative stop: 2026-11-01 17:42:57 UTC / 2026-11-01 20:30 UTC

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
- [ ] Exact account/client ownership, applicable project terms/setup and private-read authority;
  protected host token storage/auth/configuration are implemented; actual setup/auth remain unaccepted.
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
- [ ] Credentials remain in protected Windows host storage, never browser/model/Git/diagnostics.
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
- [ ] Separate bounded live read/prepare proof after concrete authority: proposed one selected
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

## Decisions, authority and blockers

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
approved project/client setup, exact local inputs and actual auth/live proof; Phase 16 has not started.
