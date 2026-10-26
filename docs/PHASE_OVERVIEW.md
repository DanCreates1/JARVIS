# JARVIS Phase Overview

## Completed prototype sequence — 2026-10-25

[PROTOTYPE_PLAN.md](PROTOTYPE_PLAN.md) is the sole delivery plan: Windows Core + existing PWA,
local text assistant, durable conversation/recovery. [Scope triage](PROTOTYPE_SCOPE_TRIAGE.md)
records historical code/tests, failures, holds and preserved work. **PROTO-0, PROTO-1 and PROTO-2
complete**. [PROTO-2.1 integrated evidence](PROTO_2_1_EVIDENCE.md) and
[PROTO-2.2 acceptance receipt](PROTO_2_2_EVIDENCE.md) prove the bounded **working prototype**.
Current estimate: **100% = 10/10 prototype acceptance groups**. Repeated corpus 8/10; polite tone
and one checklist format remain limited. Full mobile MVP, physical acceptance and production
readiness remain unestablished. Root/sidecar audits pass; native/provider holds remain. No phase queued.
Manual phone checks remain **skipped by owner; unverified**. No native or Garmin prerequisite.

## Historical portfolio status — superseded delivery ordering

The dated F15/mobile/Phase 0–11 status below preserves evidence. Older execution rules, next gates
and percentages describe those tracks only; use the prototype plan for current sequencing.

Updated: 2026-10-19

Owner override: **skip all further manual/physical phone checks**; outstanding rows are skipped
and unverified, not development blockers or passes. No phone-check requests until explicit owner
resumption. Automated code/security gates and authority/privacy/$0 controls remain enforced.
Current development: [F15 — daily-use workspace](phase-reports/PWA_F15_COMPLETION.md), shell v12.
Library/metadata/archive, safe Markdown/copy, attachment lifecycle/reuse, task timelines/filter/sort
and composer/recovery are implemented and automatically verified. Remote task cancellation stays
disabled under read-only scope; no trustworthy task/conversation relationship is inferred.
Production attachment/voice/task controls stay default off. No next phase queued. Active PWA
estimate: **98%**, based on verified F11–F15 feature milestones; remote control authority, native
dependency hold and aggregate physical acceptance remain separate/open.
Skipped phone checks add no implementation or acceptance credit.

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
| PWA MVP 4 | F15 shell v12 daily-use workspace verified; remote cancellation remains disabled. Dated F11–F14 evidence preserved. Phone checks skipped by owner, unverified; physical/MVP acceptance incomplete | No next phase queued; [F15 evidence](phase-reports/PWA_F15_COMPLETION.md); native audit hold remains |
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
- Authorized MVP 4 implementation and remaining gates: [PWA MVP 4 progress](phase-reports/PWA_MVP4_PROGRESS.md). Current source is shell v12; historical v6–v11 evidence remains dated. Manual phone checks stay skipped.
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

Foreground voice is implemented under [F13](PWA_F13_PUSH_TO_TALK.md); attachments/search/task views ship in [F14](PWA_F14_WORKFLOWS.md), with remote cancellation blocked by absent control authority.
Daily-use conversation/reply/attachment/task workspace is completed under [F15](PWA_F15_WORKSPACE.md).
Spoken replies/background voice, push notifications, widgets, proactive features, phone sensors/context,
health analytics, wearable writes, direct watch communication, and broad former M3–M9/H1–H8 work.
These do not block the basic app.
