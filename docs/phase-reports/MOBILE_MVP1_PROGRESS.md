# Mobile MVP 1 Progress

Status: `shell-local-verified-live-rotation-and-native-acceptance-pending`
Started: 2026-09-28
Updated: 2026-09-29

App completion estimate: **about 20%**. Four MVP milestones are weighted equally for this
planning estimate; MVP 1 is about four-fifths done, while MVP 2–4 are not yet implemented.
This percentage is not an acceptance gate.

## Scope

Finish M2C live iPhone/Core acceptance, then deliver the accessible Chat, Garmin, and Settings
shell. Messaging and Garmin integration belong to later MVPs; their empty states must not imply
those features already work.

## M2C live evidence

- Owner approved one five-minute v2 ticket limited to `client.status.read` and `session.revoke`,
  risk ceiling 0. Physical iPhone enrolled through private Tailscale HTTPS and passed signed Core
  status after a Core scope-guard fix. No ticket content or tailnet identifier entered Git.
- Owner confirmed logout and signed-session recreation; Wi-Fi, cellular, Tailscale off/on, Core
  stop/restart, and signed status recovery.
- Owner approved exact-device Core revocation. Signed status was denied; local credentials were
  erased. Sanitized audit shows device and session revocation reason codes.
- Owner approved removal of the locally matched iPhone from Tailscale. After the admin-console
  removal, the laptop's sole iOS peer became offline and private ping received no reply. The
  already revoked JARVIS identity separately denied application access.
- Temporary Core was stopped after live checks; port 8765 has no listener. The pre-existing
  unowned Tailscale Serve route was not changed.
- Live session-expiry and key-rotation checks remain. A fresh three-scope ticket needs separate
  owner approval. The removed phone must rejoin Tailscale before further live checks.
- Native build, signing, app-scheme, camera, SecureStore restart, VoiceOver, and Dynamic Type
  acceptance remain; no development build has started.

See [M2 progress](MOBILE_M2_PROGRESS.md) and [M2C acceptance](../MOBILE_M2C_ACCEPTANCE.md) for
the detailed matrix and security gates.

## Shell implementation

- Three persistent primary tabs: Chat, Garmin, Settings. Settings owns pairing, Core status,
  server-origin summary, session logout, disconnect, credential erase, and confirmed key rotation.
- Chat and Garmin show honest empty states. They send no requests and queue no privileged work.
- Shared color/spacing/radius/touch-target tokens, cards, banners, and empty-state components.
  Settings retains a labeled enrollment form and QR scanner; camera permission is requested only
  after choosing Scan QR.
- Connection presentation distinguishes unenrolled, unverified, connecting, connected,
  disconnected, offline, reconnecting, expired session, permission denied, recoverable error, and
  invalid setup. A restored device starts unverified; only successful signed status shows
  "Connected at last check." Session expiry triggers visible renewal state; errors never display
  API details.
- Text keeps React Native font scaling; Settings scrolls and wraps actions; controls have role
  labels and minimum 48-point height. Physical VoiceOver and Dynamic Type checks remain pending.

## Local checks

- 2026-09-29 continuation from `e5018b0`: owner rejoined the iPhone to the tailnet. Laptop
  preflight found one online iOS peer, one private HTTPS 443 Serve route to exact loopback Core,
  zero Funnel entries, and no Phase 8D ownership marker. Temporary Core bound only to
  `127.0.0.1:8765`; unauthenticated private HTTPS status returned HTTP 401. No Serve change was
  made. Owner approved the three-scope rotation ticket and operated the iPhone. One ticket was
  minted in a Codex terminal that did not become visible; it expired unused. Owner requested a
  CMD launcher, ran it locally, and confirmed the new ticket appeared in Command Prompt. The
  physical iPhone enrolled and passed signed Core status. Sanitized Core audit records
  `enrollment.completed` / `proof_verified` and `session.created` /
  `device_signature_verified`; device is active at key version 1 and enrollment protocol v2.
  Live rotation outcome remains pending.
- Expo SDK 57 patch alignment updated `expo`, `expo-camera`, and `expo-router` requirements and
  their lockfile resolution. Current `npm.cmd run verify` passes 38 Jest tests, Expo Doctor 21/21,
  1,109 license records, production high/critical audit threshold, and both static exports.
  Thirteen moderate transitive advisories remain.
- Relevant Core identity/security tests: 11 passed. Full bootstrap Python suite: 1,129 passed,
  3 skipped, 85.10% coverage. `uv lock --check`, `uv sync --locked`, Ruff lint, bootstrap
  `pip_audit`, Gitleaks (59 commits), and `git diff --check` pass. Repository Ruff format finds
  two unrelated Phase C files; bootstrap mypy finds the unrelated Phase C assignment at
  `src/jarvis/bootstrap.py:307`. Standard `uv run mypy`, `uv run pytest`, and `uv run pip-audit` are blocked by
  workstation Application Control. `rtk.exe` is also blocked; direct commands were used.
- Complete `npm.cmd run verify` passes: Prettier, ESLint, TypeScript, 38 Jest tests, Expo Doctor
  21/21, 1,109 license records, production audit threshold, and local Android/iOS static JS
  exports. Production audit reports 13 moderate transitive advisories, no high/critical ones.
  The first sandboxed attempt could not reach Expo Doctor's API; the approved network-enabled
  rerun passed. No native binary, signing, or EAS build ran.
- `git diff --check` and Gitleaks scans of 58 commits, current mobile source, docs, and remote
  auth source pass with no leaks.
- Relevant Core regression and full functional suite passed during M2C preparation: 29 targeted
  tests, then 1,129 passed and 3 skipped. Unrelated Phase C work remains dirty and untouched;
  repository-wide Ruff format and mypy failures are documented in M2 progress.

## Approval gates

- Each new enrollment ticket: exact scopes, five-minute lifetime, risk ceiling 0, explicit owner
  approval before minting.
- Physical iPhone rejoin and live steps: owner approval and owner-operated phone.
- iOS development build, signing path, bundle identifier, Apple account, and any cost: separate
  explicit owner decisions before action.
