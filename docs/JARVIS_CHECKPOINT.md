# JARVIS Checkpoint

Updated: 2026-10-05
Objective: incremental proactive/context-aware expansion requested in `docs/AGENTIC_ASSISTANT_EXPANSION.md`

## Completed

- Audited provider, routing, memory, tools, research, API/PWA, files/vision, SQLite, planning,
  proactivity, permissions, remote identity, Tailscale deployment, and fallback boundaries.
- Completed Phase A current-context subsystem and runtime integration.
- Added exact active provider/model context after routing and fallback selection.
- Added configurable IANA/local timezone and optional approximate home region.
- Added bounded cached HTTPS reachability probe that sends no conversation content.
- Preserved private routing for configured location and device/session context.
- Completed Phase B deterministic freshness routing before production answer generation.
- Added typed `STATIC`, `LOCAL_CONTEXT`, `WEB_REQUIRED`, `PERSONAL_DATA_REQUIRED`, and
  `MULTI_SOURCE` decisions plus observable runtime events and non-persistent model guidance.
- Forced personal-data decisions through the existing private/local provider boundary.
- Completed Phase C public-only automatic research for web and multi-source routes, with bounded
  turn-local URL-cited evidence and explicit missing-evidence status.
- Added optional reviewed HTTPS SearXNG JSON search; Wikimedia remains the account-free default.
- Automatic research grants no storage, personal-data, tool, or effect authority.
- Completed Phase D read-only unified discovery over current model tools and task handlers.
- Local `jarvis tools list` and JSON view expose exact names, owners, and typed definitions;
  discovery never invokes handlers, approves actions, or schedules tasks.
- Completed Phase F default-off local CLI `repo:` context: bounded tracked-source symbol/path maps,
  fresh raw-file/HEAD-blob diffs, private routing and no automatic research.
- Added one content/TTL-validated in-memory map cache and atomic metadata-only coding checkpoints
  outside the repository, with 24-hour expiry, local inspection, clear and restart revalidation.
- Retained bounded conversations, memory, tools, Phase C acquisition and Phase D execution owners.
- Completed Phase G default-off local attachments: typed metadata/status, transactional quotas,
  isolated bounded text/PDF/image processing, local chunk retrieval and optional local vision.
- Added migration 015, exact host/conversation lifecycle, expiry/deletion/restart recovery,
  CLI and guarded loopback browser controls. No phone/PWA upload scope or new model tool.
- Attachment conversations/follow-ups retain sticky private routing after deletion; automatic
  research and memory-candidate capture remain suppressed. See [Attachments](ATTACHMENTS.md).

## Modified areas

- `src/jarvis/current_context.py`
- core context port/runtime composition
- model router active-route context
- validated settings and `.env.example`
- unit tests and architecture/README documentation
- `src/jarvis/freshness_router.py`
- core freshness contract/models/events and production runtime composition
- fixed classification/latency benchmark and adversarial/runtime/router tests
- Phase B completion report and expansion/checkpoint documentation
- Phase C projector, general-web adapter, runtime events, privacy/failure/cancellation tests,
  fixed 100-case benchmark, and completion report
- Phase D immutable discovery snapshot, runtime/CLI wiring, focused tests, and completion report
- Phase F coding adapter/port, configured local CLI/runtime wiring, checkpoint/cache lifecycle,
  synthetic/workstation benchmark, functional/privacy/process/path tests and operational guide

## Verification

- `uv lock --check`: pass, 119 packages resolved.
- `uv sync --locked`: pass in ignored `.bootstrap-venv`, 68 packages installed from lock.
- Ruff format/check: pass, 362 files.
- `mypy src`: pass, 147 source files.
- Full pytest: 1,147 passed, 3 skipped, 85.04% coverage.
- `pip-audit --strict`: no known vulnerabilities after locked `pypdf 6.19.0` upgrade.
- Gitleaks: 66 commits / 5.96 MB scanned, no leaks.
- `git diff --check`: pass.
- Phase D full gate: 1,150 passed, 3 skipped, 85.01% coverage; Ruff/mypy, locked dependencies,
  pip-audit, gitleaks, doctor, and diff check pass.
- `jarvis doctor`: pass; local runtime ready.
- Phase F final gate: 1,185 passed, 3 existing skips, 85.20% coverage; coding adapter 95% coverage.
  Ruff/mypy, locked dependencies, pip-audit, gitleaks, doctor and Git whitespace checks passed.
- Phase F benchmark: 100/100 cases; cold p50/p95 410.155/477.916 ms, warm p50/p95
  393.214/474.660 ms; zero failures, provider/network calls and cost. Workstation snapshot:
  360 mapped files, partial status, 8,000 projection chars, 3,008.797 ms; checkpoint valid.
- Phase G final gate: 1,250 passed, 3 existing skips, 85.31% coverage; Ruff 384 files/mypy 156
  source files, lock/sync, vulnerability/secret/doctor/whitespace gates passed. Fresh offline
  69-package install and installed-wheel text/image processing/migration smoke passed.
- Phase G benchmark: 100/100 hits, 6,655 maximum chars, retrieval p50/p95 3.859/4.890 ms;
  20 isolated parses p50/p95 129.908/151.496 ms. Warm local vision red oracle 1,348.504 ms;
  cold 60-second timeout recorded. Real private CLI/browser streaming smoke passed; no credentials.
- Phase B benchmark: 10,000/10,000 correct, p50 0.0118 ms, p95 0.0242 ms, max 0.0651 ms.
- Phase C benchmark: 100/100 fixed cases, 40 public fake acquisitions, zero privacy/persistence/
  authority violations, projection-only p95 0.1367 ms below 5 ms.
- Windows test launcher: generated `.venv` executable blocked by Application Control; trusted
  canonical CPython with locked `.bootstrap-venv/Lib/site-packages` works. The pre-existing
  `.venv/Lib` was locked against replacement, so no destructive cleanup was attempted. Pytest
  cache write warning and existing Starlette/httpx deprecation warning only.

## Decisions

- Dynamic context is not persisted in conversation history.
- Irrelevant queries receive no current-context block.
- Home region is never inferred; absent configuration is reported as unconfigured.
- Exact model identity is inserted by the router only after selecting each attempted provider.
- A reachability result is not research evidence and cannot support a current factual answer.
- Freshness precedence is personal data, multi-source work, volatile web facts, local context, then
  static knowledge.
- Decisions contain no query content and are never persisted in conversation history.
- Classification failure stops before user-message persistence and provider invocation.

## Remaining

- Phase G local release and Git publication complete: implementation `1cfde91` published to
  `origin/main` on 2026-10-05 after fresh owner Git credential authority. Publication evidence:
  [Phase G report](phase-reports/PHASE_G_COMPLETION.md).
- Next expansion implementation: Phase I — Email, with fresh phase authority. E/H/K baselines
  are complete; Phase C/D boundaries and external credential/effect stop gates remain.
- Live public Wikimedia smoke returned `authentication_required` from the search endpoint on this
  workstation. No credential or paid service was used; synthetic and contract gates cover the path.
