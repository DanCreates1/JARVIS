# JARVIS Checkpoint

Updated: 2026-09-15
Objective: incremental proactive/context-aware expansion requested in `docs/AGENTIC_ASSISTANT_EXPANSION.md`

## Completed

- Audited provider, routing, memory, tools, research, API/PWA, files/vision, SQLite, planning,
  proactivity, permissions, remote identity, Tailscale deployment, and fallback boundaries.
- Completed Phase A current-context subsystem and runtime integration.
- Added exact active provider/model context after routing and fallback selection.
- Added configurable IANA/local timezone and optional approximate home region.
- Added bounded cached HTTPS reachability probe that sends no conversation content.
- Preserved private routing for configured location and device/session context.

## Modified areas

- `src/jarvis/current_context.py`
- core context port/runtime composition
- model router active-route context
- validated settings and `.env.example`
- unit tests and architecture/README documentation

## Verification

- `uv lock --check`: pass, 119 packages resolved.
- `uv sync --locked`: pass in ignored `.bootstrap-venv`, 68 packages installed from lock.
- Ruff format/check: pass, 338 files.
- `mypy src`: pass, 140 source files.
- Full pytest: 1,062 passed, 3 skipped, 85.09% coverage.
- `pip-audit --strict`: no known vulnerabilities.
- Gitleaks: 43 commits / 4.88 MB scanned, no leaks.
- `git diff --check`: pass.
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

## Remaining

- Next implementation: Phase B deterministic Freshness Router, then automatic volatile research.
- Do not start Phase C or later without completing Phase B gates.
