# Phase 15 — Email

- Status: `blocked-external`
- Started / updated: 2026-10-31 / 2026-10-31
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: gpt-6-astra / ultra (recommendation only)
- Session start / five-hour stop: 2026-11-01 02:20 UTC / 2026-11-01 07:20 UTC

## Objective and scope

Approved-provider read/thread summaries and visibly unsent draft preparation with provenance.
Reuse `EmailReadProvider`, isolated MIME parsing, `EmailService`, trusted-local CLI and sticky
conversation privacy. Phase 7 prerequisite and Phase 14 receipt are complete. Select mailbox
provider/account type and review current official auth/API/terms before live-adapter implementation.
No provider write/draft/send, unattended polling, new remote scope or email PWA endpoint.

## Baseline and preservation

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

- [ ] Owner-selected provider/account type and documented desktop delegated OAuth path;
  current official API/terms review, exact requested scopes and applicable private-read authority.
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

## Decisions, authority and blockers

Provider/account selection is the external blocker. Reviewed alternatives and proposed auth/data
boundary live in [provider decision](../../EMAIL_PROVIDER_DECISION.md). User was asked once; no default mailbox
is inferred. No credential, login, scope change, live private read or API terms acceptance attempted.
Provider-independent audit, acceptance freeze, local regression and isolated release verification
are complete; documentation publication continues separately. Live adapter waits for selection.
After selection, prepare concrete account/client/scope/read review before consequential access.

## Verification and measurements

Artifacts remain ignored under `runtime/phase15/`. Working environment: CPython 3.11.9,
uv 0.12.15, Node 24.20.0, Windows build 26300. Isolated publication environment: CPython 3.11.16;
locked root sync uses a new environment without changing the owner's optional environment.
Root lock/sync/base audit and Garmin lock/sync/audit pass. History and exact source secret scans
pass. Five Phase 15 documentation paths are prepared independently from `74ebda4`; all application,
configuration, tests and locks in publication remain identical to that baseline. All 28 held paths
retain exact bytes/deletion state. Initial link review: 134 local links/anchors, 591 source paths.
Legacy benchmark numbers remain historical, not current proof. Synthetic/local passes do not
satisfy the selected-provider live-read exit.

Commands used through RTK: root `uv lock --check`; isolated `uv sync --locked --link-mode copy`;
Ruff format/check, `python -m mypy src`, full strict `python -m pytest` with new ignored runtime
basetemp directories, `python -m pip_audit --strict`, Garmin lock/sync/audit; Node lifecycle/PCM,
desktop/prototype accessibility; `phase-i-email-benchmark.py --enforce` and
`phase-i-email-smoke.py`; Gitleaks history/exact-source/staged scans, local link/anchor checks and
`git diff --check`. Locked isolated execution uses `uv run --locked`; working checks use the
unchanged locked `.venv` with optional packages preserved.

## Known limits, recovery and deferred scope

Existing functionality remains explicit local `.eml` exports and trusted-local preparation only.
Disable `JARVIS_EMAIL_ENABLED`, remove selection and restart to stop local acquisition. Export
sources are never modified. Delete private derived replies using existing conversation lifecycle;
SQL deletion does not securely erase WAL, backups or storage. Preserve migration 016 on rollback.
No full email, provider, physical or production acceptance claimed.

## Publication and handoff

Initiation publication contains five documentation paths only: email contract, provider decision,
current progress, master ledger and overview. All 28 held paths retain exact bytes/deletion state;
the original 97 package versions remain unchanged. No provider/native/application/configuration/
test/lock/private/runtime artifact is included. Exact staged/publication tree agreement and
HEAD/tracking/live-remote equality are checked on publication; fresh exact-commit CI is checked
separately afterward and recorded in the final handoff. These gates validate this initiation
checkpoint, not a live email adapter or phase completion.
Progress remains **14/19 primary receipts closed (~74%)**, unweighted management count, not
code/effort or mobile MVP acceptance. Next current work: **Continue Phase 15 — Email** after
provider/account selection; Phase 16 has not started.
