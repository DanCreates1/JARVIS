# Phase 11 — Grounded public research

- Status: `complete`
- Started / updated: 2026-10-28 / 2026-10-31
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: `gpt-6-astra` / `xhigh`; `ultra` for authority
  (recommendation only; no UI model change claimed)
- Session start / five-hour stop: 2026-10-28T21:23:36-04:00 / 2026-10-29T02:23:36-04:00
- Resume checkpoint / five-hour stop: 2026-10-31T10:59:29-04:00 / 2026-10-31T15:59:29-04:00

## Objective and scope

Explicit public-research capability on existing laptop Core/PWA. Reuse freshness routing,
bounded acquisition, isolated parser, exact-span citation validation and volatile workflow.
Add user-supplied public HTTPS source URLs through the existing search port; retain configured
Wikimedia/SearXNG discovery. No account, credential, cloud model, paid source, background refresh,
new scope, owner-store read, automatic research-ledger storage or trusted-memory promotion.
Phase 7 prerequisite complete. No later phase starts.

## Baseline and preservation

- main `30296636abc1964856cebb7174b612041df6a068`, Phase 10 closed.
- 28 held paths copied/hashed under ignored `runtime/phase11/baseline/`, including deleted Groq
  adapter, native manifests and shared provider/docs changes. Task-only publication required.
- Installed package inventory saved before sync. Original prototype prompts/profile/launcher,
  frozen corpora, locks and historical failed latency evidence remain unchanged.
- Required execution/master/architecture and Legacy Phase 5/B/C receipts read. Historical
  Wikimedia `authentication_required` confirmed again using the same endpoint and production
  pinned fetcher on 2026-10-28. No usable discovery results; blocker remains.
- Same fetcher currently retrieves official Python downloads, Python 3.14 changes and SQLite
  changes pages. This is direct acquisition evidence, not Wikimedia search acceptance.

## Acceptance checklist

Frozen before implementation/tuning/current acceptance measurements:

- [x] Explicit `public-research` profile extends daily local text; all other optional integrations
  remain disabled. Public HTTPS URLs only; remote discovery receives only current public query.
  Credentials/private query components/ambiguous text denied before any network call.
- [x] Selected profile returns validated extractive evidence through canonical receipts, with nearby
  source URLs, retrieval time, unknown publication dates, freshness and uncertainty. No second model
  rewrite can introduce uncited current claims. Fetch failure returns deterministic unavailable.
- [x] Existing frozen Legacy Phase 5 three-topic/three-domain 30-run benchmark: citation coverage,
  fixture entailment, diversity, freshness, conflicts, injection resistance, reproducibility all
  1.0; zero failures; p95 <=2000 ms. Legacy C 100 cases: zero route/privacy/persistence/authority
  violations; projection p95 <5 ms. Legacy B 10000 decisions: zero errors; p95 <1 ms.
- [x] New fixed adversarial matrix: explicit URL dedup/bounds/invalid/private/credentials/domain,
  SSRF/DNS/redirect protections, fabricated answer/quote links, stale/future/inactive evidence,
  unsupported general discovery, conflict preservation, same-publisher insufficient corroboration,
  timeout/cancel/malformed/offline, wrong owner, storage approval/replay/restart/deletion.
- [x] Current bounded real public-source run through actual Core/PWA returns exact source wording
  and clickable citations; at least two official publishers across selected evidence fixtures.
  Browser content stays inert; no automatic source/memory persistence, cloud/tool call, login or
  disclosure of prior conversation. Repeated request/restart obtains fresh evidence or unavailable.
- [x] Full working/isolated release gates, >=85% coverage, locked root/sidecar audits, preserved
  optional environment, PWA/desktop regressions including prototype-text, source/history secret
  scans, whitespace, links and reviewed task-only commit/push with fresh exact CI.
- [x] Setup/recovery/limits documented. Phone checks **skipped by owner; unverified**.

## Milestone log

- Baseline and live availability probe complete. Wikimedia search remains blocked; direct official
  source acquisition works. SearXNG remains optional and needs an explicitly reviewed JSON endpoint.
  No endpoint substitution, authentication workaround or fabricated discovery acceptance.
- Implemented explicit public-research profile/launcher on existing Core/PWA. Privacy-wrapped
  explicit-source selector uses no discovery for deliberate URLs, denies query parameters and
  unsafe syntax, deduplicates and caps candidates at four. Original profiles remain unchanged.
- Added typed grounded projection: canonical receipts settle validated source excerpts without
  another model pass. Research failures now settle deterministic unavailable for every profile.
  Current clock, active state, owner and future/expired timestamps are checked before projection;
  same-site subdomains do not supply independent corroboration. Publication time stays unknown
  when absent. Final conversations retain request/reply; research ledger stays volatile/unwritten.
- Fixed exact extraction whitespace/version-number handling, excluded source-authored links/markers
  from fallback selection, and preserved HTML block boundaries in the isolated worker. Browser
  handles literal Markdown escapes without manufacturing source-authored links or HTML controls.
- Source revalidation and exact storage now compare extracted text as well as raw-byte digest.
  Parser output changes version immutable source text, stale old claims and preserve locators after
  restart; approved reports never attach new spans to an old extraction with the same raw digest.
- Current focused new/core evidence passes. Existing 30-run frozen benchmark: all seven quality
  metrics 1.0, zero failures, p50 307.644 ms / p95 334.7811 ms (unchanged 2000 ms ceiling).
  Legacy C: 100/100, 40 volatile calls, zero privacy/storage/authority failures; projection p95
  0.1055 ms (<5 ms). Legacy B: 10000/10000, zero errors; p95 0.0214 ms (<1 ms).
- Real desktop browser/auth/Core/public-source run passes two live acquisitions, exact quotes,
  linked official Python/SQLite sources, freshness/unknown publication, immutable replay without
  refetch, fresh acquisition after restart, unavailable Wikimedia discovery, inert hostile syntax,
  browser storage/cache exclusion and logout erasure. Zero models/tools, research sources/reports
  or memory rows. Evidence: ignored runtime/phase11/acceptance-5air45ub/.
- Initial live probes exposed source sentences containing URLs; strict citation validation correctly
  rejected them. Extractive selection now skips those spans. Initial replay harness used the new
  conversation ID rather than original null; Core correctly denied changed payload. Harness now
  replays exact payload. Browser harness exposure/string escaping repaired; no product gate waived.
- Full working suite initially passes 1654 tests / 3 existing skips, 86.06% coverage, 161.41 s.
  Current-span end-bound defense received focused verification afterward; the later final
  source/profile and isolated publication reruns below close that checkpoint. Root base/restored-extra and sidecar strict
  audits pass. Exact 97-package starting optional environment restored; no lock change.
- Final relevance repair excludes URL path tokens and contextless above/below references from
  lexical selection. Regression fixture frozen before that repair. Final real answer excerpts
  Python's macOS installer certificate statement and SQLite's Windows Vista minimum statement,
  each exactly acquired, source-linked, dated at retrieval and explicitly not independently verified.
- Real desktop profile matrix caught missing public-research CSS: dormant controls were visible.
  Added profile rules and accurate capability text; all seven profiles now pass in both sources.
- Final working full gate: 1659 passed / 3 existing skips, 86.13%, 160.45 s. Isolated final gate:
  1660 passed / 3 existing skips, 86.08%, 152.91 s. One additional isolated test is the held Groq
  contract restored from published HEAD; its removal remains excluded from this publication.
- Initial isolated pytest started before its runtime basetemp parent existed; setup errors were
  stopped, parent explicitly created/verified ignored, then complete gate rerun at a fresh path.
  A nested PowerShell process query also expanded $_ too early; corrected quoting identified and
  stopped only this test's two Python processes. No OS policy, application gate or test waived.
- Final working live evidence: runtime/phase11/acceptance-w52tqm1z/; isolated:
  runtime/phase11/publication-final/runtime/phase11/acceptance-kg7obz87/. Both pass two acquisitions,
  immutable replay, actual blocked discovery, restart freshness, exact source spans and browser
  erasure. No model call, action, research-source/report row or memory row. Canonical history remains.
- 2026-10-31 closeout resumed at published implementation `55231bf`. Exact implementation
  [CI run 40803928842](https://github.com/DanCreates1/JARVIS/actions/runs/40803928842) passed Windows
  quality job `123218238731` and secret job `123218238431`. Local HEAD, tracking and live upstream
  agree. All 28 held paths revalidated, including five shared-file recompositions.
- Fresh same-endpoint Wikimedia probe still returns `authentication_required`; direct official
  Python/SQLite fetches work. Historical discovery blocker stays open. Fresh working browser/Core
  acceptance passes at runtime/phase11/acceptance-93ofa7u9/ with two live runs and zero model calls.
- Fresh root audit found seven newly reported pypdf 6.21.2 advisories,
  `CVE-2026-119203` through `CVE-2026-119209`. Checked the official
  [6.21.4 security release](https://github.com/py-pdf/pypdf/releases/tag/6.21.4), raised the minimum
  to 6.21.4 and updated only pypdf in the root lock. No ignore, security waiver or provider/native
  change. Base and restored-extra audits now clean; sidecar audit remains clean.
- Optional environment retains all 97 starting package names; only pypdf changes 6.21.2 to 6.21.4.
  Corrected a focused-check command naming an absent test file; actual research/PDF/web set passes
  45 tests. Full working/isolated gates and fresh patch CI pass before closure.
- Patched full gates: working 1659 passed / 3 skipped, 86.09%, 213.51 s; isolated 1660 passed /
  3 skipped, 86.05%, 201.66 s. Fresh frozen 30-run research quality metrics all 1.0, zero failures;
  working p95 328.1023 ms and isolated p95 338.6911 ms (<2000 ms). All seven desktop profiles and
  171 PWA/PCM checks pass in both sources; format/lint/types, root base/restored-extra and sidecar
  strict audits, links, exact-source/history secrets and whitespace pass. All 28 resumed held paths
  retain exact hashes/deletion state. No application/test source change in this repair.
- Fresh isolated browser/Core live acceptance passes at
  runtime/phase11/resume-20261031/publication/runtime/phase11/acceptance-s1o0tr6s/.
  Working and isolated runs each obtain two fresh, exact cited public-source results, verify
  replay/restart/erasure and retain zero model calls or research-source/report/memory rows.

## Decisions, authority and blockers

Use explicit source URLs as bounded user-directed acquisition, not a new crawler or provider.
Existing saved query-only privacy gate remains; no history is sent to search. Keep local inference
for ordinary chat and validated extractive research for current evidence. Research sources remain
untrusted and cannot authorize actions, storage or trusted memory.

Historical Wikimedia endpoint blocker remains `authentication_required`; it need not prevent
independent direct-source acceptance. General discovery usefulness remains separately limited.
No NVIDIA requalification or provider replacement requested; legacy latency debt stays unchanged.

## Verification and measurements

Raw outputs/runtime artifacts stay ignored under `runtime/phase11/`. No real owner-store read,
cloud request, new account, login, paid service, production enrollment/scope or device check.
Live acceptance demonstrates exact acquired source statements, not general answer quality or
publisher independence. The fixed entailment oracle measures fixture-supported source-span
agreement, not probabilistic NLI or an independent truth score. Lexical extraction remains limited.

2026-10-28 implementation gates (CPython 3.11.9, uv 0.12.15, Node 24.20.0, Gitleaks 8.30.1;
no lock upgrade in that session; the 2026-10-31 security patch is recorded separately above):

| Gate | Working source | Isolated publication source |
| --- | --- | --- |
| Full pytest / 85% floor | 1659 passed / 3 skipped; 86.13%; 160.45 s | 1660 passed / 3 skipped; 86.08%; 152.91 s |
| Format / lint / Mypy | Pass; 171 source files | Pass; 171 source files |
| Root base / restored-extra strict audit | Pass; exact original 97-package inventory | Pass; same package names/versions |
| Root / sidecar locked sync and strict sidecar audit | Pass; no health reads | Pass; CPython 3.12.14 bridge |
| PWA lifecycle / PCM | 164 / 7 pass | Same |
| Desktop standard/prototype/daily/Garmin/files/memory/research | 72/9/9/13/14/9/9 pass | Same |
| Real browser/Core/public-source acceptance | 4 groups, 2 live runs, 0 model calls | Same |
| Frozen 30-run research, all seven quality metrics | 1.0 each, 0 failures | Same |
| Research p50 / p95; unchanged 2000 ms gate | 305.1273 / 336.0701 ms | 305.5626 / 327.4280 ms |
| Legacy C 100 cases; projection p95 <5 ms | Pass; 0.1055 ms | Pass; 0.0564 ms |
| Legacy B 10000 decisions; p95 <1 ms | Pass; 0.0214 ms | Pass; 0.0177 ms |
| Isolated synthetic doctor | Pass; empty state, installed local model | Pass; same |
| Local links / exact-source secret scan | 224 links in 7 task docs; history clean | 575 source files; clean |

Three existing platform/capability skips and upstream Starlette TestClient deprecation remain.
No physical acceptance or legacy latency closure follows from these current automated gates.

2026-10-31 security-patch gates supersede the earlier dependency audit for current publication:

| Gate | Working source | Isolated publication source |
| --- | --- | --- |
| Full pytest / 85% floor | 1659 passed / 3 skipped; 86.09%; 213.51 s | 1660 passed / 3 skipped; 86.05%; 201.66 s |
| pypdf / other starting packages | 6.21.4; other 96 names/versions unchanged | Same versions |
| Root base/restored-extra / sidecar strict audits | Clean / clean / clean | Clean / clean / clean |
| Format / lint / Mypy | Pass | Pass |
| PWA/PCM / seven desktop profiles | 171 pass / all pass | Same |
| Current real public-source browser/Core | 4 groups / 2 runs / 0 model calls | Same |
| Frozen 30-run quality metrics / failures | All seven 1.0 / 0 | Same |
| Research p50 / p95, <2000 ms | 309.0671 / 328.1023 ms | 309.2597 / 338.6911 ms |
| Links / exact source / full history secrets / whitespace | Pass | Pass |

Raw closeout evidence is ignored under runtime/phase11/resume-20261031/; the prior implementation
receipts remain dated historical measurements rather than being relabeled as new runs.

## Known limits, recovery and deferred scope

No authenticated/paywalled/JavaScript-rendered sources, crawling, background refresh or automatic
storage. Process parser isolation is not an OS sandbox. Extractive evidence does not establish
independent truth or consensus. Historical reports remain historical. Physical/native/MVP/
production acceptance unestablished.

## Publication and handoff

Original implementation published as `55231bf728c3dae16ac3fb88d16e24dc68d3d29b`, reviewed tree
`d8f25f3c011813bd50adb9af9d82eb556dd32871`. Reviewed 34 task paths, five shared-file three-way
merges; recomposition preserves held edits. The implementation's exact
[CI 40803928842](https://github.com/DanCreates1/JARVIS/actions/runs/40803928842) passed Windows
quality `123218238731` and secrets `123218238431`.

Security repair published as `eb7c4368420edf3e5c0965df0a44874d7dd01dc2`, reviewed tree
`1f4e17fd0325fe7b6132d0da3ebddd4371e1bccc`. Exactly three paths: root package minimum/lock and
this phase report. No application, test, native or provider source change. Current
[patch CI 41213724518](https://github.com/DanCreates1/JARVIS/actions/runs/41213724518) passed
Windows quality `124573808257` and secrets `124573808377` at that exact SHA. Root HEAD, tracking
origin/main and live upstream agreed after publication. Fresh 2026-10-31 source/citation/browser,
working/isolated, security, audit and recovery evidence above closes selected Phase 11 scope.

All 28 resumed held paths retain exact bytes/deletion state. Native manifests, original prototype
prompts/launchers/corpora, response policy, sidecar lock and every unrelated package version remain
unchanged. The root lock deliberately updates only pypdf 6.21.2 to 6.21.4 for the failed current
security gate; preserving historical acceptance does not require retaining a vulnerable dependency.
No credential, owner runtime store, private data, generated artifact or unsafe held path published.

This closing change only renames/updates the receipt, current ledger/overview and capability docs.
Application/test/script/dependency blobs remain identical to the passing security-repair commit.
Closing commit/tracking/live remote, held-state proof and its own fresh CI are verified separately
after publication and reported in the closing reply; earlier CI is not substituted for a later SHA.

Wikimedia `authentication_required` remains a recorded, freshly reconfirmed discovery limitation.
No alternate endpoint, login/paywall bypass, paid source, optional cloud qualification, production
scope/enrollment, signing/deployment, model download or health-data access occurred. Phone checks
**skipped by owner; unverified**. No physical/native/mobile MVP/production acceptance inferred.

Progress: **11/19 primary receipts closed (~58%)**, unweighted management count, not code/effort
or mobile MVP acceptance. Next current phase: **Phase 12 — Foreground voice**; prerequisite
Phase 7 complete. No Phase 12 implementation started or capture/cloud/model authority granted.
