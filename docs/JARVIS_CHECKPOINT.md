# JARVIS Checkpoint

Updated: 2026-09-16
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
- Kept Phase C automatic research disabled; web/multi-source decisions state missing evidence and
  grant no search, storage, personal-data, tool, or effect authority.

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

## Verification

- `uv lock --check`: pass, 119 packages resolved.
- `uv sync --locked`: pass in ignored `.bootstrap-venv`, 68 packages installed from lock.
- Ruff format/check: pass, 342 files.
- `mypy src`: pass, 141 source files.
- Full pytest: 1,102 passed, 3 skipped, 85.11% coverage.
- `pip-audit --strict`: no known vulnerabilities.
- Gitleaks: 44 commits / 4.91 MB scanned, no leaks.
- `git diff --check`: pass.
- `jarvis doctor`: pass; local runtime ready.
- Phase B benchmark: 10,000/10,000 correct, p50 0.0118 ms, p95 0.0242 ms, max 0.0651 ms.
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

- Next implementation: Phase C automatic volatile research for only `WEB_REQUIRED` and
  `MULTI_SOURCE` decisions.
- Reuse Phase 5 acquisition/parsing/synthesis/freshness boundaries. Do not add a competing web
  stack or silently persist research.
