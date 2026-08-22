# Roadmap

Status: concise view of `JARVIS_MASTER_ROADMAP.md`
Updated: 2026-08-20

The roadmap is capability-driven. A phase advances only after its Windows acceptance checks pass with reproducible setup and tests. Current implementation status and target behavior are stated separately.

## Implemented through Phase 1

The secure text foundation currently provides:

- locked Python 3.11 project and Windows bootstrap;
- validated settings and private local data directories;
- `jarvis doctor`, interactive/one-shot terminal chat, and loopback browser chat;
- configuration-driven NVIDIA/Groq/Gemini/Ollama roles and live catalog diagnostics;
- deterministic local sensitivity gate, direct clock path, and zero-cost fallback;
- SQLite conversations, explicit basic memories, deletion, audit, and migrations;
- schema-validated clock, system-status, and allowlisted text-file tools;
- streaming runtime/SSE events and provider usage/latency/quota metadata; and
- offline tests plus Windows format, lint, type, vulnerability, and secret gates.

Cloud roles activate only when mandatory free-tier/data-term confirmations and
keys are configured. Otherwise runtime remains local and offline-capable.

## Phase 1 — privacy-aware text core (implemented 2026-08-20)

- Added provider-neutral `FAST`, `PRIMARY`, `REASONING`, and `LOCAL` roles.
- Added NVIDIA, Groq, and Gemini adapters while retaining Ollama for private/offline fallback.
- Current active defaults map `REASONING` to NVIDIA `nvidia/nemotron-3-ultra-550b-a55b` and `LOCAL` to Ollama `nemotron-3-nano:4b`; optional `FAST`/`PRIMARY` mappings remain configurable.
- Runs deterministic local sensitivity and command classification before any cloud request.
- Send sensitive or uncertain content only to `LOCAL`; never silently weaken privacy during fallback.
- Keep initial cloud cost exactly `$0`; quota exhaustion, `429`, outage, or model retirement falls back free/local or returns a capacity error.
- Validate configured model IDs/capabilities against provider catalogs at startup.
- Added streaming events, structured usage/quota/cost metrics, personality regression checks,
  memory deletion, tool risk metadata, audit records, and local browser chat.

Acceptance suite covers safe simple, normal, reasoning, sensitive-local,
explicit override, catalog removal, quota exhaustion, outage, transient retry,
and zero-spend scenarios without live credentials. Live provider latency and
quota observations require user-owned free-tier keys and remain release checks.

## Phase 2 — voice

- Add push-to-talk before wake-word operation.
- Introduce STT/TTS/VAD/wake-word ports and cancellable streaming workers.
- Keep wake word, VAD, and initial TTS local; apply the same privacy gate to cloud speech.
- Benchmark latency, WER, CPU/GPU memory, interruption, and fallback.

## Phase 3 — controlled computer access

- Add trusted approvals, expiring grants, and a narrow privilege broker.
- Add bounded file, application, media, clipboard, browser, system, and printing tools.
- Enforce path/argument allowlists, idempotency, timeouts, output caps, postcondition checks, and durable audit.
- Never provide arbitrary shell execution or implicit administrator elevation.

## Phase 4 — durable memory and personalization

- Add source-aware working, episodic, profile, semantic, and task memory.
- Separate extraction candidates from committed memory.
- Provide inspect, correct, export, retention, and transitive deletion controls.
- Evaluate retrieval quality before adding vector infrastructure.

## Phase 5 — research and learning

- Add bounded search/browser adapters, a source ledger, claim status, citations, freshness, and conflict reporting.
- Treat all external content as untrusted data and preserve source-level provenance.

## Later phases

6. Persisted planning and bounded specialized agents.
7. Vision and configurable gestures.
8. Authenticated phone/PWA access over a private network.
9. Optional dedicated-server migration.
10. Generic wearable clients after capability validation.
11. Explicitly opt-in proactive and advanced multimodal assistance.

## Continuous requirements

Every phase must retain:

- configuration-driven, replaceable providers and model IDs;
- local privacy classification before cloud disclosure;
- a hard `$0` cloud budget until a later explicit policy decision;
- deny-by-default tools and independent action authorization;
- tests that run without live hardware or model services by default;
- no committed secrets, private runtime data, or model weights;
- Windows validation, recovery steps, and ordinary non-rewritten Git history.

Current provider facts and privacy terms are dated observations. Reverify official NVIDIA, Groq, and Gemini catalogs, free/trial limits, lifecycle status, and data terms before release.
