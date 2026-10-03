# JARVIS Checkpoint

Updated: 2026-10-02
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

## Verification

- `uv lock --check`: pass, 119 packages resolved.
- `uv sync --locked`: pass in ignored `.bootstrap-venv`, 68 packages installed from lock.
- Ruff format/check: pass, 362 files.
- `mypy src`: pass, 147 source files.
- Full pytest: 1,147 passed, 3 skipped, 85.04% coverage.
- `pip-audit --strict`: no known vulnerabilities after locked `pypdf 6.19.0` upgrade.
- Gitleaks: 66 commits / 5.96 MB scanned, no leaks.
- `git diff --check`: pass.
- `jarvis doctor`: pass; local runtime ready.
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

- Next expansion implementation: Phase D unified tool registry discovery.
- Live public Wikimedia smoke returned `authentication_required` from the search endpoint on this
  workstation. No credential or paid service was used; synthetic and contract gates cover the path.
