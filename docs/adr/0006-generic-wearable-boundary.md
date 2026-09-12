# ADR 0006: Generic Wearable Boundary Before Vendor Adapter

Status: Accepted
Date: 2026-09-11

## Context

Wearable vendors expose incompatible transports, lifecycle rules, permissions, telemetry, device
states, legal terms, and distribution paths. Meta DAT is a changing Developer Preview and its
binding terms require authenticated review. Wear OS is Android-specific and may use a Google cloud
relay. Apple Watch development requires Apple hardware and agreements. Garmin direct health access
is enterprise-gated and may create commercial cost.

Capability discovery is especially dangerous if treated as permission. Camera, microphone, display,
notifications, input, and health also carry different disclosure and retention risks. JARVIS must
not let a vendor SDK or model response silently widen Phase 3 or Phase 8 authority.

## Decision

Create an owned `jarvis.wearables` boundary before any vendor adapter:

- protocol-versioned capability descriptors for audio input/output, display, camera, input,
  notification, and health;
- immutable operation envelopes with exact purpose, host/device/session, data class, byte/time/event
  limits, indicator requirement, ephemeral retention, and no cloud disclosure;
- a negotiation result that can report availability and permission but always grants zero
  authorization;
- exact expiring host-issued capability authorization checked against trusted adapter state;
- content-free receipts, replay denial, cancellation, permission/version/limit errors, and
  disconnect/removal behavior; and
- a deterministic simulator implementing the same port for CI.

Meta DAT phone bridge is the provisional Phase 10B adapter candidate. No Meta package, source,
generated code, binary, account, term acceptance, or device registration is part of this decision.

## Consequences

- Core contracts and tests proceed without vendor terms, hardware, mobile SDKs, or network access.
- Vendor adapters remain replaceable; removing one leaves the core contract and simulator intact.
- Phase 8 identity and Phase 3 approval remain the only sources of JARVIS authority.
- Camera/microphone are always media and indicator-gated; health is always health-classified.
- A mobile bridge, live device, vendor terms, telemetry settings, and distribution remain explicit
  Phase 10B/10C gates.
- The generic API is intentionally conservative: no background operation, retained payload, raw
  health value, cloud route, or vendor-specific display tree is represented in Phase 10A.

## Rejected alternatives

- Import Meta types into core: preview API churn and legal coupling.
- Treat pairing or discovered capability as authorization: confused-deputy and replay risk.
- Start with Garmin health synchronization: enterprise access, possible cost, and unnecessary
  sensitive-data scope.
- Depend on unofficial consumer-account connectors: reliability and vendor-policy risk.
- Wait for real hardware before defining contracts: prevents hardware-independent security and
  removal tests.

## Reversal

Delete the isolated package and ADR. No migration, credential, runtime state, listener, mobile
project, vendor dependency, or device setting is created by Phase 10A.
