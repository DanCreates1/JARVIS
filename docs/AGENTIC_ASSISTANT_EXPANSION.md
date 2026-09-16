# Agentic Assistant Expansion

Status: active incremental plan
Updated: 2026-09-16

This plan maps the requested A–M capability sequence onto the existing Phase 0–11 repository. The
two naming schemes are independent. Existing security, privacy, approval, and deployment gates
remain authoritative.

## Repository audit

| Area | Existing implementation | Gap relevant to expansion |
| --- | --- | --- |
| LLM providers/routing | Typed roles, Ollama/Groq/Gemini/NVIDIA adapters, privacy gate, health tracking, zero-cost fallback | No vision model role or attachment-aware capability routing |
| Memory/context | SQLite/FTS5 working, episodic, profile, semantic, and task memory; bounded recent-turn reduction | No repository map or durable coding-session checkpoint before this plan |
| Tools/actions | Typed registry, schemas, result caps, policy, approval, one-use grants, broker, audit | Integration registries for communications/calendar do not exist |
| Web/research | Search/fetch/parse/synthesis ports, safe HTTPS acquisition, citations, PDF parsing, freshness evaluation | Research is explicit, Wikimedia-backed, and not automatically invoked from chat |
| API/UI | FastAPI JSON/SSE, loopback browser, authenticated PWA transport | No attachment-upload or briefing surface |
| Files/images | Allowlisted UTF-8 reads; bounded HTML/text/PDF research parsing; ephemeral camera/screen capture | No durable `Attachment` abstraction, upload processing, OCR, or image understanding |
| Storage | SQLite WAL, numbered migrations, host isolation, backup/integrity paths | No attachment/email/calendar/briefing schema |
| Scheduling/proactivity | Durable bounded task DAGs plus default-off foreground proactivity rules/inbox | No daemon, provider polling, or event ingestion; deliberate safety boundary |
| Authentication/security | Local privacy gate, remote device identity, signed requests, browser sessions, CSRF/CORS/CSP, prompt-injection controls | Provider OAuth/credential lifecycle for email/calendar absent |
| Networking | Local-only default, receipt-gated server topology, Tailscale Serve deployment | Internet reachability was not projected into chat context before Phase A |
| Cloud/local fallback | Automatic capability/privacy-aware fallback with provider health | Already stronger than requested baseline; preserve it |

## Architecture decisions

- Keep the modular monolith and existing ports/adapters. Do not add a second orchestrator, memory
  store, permission system, or scheduler.
- Map requested `READ`, `PREPARE`, `WRITE_EXTERNAL`, and `DESTRUCTIVE` semantics onto existing
  permission Levels 0–4 instead of creating conflicting authority enums.
- Treat external email, calendar, webpages, files, OCR, and model output as untrusted data. They
  may propose actions but never approve or execute them.
- Keep automatic research volatile by default. Durable research still requires existing exact
  storage approval.
- Preserve default-off proactivity. A future background worker needs an explicit process gate,
  per-feature enablement, bounded polling, leases, and the existing approval boundary.
- Add no empty modules. Each phase must ship a used contract, adapter, runtime wiring, and tests.

## Phased checklist

- [x] **A — Current Context:** compact request-relevant date/time/day/timezone, configured home
  region, session/device, inference mode, internet reachability, and exact post-route model context.
- [x] **B — Freshness Router:** deterministic `STATIC`, `LOCAL_CONTEXT`, `WEB_REQUIRED`,
  `PERSONAL_DATA_REQUIRED`, and `MULTI_SOURCE` classification integrated before answer generation.
- [ ] **C — Automatic Web Research:** reuse Phase 5 ports/workflow, add general search-provider
  capability, volatile compact evidence projection, timestamps, citations, and offline behavior.
- [ ] **D — Unified Tool Registry:** expose existing typed registries through one discovery view
  without weakening separate action ownership or immutable handler sets.
- [x] **E — Model Router/Fallback baseline:** existing role routing, health, quota/outage fallback,
  privacy enforcement, and configuration-driven model IDs satisfy the core request.
- [ ] **F — Token/Continuity:** retain existing bounded conversation/memory/tool context; add
  repository maps, diff-oriented coding context, cache policy, and automated checkpoint upkeep.
- [ ] **G — Attachments:** typed attachment metadata/status, bounded upload storage, isolated type
  processing, chunk/retrieval projection, deletion, and vision routing.
- [x] **H — Memory baseline:** existing Phase 4 lifecycle, provenance, confidence, timestamps,
  retention, retrieval, correction, and deletion cover the requested foundation.
- [ ] **I — Email:** provider-neutral read/thread/summarize/extract/draft ports; no sending without
  exact approval and provider authorization.
- [ ] **J — Calendar:** provider-neutral read/conflict/suggestion ports; mutations remain separate
  approval-gated actions.
- [x] **K — Approval baseline:** existing Levels 0–4, policy engine, trusted surfaces, grants,
  broker, receipts, and audit exceed the proposed four-category foundation.
- [ ] **L — Background Worker:** explicit opt-in event adapters and bounded scheduler loop using
  deterministic filters before local/cloud models; no uncontrolled polling or spending.
- [ ] **M — Morning Briefing:** backend model and synthesis across approved weather, calendar,
  email, tasks, projects, reminders, and optional news; simple UI projection last.

## Next phase

Phase C. Connect only `WEB_REQUIRED`/`MULTI_SOURCE` decisions to volatile Phase 5 research. Add a
general search-provider capability, compact cited evidence projection, timestamps, and explicit
offline behavior without building a competing web stack or persisting results automatically.
