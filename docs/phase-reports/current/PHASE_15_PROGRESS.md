# Phase 15 — Email

- Status: `blocked-external`
- Started / updated: 2026-10-31 / 2026-11-01
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Current verification checkpoint / conservative stop: 2026-11-01 16:43:47 UTC / 2026-11-01 20:30 UTC

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
  protected production token storage/auth/activation remain unimplemented and unaccepted.
- [x] Inactive Gmail read-adapter milestone: synthetic account/scope/provenance/transport/lifecycle
  matrix and real parser/Core privacy checks; no runtime activation or production token source.
- [ ] Explicit default-off configuration and exact account binding. No startup login, mailbox
  discovery, automatic fallback to exports/another account, remote email endpoint or polling.
- [ ] Foreground reads only: bounded list of at most 100 thread references; explicitly selected
  thread at most 16 messages, each at most 128 KiB; reject over-limit/incomplete thread responses
  rather than silently summarizing an incomplete thread. Provider mapping must preserve canonical
  IDs/provenance without changing local export ID rules or inventing verified chronology.
- [ ] Read data: selected message text, bounded unverified From/To/Subject/Date metadata and
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
- [ ] Every network operation bounded by time/bytes/request count; read/thread <=30 s and list
  <=5 s, zero automatic read retries. Freeze provider-specific request/response budgets before
  implementation. Redirects/unapproved origins denied; malformed schema, wrong ownership,
  over-size, rate limit and provider outage fail with content-free errors. Cancel drains work.
- [ ] Disable prevents new acquisition and discards in-flight results. Revoked/expired/denied
  credentials stop access; no automatic login, account switch or scope expansion. Any authorized
  same-account renewal stays bounded. Disconnect behavior and provider-side revocation instructions
  documented; token deletion/revocation never conflated with disabling reads or erasing history.
- [ ] Synthetic hostile MIME/provider lifecycle matrix: injection, cross-account/ID mismatch,
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

## Decisions, authority and blockers

Provider/account type and auth design are selected; exact mailbox binding, local account alias and
Desktop OAuth client-registration ownership/status remain missing. One information question is
pending; no connected-chat mailbox or credential is inferred. Reviewed alternatives and selected
auth/data contract live in [provider decision](../../EMAIL_PROVIDER_DECISION.md). No credential,
login, scope change, live private read, new client/project or terms acceptance attempted.
Independent safe work completed: frozen provider budgets, inactive adapter, hostile lifecycle/Core
privacy tests and shared disable-generation repair. The next concrete auth/setup review depends
on whether an owner-controlled Desktop client already exists. Protected-token implementation,
runtime activation and bounded live proof remain unfinished; synthetic injected tokens grant no
production authority. Do not request passwords, tokens or secret client files in chat.

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

## Known limits, recovery and deferred scope

Existing functionality remains explicit local `.eml` exports and trusted-local preparation only.
The new Gmail adapter is inactive and reachable only by explicit trusted-host Python composition
with an injected token source; ordinary bootstrap/CLI still supports exports only. No production
auth/token-storage/renewal acceptance is claimed. Existing source replies retain normal history
semantics; provider bytes/errors/projections remain volatile. Google profile/account binding proves
the authenticated mailbox match, not authentic senders or transactional thread chronology.
Disable `JARVIS_EMAIL_ENABLED`, remove selection and restart to stop local acquisition. Export
sources are never modified. Delete private derived replies using existing conversation lifecycle;
SQL deletion does not securely erase WAL, backups or storage. Preserve migration 016 on rollback.
No full email, provider, physical or production acceptance claimed.

## Publication and handoff

Prior initiation publication `ad47467` contains five documentation paths only: email contract,
provider decision,
current progress, master ledger and overview. All 28 held paths retain exact bytes/deletion state;
the original 97 package versions remain unchanged. No provider/native/application/configuration/
test/lock/private/runtime artifact is included. Exact staged/publication tree agreement and
HEAD/tracking/live-remote equality and fresh exact-commit CI passed for that initiation checkpoint.
Those gates did not validate a live email adapter or phase completion.
Current checkpoint additionally reviews the inactive adapter, shared preparation lifecycle and
focused unit/Core integration tests. Only this task's ten source/documentation/test paths may be
published; no held path, dependency lock, private account/client descriptor or runtime artifact.
Current release checks pass for both sources, including unchanged root/Garmin locks and audits,
PWA/desktop checks, synthetic local benchmark/smoke, secret scans and documentation/source review.
The exact publication tree, normal push and HEAD/tracking/live-remote agreement are verified when
published; fresh exact-commit CI is checked separately afterward and recorded in the final handoff
and ignored publication receipt. This checkpoint does not close Phase 15 or activate Gmail.
Progress remains **14/19 primary receipts closed (~74%)**, unweighted management count, not
code/effort or mobile MVP acceptance. Next current work: **Continue Phase 15 — Email** with exact
local account/client setup and protected auth/activation review; Phase 16 has not started.
