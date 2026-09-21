# Mobile M2 Progress Report

Status: `M2A-local-complete-remote-ci-pending`  
Started: 2026-09-21  
Updated: 2026-09-21  
Active subphase: M2A — Native authentication contract and enrollment v2

## Objective

Add an authority-bound enrollment v2 contract, additive client capability metadata, a compatible
SQLite migration, and deterministic signing vectors shared by Python and TypeScript. Preserve
enrollment v1 and all existing PWA behavior. Do not persist mobile keys or perform live pairing.

## Implemented

- Enrollment v2 normalizes and signs one exact HTTPS server origin.
- Migration 014 stores enrollment protocol and bound origin on enrollment/device records; existing
  rows default to v1 with no origin.
- Core rejects every v2 device request whose signed authority differs from its enrolled origin.
- The trusted-local enrollment CLI accepts `--server-origin`; insecure HTTP requires explicit
  loopback-only development override.
- Client status adds protocol version, UTC server time, sorted capability names, and compatibility
  flags without removing existing fields.
- Python and TypeScript consume one deterministic Ed25519 request/v1/v2 fixture. No production
  secret is present; the fixture key is a public deterministic test vector.

## Verification evidence

```text
targeted Python remote/PWA/security/migration regression
PASS: 41 tests

targeted Ruff and mypy for changed Python modules
PASS

mobile npm run verify
PASS: formatting, lint, typecheck, 8 Jest tests, 100% statements/lines,
Expo Doctor 21/21, 1,100 license records, 0 high/critical production advisories,
Android export, iOS export

complete Python repository suite
PASS: 1,129 passed, 3 skipped, 85.09% coverage

uv lock --check / uv sync --locked / repository Ruff check
PASS

bootstrap Python pip-audit / Gitleaks / git diff --check
PASS: no known Python vulnerabilities; 48 commits and 5.65 MB scanned; no leaks
```

## Security boundaries

- Enrollment v1 proof bytes remain unchanged.
- V2 origin is normalized before ticket creation and repeated in completion proof.
- Production requires HTTPS. HTTP is accepted only for explicit localhost/loopback development.
- Request size, nonce replay, clock skew, scope intersection, short session, rotation, revocation,
  browser cookie/CSRF, and audit behavior remain unchanged.
- No private key, bearer token, server secret, EAS identifier, or live credential was added.

## Preserved unrelated work

Pre-existing Phase C research changes remain unstaged and untouched. Repository-wide Ruff/mypy
results must continue to classify their known unrelated failures separately.

## Gate classification

- Repository-wide Ruff format still reports two pre-existing Phase C files. M2A-owned Python files
  pass targeted format and lint checks.
- Standard `uv run mypy src` and `uv run pip-audit` fail because this workstation's generated
  mypyc extension modules cannot be imported. Bootstrap mypy checks all 144 source files and finds
  only the pre-existing Phase C assignment error at `src/jarvis/bootstrap.py:307`; bootstrap
  pip-audit passes.

## Remaining M2A closeout

- Commit/push the isolated M2A diff and confirm GitHub Actions.
- M2B follows after M2A closeout. M1A physical-device and M2C live acceptance remain deferred until
  the owner can sign into Expo on the laptop and phone.
