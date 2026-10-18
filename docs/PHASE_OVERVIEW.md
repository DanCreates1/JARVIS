# JARVIS Phase Overview

Updated: 2026-10-17

Owner override: **skip all further manual/physical phone checks**; outstanding rows are skipped
and unverified, not development blockers or passes. No phone-check requests until explicit owner
resumption. Automated code/security gates and authority/privacy/$0 controls remain enforced.
Completed development: [F12 — Chat / Garmin / Settings navigation](PWA_F12_NAVIGATION.md), shell v9.
Proposed next subphase: [F13 — PWA push-to-talk](PWA_F13_PUSH_TO_TALK.md); planning complete,
implementation not started. Active PWA estimate: **94%**, milestone-based, including verified F12
navigation; planning and skipped phone checks add no acceptance credit.

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
| Phone PWA | Historical chat acceptance; M3A/M3B complete; remaining manual M3C phone checks skipped by owner, unverified | Continue development; health-access authority remains separate, no new enrollment granted |
| PWA MVP 4 | F12 shell v9 Chat / Garmin / Settings implemented; automated gates pass. Dated F11 evidence preserved. Remaining F11/M4A phone checks skipped by owner, unverified; MVP physical acceptance not claimed | Proposed [F13 push-to-talk](PWA_F13_PUSH_TO_TALK.md), planning only; [F12 completion](phase-reports/PWA_F12_COMPLETION.md); native audit hold remains |
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
- Authorized MVP 4/F11 implementation and remaining gates: [PWA MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md). Current source is shell v9; historical v6/v7/v8 evidence remains dated. Manual phone checks stay skipped.
- F11 physical acceptance initiated at `4fa75e3`: [phone ledger and frozen performance targets](PWA_F11_PHYSICAL_ACCEPTANCE.md). Host readiness and fresh 63 lifecycle/24 desktop checks pass; no new phone observation or phase closure.
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

Foreground PWA voice input now has a proposed [F13 plan](PWA_F13_PUSH_TO_TALK.md); no implementation yet.
Spoken replies/background voice, photos/files, push notifications, widgets, proactive features, phone sensors/context,
health analytics, wearable writes, direct watch communication, and broad former M3–M9/H1–H8 work.
These do not block the basic app.
