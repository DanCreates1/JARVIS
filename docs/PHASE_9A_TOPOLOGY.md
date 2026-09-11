# Phase 9A Topology, Ownership, and Protocol Boundary

Phase 9A defines server-migration contracts. It does not migrate data, start a server, add a
replica, or enable a remote writer. Shipped configuration remains hard-locked to `local-only`.

## Profiles and roles

| Profile | Primary core/gateway | Laptop | Network-loss behavior |
| --- | --- | --- | --- |
| `local-only` | Laptop | Primary core, gateway, device node, offline core | Same local owner continues |
| `split` | Dedicated server | Device node plus explicitly declared offline core | Only negotiated offline capabilities remain; canonical ownership does not move |
| `server-primary` | Dedicated server | Device node | Remote work fails closed unless a later manifest explicitly declares offline capability |

`TopologyManifest` is an immutable desired-state document with exact host ID, epoch, nodes, roles,
capabilities, ownership map, and network-loss behavior. Its canonical sorted JSON has a SHA-256
digest. Changing any role, capability, owner, epoch, or fallback changes the digest and forces a
fresh negotiation.

Only `local-only` is accepted by `Settings`. Phase 9B now provides verified backup, restore,
shadow comparison, cutover-receipt, and rollback-receipt tooling, but intentionally does not widen
that executable setting. Phase 9C owns any deployment activation.

## Single-owner map

Every manifest covers all eleven domains exactly once. Duplicate, missing, unknown, or
role-incompatible owners are invalid.

| Domain | `local-only` owner | `split` / `server-primary` owner |
| --- | --- | --- |
| Identity | Laptop core | Server primary core |
| Sessions and replay | Laptop core | Server primary core |
| Conversations | Laptop core | Server primary core |
| Memory | Laptop core | Server primary core |
| Research | Laptop core | Server primary core |
| Tasks | Laptop core | Server primary core |
| Permission authority | Laptop core | Server primary core |
| Audit | Laptop core | Server primary core |
| Device settings | Laptop | Laptop device node |
| Computer effects | Laptop | Laptop device node |
| Media capture | Laptop | Laptop device node |

Offline fallback never rewrites this table. A disconnected laptop may use only capabilities listed
in its signed negotiation result's `offline_capabilities`; it cannot become canonical writer for
server-owned identity, sessions, conversations, memory, research, tasks, permissions, or audit.
Phase 9B defines exact-snapshot reconciliation and fenced ownership receipts. Those receipts remain
evidence, not runtime authority, until Phase 9C enforces them during deployment.

## Authenticated protocol negotiation

An enrolled service/laptop node needs the exact `topology.negotiate` device and session scope. It
sends `POST /api/v1/topology/negotiate` through the existing Phase 8 private TLS gateway and signs
method, authority, raw path/query, body digest, timestamp, nonce, audience, device, key version,
and session-token digest with its enrolled Ed25519 key.

The signed `ProtocolHello` binds:

- host, device/node, browser-independent signed session, and `jarvis-api` audience;
- topology profile, epoch, and exact manifest digest;
- supported versions and a signed minimum acceptable version; and
- offered capabilities plus the subset required for safe operation.

The server selects the highest common version not below the signed minimum. Protocol `1.0` is the
only shipped version. Capability output is the intersection of caller offers, the exact configured
node allowance, and the server registry. Unknown optional capability is returned as denied; an
unavailable required capability rejects the whole negotiation. Caller payload has no owner or role
field, so it cannot claim either.

The result expires with the authenticated session and contains only profile/epoch/digest, selected
version, configured roles, granted/denied capabilities, owned domains, bounded offline
capabilities, network-loss policy, and server node ID. It is not a new credential or permission
grant.

Stable failure codes include `scope_denied`, `host_mismatch`, `device_mismatch`,
`session_mismatch`, `session_expired`, `topology_profile_mismatch`, `topology_epoch_mismatch`,
`topology_digest_mismatch`, `node_not_allowed`, `protocol_version_mismatch`, and
`required_capability_unavailable`. Identity failures remain generic HTTP 401; authenticated
negotiation conflict returns HTTP 409 with a bounded code and generic message. Success and denial
audit stores no request body, capability list, key, token, signature, or private content.

## Threat and recovery rules

- Tailnet membership and forwarded identity/app-capability headers are network context, not JARVIS
  authorization. The backend remains loopback-only and still requires application identity.
- A signature replay is rejected by atomic nonce consumption. A stale timestamp, revoked device or
  session, wrong key/audience/scope, or mutated body fails before negotiation.
- Highest-common-version selection plus a signed minimum rejects forced downgrade. Unknown version
  never silently falls back.
- Capability advertisement grants nothing. The static manifest remains the owner and capability
  authority.
- Network loss never elects a new owner or replays an effect. Use only declared offline capability;
  otherwise fail closed.
- Roll back 9A by keeping `JARVIS_TOPOLOGY_PROFILE=local-only` and removing/ignoring the additive
  negotiation route. Existing Phase 8 phone/PWA behavior is unchanged.

## Verification

```powershell
uv run pytest --no-cov -q tests/unit/test_phase9_topology.py `
  tests/integration/test_phase8_remote_web.py `
  tests/security/test_phase9_topology_security.py
uv run python scripts/phase9a-topology-benchmark.py `
  --output runtime/phase9a/benchmark.json
uv run jarvis doctor
```

The benchmark freezes 10,000 valid and 10,000 downgrade/abuse negotiations, valid p95 <= 10 ms,
zero valid failures, zero false accepts, and <= 50 MiB RSS growth.

## Primary references checked

- [NIST SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final): network location grants no
  implicit trust; subject and device authentication/authorization are separate.
- [NIST SP 800-207A](https://csrc.nist.gov/pubs/sp/800/207/a/final): hybrid services need
  application/service identities and granular application-layer policy.
- [RFC 9421](https://www.rfc-editor.org/rfc/rfc9421.html): cover security-relevant HTTP components,
  bind time, and use unique nonces against replay; message signatures do not replace TLS.
- [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve): Serve applies tailnet
  access control and can forward identity/capability context, but localhost binding is required to
  prevent direct header spoofing.
