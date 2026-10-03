# Phase C Automatic Web Research Completion Report

Status: `complete`  
Started: 2026-09-16  
Completed: 2026-10-02  
Active subphase: Phase C — Automatic Web Research  
Recommended Codex model: `gpt-6-astra`  
Recommended reasoning: `xhigh`  
Prior session start / five-hour stop: 2026-09-16T11:06:02-04:00 / 2026-09-16T16:06:02-04:00

## Objective

Connect only `WEB_REQUIRED` and `MULTI_SOURCE` chat decisions to bounded, volatile Phase 5
research. Supply compact timestamped cited evidence to answer generation, add a configurable
general-web search adapter, and degrade explicitly when live evidence is unavailable. Preserve
privacy, `$0` cost, untrusted-source, approval, authority, and no-automatic-persistence boundaries.

## Baseline

- Git branch/HEAD at continuation: `main` at `b8e4423`, matching `origin/main` before closeout.
- Worktree state and preserved unrelated changes: Phase C implementation, tests, benchmark, and this
  report were already modified/untracked. All were preserved and completed. Earlier Phase C start
  was clean at `00c79d9`; intervening mobile commits were left intact.
- Relevant state: Phase B deterministic freshness routing and Phase 5 bounded research are
  complete. Production search is Wikimedia-only and chat does not invoke research.
- Environment: Windows, CPython 3.11.9, uv 0.12.5, RTK 0.45.0. Project `.venv` hardlink repair is
  blocked; locked `.bootstrap-venv` is the established test path.
- Baseline targeted result: 92 tests passed; pytest process returned nonzero only because a narrow
  subset cannot meet the repository-wide 85% coverage threshold.

## Acceptance checklist

- [x] Only `WEB_REQUIRED` and `MULTI_SOURCE` trigger automatic research.
- [x] Static, local-context, and personal-data routes make zero research calls.
- [x] Public privacy classification runs before every remote search; uncertain/private queries
  fail closed without network disclosure.
- [x] Phase 5 search/fetch/parse/synthesis/citation bounds and cancellation remain authoritative.
- [x] Volatile evidence projection is at most 20,000 characters and includes source URLs,
  retrieval/publication timestamps, nearby citation links, conflicts, uncertainty, and freshness.
- [x] `MULTI_SOURCE` requires at least two independent source hosts or is labeled insufficient.
- [x] No automatic ledger write, storage approval, memory commit, tool/action authority, or
  query-bearing audit is added.
- [x] Search timeout, malformed response, no usable sources, privacy denial, provider outage, and
  offline behavior produce explicit missing-evidence guidance without fabricated current facts.
- [x] Cancellation propagates through in-flight research and provider work.
- [x] Configurable general-web search capability has bounded HTTPS, response, schema, and domain
  controls; Wikimedia remains a safe account-free fallback.
- [x] Fixed synthetic benchmark completes 100/100 cases with zero route, privacy, persistence, or
  authority violations; projection-only p95 is below 5 ms.
- [x] Bounded live public no-storage smoke passes or exact external blocker is recorded.
- [x] README, architecture, security, setup, expansion plan, checkpoint, and phase status match.
- [x] Full release, vulnerability, secret, doctor, and Git gates pass.

## Milestones

### Milestone 1 — Baseline, contracts, and threat boundary

- Status: complete.
- Changes: acceptance targets frozen; runtime, freshness, Phase 5 workflow, adapters,
  configuration, tests, official SearXNG docs, and prior evidence audited.
- Evidence: initial 92 targeted baseline tests passed; continuation Git state inspected and preserved.
- Remaining: none.

### Milestone 2 — Runtime vertical slice

- Status: complete.
- Changes: provider-neutral research port, Phase 5 volatile workflow entry, runtime wiring/events,
  public-only preflight, bounded timestamped URL-cited projection, independent-host sufficiency,
  content-free failure codes, and cancellation propagation.
- Evidence: focused runtime/projector/workflow tests passed; no automatic pending storage record.
- Remaining: none.

### Milestone 3 — General search adapter and configuration

- Status: complete.
- Changes: optional SearXNG JSON search adapter, explicit HTTPS endpoint validation, bounded JSON,
  URL/domain checks, timeout and cancellation; Wikimedia remains default.
- Evidence: adapter contract/config tests passed; official
  [SearXNG search API](https://docs.searxng.org/dev/search_api) confirms GET JSON format and that
  public instances may disable JSON.
- Remaining: live SearXNG smoke needs an independently reviewed JSON-enabled endpoint.

### Milestone 4 — Failure, privacy, benchmark, and live evidence

- Status: complete with recorded external live-smoke blocker.
- Changes: privacy denial before workflow, safe failure projections, URL links next to claims,
  100-case fixed benchmark, and bounded Wikimedia live-smoke attempt.
- Evidence: benchmark 100/100, 40 live-route fake acquisitions, zero route/privacy/persistence/
  authority violations, projection p95 0.103 ms. Live Wikimedia search returned
  `authentication_required` and no usable source; no credentials, store, or paid service used.
- Remaining: repeat a live public smoke when an account-free endpoint permits access.

### Milestone 5 — Release gate and closeout

- Status: complete.
- Changes: setup, architecture, security, README, expansion/checkpoint/status docs; upgraded locked
  `pypdf` from 6.17.0 to 6.19.0 after vulnerability gate found seven advisories.
- Evidence: full release/security gates below; `pypdf` minimum raised to 6.19.
- Remaining: none within local release gate.

## Decisions

- Decision: use the existing Phase 5 orchestrator and volatile workflow; do not create a second web
  stack or durable chat research schema.
- Reason: Phase 5 already owns SSRF, parser isolation, synthesis validation, citations, and storage
  approval.
- Alternatives: model tool-calling and silent report storage were rejected because they weaken
  deterministic routing and approval boundaries.
- Reversible later: automatic research gets a separate configuration gate and can be disabled
  without deleting approved research.

## Verification evidence

```text
rtk uv lock --check
PASS: 119 packages resolved

UV_PROJECT_ENVIRONMENT=.bootstrap-venv; rtk uv sync --locked
PASS: locked environment; pypdf 6.19.0 installed

rtk .bootstrap-venv\Scripts\python.exe -m ruff format --check .
PASS: 362 files already formatted

rtk .bootstrap-venv\Scripts\python.exe -m ruff check .
PASS: all checks passed

rtk .bootstrap-venv\Scripts\python.exe -m mypy src
PASS: no issues in 147 source files

rtk .bootstrap-venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp runtime/phase-c-full-20261002
PASS: 1,147 passed, 3 skipped, 85.04% coverage

rtk .bootstrap-venv\Scripts\python.exe -m pip_audit --strict
PASS: no known vulnerabilities after pypdf 6.19.0 upgrade

rtk gitleaks detect --source . --redact --no-banner
PASS: 66 commits / 5.96 MB scanned, no leaks

rtk .bootstrap-venv\Scripts\python.exe -m jarvis doctor
PASS: JARVIS ready; all diagnostics pass

rtk git diff --check
PASS
```

The generated `.venv` interpreter remains blocked by Windows Application Control (OS error 4551).
The established ignored `.bootstrap-venv` uses locked packages and passed sync, tests, types,
dependency audit, and doctor. Pytest used a new ignored workspace-local base temp. One existing
Starlette/httpx deprecation warning remained.

## Benchmarks

- Samples: 100 fixed route cases; 40 public live-route fake acquisitions; 40 separately timed
  projection-only renders.
- Cold/warm: one in-process synthetic run after import; no network or model initialization timed.
- p50: 0.0892 ms projection only.
- p95: 0.1367 ms projection only, below 5 ms target; max 0.2262 ms.
- Errors/failures: zero synthetic route, privacy, persistence, authority, and projection failures.
- Hardware/runtime/model/device versions: Windows 10.0.26200, CPython 3.11.9, Intel64 Family 6
  Model 141; no model, device, or network in the timed path.
- Relevant settings: fake Phase 5 workflow/report; at most 20,000 projection characters; no store.

## Security and privacy

- Threats tested: private/uncertain query denial before workflow, search-adapter privacy recheck,
  query-free events, source injection/citation validation, one-host insufficient corroboration,
  malformed search, timeout, cancellation, and volatile no-storage workflow.
- Data boundaries: public current request only; prior conversation, memory, personal data, files,
  credentials, and uncertain content excluded from remote queries.
- Permissions/approvals: research grants no action authority; ledger storage remains separate exact
  one-use approval.
- Audit/retention/deletion: automatic result is turn-local and non-persistent.
- Secret scan: pending final gate.

## Blockers

- Live no-storage Wikimedia smoke on 2026-10-02 used a public Python-version query with a
  20-second total deadline, one search, at most three fetches, two sources, 200,000 bytes per fetch,
  five-second fetch/search/parser limits, and extractive synthesis. Search failed with
  `authentication_required`; orchestrator reported `unavailable`/no usable sources. No storage or
  model call occurred. This is an external endpoint response, not a waived local security gate.
- No reviewed JSON-enabled SearXNG endpoint is configured. Do not create an account, use credentials,
  accept terms, enable billing, or switch to an unreviewed endpoint to clear this live smoke.

## Known limits and deferred scope

- Personal email/calendar/files remain later phases and never trigger automatic web research.
- Authenticated/paywalled sources, JavaScript rendering, crawling, OCR, and background refresh stay
  out of scope.

## Recovery and rollback

- Disable automatic chat research through its dedicated setting, or disable all Phase 5 acquisition
  with `JARVIS_RESEARCH_ENABLED=false`. No migration rollback or data deletion is required.

## Final handoff

- Final status: complete; bounded public live smoke remains externally unverified as recorded.
- Files changed: core/runtime/config/bootstrap, Phase 5 research adapter/workflow/projector,
  pyproject/lock, tests/benchmark, README/setup/architecture/security/status documents, this report.
- Next recommended phase: Phase D — Unified Tool Registry after Phase C closes.
- Commit/push status: final local gates passed; standing repository authorization applies.
