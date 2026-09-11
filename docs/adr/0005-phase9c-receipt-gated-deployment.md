# ADR 0005: Receipt-Gated Single-Replica Deployment

Status: accepted
Date: 2026-09-11

## Context

Phase 9A defines one-owner topology and authenticated capability negotiation. Phase 9B creates an
encrypted accepted snapshot and chained owner-transition receipts. Neither proves that executable
code, service configuration, database path, host role, or release bytes match the reviewed state.
Starting a remote writer from configuration alone risks split ownership, stale code, unsafe
fallback, or unreviewed public exposure.

## Decision

Keep local-only as default. Permit `split` or `server-primary` runtime only with deployment
enforcement enabled and complete pinned paths plus canonical SHA-256 digests. Before opening any
writable store, verify exact topology, node/role/epoch, release artifact, Python patch version,
database path/integrity, Phase 9B receipt, deployment manifest, and monotonic deployment-state
receipt. Bind JARVIS to loopback behind private Tailscale Serve HTTPS.

Support one core replica only. Keep device-owned effects/capture on laptop. Under partition, permit
only declared read/offline capability and never transfer shared ownership or replay an effect.
Use immutable release staging and compare-and-swap promotion/rollback with last-known-good state.
Expose status-only public health and bounded typed internal telemetry.

## Consequences

- Missing, malformed, symlinked, oversized, duplicate-key, stale, or mismatched control input blocks
  startup before SQLite initialization.
- A valid activation permits normal database growth; every restart still validates owner, schema,
  integrity, path, release, topology, and receipt chain.
- Remote configuration cannot silently enable itself. Actual server/Tailscale/systemd mutations need
  separate operator authority and live acceptance evidence.
- SQLite remains viable for one writer. Multiple replicas, automatic failover/election, public
  ingress, and PostgreSQL remain deferred until measured requirements justify them.

## Rejected alternatives

- Treating a Phase 9B receipt, tailnet membership, source IP, or forwarded identity header alone as
  runtime authority.
- Mutable tags, unpinned package installation, in-place release overwrite, or restart without an
  exact health probe.
- Tailscale Funnel, public reverse proxy, direct JARVIS/Ollama/database exposure, or root service.
- Multi-primary SQLite, automatic laptop promotion, queued offline shared writes, or effect replay.
