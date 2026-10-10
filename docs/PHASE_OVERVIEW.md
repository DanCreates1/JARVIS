# JARVIS Phase Overview

Updated: 2026-10-09

## Active product path

The $0 iPhone Home Screen PWA is the active product path. Existing Phase 8 PWA chat and secure
connection are accepted; [PWA Garmin](PWA_GARMIN.md) adds the remaining read-only Garmin view.
Native M2C acceptance is deferred because there is no Mac or paid Apple membership. The native
milestones below are retained as historical planning context, not an active sequence:

1. **MVP 1 — Design and connection** — local shell and Expo Go checks passed; native build unverified.
2. **MVP 2 — Chat** — text, streaming, history, cancel, retry, reconnect.
3. **MVP 3 — Garmin** — private read-only daily health/activity summaries through Core.
4. **MVP 4 — Polish and release** — physical-device recovery, accessibility, performance, and an
   optional explicitly authorized development build.

**Phone app goal complete** means an enrolled iPhone can securely send text to JARVIS, stream an
answer, view basic read-only Garmin data, recover from ordinary connection failures, and
disconnect cleanly.

For deferred native history, see [Native Mobile Milestones](MOBILE_PHASES.md),
[Mobile Architecture](MOBILE_ARCHITECTURE.md), and
[M2C Acceptance](MOBILE_M2C_ACCEPTANCE.md). Existing phase reports remain the detailed historical
record.

## Current status

| Track | Status | Next gate |
| --- | --- | --- |
| Phone PWA | Physical-iPhone chat accepted; M3A/M3B complete; M3C shell v6 repairs offline logout and obsolete response/reconnect handling with synthetic evidence | Pending grouped health-read enrollment/recovery decision and physical-iPhone acceptance |
| PWA MVP 4 | M4A shell v7 accessibility/reconnect fixes pass synthetic lifecycle and desktop checks | Physical accessibility, chat cancel/retry/history, performance and release acceptance remain; M3C stays separate |
| Native MVP | Expo Go checks passed; independent native build unverified and deferred under $0/no-Mac constraint | No active native gate |
| Mobile MVP 2 | Deferred | No active native gate |
| Mobile MVP 3 | Deferred | No active native gate |
| Mobile MVP 4 | Deferred | No active native gate |
| Phase 0 | Complete; continuous audit | Maintenance |
| Phase 1 | Implemented; formally `blocked-external` | NVIDIA latency and local-cold revalidation |
| Phase 2 | Complete; continuous listening default-off | Maintenance |
| Phase 3 | Implemented; live closeout pending | Separately authorized live effects only |
| Phases 4–8 | Complete | Maintenance |
| Agentic expansion A–I | A–G and E/H/K baselines complete; IA local email read/prepare complete; aggregate I `blocked-external`; Phase C Wikimedia `authentication_required` preserved | IB needs provider choice and fresh credential/private-read authority; writes need exact approval plus fresh external-effect authority |
| Phase 9 | Repository implementation complete; deployment blocked external | Authorized server target only |
| Phase 10 | Generic boundary complete; previous vendor integration deferred | PWA Garmin path covers current read-only phone goal |
| Phase 11 | Complete; proactive/effect paths default-off | Maintenance |

## Execution rules

- Use the PWA Garmin acceptance list for current phone work; native mobile milestones are deferred.
- Current MVP 3 evidence and M3A/M3B/M3C gates: [PWA MVP 3 progress](phase-reports/PWA_MVP3_PROGRESS.md).
- Authorized MVP 4 accessibility work and remaining gates: [PWA MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md). Reload current shell v7 for new acceptance; historical M3C v6 evidence remains unchanged.
- Preserve Core as sole authority, memory, routing, permission, and audit system.
- Keep production Core loopback-bound behind approved private-network HTTPS.
- Follow the root Codex confirmation policy: routine requested work proceeds; important new
  enrollment/scopes, login/MFA, signing, costs, deployments and App Store decisions need confirmation
  only when not already explicitly approved.
- Preserve unrelated work and historical completion evidence. Run focused checks during work and
  full applicable release/security gates before milestone closure.
- Detailed Phase 0–11 execution remains governed by
  [Codex Phase Playbook](CODEX_PHASE_PLAYBOOK.md) when one of those phases is explicitly invoked.

## Deferred backlog

Voice, photos/files, push notifications, widgets, proactive features, phone sensors/context,
health analytics, wearable writes, direct watch communication, and broad former M3–M9/H1–H8 work.
These do not block the basic app.
