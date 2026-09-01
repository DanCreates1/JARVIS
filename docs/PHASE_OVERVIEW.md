# JARVIS Phase Overview

Updated: 2026-08-31

This is the concise execution view of the master roadmap. Status describes implemented code,
not just design work. "Sol thinking" is the recommended reasoning effort for the main
implementation work in that phase.

To execute a phase with Codex, use `Initiate Phase X and finish it.` Root `AGENTS.md` then loads
the full [Codex Sol phase execution playbook](CODEX_PHASE_PLAYBOOK.md), including prerequisites,
implementation protocol, acceptance gates, safety boundaries, and completion reporting.

## Thinking-level guide

| Level | Use |
| --- | --- |
| Low | Mechanical edits, formatting, straightforward documentation, and known commands |
| Medium | Bounded implementation with familiar patterns and limited architectural impact |
| High | Multi-module implementation requiring careful design, tests, and failure handling |
| Extra high | Complex real-time, multimodal, or stateful integration with difficult debugging |
| Ultra | Security-critical, autonomy, remote access, destructive actions, or system-wide architecture |

## Phase status

| Phase | Scope | Status | Remaining completion work | Sol thinking |
| --- | --- | --- | --- | --- |
| 0 | Repository baseline and reset verification | Complete | Maintain passing CI/secret scans and a clean reproducible `main` | Medium |
| 1 | JARVIS core and first text vertical slice | Blocked external | Deterministic gate passes, but local cold/warm p50/p95 miss targets; hosted NVIDIA requests time out; clean independent Windows reproduction is unavailable | High |
| 2 | Voice | Implemented; closeout pending | Current synthetic/STT/soak gates pass; repeat live microphone/render/kill smokes only with separate device-control authorization; always-listening stays hard-disabled | Extra high |
| 3 | Controlled computer access | Implemented; closeout pending | Current broker/adversarial/rollback gates pass; repeat live app/volume/media smokes only with separate real-application/device authorization | Ultra |
| 4 | Durable memory and personalization | Complete | Current host isolation, lifecycle, retrieval/deletion, migration, concurrency, backup/restore, and benchmark gates pass | Extra high |
| 5 | Research and self-education | Not started | Browser/retrieval sandbox, citations, hostile-page defenses, source-quality scoring, conflict reporting, and reproducible research benchmarks | High |
| 6 | Planning and bounded agents | Foundations only | Durable task graphs, budgets, checkpoints, cancellation, resumability, bounded parallel work, and approval-aware execution | Ultra |
| 7 | Vision and gestures | Not started | Screen/camera ports, finger-roll volume and palm/fist/navigation gestures, local perception, calibration, privacy indicators, and accuracy/latency datasets | Extra high |
| 8 | Secure phone/PWA access | Foundations only | Authenticated PWA, TLS/private networking, device enrollment/revocation, rate limits, secure streaming, and remote threat tests | Ultra |
| 9 | Dedicated server migration | Not started | Configurable split deployment, encrypted transport, service identity, backup/restore, offline degradation, migration rehearsal, and rollback | Ultra |
| 10 | Wearables and Meta glasses | Not started; lower priority | Generic wearable protocol, safe local read-only Garmin data integration, capability discovery, revocation, camera/mic indicators, and one real-device interaction | Extra high |
| 11 | Advanced JARVIS | Not started; long-term | Proactive/scheduled help, multi-device orchestration, deeper multimodal workflows, autonomy budgets, disable controls, and host acceptance thresholds | Ultra |

## Recommended order

1. Resolve Phase 1 local latency, hosted endpoint availability, and independent clean-Windows
   reproduction without weakening thresholds.
2. With separate authority, repeat Phase 2 live device and Phase 3 live application/device smokes.
3. Maintain completed Phase 4 memory and the safe local Phase 2/3 baselines.
4. Start Phase 5 only after deciding whether the blocked Phase 1–3 closeout gates are release
   prerequisites for that work.
5. Add Phase 6 bounded agents only after permissions, memory, and research are dependable.
6. Add vision, phone, server, wearables, and proactive behavior in Phases 7–11.

Hands-free control is a cross-phase track: Phase 2 detects claps, Phase 7 recognizes hand
gestures, and Phase 3 alone authorizes and executes the mapped computer action. See
[Hands-Free Control Plan](HANDS_FREE_CONTROL.md).

Routine subtasks inside any phase may use Low or Medium. Do not lower the listed effort for
security boundary design, permission changes, destructive actions, authentication, privacy
routing, or autonomy policy.
