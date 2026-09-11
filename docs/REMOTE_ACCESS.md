# Phase 8 remote identity, trusted browser, PWA, and private deployment boundary

Phase 8A supplies device identity. Phase 8B adds trusted browser sessions, origin/CSRF/CORS/CSP,
bounded request/rate policy, and low-risk remote approval rules. Phase 8C adds an installable,
offline-safe shell plus scoped status/task/chat and resumable event transport. Phase 8D deploys
that boundary through tailnet-only Tailscale Serve HTTPS while JARVIS stays loopback-only.

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
| `GET /api/v1/client/status` | browser cookie + exact origin | `client.status.read` | bounded device/session/task-count status |
| `GET /api/v1/client/tasks?limit=N` | browser cookie + exact origin | `client.tasks.read` | status-only task summaries; no objective, arguments, or outputs |
| `POST /api/v1/client/subscriptions` | browser cookie + exact origin + CSRF | `events.read` plus each topic scope | opaque session-owned subscription and initial cursor |
| `GET /api/v1/client/events?subscription_id=...&after=N` | browser cookie + exact origin | `events.read` | finite SSE page with monotonic cursor headers |
| `DELETE /api/v1/client/subscriptions/ID` | browser cookie + exact origin + CSRF | `events.read` | clear exact owned subscription buffer |
| `POST /api/v1/client/chat` | browser cookie + exact origin + CSRF | `client.chat` | idempotent request result plus streamed private in-memory events |

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

Cookie-authenticated unsafe requests require the exact configured `Origin`. Safe `GET`/`HEAD`
requests may use the PWA's exact `X-Jarvis-Browser-Origin` only when iOS standalone mode omits
`Origin` or sends `Origin: null`; hostile or missing fallback is denied. `POST`, `PUT`, `PATCH`, and
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

## Phase 8C PWA and reconnect boundary

The static shell is served at `/app/`. It contains separate same-origin script/style assets, a web
manifest, icon, and service worker. CSP contains no inline-script/style exception. The service
worker caches only five `/app/` shell assets. `/api/*`, authentication state, chat/task data,
notification text, and user content are never added to Cache Storage. The fixed packaged shell
ceiling is 250 KiB. Offline mode never queues chat, task changes, approvals, or other effects.

Enrollment uses Web Crypto Ed25519. The PWA generates a non-exportable private `CryptoKey` and
stores that structured-clone key in its dedicated IndexedDB database; only the public key is
exported for the existing Phase 8A proof. The user pastes the one-time local enrollment ticket.
The ticket, key, CSRF value, session ID, cursor, and subscription ID are never placed in a URL,
browser local storage, service-worker cache, notification, or model context. CSRF remains only in
JavaScript memory; cursor/subscription state is tab-scoped `sessionStorage`. Reloading or closing
the tab requires a fresh signed browser bootstrap before any state-changing request.

Use these exact enrollment scopes for the Phase 8C client:

```powershell
uv run jarvis remote enroll "My PWA" `
  --type browser `
  --scope browser.session `
  --scope identity.read `
  --scope events.read `
  --scope session.revoke `
  --scope client.chat `
  --scope client.tasks.read `
  --scope client.status.read `
  --risk-ceiling 1
```

`chat`, `tasks`, and `device` are desired subscription topics. Each additionally requires its own
product scope. Subscriptions bind exact host, device, and browser-session IDs, expire no later than
the browser session, retain at most 256 events/256 KiB, and cap at four per session/64 process-wide.
Each event is at most 64 KiB. Private chat deltas live only in bounded process memory. A reconnect
sends the last accepted cursor and receives only later events. Duplicate cursors are ignored by the
client; a gap or expired cursor causes a clean state refresh/new subscription, never guessed data.
Server restart intentionally drops volatile event buffers; durable conversation/task state remains
canonical and the client creates a new subscription.

Chat requests carry a client-generated request ID. The server keeps at most 128 session-bound,
128-KiB in-memory results, so response loss can retry without a second model turn while retained.
This is not permission or effect idempotency: the Phase 8C route has no task-run, approval,
computer-action, or offline-effect endpoint. One tab owns the live stream through the browser Locks API where
available. Other tabs remain read-only until they acquire ownership or establish a new session.

Notifications require an explicit user gesture and browser permission. They are non-persistent,
silent, and always use generic text: `JARVIS has an update.` Message/task content, identifiers, and
links are excluded. Remote voice capture is not enabled by Phase 8C.

Online logout revokes the durable browser session, clears its server event/request buffers, deletes
the host-only cookie, returns `Clear-Site-Data` for cache/cookies/storage, and makes the client erase
its IndexedDB key, tab state, notification setting, Cache Storage, and service-worker registration.
Offline local erasure cannot contact the host or directly delete an HttpOnly cookie; it removes all
script-accessible credentials and the remaining server session expires within 15 minutes. Use local
device revocation for a lost/offline phone.

## Operations and limits

- Keep `JARVIS_WEB_HOST=127.0.0.1`. Phase 8A-8C create no firewall rule, certificate, Tailscale grant,
  public listener, or background listener.
- Run `uv run jarvis doctor` to verify the identity database and confirm the loopback listener
  configuration.
- Server time and client time must differ by no more than 60 seconds.
- Client private keys are non-exportable Web Crypto keys in dedicated IndexedDB. Do not place any
  key in Git, logs, browser local storage, query strings, Cache Storage, or model context.
- Existing unversioned `/api/*` routes remain local-only and are not a remote compatibility API.
- Locked runtime dependency evidence: `cryptography 50.0.1` (`Apache-2.0 OR BSD-3-Clause`),
  `cffi 2.1.1` (`MIT-0`), and `pycparser 3.0` (`BSD-3-Clause`), from installed package metadata.

## Deferred remote work

- Remote voice, persistent push, remote effects, public access, and multi-replica state remain
  unavailable. They require separate future threat models and acceptance gates.

## Phase 8D private deployment controls

Phase 8D uses Tailscale Serve as the HTTPS gateway and keeps JARVIS on
`http://127.0.0.1:8765`. It forbids Funnel, direct LAN/tailnet binding, port forwarding, broad
firewall rules, and multiple JARVIS replicas. The deployment planner derives the exact `.ts.net`
origin from bounded live Tailscale status instead of accepting a caller-supplied hostname.

Use `scripts/phase8d-private.ps1` for preflight, foreground run, sanitized status, and owned-route
rollback. The launcher refuses an offline/malformed node, public Funnel, non-loopback backend
listener, occupied backend port, existing unowned Serve route, invalid origin/port, missing policy/Certificate
Transparency acknowledgement, or failed JARVIS diagnostics. Runtime status and the ownership marker
remain under ignored `runtime/`; no Tailscale status, login identity, key, ticket, or phone data is
committed.

Tailscale HTTPS places the exact machine FQDN in public Certificate Transparency logs. Review and,
if needed, rename the node before enabling Serve. Tailnet grants must restrict the intended source
to this host's TCP 443; tailnet access never replaces JARVIS enrollment. Full operator steps,
live-test matrix, lost-phone recovery, and rollback are in
[`PHASE_8D_DEPLOYMENT.md`](PHASE_8D_DEPLOYMENT.md).

The completed physical-iPhone matrix covers install, exact minimum scopes, minimized status/tasks,
public-fixture chat, generic notifications, cache privacy, network loss/reconnect, restart,
immediate revocation, offline erase, and fresh-key re-enrollment. iOS standalone safe reads may
send no `Origin` or opaque `Origin: null`; the PWA supplies its exact `window.location.origin` in a
custom header. Only safe `GET`/`HEAD` may use that reviewed fallback. Unsafe methods still require
the browser `Origin` plus CSRF proof, and hostile/missing fallback fails closed.
