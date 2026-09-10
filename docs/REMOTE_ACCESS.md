# Phase 8A-8B remote identity and trusted browser boundary

Phase 8A supplies device identity. Phase 8B adds trusted browser sessions, origin/CSRF/CORS/CSP,
bounded request/rate policy, and low-risk remote approval rules. Neither subphase enables remote
networking. JARVIS still refuses non-loopback web binding; the PWA, TLS/private-network deployment,
and real-phone validation remain Phase 8C-8D.

## Security properties

- A trusted local terminal creates a five-minute, one-use enrollment challenge with exact device
  type, scopes, and risk ceiling.
- Each device supplies a unique Ed25519 public key and proves possession of the matching private
  key. JARVIS never creates or stores a device private key.
- Device credentials expire after 365 days. Sessions expire after 15 minutes and store only a
  SHA-256 token digest.
- Every session request and protected API request has an Ed25519 signature. The canonical message
  binds method, authority, raw path, raw query, body digest, date, nonce, audience, device ID, key
  version, and session-token digest.
- A nonce is consumed atomically and retained across restart for twice the accepted 60-second clock
  window. Concurrent or restarted replay fails closed.
- Effective authority is the intersection of enrolled device scope and session scope. No endpoint
  accepts a model-selected scope, device, key, token, or enrollment decision.
- Key rotation requires the old authenticated request plus proof from the new key, increments the
  key version, and revokes every old session. Local device revocation immediately revokes all
  sessions.
- Lifecycle and denial audit contains identifiers, outcome, reason code, and time only. It contains
  no token, challenge, signature, key material, request body, or private content. Denial records are
  capped at 1,000 per device or enrollment.

## Trusted-local administration

Create a challenge only while controlling the Windows host:

```powershell
uv run jarvis remote enroll "My phone" `
  --type phone `
  --scope identity.read `
  --scope events.read `
  --scope session.revoke `
  --scope key.rotate
```

The JSON challenge is shown once and expires in five minutes. Transfer it through a private local
channel. Device software must generate and securely retain its Ed25519 private key, then sign the
`jarvis-enrollment-v1` proof defined in `jarvis.remote.signing`.

Inspect or recover locally:

```powershell
uv run jarvis remote devices
uv run jarvis remote audit DEVICE_ID --after 0 --limit 100
uv run jarvis remote revoke DEVICE_ID --confirm-device-id DEVICE_ID
```

Revocation is the lost-device recovery path. It is irreversible for that device record; enroll the
device again with a new key if access should return.

## Version 1 HTTP contract

| Method and path | Authentication | Required scope | Result |
| --- | --- | --- | --- |
| `POST /api/v1/enrollments/complete` | enrollment challenge + key proof | local grant fixed at challenge creation | device metadata |
| `POST /api/v1/sessions` | signed request, no bearer token | requested scopes must be a device-scope subset | one-time bearer token |
| `POST /api/v1/browser/sessions` | signed request plus exact configured HTTPS `Origin` | requested scopes include `browser.session` and remain a device-scope subset | host-only secure cookie plus one-time in-memory CSRF token |
| `GET /api/v1/identity` | bearer token + signed request | `identity.read` | current device metadata |
| `GET /api/v1/events?after=N&limit=N` | bearer token + signed request | `events.read` | current-device audit only |
| `DELETE /api/v1/sessions/current` | bearer token + signed request | `session.revoke` | current-session revocation |
| `POST /api/v1/device/key` | bearer token + old-key request signature + new-key proof | `key.rotate` | rotated device metadata |

Every signed request sends exactly one of each header:

```text
Authorization: Bearer SESSION_TOKEN       # protected routes only
Host: exact-authority
X-Jarvis-Audience: jarvis-api
X-Jarvis-Date: UTC-RFC3339-timestamp
X-Jarvis-Device: device:...
X-Jarvis-Key-Version: 1
X-Jarvis-Nonce: canonical-base64url
X-Jarvis-Signature: canonical-base64url-Ed25519-signature
```

Clients must sign the exact bytes sent. Path and query are not normalized; JSON whitespace changes
the body digest. The maximum authenticated body is 1 MiB. Authentication errors are deliberately
generic over HTTP to avoid identity and token oracles.

## Phase 8B browser boundary

Browser bootstrap is disabled by default because `JARVIS_TRUSTED_BROWSER_ORIGINS` defaults to an
empty JSON array. Configure only exact reviewed HTTPS origins; HTTP, wildcard, `null`, credentialed,
path, query, fragment, duplicate, and suffix-confused origins are rejected. Phase 8D owns the real
private-network hostname and TLS deployment. Configuration alone does not open a listener.

An enrolled phone/browser requests a session with a signed
`POST /api/v1/browser/sessions`. Its enrolled scopes must include `browser.session`; add
`approval.review` only if that device may display exact low-risk approval prompts. The response:

- sets `__Host-jarvis-session` with `Secure`, `HttpOnly`, `SameSite=Strict`, `Path=/`, no `Domain`,
  and the existing 15-minute session expiry;
- returns the CSRF token once in JSON for memory-only client use; and
- persists only SHA-256 digests of both values and marks the row as a browser session.

Cookie-authenticated requests require the exact configured `Origin`. `POST`, `PUT`, `PATCH`, and
`DELETE` additionally require exactly one `X-Jarvis-CSRF` value. Signed API tokens and browser
cookies are different session types and cannot be exchanged. Logout clears the cookie and revokes
the durable session. Device revocation or key rotation invalidates browser sessions immediately;
restart preserves valid session state and denial audit.

Strict CORS returns credentials only for an exact trusted origin and never uses `*`. Preflight
permits only fixed v1 methods and headers. API CSP is `default-src 'none'`; the legacy loopback page
uses fixed SHA-256 hashes for existing inline style/script, not `unsafe-inline`. All API responses
add no-store/no-cache, no-sniff, deny-frame, no-referrer, restrictive permissions, same-origin
opener, and HSTS headers.

Fixed request ceilings are 100 headers, 32 KiB total header bytes, 2 KiB raw path, 8 KiB raw query,
and 1 MiB streamed body. Default fixed-window limits are 20 public and 240 authenticated requests
per minute per client IP, with a second bounded identity key and 4,096 maximum limiter entries.

Remote approval is not chat text. `RemoteBrowserApprovalSurface` accepts only a trusted
cookie-authenticated identity carrying `approval.review`, recent enrolled-device authentication,
the same host/device/session and capabilities as the canonical Phase 3 action, the exact displayed
fingerprint phrase, and a permission level within the enrolled device risk ceiling. Levels 2-4
always require exact trusted local-host approval. Phase 8B adds no remote action execution route.

## Operations and limits

- Keep `JARVIS_WEB_HOST=127.0.0.1`. Phase 8A-8B create no firewall rule, certificate, Tailscale grant,
  public listener, or background listener.
- Run `uv run jarvis doctor` to verify the identity database and confirm the loopback listener
  configuration.
- Server time and client time must differ by no more than 60 seconds.
- Client private-key storage is client-platform work. Do not place a private key in Git, logs,
  browser local storage, query strings, or model context.
- Existing unversioned `/api/*` routes remain local-only and are not a remote compatibility API.
- Locked runtime dependency evidence: `cryptography 50.0.1` (`Apache-2.0 OR BSD-3-Clause`),
  `cffi 2.1.1` (`MIT-0`), and `pycparser 3.0` (`BSD-3-Clause`), from installed package metadata.

## Deferred Phase 8 work

- Phase 8C: installable PWA, conversation/task transport, reconnect/resume, offline shell, and
  notification controls.
- Phase 8D: reviewed TLS/private-network deployment, firewall/Tailscale policy, external listener
  scan, and real-phone enrollment/revocation testing.
