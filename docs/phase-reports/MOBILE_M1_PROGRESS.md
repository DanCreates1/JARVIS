# Mobile M1 Progress Report

Status: `M1A-and-M1B-complete`
Started: 2026-09-20  
Updated: 2026-09-21  
Active subphase: M1A physical-device acceptance complete; M1B complete
Recommended Codex model: `gpt-6-astra`  
Recommended reasoning: `max`

## Objective

Create an isolated Expo SDK 57 TypeScript workspace with a minimal branded, offline-safe shell,
then enforce its independent quality and CI gate without changing Python CI.

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
- [x] Physical iPhone launches the shell through Expo Go (owner confirmed 2026-09-21).
- [x] No permissions, secrets, API calls, telemetry, EAS IDs, or sensitive persistence added.
- [x] M1A-specific documentation and gates pass.

## Milestones

### Milestone 1 — Isolated workspace

- Status: complete.
- Changes: package/configuration, route shell, UI primitives, focused tests, architecture notes,
  and locked dependencies.
- Evidence: typecheck and 2 tests pass; Expo Doctor 21/21; Android and iOS exports pass; full Python
  suite passes 1,115 with 3 skips at 85.08% coverage; Gitleaks and diff checks pass.
- Live evidence: laptop Expo CLI authenticated; Metro served `exp://192.168.18.6:8081`, returned
  HTTP 200 locally, bundled the iOS route (1,306 modules in 8,135 ms), and owner confirmed JARVIS
  launch screen opened in Expo Go on physical iPhone. No enrollment or credential was used.
- Remaining: none for M1A.

### Milestone 2 — Quality and CI gate

- Status: complete.
- Changes: pinned ESLint/Prettier/Expo Doctor tooling, coverage thresholds, dependency-license
  policy, production audit threshold, and separate least-privilege mobile CI workflow.
- Evidence: format, lint, strict typecheck, 3 tests at 100% coverage, Expo Doctor 21/21, 1,098
  package-license entries, high/critical audit threshold, and Android/iOS exports pass. A temporary
  invalid assignment produced TS2322, proving the type gate rejects broken code; the probe was then
  removed and the clean gate rerun.
- Remote evidence: commit `ec5b11d` passed both GitHub Actions workflows: Mobile CI run
  `35632485139` and repository CI run `35632485147`.
- Remaining: none for M1B.

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

rtk npm.cmd run format:check
PASS

rtk npm.cmd run lint
PASS

rtk npm.cmd run typecheck
PASS

temporary negative probe: const mustFailTypecheck: string = 42
PASS: typecheck rejected probe with TS2322; probe removed

rtk npm.cmd run test:ci
PASS: 3 tests; 100% statements, branches, functions, and lines

rtk npm.cmd run doctor
PASS: 21/21 checks

rtk npm.cmd run license:check
PASS: 1,098 packages; 15 reviewed license expressions

rtk npm.cmd run audit:production
PASS at configured threshold: 0 high, 0 critical; 13 moderate transitive advisories recorded

rtk npm.cmd run export:android
PASS

rtk npm.cmd run export:ios
PASS

GitHub Actions Mobile CI run 35632485139
PASS

GitHub Actions repository CI run 35632485147
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
- Tool compatibility: Expo 57 lint plugins require ESLint 9; ESLint 10 is not yet accepted by
  `eslint-plugin-import` or `eslint-plugin-react`. ESLint 9.39.5 is pinned until Expo's compatible
  dependency set advances.

## Resolved blocker and remaining gate classification

- Owner signed into Expo CLI and Expo Go under the same account. Physical iPhone Expo Go launch now
  passes. No EAS project was created or linked.
- Metro warned that a production linking `scheme` is absent. Expo Go still launched; add a reviewed
  scheme before an M2C development build.
- Repository-wide Ruff format and mypy gates are blocked by preserved Phase C work: Ruff reports
  two unformatted Phase C files, and mypy reports one assignment mismatch in `bootstrap.py`.
  M1A changes contain no Python files. `uv run mypy` also hits Windows Application Control error
  4551; the established bootstrap interpreter reproduced the one Phase C type error.

## Known limits and deferred scope

- M2A/M2B subsequently added authentication and native secure storage. M1A smoke exercised only
  native launch, not pairing or Core connectivity. M2C live pairing and any development build remain
  separate work.

## Recovery and rollback

- Remove only M1A-owned `mobile/` and mobile documentation changes. Do not alter Phase C files.

## Final handoff

- Final status: M1A and M1B complete; physical iPhone Expo Go smoke passed.
- Files changed: isolated `mobile/` foundation, mobile architecture/phase docs, report, ignore rules.
- Next live subphase: M2C physical-device pairing and revocation, subject to its separate build and
  credential authority gates. M2A/M2B laptop work is complete.
- Commit/push status: M1A commit `7f9ccf5` and M1B commit `ec5b11d` are pushed separately from
  Phase C. Both M1B workflows are green. Phase C files remain unstaged and untouched.
