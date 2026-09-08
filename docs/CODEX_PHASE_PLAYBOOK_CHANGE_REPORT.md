# Codex Phase Playbook Change Report

Date: 2026-09-08
Scope: documentation and repository instructions only; no application source or runtime
configuration changed.

## Phase splits

| Phase | Resume-safe sessions |
| --- | --- |
| 0 | Continuous one-session baseline audit |
| 1 | 1A contracts/config/persistence; 1B providers/routing/privacy; 1C tools/interfaces; 1D performance/closeout |
| 2 | 2A push-to-talk/adapters; 2B duplex/wake safety; 2C device closeout |
| 3 | 3A permission broker; 3B actions/recovery; 3C adversarial/live closeout |
| 4 | 4A schema/lifecycle/provenance; 4B retrieval/interfaces; 4C evaluation/deletion |
| 5 | 5A acquisition/parsing; 5B evidence/synthesis; 5C ledger/closeout |
| 6 | 6A DAG/validator/store; 6B scheduler/recovery; 6C interfaces/benchmark |
| 7 | 7A capture/privacy/contracts; 7B temporal gestures/calibration; 7C mapping/closeout |
| 8 | 8A API/identity/enrollment; 8B approval/web hardening; 8C PWA/reconnect; 8D deployment/closeout |
| 9 | 9A topology/protocol/identity; 9B migration/backup/reconciliation; 9C deployment/resilience |
| 10 | 10A feasibility/license/contracts; 10B adapter/phone bridge; 10C real-device closeout |
| 11 | 11A trigger/proactivity policy; 11B runner/notifications; 11C multi-device/adapters; 11D long-duration closeout |

Each subphase is capped at five elapsed hours and has explicit objective, scope, prerequisites,
dependencies, deliverables, exclusions, sequence, tests, security/privacy, docs, acceptance, exit,
session count, model, reasoning, and rationale.

## Model changes

- Added exact `gpt-6-astra` assignments for architecture, security, difficult debugging,
  cross-system integration, migration, remote identity, autonomy, and real-effect risk.
- Retained `gpt-5.6-sol` for bounded implementation/evaluation/closeout and `gpt-5.6-terra` for the
  bounded PWA client after Astra-defined security contracts.
- Restricted Luna/Mini to isolated mechanical work.
- Replaced stale `Extra high` with supported `xhigh` and documented exact effort availability.
- Distinguished Codex execution models from JARVIS runtime provider roles.

## External ideas

Adopted as independently implemented requirements: target-versus-current architecture truth,
execution-time scope recheck, deny on empty scope intersection, atomic approval decisions,
authenticated reconnect/logout cleanup, signed-request test vectors, single-replica state invariant,
loopback datastore binding, data-first health checks, restore rehearsal, and pinned CI lint/audit
patterns.

Rejected: blacklist shell, substring approval, unbounded supervisor/swarm, fail-open sensitive audit,
automatic conversation-to-file memory, cloud-first voice, DNS preflight followed by unpinned fetch,
remote Python plugin loading, premature service/datastore stack, and committing private project
memory. See [External Repository Comparison](EXTERNAL_REPOSITORY_COMPARISON.md) for pinned links and
license analysis. No external code was copied. Local repository has no license, so later code
adoption needs an owner licensing decision.

## Files changed

- `docs/CODEX_PHASE_PLAYBOOK.md`
- `docs/CODEX_PHASE_PLAYBOOK_CHANGE_REPORT.md`
- `docs/EXTERNAL_REPOSITORY_COMPARISON.md`
- `docs/PHASE_OVERVIEW.md`
- `docs/JARVIS_MASTER_ROADMAP.md`
- `docs/roadmap.md`
- `docs/JARVIS_ARCHITECTURE.md`
- `docs/HANDS_FREE_CONTROL.md`
- `docs/phase-reports/TEMPLATE.md`
- `README.md`
- `AGENTS.md`

## Validation, risks, blockers

Validation passed on 2026-09-08:

- internal Markdown links: 27 files checked;
- external pinned links: 29 checked;
- schema/consistency: 12 phases, 36 subphases, and Markdown table shapes checked;
- lock/sync, Ruff format/lint, Mypy, Pytest, pip-audit, Gitleaks, `git diff --check`, and
  `jarvis doctor` passed;
- Pytest: 703 passed, 1 skipped, 85.16% coverage;
- Gitleaks: 15 commits and approximately 2.97 MB scanned, no leaks;
- Windows Application Control blocked the `mypy`, `pytest`, and `pip-audit` console shims with OS
  error 4551; equivalent `uv run python -m ...` commands passed. UTF-8 output was set for doctor to
  avoid the Windows CP1252 console limitation.

No product source changed. Existing product blockers remain: Phase 1 NVIDIA hosted latency; current
authorized live hardware/effect evidence for Phases 2-3. External code adoption is blocked until
JARVIS licensing is defined. Phase 8+ remains unimplemented as stated.
