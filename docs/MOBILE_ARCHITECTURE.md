# JARVIS Native Mobile Architecture

Status: M1A foundation in progress  
Updated: 2026-09-20

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

M1A contains only an offline-safe shell and validated non-secret environment name. It performs no
network request, persistence, telemetry, permission request, enrollment, or EAS account linkage.

## Security invariants

- Core remains canonical. Mobile cache never becomes authority.
- Browser cookie/CSRF identity and future native signed-session identity remain type-separated.
- No model, Garmin, notification-provider, or other service credential is shipped to the client.
- Production network trust, secure key storage, enrollment, and device revocation belong to M2.
- Generated output, dependencies, local Expo state, and native build output stay outside Git.

## Compatibility

M1A targets iOS first for live acceptance while keeping Android export-compatible. Node must be
`>=22.13.0 <25`; the current workstation uses Node 24.20.0. On Windows, use `npm.cmd` and `npx.cmd`
because PowerShell script shims are blocked by workstation execution policy.

Current Expo Go policy requires a physical iOS device and Expo CLI to be signed into the same free
Expo account before the device can open a development-server manifest. This authenticates manifest
signing only; M1A does not create or link an EAS project.
