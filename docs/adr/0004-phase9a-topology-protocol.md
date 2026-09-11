# ADR 0004: Static Single-Owner Topology and Signed Capability Negotiation

Status: accepted
Date: 2026-09-10

## Context

Phase 8 runs one laptop-hosted JARVIS replica. Its SQLite state, sessions, replay cache, rate state,
subscriptions, permission authority, and device effects have one process/local host owner. Moving
selected work to a server without an explicit ownership and compatibility contract risks
split-brain writes, capability escalation, replay, and unsafe fallback.

## Decision

Represent `local-only`, `split`, and `server-primary` as immutable validated manifests. Every
mutable state/effect domain has exactly one configured owner. Shared durable state belongs to the
single primary core; device settings, computer effects, and capture belong to the laptop device
node. Offline capability never transfers canonical ownership.

Keep executable settings hard-locked to `local-only` in 9A. Add protocol `1.0` negotiation only
inside an enrolled Phase 8 Ed25519 signed session carrying exact `topology.negotiate` scope. Bind
host, device, session, audience, profile, epoch, manifest digest, supported/minimum version, and
offered/required capabilities. Select highest common version. Grant only the intersection with the
configured node and server registry. Audit content-free outcomes.

## Consequences

- No server, second writer, database migration, or failover becomes active in 9A.
- A caller cannot self-assign role, ownership, or capability.
- Manifest drift, stale session, replay, downgrade, mismatch, or missing required capability fails
  closed with a stable bounded code.
- Phase 9B can reuse the manifest digest and one-owner invariants for backup, shadow, cutover,
  reconciliation, and rollback.
- Phase 9C can put mTLS/SPIFFE or another service-identity adapter behind the same owned contract if
  deployment measurements justify it.

## Rejected alternatives

- Tailnet membership, source IP, or forwarded headers as sole authorization.
- Caller-declared role/owner or optimistic capability enablement.
- Multi-primary SQLite, automatic owner election, or offline writes to server-owned domains.
- PostgreSQL, service mesh, queue, or second replica before measurements and migration rehearsal.
