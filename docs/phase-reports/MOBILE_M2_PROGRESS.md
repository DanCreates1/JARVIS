# Mobile M2 Progress Report

Status: `M2C-local-rotation-verified-live-acceptance-pending`
Started: 2026-09-21  
Updated: 2026-09-22
Active subphase: M2C — physical iPhone/Tailscale acceptance

## M2C objective

M2C: prove authority-bound native enrollment and scoped signed status on a physical iPhone through
the existing private Tailscale Serve gateway. Exercise Wi-Fi/cellular, Tailscale loss/reconnect,
Core restart, logout, device revoke/rotation, and lost-phone recovery. Keep Core loopback-only and
Phase C work untouched.

## M2C baseline and acceptance

- Git: continuation started from `aa0177c`, matching `origin/main`; prior M2C preflight evidence is pushed.
- Phase C research edits were already modified/untracked; outside M2C scope.
- M1 Expo Go launch passed; M2A `676fd08` and M2B `62eb778` are present.
- Node 24.20.0, npm 11.19.0, Tailscale CLI, `uv`, and Gitleaks are installed.
- [x] Reviewed `jarvis-mobile` linking scheme and on-device signed status control.
- [x] Implemented and locally verified explicit, crash-recoverable native key rotation.
- [x] Mobile quality gate and relevant Core regression gate pass.
- [ ] iPhone v2 minimum-scope enrollment through Tailscale HTTPS passes.
- [ ] Signed status, logout/recreation, Wi-Fi/cellular, Tailscale loss/reconnect, Core restart pass.
- [ ] Revoke/rotation and lost-phone drill pass with sanitized audit evidence.
- [x] Private listener/Funnel boundaries, secret scan, docs, and isolated local M2C milestone commit pass.

Fresh enrollment ticket and Expo development build each require owner approval before action.
Do not record live tickets, signatures, tokens, private keys, tailnet identity, or phone data in
Git. Expo Go can provide provisional live evidence; native build acceptance requires separate
development-build approval.

## M2C local preparation and evidence

- `mobile/app.config.ts` sets `jarvis-mobile` as the app scheme. Expo's current linking guidance
  requires a new development build before that scheme works on device. Ticket content remains
  excluded from routes.
- The enrolled iPhone screen can request signed Core status, revoke its current session, recreate
  a session on next status, and erase local credentials. It hides ticket intake after enrollment
  and keeps erase available after network or revoke failure.
- `docs/MOBILE_M2C_ACCEPTANCE.md` freezes the provisional Expo Go matrix and the later native
  build/rotation gates.
- 2026-09-21 continuation found a scope mismatch before live enrollment: Core requires
  `session.revoke` on `DELETE /api/v1/sessions/current`, while the client requested only
  `client.status.read`. The client now requires both scopes on the approved ticket and session,
  so logout and erase can revoke remotely. It rejects a session response missing either scope;
  the test fake enforces endpoint scopes. No live ticket was created.
- Read-only Tailscale status: client online, private HTTPS Serve route points to
  `http://127.0.0.1:8765`, no public Funnel detected. No backend listener exists now. The Phase 8D
  ownership marker is absent; do not use its `Run`/`Stop` actions over the existing route.
- Read-only continuation preflight: Tailscale 1.102.3 online, `.ts.net` DNS present, Serve still
  has one HTTPS 443 route and one root handler to `http://127.0.0.1:8765`, Funnel disabled,
  no port 8765 listener, ownership marker absent.
  The owner confirmed the intended tailnet TCP 443 grant; this workstation cannot independently
  inspect the admin-console policy. Existing unowned route unchanged.
- Read-only continuation found the registered iPhone peer offline in Tailscale. The Serve-owned
  tailnet TCP 443 listener is present; Core port 8765 remains closed. No live phone result is claimed.
- 2026-09-22 read-only preflight: Tailscale reports online with private `.ts.net` DNS; the single
  HTTPS TCP 443 Serve authority has one root handler to exact `http://127.0.0.1:8765`. Funnel has
  zero enabled entries. The registered iOS peer remains offline. No Core port 8765 listener or
  Phase 8D deployment marker exists. The owner-confirmed intended TCP 443 tailnet grant is carried
  forward; local CLI cannot inspect admin-console policy. Existing unowned Serve route unchanged.
- 2026-09-22 `.bootstrap-venv` imports `cryptography.exceptions`; `git diff --check` passes.
  Mobile `npm.cmd run verify` passes: Prettier, ESLint, TypeScript, 29 Jest tests, 93.93% statements,
  88.32% branches, 94.59% functions, 95.77% lines, Expo Doctor 21/21, 1,108 license records,
  no high/critical production advisories, and Android/iOS exports. The 13 moderate transitive
  advisories remain. No live phone result or ticket is claimed.
- 2026-09-22 continuation added the missing native `key.rotate` path without starting Core or
  creating a ticket. Rotation requires explicit on-device confirmation and a separately granted
  scope. The client stages the new seed in SecureStore, submits an old-key signed request plus
  new-key proof, invalidates the cached session, validates Core's exact key-version/origin response,
  and commits the replacement identity. If the response is lost before or after Core commit, the
  next signed status deterministically tries the staged and current keys, then commits or discards
  the staged key. Credential erase deletes current and pending key records.

```text
M2C native rotation mobile npm.cmd run verify
PASS: Prettier, ESLint, TypeScript, 36 Jest tests, 92.06% statements,
86.47% branches, 95.45% functions, 94.25% lines, Expo Doctor 21/21,
1,108 dependency license records, no high/critical production advisories,
Android and iOS exports. 13 moderate transitive advisories remain.

Core rotation regression with bootstrap Python and --no-cov
PASS: 1 test. Pytest cache warning only; repository-root .pytest_cache is not writable.

uv lock --check / Gitleaks full Git scan / git diff --check
PASS: lock current; 55 commits and 5.78 MB scanned with no leaks; no whitespace errors.
```

- Isolated native-rotation milestone commit `8dcb518` was pushed to `origin/main`; Phase C files
  remained unstaged and untouched.

```text
M2C continuation mobile npm.cmd run verify
PASS: Prettier, ESLint, TypeScript, 29 Jest tests, 93.93% statements,
88.32% branches, 94.59% functions, 95.77% lines, Expo Doctor 21/21,
1,108 dependency license records, no high/critical production advisories,
Android and iOS exports. 13 moderate transitive advisories remain.

bootstrap Python cryptography.exceptions import / git diff --check
PASS

Gitleaks --no-git mobile/src, mobile/__tests__, docs
PASS: no leaks in 32.28 KB, 32.72 KB, and about 786 KB respectively
```

```text
mobile npm.cmd run verify
PASS: Prettier, ESLint, TypeScript, 28 Jest tests, 93.58% statements,
88.21% branches, 94.52% functions, 95.42% lines, Expo Doctor 21/21,
1,108 dependency license records, no high/critical production advisories,
Android and iOS exports

bootstrap Python full suite
PASS: 1,129 passed, 3 skipped, 85.09% coverage

uv lock --check / uv sync --locked / uv run ruff check .
PASS

bootstrap pip-audit / Gitleaks Git history, mobile, and docs / git diff --check
PASS: no known Python vulnerabilities and no leaks in scanned source
```

The production npm audit still reports 13 moderate transitive advisories; its configured release
threshold rejects high/critical. Repository-wide Ruff format finds two pre-existing Phase C files.
Bootstrap mypy finds the pre-existing assignment error at `src/jarvis/bootstrap.py:307` and checks
all 144 source files. The standard `.venv` still cannot import generated mypyc modules or
`cryptography.exceptions`; standard `uv run mypy src`, `uv run pip-audit`, and live CLI use remain
impaired. The verified `.bootstrap-venv` works for imports, tests, mypy, and pip-audit. Phase C
files remain untouched.

## M2C live blockers

- Owner approval for each fresh five-minute, two-scope (`client.status.read`, `session.revoke`),
  risk-0 v2 phone ticket is pending. No ticket has been created in M2C.
- Core is not running on port 8765. Existing Serve route is unowned; starting Core must keep
  `JARVIS_WEB_HOST=127.0.0.1` and exact trusted HTTPS origin without launcher Run/Stop.
- Physical iPhone/Tailscale evidence requires the owner's on-device actions.
- Development build has not been requested or started. It needs separate owner approval plus a
  chosen Apple signing/account and iOS bundle identifier.
- Native key rotation is implemented and locally tested. Live rotation still needs fresh approval
  for a three-scope ticket adding `key.rotate`, plus physical-iPhone, Core-audit, restart, and
  old-session rejection evidence. Core's existing rotation tests are not live native evidence.

## M2A objective

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
