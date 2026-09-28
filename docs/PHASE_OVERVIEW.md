# JARVIS Phase Overview

Updated: 2026-09-28

## Active product path

Native mobile MVP is the active execution path. Work proceeds in this order:

1. **MVP 1 — Design and connection** — active; finish M2C live iPhone/Core acceptance.
2. **MVP 2 — Chat** — text, streaming, history, cancel, retry, reconnect.
3. **MVP 3 — Garmin** — private read-only daily health/activity summaries through Core.
4. **MVP 4 — Polish and release** — physical-device recovery, accessibility, performance, and an
   optional explicitly authorized development build.

**Mobile MVP complete** means an enrolled iPhone can securely send text to JARVIS, stream an
answer, view basic read-only Garmin data, recover from ordinary connection failures, and
disconnect cleanly.

See [Native Mobile Milestones](MOBILE_PHASES.md),
[Mobile Architecture](MOBILE_ARCHITECTURE.md), and
[M2C Acceptance](MOBILE_M2C_ACCEPTANCE.md). Existing phase reports remain the detailed historical
record.

## Current status

| Track | Status | Next gate |
| --- | --- | --- |
| Mobile MVP 1 | M1 foundation complete; M2A/M2B local auth complete; M2C live evidence pending | Owner-approved ticket and physical-iPhone/Tailscale matrix |
| Mobile MVP 2 | Not started | MVP 1 complete; add scoped native chat/history/cancel contracts |
| Mobile MVP 3 | Planned | MVP 2 complete; resolve Python runtime/dependency gate and authorize any live account test |
| Mobile MVP 4 | Planned | MVP 1–3 complete; owner approval for any build/signing |
| Phase 0 | Complete; continuous audit | Maintenance |
| Phase 1 | Implemented; formally `blocked-external` | NVIDIA latency and local-cold revalidation |
| Phase 2 | Complete; continuous listening default-off | Maintenance |
| Phase 3 | Implemented; live closeout pending | Separately authorized live effects only |
| Phases 4–8 | Complete | Maintenance |
| Phase 9 | Repository implementation complete; deployment blocked external | Authorized server target only |
| Phase 10 | Generic boundary complete; previous vendor integration deferred | Mobile MVP 3 supersedes Garmin planning only |
| Phase 11 | Complete; proactive/effect paths default-off | Maintenance |

## Execution rules

- Use the four mobile milestones, not the former M3–M9 or H1–H8 sequence.
- Preserve Core as sole authority, memory, routing, permission, and audit system.
- Keep production Core loopback-bound behind approved private-network HTTPS.
- Require fresh owner authority for enrollment tickets, live Garmin credentials/MFA, signing,
  cloud builds, costs, deployments, and App Store work.
- Preserve unrelated work and historical completion evidence. Run focused checks during work and
  full applicable release/security gates before milestone closure.
- Detailed Phase 0–11 execution remains governed by
  [Codex Phase Playbook](CODEX_PHASE_PLAYBOOK.md) when one of those phases is explicitly invoked.

## Deferred backlog

Voice, photos/files, push notifications, widgets, proactive features, phone sensors/context,
health analytics, wearable writes, direct watch communication, and broad former M3–M9/H1–H8 work.
These do not block the basic app.
