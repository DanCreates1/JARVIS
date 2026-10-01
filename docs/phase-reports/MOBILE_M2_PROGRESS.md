# Mobile M2 Progress Report

Status: `M2C-live-Expo-Go-rotation-expiry-lost-phone-passed-native-build-pending`
Started: 2026-09-21  
Updated: 2026-09-30
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
- [x] iPhone v2 minimum-scope enrollment through Tailscale HTTPS passes.
- [x] Signed status, logout/recreation, Wi-Fi/cellular, Tailscale loss/reconnect, Core restart pass.
- [x] Device revoke, local erase, and lost-phone tailnet isolation pass with sanitized evidence.
- [x] Live Expo Go key rotation, new-key status, and app-restart status pass.
- [x] Explicit live session-expiry observation and signed recovery pass.
- [ ] Native development-build acceptance passes.
- [x] Private listener/Funnel boundaries, secret scan, docs, and isolated local M2C milestone commit pass.

Fresh enrollment ticket and Expo development build each require owner approval before action.
Do not record live tickets, signatures, tokens, private keys, tailnet identity, or phone data in
Git. Expo Go can provide provisional live evidence; native build acceptance requires separate
development-build approval.

## M2C local preparation and evidence

- 2026-09-30 owner decisions from `7f90383`: Expo cloud source upload and one iOS development
  build approved; intended iPhone registration and Developer Mode approved. The owner has no
  Apple Developer Program membership, declines paid membership, and requires $0 new spending
  for the project. The owner did not choose an `ios.bundleIdentifier`. Expo's physical-device
  EAS route requires Apple signing, so no EAS upload, configuration, registration, signing,
  or build was started. Official Expo and Apple guidance identifies a no-cost local route:
  Xcode on a Mac with a free Apple Account Personal Team, connected to the iPhone. Personal
  Team provisioning expires after seven days. Mac access is the current open prerequisite.
  The prior mobile gate still passes (38 Jest tests, Expo Doctor 21/21, both exports); the
  2026-09-29 read-only Tailscale check found one online iOS peer, private HTTPS 443 Serve to
  `http://127.0.0.1:8765`, Funnel off, and no Core or Metro listener. Phase C edits remain
  untouched. No new enrollment ticket was created.
- 2026-09-29 native continuation from `69112a9`: Phase C edits remain dirty and untouched.
  Mobile `npm.cmd run verify` passes: 38 Jest tests, Expo Doctor 21/21, 1,109 license
  records, production audit high/critical threshold, and Android/iOS static exports.
  Thirteen moderate transitive advisories remain. Read-only Tailscale preflight finds the host
  and one iOS peer online, one private HTTPS 443 Serve route with exact
  `http://127.0.0.1:8765` handler, Funnel disabled, and no Phase 8D ownership marker.
  Ports 8765 and 8081 have no listeners. No EAS configuration, source upload, signing,
  device registration, native binary, or new enrollment ticket was created. Separate owner
  decisions were requested for the $0 cloud upload/build, exact iOS bundle identifier,
  Apple membership/signing custody, and physical iPhone registration/Developer Mode.
- 2026-09-29 continuation from `9313c4a`: mobile `npm.cmd run verify` passed again:
  Prettier, ESLint, TypeScript, 38 Jest tests, Expo Doctor 21/21, 1,109 license records,
  production audit threshold (no high/critical advisories), and Android/iOS static exports.
  Thirteen moderate transitive advisories remain. Tailscale was online with one online iOS peer;
  Serve retained one HTTPS TCP 443 root handler to `http://127.0.0.1:8765`, Funnel had zero enabled
  entries, and no Phase 8D ownership marker existed. Port 8765 had zero listeners, so no live Core
  authentication check was possible in this preflight. `git diff --check` passed. RTK remains
  blocked by Windows Application Control; direct commands were used. Expo Go rotation and explicit
  post-expiry recovery remain accepted from prior live evidence. No native binary, signing, EAS
  configuration, device registration, or new ticket was created. The `$0` new-spend ceiling stands;
  separate owner decisions remain pending for cloud upload/build, Apple membership and signing
  custody, exact iOS bundle identifier, and physical-device registration/Developer Mode.
- 2026-09-29 continuation from `e5018b0`: owner-approved iPhone tailnet rejoin is online.
  Private HTTPS Serve still has one root handler to `http://127.0.0.1:8765`; Funnel is disabled;
  the existing route has no Phase 8D ownership marker and was not changed. Loopback-only Core
  passed `jarvis doctor` and returned HTTP 401 for unauthenticated private HTTPS status.
  Owner approved one three-scope five-minute ticket. Its Codex terminal did not become visible,
  so the unused ticket expired. At owner request, an ignored local CMD helper was checked without
  minting and supplied for a fresh terminal-displayed ticket. Owner confirmed physical-iPhone v2
  enrollment and signed status. Sanitized Core audit records `enrollment.completed` /
  `proof_verified` and `session.created` / `device_signature_verified`; the enrolled device is
  active at key version 1. No ticket content was added to source, reports, or Git. The unused
  first ticket appeared in local tool output during terminal shutdown after its expiry; its
  replacement was entered by the owner only in Command Prompt and Expo Go.
- Owner performed confirmed physical-iPhone key rotation in Expo Go. Local Core audit records
  `device.key_rotated` / `old_and_new_proof_verified`; key version advanced from 1 to 2.
  The two prior sessions are revoked, and Core created a new signed session. Owner confirmed
  signed status before and after restarting Expo Go. Core's existing identity test also rejects
  a request signed with the old key and session; a direct old-session attempt was not made on
  the physical phone. The later post-expiry check passed; independent native-build checks remain.
- A later status check created another signed session, but Core timestamps show it was created
  before the prior session expired. This proves near-expiry refresh, not the explicit post-expiry
  gate; that gate remains open.
- The replacement session subsequently reached its recorded `expires_at` with no newer session.
  Owner's first recovery report could not be correlated with Core audit after the temporary services
  stopped. With loopback Core and Metro restarted, owner repeated **Check Core status** and
  confirmed a fresh connected result. Core audit then showed one new signed session with
  `session.created` / `device_signature_verified`; its creation timestamp followed the prior
  session's `expires_at`. This closes the explicit post-expiry recovery gate.
- Current mobile verify: 38 Jest tests, Expo Doctor 21/21 after locked SDK 57 patch alignment,
  1,109 license records, no high/critical production advisories, and Android/iOS static exports
  pass. Thirteen moderate transitive advisories remain. Current Core remote/security targeted
  tests: 11 passed; full bootstrap suite: 1,129 passed, 3 skipped, 85.10% coverage. `uv lock
  --check`, `uv sync --locked`, Ruff lint, bootstrap pip-audit, 59-commit Gitleaks scan, and
  `git diff --check` pass. Ruff format and bootstrap mypy find only pre-existing Phase C edits.
  Standard mypy/pytest/pip-audit executables and RTK are blocked by workstation Application
  Control; bootstrap Python supplied current equivalent checks.
- Isolated continuation commit `a529ec1` was pushed to `origin/main`. Its [Mobile CI](https://github.com/DanCreates1/JARVIS/actions/runs/36650679127)
  and [Python CI](https://github.com/DanCreates1/JARVIS/actions/runs/36650679032) both passed.
  Unrelated Phase C edits remained unstaged.
- 2026-09-28 continuation starts from `dd30a92` on `main`, matching `origin/main`.
  Unrelated Phase C modifications and untracked files remain untouched. Owner approved one
  five-minute v2 phone ticket with only `client.status.read` and `session.revoke`, risk ceiling 0,
  and performed the physical-iPhone steps. The ticket appeared only in a trusted local terminal;
  its contents were not recorded. The phone enrolled through private HTTPS. Initial signed status
  returned HTTP 403 after successful session creation because the status handler reused an
  `identity.read`-guarded service method. Core now uses a status-specific `client.status.read` guard;
  an integration regression proves the two-scope status succeeds while `/api/v1/identity` remains
  denied. After loopback Core restart, owner confirmed signed status passed and Core logged HTTP 200.
  Owner then confirmed logout/recreation, signed status over cellular and Wi-Fi, fail-closed status
  while iPhone Tailscale was off, recovery when it reconnected, failure while Core was stopped,
  and signed status after Core restarted. Core logged HTTP 200 for the revoke-session request,
  HTTP 201 for a replacement session, and HTTP 200 for its signed status. Expiry, device revoke,
  rotation, local erase, and lost-phone checks remain open until individually observed.
- Owner separately approved revocation of the one active M2C phone identity. The trusted-local
  CLI revoked that exact device and its sessions without exposing its identifier. On iPhone, signed
  status failed and local credential erase removed the enrolled state. Core logged HTTP 401 for
  post-revocation status and remote session-revoke attempts. Sanitized audit shows
  `device.revoked` / `local_host_revoked` and `request.denied` / `session_revoked`. Tailnet removal,
  live key rotation, explicit session-expiry observation, and native-build checks remain pending.
- Owner approved tailnet removal and reported removing the locally matched iPhone row in the
  Tailscale Machines console. The first laptop check still saw an online iOS peer and a private
  Tailscale ping reply, so removal was initially unverified. Two later checks showed the sole iOS
  peer offline; the final private ping received no reply. The revoked JARVIS identity also denied
  signed status, and sanitized audit recorded `device.revoked` / `local_host_revoked` and
  `request.denied` / `session_revoked`. Lost-phone isolation now passes. No second machine was
  removed. Exact tailnet identifiers remain local only.
- Expo's compatibility check required SDK 57 patch alignment. Updated only `expo` to `~57.0.25`,
  `expo-linking` to `~57.0.11`, and `expo-router` to `~57.0.23` in the locked mobile workspace.
  The complete `npm.cmd run verify` gate now passes: 36 Jest tests; Expo Doctor 21/21; 1,109
  license records; no high/critical production advisories; Android/iOS static JS exports.
  Thirteen moderate transitive advisories remain. No native binary, signing, or EAS build ran.
- Same-day sanitized preflight: Tailscale host and one iOS peer online; one private HTTPS 443 Serve
  authority and one root handler target exact `http://127.0.0.1:8765`; Funnel has zero enabled
  entries. Phase 8D ownership marker absent. Core runs on one loopback listener; unauthenticated
  status returned HTTP 401. Existing unowned Serve route was not modified.
- Local Python virtual-environment executables are blocked by workstation Application Control.
  A real Python 3.11.16 interpreter with the locked bootstrap site-packages passes `jarvis doctor`,
  targeted remote/PWA regression (29 tests), and the full functional suite (1,129 passed, 3
  skipped). A first full run through a uv path alias hit three unrelated Windows executable-path
  tests because the alias is a name-surrogate reparse point; the real interpreter path passes.
  Current unrelated Phase C edits leave repository coverage at 84.97% against the 85% gate.
  Gitleaks scanned 58 commits with no leaks. Mobile 36 Jest tests, format, lint, typecheck,
  licenses, production audit threshold, and both exports pass. Expo Doctor is 20/21 because three
  SDK 57 patch versions need alignment; npm audit reports 13 moderate advisories.

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

- Earlier two-scope and current three-scope v2 tickets were used for separate live enrollments.
  The first three-scope ticket expired unused because its terminal was hidden; the owner requested
  and locally minted the replacement. Any further ticket needs fresh owner approval. Keep all
  ticket content out of chat, reports, logs, and Git.
- Temporary loopback Core and Metro were stopped after post-expiry verification. Ports 8765 and
  8081 have zero listeners; the existing unowned Serve route remains untouched. Do not use Phase
  8D launcher Run/Stop against that route.
- Physical iPhone pairing, network, logout, Core restart, revoke, local erase, tailnet
  lost-phone removal, Expo Go key rotation, and post-expiry signed recovery evidence passed.
  Independent native-build evidence remains.
- Development build has not started. The owner set a `$0` new-spend ceiling; cloud-build approval,
  Apple signing/account choice, and iOS bundle identifier remain separate pending decisions.
- Native key rotation is implemented and locally tested. Expo Go live rotation now has
  physical-iPhone, Core-audit, and restart evidence. Direct old-session rejection on the phone
  and native-build evidence remain unverified; Core's existing rotation test covers the former
  contract in a controlled integration test.

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
