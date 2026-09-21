# JARVIS Native Mobile Architecture

Status: M1B complete; M2A contract implemented  
Updated: 2026-09-21

## Boundary

The Expo/React Native client is a presentation and device-I/O surface. JARVIS Core remains the
canonical brain, authority source, memory store, model router, audit boundary, and future health
store. The mobile client cannot mint permission grants or hold model/provider credentials.

The existing PWA remains a supported fallback, admin/compatibility surface, and API-behavior
reference. Native and PWA share versioned `/api/v1` contracts, not UI code or authentication state.

## Workspace

`mobile/` is an independent npm workspace using Expo SDK 57, React Native 0.86, TypeScript, Expo
Router, and Continuous Native Generation. Native `ios/` and `android/` directories are not committed
unless a later reviewed native-module requirement proves necessary.

The intended layering is:

- `app/`: routes and navigation composition.
- `src/core/`: future API, request-signing, authentication, secure storage, connectivity, and cache
  policy.
- `src/features/`: future chat, voice, media, files, health, notification, device, and settings
  features.
- `src/ui/`: accessible reusable presentation primitives.
- `src/testing/`: fixtures and test helpers.

M1 contains only an offline-safe shell and validated non-secret environment name. M2A adds pure
cross-language request/enrollment canonicalization and test vectors; it still performs no network
request, key persistence, telemetry, permission request, or EAS account linkage.

## Security invariants

- Core remains canonical. Mobile cache never becomes authority.
- Browser cookie/CSRF identity and native signed-session identity remain type-separated.
- No model, Garmin, notification-provider, or other service credential is shipped to the client.
- Enrollment v2 binds a normalized exact HTTPS server origin. Core persists that binding and rejects
  every signed session or API request whose authority differs. Enrollment v1 remains available for
  existing PWA clients.
- HTTP origins require an explicit development-only loopback override. They cannot be used for a
  non-loopback host.
- Private-key generation and SecureStore persistence remain M2B work; no private key or live
  credential is present in the repository.
- Generated output, dependencies, local Expo state, and native build output stay outside Git.

## Compatibility

M1A targets iOS first for live acceptance while keeping Android export-compatible. Node must be
`>=22.13.0 <25`; the current workstation uses Node 24.20.0. On Windows, use `npm.cmd` and `npx.cmd`
because PowerShell script shims are blocked by workstation execution policy.

Current Expo Go policy requires a physical iOS device and Expo CLI to be signed into the same free
Expo account before the device can open a development-server manifest. This authenticates manifest
signing only; M1A does not create or link an EAS project.

## Quality gate

M1B adds a separate least-privilege GitHub Actions workflow for the mobile workspace. It installs
only the committed npm lock, rejects lock drift, checks formatting, lint, strict TypeScript, Jest
coverage, Expo package compatibility, dependency licenses, high/critical production advisories,
and deterministic Android/iOS exports. It has read-only repository permission and receives no
secrets. Python CI remains separate and unchanged.

## Auth contract

The signed HTTP profile remains `jarvis-http-signature-v1` and continues to bind method, authority,
raw path/query, body digest, UTC timestamp, nonce, audience, device/key identity, and session-token
digest. Enrollment v1 keeps its original proof bytes. Enrollment v2 adds the normalized server
origin to `jarvis-enrollment-v2` proof bytes and stores it with the device.

`GET /api/v1/client/status` now advertises API protocol version, server time, sorted capabilities,
and compatibility flags. Older PWA clients can ignore these additive fields. Shared deterministic
vectors in `tests/fixtures/remote_signing_vectors.json` are consumed by Python and TypeScript tests.
