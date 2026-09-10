# ADR 0002: Ed25519 device identity with hashed short-lived sessions

- Status: Accepted
- Date: 2026-09-10

## Context

The phone/PWA roadmap needs unique revocable device identity before any remote network or user
interface is enabled. Tailnet membership alone cannot authorize JARVIS actions. A shared API key
would prevent per-device revocation and would expose the same secret to every client. Bearer-only
sessions would allow a stolen token to act without proving possession of the enrolled device key.

## Decision

Use a unique Ed25519 key pair per enrolled device. The client owns the private key; JARVIS stores
only the public key and SHA-256 fingerprint. A trusted local command fixes device metadata, scopes,
risk ceiling, and a five-minute one-use challenge. Enrollment completes only after challenge match
and Ed25519 proof.

Issue opaque 15-minute sessions only after a directly signed device request. Store only the token
SHA-256 digest. Require bearer token plus an Ed25519 signature on every protected request. Canonical
request version 1 length-prefixes and binds method, authority, raw path/query, body digest, date,
nonce, audience, device, key version, and bearer-token digest. Atomically consume nonces in SQLite.

Rotation requires authentication by the current key and proof by the new key. Rotation increments
the key version and revokes existing sessions. Trusted-local revocation marks the device revoked and
revokes all sessions. The listener remains loopback-only until separate Phase 8D deployment work.

## Consequences

Positive consequences:

- stolen session tokens are unusable without the device private key;
- each device has independent scope, expiry, rotation, revocation, and audit;
- no shared authentication secret or plaintext session token exists in server persistence;
- SQLite transactions make replay and lifecycle changes restart-safe on the current single host;
- owned contracts can later sit behind a TLS/private-network gateway without changing authority.

Costs and constraints:

- client software must securely generate, store, rotate, and delete an Ed25519 private key;
- client and host clocks must remain within 60 seconds;
- raw request-target and body-byte canonicalization must be implemented exactly;
- this is application authentication, not transport encryption or browser-origin hardening.

## Alternatives considered

### Shared HMAC or API key

Rejected. It creates shared blast radius, weak device attribution, and poor lost-device recovery.

### Bearer token without proof of possession

Rejected. Token theft alone would be sufficient for access during the token lifetime.

### WebAuthn, passkeys, or OIDC as the Phase 8A core

Deferred to the trusted browser surface. Those mechanisms can become enrollment/authentication
adapters, but do not replace device, audience, scope, replay, expiry, and revocation enforcement.

### Enable Tailscale/TLS and a non-loopback listener now

Rejected for Phase 8A. Network deployment, certificate lifecycle, firewall policy, external scan,
and real-device evidence form a separate reviewed Phase 8D boundary.
