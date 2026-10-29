# Phase 10 — Inspectable memory and project context

- Status: `implemented-closeout-pending`
- Started / updated: 2026-10-28 / 2026-10-28
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: `gpt-6-astra` / `xhigh`, `ultra` for authority
  (recommendation only; no UI model change claimed)
- Session start / five-hour stop: 2026-10-28T20:27:00-04:00 / 2026-10-29T01:27:00-04:00

## Objective and scope

Owner inspection, exact approval, correction, rejection, retention and forgetting in existing Core.
Reuse canonical memory/FTS5/provenance/conflicts and private coding continuity. Phase 7 prerequisite
is complete. Add a trusted-local review workspace linked from PWA, not remote mutation authority.
Explicit private-memory profile extends daily local text; repository context still requires an
explicit configured root and CLI repo: request. No vectors, repository execution, cloud disclosure,
new scopes, enrollment, credentials, health reads, native publication or automatic trust.

## Baseline and preservation

- main at e904cc2. All 28 held paths copied and hashed under ignored runtime/phase10/baseline/;
  installed root packages captured before sync. Shared files need task-only publication merges.
- Read execution protocol, full master, current architecture, legacy memory receipt,
  TOKEN_CONTINUITY.md and architecture memory boundary. Preserve prototype-text prompt, launcher,
  corpus, existing profiles, held native manifests and provider changes.
- uv 0.12.15, Node 24.20.0, Gitleaks 8.30.1. No dependency upgrade planned.

## Acceptance checklist

Frozen before implementation/tuning/current measurements:

- [x] Owner workspace displays state, provenance/trust, confidence, expiry, correction lineage,
  conflicts and retrieval reasons. Candidate promotion binds exact ID/version/digest; stale/replay,
  wrong owner and client-supplied trust fail closed. Explicit correction/rejection/forget/retention.
- [x] Local peer plus literal Host/Origin, no forwarded/authenticated remote identity on every
  workspace/control route. No remote memory scope inferred from chat/read scopes. No private data
  in browser persistence/cache/URLs, diagnostics or cloud. Navigation alone grants no trust.
- [x] Existing frozen 20-record/25-query retrieval set: precision/recall/accepted hit >=0.90,
  false recall <=0.05, zero cross-host hits, warm p95 <=50 ms over 500 queries/2500 records,
  storage <=16384 bytes/record, 100 concurrent operations with zero failures, deletion 1.0.
- [x] Candidate/rejected/corrected/expired excluded from prompt; max 8 items/4000 chars.
  Correction/retention/restart, source and sole-source transitive deletion checked in SQLite.
- [x] Coding continuity frozen 100 synthetic snapshots/60 files: zero privacy/oracle failures,
  <=8000 chars and cold/warm p95 <=1000 ms. Explicit root/CLI-only private context, timeout,
  cancellation, hostile Git settings, stale checkpoint/restart/clear tests retained.
- [x] Frozen live fact: quarantined amber orchard count 91; approve exact candidate, correct to
  29, then require local model answer 29 with approved source present and stale 91 absent from
  projected memory. No cloud calls or tools.
- [x] Actual synthetic local browser/Core lifecycle, source-explained retrieval and approved
  context generation; no owner store. Unavailable/error/cancel/restart and private erasure tested.
- [x] Full working and isolated publication gates, >=85% coverage, preserved extras, both locked
  audits, PWA/desktop regression profiles, secret/whitespace checks.
- [ ] Safe commit/push and fresh exact CI.
- [x] Current setup/recovery/limits docs; phone checks **skipped by owner; unverified**.

## Milestone log

- Baseline inspected and frozen. Existing canonical store and CLI cover lifecycle; PWA has no
  authorized memory-control scope. Trusted local interface is existing confirmation boundary.
- Implemented explicit private-memory profile/launcher, local peer/Host/Origin admission for all
  memory routes, no-cookie data/control calls, bounded preview pagination, exact review lifecycle,
  POST retrieval explanation, retention and private view erasure. Static page/script navigation may
  carry cookies but never private data. No scope/enrollment or remote approval added.
- Fixed canonical derived-memory privacy: private source sensitivity cannot become public; direct
  expired sources cannot derive. Recursive invalid-ancestor filtering excludes stale rollups after
  correction/expiry/restart, without silently approving a recomputation. Existing final-source
  deletion semantics and separately inspectable correction history remain explicit.
- New lifecycle/security matrix: 11 passed; profile matrix 22 passed; existing PWA API profiles now
  include private-memory. PWA/PCM 161 + 7 passed. Desktop standard/prototype/daily/Garmin/files/memory
  72/9/9/13/14/9 pass. First regression run exposed old shell-v17 assertions; updated for v18 and
  corrected test-only DOM/keyboard assumptions. No production criterion weakened.
- Working complete gate: 1,631 passed / 3 existing skips, 86.09% coverage, 170.01 s. Format/lint/types,
  root base/sidecar strict audits, full-history secret scan and whitespace pass. Root 97-package
  optional environment restored to the same package names/versions as baseline; strict audit clean.
- Initial isolated pytest used an absent nested basetemp parent, causing WinError 3 setup errors.
  A fresh verified path under the existing ignored runtime parent passes focused checks; full rerun
  passed (1632 tests). This is fixture preparation, not an application skip or accepted failure.
- Publication export: 26 safe task paths, five shared-file three-way merges, all 28 held paths
  preserved. Prototype prompt constants/launchers/corpora and both locks unchanged; exported native
  manifests equal baseline HEAD. 228 local links/anchors and exact 568-file source secret scan pass.
- Real working browser/Core/Ollama lifecycle passes initial frozen fact: candidate quarantine,
  approval, 91-to-29 correction, exact retrieval reasons and approved prompt context, one local
  generation answering 29, inert hostile content, no browser persistence, restart/forget and zero
  canonical/FTS/provenance rows after restart. Extended abort/stale-response acceptance passes.
- Isolated live harness exposed nondeterministic fixture selection: correction timestamps match
  old/new rows and UUID ordering does not imply newest semantic version. Select committed 29 item
  explicitly; never infer lifecycle from first list row. Product chronology/approval unchanged.

## Decisions, authority and blockers

Existing repository/local synthetic test/publication authority applies. No external blocker.
Remote memory approval would require a new security boundary; unnecessary for laptop-first owner
workflow. Keep existing trusted local confirmation and deny proxy/cookie/bearer requests.

## Verification and measurements

Current working and isolated publication evidence, all thresholds unchanged. Evidence stays ignored
under runtime/phase10/. No historical measurement relabeled current. Python 3.11.9, SQLite 3.45.1,
uv 0.12.15, Node 24.20.0, Gitleaks 8.30.1. No lock/dependency upgrade.

| Gate | Working source | Isolated publication source |
| --- | --- | --- |
| Full serial pytest; 85% floor | 1631 passed / 3 skipped; 86.09%; 170.01 s | 1632 passed / 3 skipped; 86.05%; 167.06 s |
| Format/lint / Mypy | Pass; 170 source files | Pass; 170 source files |
| Root lock/copy sync/base/restored-extra audit | Pass; restored exact 97-package inventory | Pass; base and restored extras clean |
| Sidecar lock/copy sync/strict audit | Pass, no health reads | Pass, no health reads |
| PWA lifecycle / PCM | 161 / 7 pass | 161 / 7 pass |
| Desktop standard/prototype/daily/Garmin/files/memory | 72/9/9/13/14/9 pass | Same counts pass |
| Real browser/Core/local model | 7 check groups; grounded 29; one local call | Same frozen fact and seven groups pass |
| Frozen retrieval precision / recall / accepted hit | 0.90909 / 1.0 / 1.0 | Same |
| False recall / cross-host hits / concurrency failures | 0 / 0 / 0 across 100 operations | Same |
| Warm FTS, 500 queries / 2500 records; p50 / p95 | 2.283 / 41.226 ms | 2.100 / 38.526 ms |
| Cold/restart retrieval, 20 samples; p50 / p95 | 57.050 / 103.033 ms | 47.076 / 86.323 ms |
| Storage / deletion | 2388.787 bytes/record; completeness 1.0 | Same; zero content rows after tested deletion |
| Coding 100 snapshots; cold / warm p95 | 381.991 / 368.859 ms | 402.722 / 365.677 ms |
| Coding projection / oracle/privacy failures | 2375 chars / 0 | Same; zero network/provider/cost |
| Local links / secrets / whitespace | 230 links; 136-commit history clean; diff clean | 230 links; 568-file exact source clean |

Three pre-existing platform/capability skips and upstream Starlette TestClient deprecation warning
remain. Owner-skipped phone checks are not test passes. Cold retrieval is reported separately;
unchanged memory benchmark gates warm p95 <=50 ms, not an invented cold threshold. FTS5 still meets
the frozen oracle, so no vector model/service is justified.

Both final real-browser runs additionally pass ignored-abort late response rejection, private view
erasure, exact correction selection, full forget/restart, inert hostile content, cache/storage/URL
exclusion, named form controls/keyboard order, high-contrast links and 200% font reflow at 320/1280px.
Actual launcher doctor passes with an empty synthetic store and no owner config/credentials.
Explicit private-memory CLI context/checkpoint/clear passes on a synthetic configured Git root;
checkpoint contains no source name, code, symbol or absolute root, then is removed by exact clear.

Initial isolated basetemp lacked its parent (WinError 3); fresh existing-parent basetemp repaired
all setup errors. Both root and isolated full suites pass. Initial live UUID-order fixture bug was
repaired by selecting exact committed content; both final live runs pass. No gate was waived.

## Known limits, recovery and deferred scope

Logical deletion does not erase transcripts, SQLite free pages/WAL or prior backups. Retention
expiry excludes recall; physical forgetting remains explicit. No physical/mobile acceptance claim.

## Publication and handoff

- Held paths preserved; prototype baseline unchanged. Publication source reviewed; exact-source
  quality, audits, benchmarks, live/browser and recovery gates pass. Commit/push/fresh CI pending.
- Progress: 9/19 primary receipts closed (~47%), unweighted management count.
- Next current work remains Phase 10 until acceptance closes; Phase 11 not started.
