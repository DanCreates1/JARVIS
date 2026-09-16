# Phase B Freshness Router Completion Report

Status: `complete`  
Started: 2026-09-16  
Completed: 2026-09-16  
Active subphase: Phase B — Freshness Router  
Recommended Codex model: `gpt-6-astra`  
Recommended reasoning: `xhigh`  
Session start / five-hour stop: 2026-09-16T09:56:56-04:00 / 2026-09-16T14:56:56-04:00

## Objective

Classify every production chat request before answer generation as `STATIC`, `LOCAL_CONTEXT`,
`WEB_REQUIRED`, `PERSONAL_DATA_REQUIRED`, or `MULTI_SOURCE`. Make the decision observable and
non-persistent, force personal-data routes local, and leave automatic web acquisition to Phase C.

## Baseline

- Git branch/HEAD: `main` at `1d79c16`, matching `origin/main` before Phase B work.
- Worktree state and preserved unrelated changes: clean before Phase B; none present.
- Existing capability: Phase A request-aware current context and Phase 5 explicit research plus
  report freshness evaluation.
- Gap: no deterministic evidence-need route existed before provider generation. Chat did not
  automatically invoke research.
- Environment: RTK 0.45.0, uv 0.12.5, Git 2.55.0, CPython 3.11.9 on Windows.

## Acceptance checklist

- [x] Pure deterministic classifier covers all five routes with documented precedence.
- [x] Stable/historical requests avoid unnecessary live research routes.
- [x] Volatile facts require web evidence; comparison/recommendation/corroboration requires
  multiple sources.
- [x] Personal data routes are marked private and cannot authorize data access.
- [x] Runtime classifies once before provider generation and emits a typed decision event.
- [x] Compact route context reaches the provider but never conversation persistence.
- [x] Router failure prevents provider invocation and returns a bounded typed error.
- [x] Phase C remains disabled: no automatic fetch, search, persistence, or cloud disclosure added.
- [x] Unit/runtime/privacy/failure tests pass.
- [x] Fixed 10,000-decision local benchmark completes with zero errors and p95 below 1 ms.
- [x] README, architecture, expansion plan, and checkpoint match implementation.
- [x] Full release, vulnerability, secret, doctor, and Git gates pass.

## Implemented scope

### Contract and rules

- Added immutable `FreshnessRoute` and `FreshnessDecision` core models.
- Added a provider-neutral `FreshnessRouter` port and local
  `DeterministicFreshnessRouter` implementation.
- Normalizes Unicode NFKC, whitespace, and case; rejects blank, non-text, and oversized inputs.
- Applies fixed precedence: personal data, multi-source work, volatile web evidence, local context,
  then static knowledge.
- Decision reasons and projections contain no query text.

### Runtime and privacy

- Production bootstrap always composes the freshness router.
- `AssistantService` classifies and validates one projection before user-message persistence and
  before provider invocation.
- Emits `FRESHNESS_CLASSIFIED` with a typed content-free decision.
- Injects a bounded `local-freshness-router` system projection for generation; it is never written
  to conversation storage.
- Marks `PERSONAL_DATA_REQUIRED` projections private. Existing disclosure aggregation then rejects
  an explicit cloud role and selects the local provider.
- Returns `FRESHNESS_ROUTING_ERROR` without calling the provider if classification/projection fails.

### Deliberately deferred

- No search, fetch, source selection, research synthesis, or report caching.
- No email, calendar, file, account, or other personal-data provider access.
- No new storage schema, migration, background worker, permission, or effect authority.
- Phase C owns automatic volatile Phase 5 research for `WEB_REQUIRED` and `MULTI_SOURCE` only.

## Verification evidence

```text
rtk uv lock --check
PASS: 119 packages resolved

UV_PROJECT_ENVIRONMENT=.bootstrap-venv; uv sync --locked
PASS: 68 packages checked from lock

trusted CPython + locked bootstrap packages; ruff format --check .
PASS: 342 files already formatted

trusted CPython + locked bootstrap packages; ruff check .
PASS: all checks passed

trusted CPython + locked bootstrap packages; mypy src
PASS: no issues in 141 source files

trusted CPython + locked bootstrap packages; pytest
PASS: 1,102 passed, 3 skipped, 85.11% coverage

trusted CPython + locked bootstrap packages; pip-audit --strict
PASS: no known vulnerabilities

gitleaks detect --source . --redact --no-banner
PASS: 44 commits / 4.91 MB scanned, no leaks

trusted CPython + locked bootstrap packages; python -m jarvis doctor
PASS: JARVIS ready; all diagnostics pass

git diff --check
PASS
```

The ordinary `.venv` remains locked against uv hardlink replacement on this workstation. No
cleanup or security weakening was attempted. Commands requiring Python packages used the trusted
canonical CPython with locked `.bootstrap-venv/Lib/site-packages`, matching the Phase A workaround.
The full test gate used an explicit ignored `runtime/` base-temp path and disabled only pytest's
non-test cache provider. One existing Starlette/httpx deprecation warning remains.

## Benchmark

Command: `uv run python scripts/phase-b-freshness-benchmark.py` or the trusted CPython equivalent.

- Fixed corpus cases: 23.
- Timed decisions: 10,000.
- Correct decisions: 10,000.
- Errors/failures: 0.
- p50: 0.0118 ms.
- p95: 0.0242 ms; target below 1 ms.
- max: 0.0651 ms.
- Runtime: CPython 3.11.9, Windows 10.0.26200.
- Network/model/provider calls: 0.

## Security and privacy

- Adversarial text requesting a `STATIC` downgrade cannot override personal/weather cues.
- Personal-data classification and projection are private; explicit FAST cloud override still runs
  local and sends zero cloud requests.
- A decision grants no data access, tool call, research run, storage action, or side effect.
- Web/multi-source projections explicitly say that no evidence is attached. The model must not
  present volatile facts or consensus as verified without evidence.
- Router failure occurs before user-message persistence and provider invocation.
- Turn-local decision events/projections retain no query content and require no deletion migration.

## Known limits

- Rules classify the current request surface with fixed lexical patterns; they are not a semantic
  model. Novel wording can conservatively miss an intended volatile/personal cue. Phase C must keep
  evidence enforcement independent of model claims and extend the fixed regression corpus when
  new misses are found.
- A single route cannot represent every compound request. Security-first precedence selects
  personal data over web/multi-source work; downstream personal-data adapters must still enforce
  their own freshness and authorization.
- Follow-up pronouns depend on existing privacy uncertainty handling and conversation context;
  Phase C must not treat an ambiguous follow-up as permission to browse or disclose history.

## Recovery and rollback

- Remove `freshness_router=DeterministicFreshnessRouter()` from production composition to disable
  the feature, then remove its turn-local contract/event/projection integration.
- No database rollback, credential rotation, external cleanup, or user-data deletion is required.

## Final handoff

- Final status: complete.
- Main files: `src/jarvis/freshness_router.py`, core contract/models/runtime/bootstrap, fixed
  benchmark/tests, README/architecture/expansion/checkpoint documentation.
- Next recommended phase: Phase C — Automatic Web Research.
- Commit/push: governed by standing repository authorization; final handoff records verified refs.
