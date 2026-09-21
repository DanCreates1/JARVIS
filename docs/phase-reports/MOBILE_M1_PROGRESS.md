# Mobile M1 Progress Report

Status: `implemented-closeout-pending`  
Started: 2026-09-20  
Updated: 2026-09-20  
Active subphase: M1A — Expo workspace scaffold  
Recommended Codex model: `gpt-6-astra`  
Recommended reasoning: `max`

## Objective

Create an isolated Expo SDK 57 TypeScript workspace with a minimal branded, offline-safe shell,
validated non-secret environment metadata, dependency lock, focused tests, and deterministic iOS
and Android exports. Do not start M1B CI or M2 authentication work.

## Baseline

- Git branch/HEAD: `main` at `00c79d9`, matching `origin/main` before M1A work.
- Worktree state: ongoing Phase C research changes were present before M1A and are preserved,
  unstaged, and outside `mobile/` and M1A documentation.
- Workstation: Windows, Node 24.20.0, npm 11.19.0; PowerShell npm shims require `.cmd`.
- Mobile baseline: no JavaScript workspace, native project, lockfile, SDK, or mobile CI existed.
- Existing remote/PWA/security baseline: 74 relevant tests passed during M0 inspection.

## Acceptance checklist

- [x] Expo SDK 57 and React Native 0.86 dependencies resolve from a lockfile ready to commit.
- [x] Minimal TypeScript/Expo Router shell renders an honest offline-safe state.
- [x] Unknown runtime environment metadata fails closed to `development`.
- [x] Unit tests and strict TypeScript check pass.
- [x] Deterministic iOS and Android exports pass without committed native projects.
- [ ] Physical iPhone launches the shell through Expo Go.
- [x] No permissions, secrets, API calls, telemetry, EAS IDs, or sensitive persistence added.
- [x] M1A-specific documentation and gates pass.

## Milestones

### Milestone 1 — Isolated workspace

- Status: implemented; live-device closeout pending.
- Changes: package/configuration, route shell, UI primitives, focused tests, architecture notes,
  and locked dependencies.
- Evidence: typecheck and 2 tests pass; Expo Doctor 21/21; Android and iOS exports pass; full Python
  suite passes 1,115 with 3 skips at 85.08% coverage; Gitleaks and diff checks pass.
- Remaining: physical iPhone Expo Go smoke, completion report, isolated commit/push.

## Decisions

- Decision: use Expo SDK 57.0.24, React Native 0.86.3, TypeScript 6.0, and Expo Router 57.
- Reason: current official Expo template compatibility set; matches approved architecture.
- Alternatives: bare React Native rejected for M1A because no custom native requirement exists.
- Reversible later: Continuous Native Generation permits reviewed native projects when required.

## Verification evidence

```text
rtk npm.cmd ci
PASS: 850 packages installed from lockfile

rtk npm.cmd run typecheck
PASS

rtk npm.cmd test -- --coverage=false
PASS: 2 tests

rtk npx.cmd expo-doctor@latest
PASS: 21/21 checks

rtk npm.cmd run export:android
PASS: Android bundle exported to ignored dist/android

rtk npm.cmd run export:ios
PASS: iOS bundle exported to ignored dist/ios

EXPO_PUBLIC_JARVIS_ENV=invalid npx.cmd expo config --type public
PASS: invalid environment rejected

rtk npm.cmd audit --omit=dev --audit-level=high
PASS at configured threshold: 0 high, 0 critical; 13 moderate transitive Expo advisories recorded

rtk .bootstrap-venv\Scripts\python.exe -m pytest --basetemp runtime\pytest-mobile-m1a-final
PASS: 1,115 passed, 3 skipped, 85.08% coverage

rtk .bootstrap-venv\Scripts\python.exe -m pip_audit
PASS: no known Python vulnerabilities

gitleaks detect --source . --redact --no-banner
PASS: 45 commits, 4.95 MB, no leaks

rtk git ... diff --check
PASS
```

## Security and privacy

- Data boundary: no Core or external network data is requested by application code.
- Permissions: none.
- Persistence: none.
- Secrets: Gitleaks passed across history and worktree.
- Dependency audit: 13 moderate transitive Expo/Router advisories; no high or critical findings.
  npm's proposed force-fix downgrades to incompatible Expo 46/Router 5, so no unsafe force-fix was
  applied.

## Blockers

- Physical iPhone Expo Go launch is blocked until Expo CLI and Expo Go are signed into the same
  owner-controlled free Expo account. The unauthenticated LAN attempt was correctly rejected before
  loading the project. The owner deferred laptop login and live-device validation until returning
  home. M1A does not require EAS project creation or linkage.
- Repository-wide Ruff format and mypy gates are blocked by preserved Phase C work: Ruff reports
  two unformatted Phase C files, and mypy reports one assignment mismatch in `bootstrap.py`.
  M1A changes contain no Python files. `uv run mypy` also hits Windows Application Control error
  4551; the established bootstrap interpreter reproduced the one Phase C type error.

## Known limits and deferred scope

- M1B lint/format/CI workflow is not part of M1A.
- Authentication, API transport, native secure storage, tabs, features, EAS linkage, and native
  signing are deferred.

## Recovery and rollback

- Remove only M1A-owned `mobile/` and mobile documentation changes. Do not alter Phase C files.

## Final handoff

- Final status: implementation verified; physical iPhone closeout pending.
- Files changed: isolated `mobile/` foundation, mobile architecture/phase docs, report, ignore rules.
- Next recommended phase: M1B only after M1A live-device acceptance.
- Commit/push status: M1A implementation committed/pushed separately from Phase C; physical iPhone
  acceptance remains pending. Phase C files remain unstaged and untouched.
