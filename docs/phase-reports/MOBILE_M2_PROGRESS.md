# Mobile M2 Progress Report

Status: `M2B-laptop-complete-live-acceptance-deferred`
Started: 2026-09-21  
Updated: 2026-09-21  
Active subphase: M2B — Mobile key, session, and pairing client

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

## M2A closeout

- Isolated M2A commit `676fd08` pushed. [Mobile CI](https://github.com/DanCreates1/JARVIS/actions/runs/35636138106)
  and [Python CI](https://github.com/DanCreates1/JARVIS/actions/runs/35636138069) both succeeded.

## M2B objective and implementation

Generate and retain one Ed25519 identity bound to the enrolled Core origin. Pair with a v2 ticket,
create scoped signed API sessions, refresh them in memory, and support logout and local credential
erase. No live account, EAS project, or physical-device proof is claimed.

- Expo Crypto generates the Ed25519 seed and fresh request nonces. Expo SecureStore uses
  `WHEN_UNLOCKED_THIS_DEVICE_ONLY` for the identity record.
- QR scanning is foreground-only; camera permission is requested only after selecting **Scan QR**.
  Manual JSON paste remains available. Neither ticket nor credential enters a deep link.
- Production origins require HTTPS. Explicit debug-only loopback is separate. V2 ticket parsing
  checks device type, required `client.status.read` scope, expiration, and bound origin.
- Enrollment proof and every session/API request use the shared canonical Ed25519 contract.
  Enrollment response must match the exact bound origin. Requests use fresh nonces and bind the
  bearer-token digest; a one-time bounded clock-skew retry uses the server `Date` response.
- Session token is process-memory-only. Restart and near-expiry recreate a scoped session. Pairing
  requests only `client.status.read`, not every enrolled scope. Re-enrollment to the same Core is
  rejected until local identity is explicitly erased; a changed origin erases old local identity.
- Logout revokes the current session. Credential erase attempts revocation and always removes the
  local identity even if remote revocation fails. UI instructs Core-side revocation on failure.
- No provider credentials, model secrets, telemetry, background permissions, native directories,
  EAS account identifiers, or server authority changes were added.

## M2B verification evidence

```text
mobile npm run verify
PASS: Prettier, ESLint, TypeScript, 26 Jest tests, 93.22% statements,
87.94% branches, 94.20% functions, 95.15% lines, Expo Doctor 21/21,
1,108 dependency license records, 0 high/critical production advisories,
deterministic Android export (2.9 MB), deterministic iOS export (2.6 MB)

uv lock --check / uv sync --locked / uv run ruff check .
PASS

bootstrap Python complete repository suite
PASS: 1,129 passed, 3 skipped, 85.09% coverage

bootstrap pip-audit / Gitleaks
PASS: no known Python vulnerabilities; 49 commits/5.69 MB scanned; no leaks
```

Production npm audit reports 13 moderate transitive advisories; current gate rejects high/critical.
`npm audit fix --force` would change the Expo SDK/Router compatibility line and was not applied.

## M2B gate classification and owner handoff

- Repository-wide Ruff format reports only two pre-existing Phase C files; M2B changed no Python
  file. Bootstrap mypy reports only the pre-existing Phase C assignment at
  `src/jarvis/bootstrap.py:307`.
- Standard `uv run mypy src` and `uv run pip-audit` fail due generated mypyc import errors in the
  local `.venv`. Standard `uv run pytest` cannot import `cryptography.exceptions` from that same
  environment. Bootstrap Python provided equivalent full-suite, mypy, and audit evidence.
- Phase C research changes remain unstaged and untouched. M2B files/docs alone form the commit.
- M1A Expo Go physical iPhone smoke passed on 2026-09-21; see the M1 report. M2C physical
  iPhone/Tailscale pairing, Wi-Fi/cellular transitions, server restart, revoke/rotation, and
  lost-phone drill remain pending. No M3 work starts before M2C.
