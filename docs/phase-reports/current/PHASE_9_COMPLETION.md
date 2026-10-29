# Phase 9 — Files and attachments

- Status: `complete`
- Started / updated: 2026-10-28 / 2026-10-28
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: `gpt-6-astra` / `xhigh`; `ultra` for authority
  (recommendation only; no UI model change claimed)
- Session start / five-hour stop: 2026-10-28T19:48:00-04:00 / 2026-10-29T00:48:00-04:00

## Objective and scope

Reliable supplied-content workflows in the existing Windows Core/PWA. Explicit `private-files`
profile extends daily local text with existing attachments, bounded processing, source references,
preview, search and same-conversation reuse. Actual prerequisite: completed Phase 7. Reuse legacy
G/F14/F15 contracts; no second Core, store, router or client. Text/PDF extraction and image
normalization are distinct from optional local image understanding. No arbitrary filesystem tool,
cloud upload, automatic memory promotion, OCR, model download, new scope/enrollment or deployment.

## Baseline and preservation

- `main` at `a1f64a5`; 28 held paths captured with exact bytes/deletion hashes under ignored
  `runtime/phase9/baseline/`, alongside host-interpreter package versions before sync. Root locked
  environment restoration is verified separately; host interpreter inventory is not its inventory.
- Held native manifests and provider changes excluded from publication. Shared source/docs require
  task-only three-way merges and held-hunk recomposition proof. Preserve accepted `prototype-text`
  prompts, launcher and corpus, daily/Garmin profiles and historical evidence.
- Read full execution protocol/master roadmap, current architecture decision, all three Phase 9
  references, security/authority rules, Phase 8 and legacy G receipts. Existing attachment parser,
  staging/private routing/provenance and PWA lifecycle provide the implementation foundation.
- Installed uv 0.12.15, Node 24.20.0, Gitleaks 8.30.1. Installed local models include qwen3:1.7b
  and qwen3.5:0.8b; installation alone does not qualify vision. No dependency upgrade planned.

## Acceptance checklist

Frozen before implementation and live measurement:

- [x] Explicit local-only `private-files` profile and launcher: only clock plus deliberate supplied
  attachments; other optional integrations disabled. Existing profiles retain behavior. Capability
  presentation distinguishes text/PDF, image normalization and configured local vision.
- [x] Actual authenticated PWA/Core/SQLite/Ollama workflow using only disposable synthetic files:
  text and PDF answers contain exact synthetic facts and selected attachment/chunk references;
  deliberate same-conversation reuse, source metadata, literal search and restart recovery pass.
  Three frozen facts: text `cedar inventory has 17 lanterns`, PDF `harbor shipment has 23 crates`,
  follow-up reuse asks original lantern count. Require all three grounded answers, no invented
  source, no cloud/research/tool effect or automatic memory candidate.
- [x] Image upload/normalization with absent vision yields explicit `vision_unavailable`; optional
  installed loopback adapter must pass capability check and synthetic red-image oracle before any
  qualified claim. No remote model/profile, download, fallback or inferred OCR. Existing 60 s/image
  deadline retained; cold failure recorded honestly, unsupported path may satisfy product scope.
- [x] Preserve four combined files, 1 MiB/PWA file, 600 s staging, existing storage/count/retention,
  10 s parser and 30 s service deadlines, 8,000-character projection and original G benchmark:
  100/100 expected-chunk retrieval, retrieval p95 <=100 ms, 20 parses p95 <=2,000 ms.
- [x] Failure/security matrix: invalid text/PDF/image/type/size, parser timeout/output flood/cancel,
  quota/expiry/delete, restart/interruption, duplicate/replay, stale client/server result, forged
  auth/origin/scope/ownership and cross-conversation/device denial. Source bytes remain untrusted;
  zero private disclosure, tool authority or automatic memory promotion; sticky privacy survives
  deletion/restart. Staging/selecting alone invokes no parser/model.
- [x] Current setup/capability/privacy/retention/deletion/recovery docs and official primary
  dependency/OS/provider documentation checked. Physical phone checks **skipped by owner; unverified**.
- [x] Full protocol gates: locks/sync, format/lint/types, pytest >=85%, base/restored-extra/sidecar
  audits, PWA/PCM and desktop standard/prototype/daily/Garmin/files, secret/whitespace/link checks,
  exact isolated publication-source gates, held/baseline preservation, safe commit/push and fresh CI.

## Milestone log

- Baseline snapshot and reference review complete. Profile currently disables attachments in all
  accepted local text profiles; standard foundation exposes files but also unrelated capabilities.
  Add explicit bounded product profile without globally enabling optional features.
- Implemented profile/launcher, scoped capability presentation, text/PDF/image controls and bounded
  pipe drain before parser reap. Focused profile/parser/API gate 62 passed; existing attachment/
  workspace matrix 54 passed. Files desktop fixture 14 passed; standard desktop 72 passed.
- First two live harness attempts failed before generation: synthetic enrollment omitted existing
  `client.tasks.read` requested by PWA bootstrap. Corrected fixture scope only; no production grant.
  Third run produced all three exact facts/citations and honest `vision_unavailable`, then exposed
  a harness expectation error: unavailable staging returns an HTTP 200 **failed receipt**, rather
  than HTTP 409/422. Enforce exact failed status/error and zero generation. No product gate lowered.
- Current G benchmark: 100/100 expected hits, projection max 6,655 chars, retrieval p50/p95
  2.766/3.236 ms; 20 isolated parses p50/p95 114.870/121.119 ms. Restart/delete pass; no cloud,
  research, tool effects or cost. Root restored-extra and sidecar strict audits report zero known
  vulnerabilities. Root extras restored after base sync; compare against prior root receipt and lock.
- Complete working gate: 1,614 passed / 3 existing skips, 86.03% coverage, 157.76 s. Expanded
  existing PWA workflow/workspace API matrix now runs both standard and private-files: 42 passed.
  PWA lifecycle/PCM: 159 + 7 passed. Desktop standard/prototype/daily/Garmin/files: 72/9/9/13/14.
- Successful real PWA/Core run: all three frozen exact facts and owned chunk references pass;
  fourth reply is `vision_unavailable`, no invented image contents. Four local generation calls;
  reuse selection/staging/replay invoke no extra generation. Restart preserves three ready sources;
  obsolete staging returns exact failed `upload_unavailable` receipt without provider invocation.
  Literal private search, cancel receipt, logout erasure, shell-only cache/private browser-state
  exclusions and foreign-device file denial pass. SQLite: zero memory items/candidates, zero running
  requests, sticky private conversation retained. Evidence stays ignored under runtime/phase9/.
- Publication export contains 25 reviewed task paths with five shared three-way merges; all 28
  held paths preserved. Original prompt constants/launchers/corpora and both dependency locks
  unchanged. Exported native manifests equal baseline HEAD. 225 local links/anchors pass in both
  source variants. Full-history scan: 134 commits, no leaks; exact 559-file source scan clean.
- Exact `open-files.cmd doctor` passes with a new empty synthetic store, no owner configuration,
  credentials or route. Locked extras retained for this check via `UV_NO_SYNC=1`; no OS policy
  bypass. Root installed set is 97 packages, same names as prior Phase 8 root snapshot; only its
  already-published msgpack 1.2.1 -> 1.2.3 repair differs. No Phase 9 lock/package change.

## Decisions, authority and blockers

Existing authority covers repository work, synthetic local services/files/models and normal safe
source publication. No owner-store reads needed. Production scopes/enrollment/settings stay owned
by existing controls. No external blocker established. Native/provider publication holds remain.

## Verification and measurements

Current gates below retain unchanged thresholds; legacy G/F14/F15 evidence remains historical.
Core Python 3.11.9, bridge Python 3.12.14; uv 0.12.15; Node 24.20.0; Gitleaks 8.30.1.
Locked Pillow 13.0.0, pypdf 6.21.2, httpx 0.28.1, cryptography 50.0.1, FastAPI 0.141.1.
No dependency/lock upgrade. All current official reference links are in PRIVATE_FILES.md.

| Gate | Working checkout | Isolated publication source |
| --- | --- | --- |
| Root lock / locked copy sync | Pass | Pass; official PSF Python 3.11.9 |
| Strict Python audit | Restored 97-package extras: zero vulnerabilities | Base and restored extras: zero vulnerabilities |
| Sidecar lock / locked copy sync / strict audit | Pass; no health read | Pass; identical locked dependencies |
| Ruff format/lint / Mypy | Pass; 169 typed source files | Pass; 169 typed source files |
| Complete serial pytest; 85% floor | 1,614 passed / 3 skips; 86.03%; 157.76 s | 1,615 passed / 3 skips; 85.98%; 153.48 s |
| PWA lifecycle / PCM | 159 / 7 pass | 159 / 7 pass |
| Standard / prototype / daily / Garmin / files desktop | 72 / 9 / 9 / 13 / 14 pass | Same counts pass |
| Live synthetic PWA/Core/local model | Three grounded answers; unavailable image; full recovery matrix pass | Same frozen facts/citations and complete matrix pass; four local calls |
| Local links/anchors | 225 pass | 225 pass |
| Secret scan / whitespace | 134-commit history clean; diff clean | 559-file source clean |

Extra isolated test and coverage denominator come from preserved original provider code/tests,
excluded held provider removal. Three existing platform/capability skips and Starlette TestClient
deprecation warning remain; no skipped phone check is counted as a test pass. Forced synthetic
TLS Core crash can emit Windows connection-reset callbacks; restart recovery is independently
asserted. No production deadline, security gate, test criterion or OS policy weakened.

Final isolated benchmark: 100/100 expected-chunk hits, max projection 6,655 chars; retrieval
p50/p95 2.321/2.632 ms and 20 isolated parses p50/p95 97.922/106.951 ms. Restart/delete pass;
cloud/research/tool effects/cost all zero. Optional configured vision was not requested or qualified;
default image normalization/unavailable interpretation is the accepted capability behavior.

## Known limits, recovery and deferred scope

Process isolation is not an AppContainer/network/filesystem sandbox. Logical SQLite payload quotas
do not bound DB/WAL/backups; deleting attachments does not erase earlier replies/backups. OCR,
Office/archive/audio, arbitrary host paths, automatic research/memory and physical/native acceptance
excluded. Phone checks **skipped by owner; unverified**.

## Publication and handoff

Reviewed implementation published as `5170d0194f1a935a5d3501660b728c3671fae25f`, tree
`11daf9edc691226d2f9803a4e773a0b11c9e8f52`, exactly matching isolated tested source.
HEAD, tracking `origin/main` and live upstream matched after push.
[Fresh CI 40792578005](https://github.com/DanCreates1/JARVIS/actions/runs/40792578005)
passes Windows quality job `123181138615` and secret job `123181138947` at that exact SHA.
Post-publication scan: 135 commits, no leaks. All 28 held paths remain dirty as intended;
five shared held hunks recompose exactly and other held hashes/deletion state remain identical.
Index clean. Native manifests, held provider edits and original prototype baseline preserved.

This closure changes documentation only. All 399 application/test/script blobs remain identical
to the accepted implementation; locks remain unchanged. Closing commit/tracking/live remote,
held-state preservation and its own fresh CI are verified separately after publication and
reported in the closing reply; implementation CI is not substituted for a later commit.
No deployment, signing, production scope/enrollment, health read, credential change, cloud upload,
new model, paid service or phone request occurred. No next-phase implementation started.

Progress: **9/19 primary receipts closed (~47%)**, unweighted management count, not code/effort
or mobile MVP acceptance. Next current phase: **Phase 10 — Inspectable memory and project context**;
actual prerequisite Phase 7 is complete. Handoff grants no automatic execution or new authority.
