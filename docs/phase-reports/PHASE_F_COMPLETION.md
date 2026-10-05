# Phase F Token/Continuity Completion Report

Status: `complete`

Started: 2026-10-05

Updated: 2026-10-05

Completed: 2026-10-05

Active subphase: Phase F — Token/Continuity

Recommended Codex model/reasoning: `gpt-6-astra`, `xhigh` (privacy/context design)

Session start / five-hour stop: 2026-10-05 18:37 / 23:37 America/Toronto

## Objective

Add opt-in local coding context: compact repository maps, HEAD-relative changed-code context,
explicit cache invalidation, and automatic content-minimized checkpoint upkeep. Preserve bounded
conversation/memory/tool context, Phase C public-only volatile research, and Phase D discovery.

## Baseline

- Clean `main` at `c03ff10`, matching `origin/main`; no unrelated edits.
- Phase D complete; Phase E routing/fallback baseline complete.
- Phase C live Wikimedia smoke still blocked by `authentication_required`; no retry in scope.
- Windows CPython 3.11.9 and locked `.bootstrap-venv` available; generated `.venv` has prior
  Application Control limitations. Use established locked environment for checks.
- No credential use, paid services, remote deployment, or live computer effects authorized.

## Acceptance checklist

- [x] Default-off configured repository root; only explicit local CLI `repo:` requests project.
- [x] Typed bounded file/symbol map and fresh staged/unstaged HEAD-relative diff; excluded secrets,
  ignored/untracked files, runtime/media, path escapes, symlinks/junctions, and submodules.
- [x] Private non-persistent projection forces existing local routing and skips automatic research.
- [x] Map cache content fingerprint/TTL; diffs never cached; clear/close removes in-memory state.
- [x] Automatic atomic metadata-only checkpoint outside checkout; root/policy binding, expiry,
  corruption/staleness handling, inspection and explicit deletion; no conversation/code/diff stored.
- [x] Timeout/cancellation/missing Git/output caps; no hooks, external diff, textconv, shell or network.
- [x] Existing recent-turn reduction, memory, tool bounds and Phase C/D regressions pass.
- [x] 100 synthetic snapshots: projection <=8,000 chars, cold/warm p95 <=1,000 ms,
  zero privacy/authority failures. Actual workstation local snapshot smoke also passes.
- [x] Documentation/setup/recovery and complete release/security gates pass.

## Milestones

1. Baseline/contracts/threat boundary: complete; isolated opt-in private local context.
2. Repository adapter, cache/checkpoint lifecycle: complete; source exclusions, bounded inert Git
   inspection, freshness/cancellation/atomicity and recovery validated.
3. Runtime/CLI wiring and focused functional/security tests: complete; 35 Phase F tests and 102
   targeted cross-boundary regression tests passed before final cleanup hardening.
4. Benchmark, full gates and documentation: complete. Final source revision passed 1,185 tests,
   three existing skips, 85.20% coverage. Safe Git publication follows standing owner authority.

## Verification evidence

```text
rtk uv lock --check
PASS: 119 locked packages resolved

UV_PROJECT_ENVIRONMENT=.bootstrap-venv; rtk uv sync --locked
PASS: 68 locked packages checked; no dependency/lock changes

rtk proxy .bootstrap-venv\Scripts\python.exe -m ruff format --check .
PASS: 370 files formatted

rtk proxy .bootstrap-venv\Scripts\python.exe -m ruff check .
PASS

rtk proxy .bootstrap-venv\Scripts\python.exe -m mypy src
PASS: 149 source files

rtk proxy .bootstrap-venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp runtime/phase-f-release-20261005 --cov-report=term:skip-covered
PASS: 1,185 passed, 3 existing skipped, 85.20% coverage, 83.91 s
Phase F adapter coverage: 95%; focused final Phase F suite: 35 passed
Existing Starlette/httpx deprecation warning only

rtk proxy .bootstrap-venv\Scripts\python.exe -m pip_audit --strict
PASS: no known vulnerabilities

rtk gitleaks detect --source . --redact --no-banner
PASS: 69 commits / 6.04 MB, no leaks (baseline history; staged source scanned before commit)

rtk gitleaks protect --staged --redact --no-banner
PASS: 78.34 KB staged source, no leaks

rtk proxy .bootstrap-venv\Scripts\python.exe -m jarvis doctor
PASS: local runtime ready; all diagnostics pass

rtk proxy .bootstrap-venv\Scripts\python.exe scripts/phase-f-continuity-benchmark.py --repository . --enforce
PASS: 100 snapshots and workstation metadata/checkpoint smoke

rtk proxy .bootstrap-venv\Scripts\python.exe scripts/phase-b-freshness-benchmark.py
PASS: 10,000 samples, p50/p95 0.0107/0.0185 ms, no failures

rtk proxy .bootstrap-venv\Scripts\python.exe scripts/phase-c-automatic-research-benchmark.py --enforce
PASS: 100 cases, 40 fake acquisitions, p50/p95 0.0497/0.0667 ms,
zero persistence/privacy/authority violations; no live Wikimedia retry

rtk git diff --check
PASS
```

The established locked `.bootstrap-venv` on Windows/CPython 3.11.9 supplied all Python gates.
Ignored workspace-local pytest directories avoid historical Windows temp permissions issues.
No dependencies, migrations, remote endpoints, models, source code from external repositories,
or new-machine/bootstrap claims were introduced.

## Benchmark evidence

- Fixed 100 snapshots: 50 content misses/50 validated hits, 60 synthetic source files; zero failures.
- Cold p50/p95: 410.155/477.916 ms; warm p50/p95: 393.214/474.660 ms; p95 <=1,000 ms gate passed.
- Largest synthetic projection: 2,375 chars; provider/network calls and cloud cost: zero.
- Actual Windows repository smoke: 360 mapped files, eight changed files, partial status,
  8,000 chars, 3,008.797 ms, valid metadata checkpoint; temporary evidence removed.
- Windows / CPython 3.11.9; no model/hardware/network included in timed path.

## Security and privacy

Source is untrusted data. No source code executes. Fixed Git argument arrays disable fsmonitor,
external diff and textconv; inherited Git environment overrides are removed. Repository context
is private regardless of content classification. Existing providers, policy, grants, scheduler,
memory promotion, and tool discovery retain ownership. Checkpoints cannot create instructions,
approvals, actions, or trusted memory. No remote coding endpoint or background worker is added.

Tests cover staged additions/deletions, unstaged same-size/same-mtime edits, fresh diffs, map cache
hits/content invalidation/TTL/restart/clear, ignored/secret/untracked/binary/oversize/control files,
invalid Python, pathspec/traversal/private-directory denial and real Windows symlink/junction
escape. Git clean/textconv/external helpers remain inert; inherited override and credential
sentinels are excluded. Missing Git, malformed HEAD, timeout, cancellation, oversized subprocess
output, sanitized failure and child reaping are covered. Exact existing global Git trust entries
are preserved, including reset semantics, without granting new trust. Checkpoint wrong root/policy,
expiry, corruption/oversize, atomic-write disk failure and partial projection caps are covered.
Model cloud overrides cannot disclose private projection, automatic research receives no request,
and browser/voice/disabled/malformed-public paths stop before persistence/provider calls.

## Decisions and limitations

- Reuse existing context/privacy/router boundaries; no new model-facing tool or authority system.
- Compute diffs from raw local text and inert HEAD blobs to avoid Git clean-filter execution.
  Net working-tree-versus-HEAD content is shown; index-only changes reverted in the working tree
  do not appear as code changes. Encoding/EOL differences can remain visible in raw comparisons.
- Maps inspect only fixed eligible tracked source scopes and omit untracked files, root-level
  configuration, fixtures and generated/private artifacts. Stage reviewed source explicitly to
  include a new file. Python gets top-level symbols; other supported text gets paths only.
- Context limits are characters, not exact provider token counts. Map caching saves parsing,
  not source revalidation or diff reads. Truncated/partial output is marked explicitly.
- No atomic multi-file Git/working-tree snapshot is claimed. Captured source fingerprint identifies
  observed bytes; HEAD is rechecked. Run another snapshot after concurrent edits.
- Checkpoints contain metadata only and never enter prompts. They expire logically after 24 hours;
  physical cleanup is explicit or overwrite-on-refresh, with no background worker.
- No private query/code/diff appears in checkpoint metadata; canonical conversations/memory retain
  their existing explicit deletion/export/provenance behavior.

## Documentation and recovery

`docs/TOKEN_CONTINUITY.md`, README and `.env.example` document opt-in root/limits, local CLI use,
cache/checkpoint policy, exclusions and recovery. Expansion, playbook, checkpoint, overview,
roadmap, architecture and security reflect completed Phase F and the unchanged C/D boundaries.
Disable `JARVIS_CODING_CONTEXT_ENABLED` to stop projection. Re-enable the exact root and run
`jarvis coding clear` to remove its derived checkpoint; refresh with `jarvis coding context`.
There is no schema rollback. Preserve conversation/memory and unrelated files during code rollback.

## Blockers / recovery / handoff

- No Phase F external blocker known. Phase C live blocker remains separate.
- Disable coding context to remove projection; clear exact local checkpoint to delete derived state.
- Next planned expansion: Phase G — Attachments; fresh phase authority required.

## Final handoff

- Final status: complete; local functional/security/performance/quality gates passed.
- Files changed: coding adapter/port/runtime/settings/CLI, focused tests and benchmark; Phase F
  guide/report and reviewed state/architecture/security/setup documentation.
- Safe local commit: final Git receipt recorded in chat. Authenticated push requires fresh
  credential authority under this session's explicit no-credentials constraint; standing safe
  publication authorization does not waive that constraint. Private runtime artifacts stay out of Git.
- Next phase: G — Attachments. Phase C live Wikimedia `authentication_required` blocker remains;
  do not use application credentials, paid services or deployments without fresh authority.
