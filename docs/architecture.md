# Architecture

## Status

This document describes implemented Phases 1–6: one modular Python application
with deterministic local privacy routing, NVIDIA/Groq/Gemini/Ollama adapters, SQLite,
audited tools, CLI, loopback browser/API interfaces, optional local push-to-talk voice, and an
opt-in controlled Windows action broker, plus host-isolated candidate/committed memory with FTS5
retrieval and transitive deletion, bounded cited public research with explicit storage approval,
and durable default-off foreground task graphs with hard budgets and effect reconciliation.
Current release status and external gates are tracked in
`docs/PHASE_OVERVIEW.md`; implementation presence alone is not a completion claim.

## Goals

- Run reproducibly on Windows with Python 3.11 and a committed `uv.lock`.
- Use interchangeable role-based providers without model IDs in orchestration.
- Persist conversations without putting private runtime data in the repository.
- Treat every model-requested action as untrusted until validated by policy.
- Add voice and vision clients without rewriting the core.
- Keep ordinary tests independent of models, microphones, GPUs, and networks.

## Component model

```text
Terminal CLI        Browser + local API       Voice / future vision adapters
     \                    |                           /
      \                   |                          /
                 AssistantService
                        |
       context -> local privacy gate -> ModelRouter -> tool-call loop
                           |                 |              |
                NVIDIA/Groq/Gemini/Ollama   |              |
                                  ConversationStore      ToolPolicy
                                          |                  |
                                     ToolRegistry      proposal only
                                                             |
                                              trusted CLI approval
                                                             |
                                              one-use grant -> broker
                                                             |
                                               fixed Windows handlers
```

The application is composed once at its entry point. Interfaces do not construct
their own providers or stores.

### Core runtime

The core owns normalized messages, requests, responses, tool calls, and runtime
errors. `AssistantService` coordinates a turn but contains no Ollama, SQLite,
terminal, audio, or HTTP details.

A turn follows this bounded flow:

1. Accept a validated user message and conversation identifier.
2. Persist the user message.
3. Load a bounded context window, retain its recent tail, and locally extract only older turns
   relevant to the latest request.
4. Add only relevant approved memory, scan the full candidate disclosure locally, select a tier,
   and ask a configured provider with only query-relevant public tool schemas on cloud routes.
5. Forward visible token deltas as typed events; hidden reasoning is never forwarded or stored.
6. If the response requests a tool, validate its name and arguments, apply the
   tool policy, execute it, and record an audit result.
7. Return the tool result to the provider when another model pass is needed.
8. Persist and return only the validated final assistant response.

The number of tool rounds, model duration, result size, and message size must be
bounded. A provider failure must not corrupt a conversation.

### Provider boundary

`ModelProvider` normalizes NVIDIA, Groq, Gemini, and Ollama wire formats. Tier 0 handles deterministic
tools/direct results (and only tool-owned caches with explicit freshness); Tier 1 is local Ollama;
Tier 2 is responsive Groq `FAST`/`PRIMARY`; Tier 3 is NVIDIA difficult reasoning. Ollama NDJSON and NVIDIA
SSE emit genuine visible-token deltas plus one terminal normalized response; Groq/Gemini currently
emit terminal frames. `ModelRouter`
owns sensitivity gating, role selection, bounded transient retry, quota/model
fallback, and zero-cost enforcement. Sensitive or uncertain routes never use a
cloud provider. Fallback is allowed only before streamed output begins; partial output cannot be
silently combined with another provider. Cloud providers receive one attempt; congestion does not
cause an immediate retry storm. Rolling health records TTFT p50/p95, total p50/p95, error rate,
recent `429`/`5xx`, quota state, and temporary degradation. Automatic deep work deprioritizes
severely degraded NVIDIA, but explicit NVIDIA requests remain available and never count as a
provider-specific pass unless NVIDIA itself meets the fixed benchmark. Profiles expose lifecycle,
context, and verified capabilities.

NVIDIA owns one process-lifetime pooled `httpx.AsyncClient` with explicit connection and keep-alive
limits. Per-request milestones cover DNS probe, TCP connect, TLS, upload, headers, first SSE frame,
first reasoning token, first visible token, final visible token, and completion. TCP/TLS are absent
when a keep-alive connection is reused; telemetry retains no prompt or response text.

Phase 5 research uses separate `SearchProvider`, `DocumentFetcher`, and `DocumentParser` ports.
The first fetch adapter validates public DNS, connects to the validated IP while retaining the
original Host/SNI for TLS verification, ignores proxy environment configuration, follows only
manually revalidated bounded redirects, streams under type/byte/time limits, and propagates
cancellation. HTML/plain/PDF extraction runs in a short-lived isolated Python worker with a minimal
environment, temporary working directory, page/filter/input/output/time limits, and no action
tools. It never executes scripts, styles, templates, macros, or source instructions. This process
boundary is defense in depth, not a Windows AppContainer. Parsed text remains untrusted data and
has no action authority.

Migrations 006–007 add the host-isolated research ledger and approved report workflows beside—not
inside—trusted Phase 4 memory.
`SQLiteResearchStore` owns immutable source versions, content hashes, access/publication metadata,
claim-to-source links, claim replacement, conflicts, active-source FTS5, append-only events,
exclusive JSON export, and transitive deletion with content-free tombstones. Changed/unavailable
sources stale dependent claims. `BoundedResearchOrchestrator` enforces source/fetch/domain/text/time
budgets and exact citation validation. Reports are volatile unless the trusted host explicitly
approves the displayed digest; model or source text cannot approve storage. Runtime composition
opens and closes this store explicitly; no research artifact is silently promoted into trusted
memory.

### Memory boundary

Phase 1 uses SQLite for durable transcripts. SQLite enables foreign keys,
WAL mode, a busy timeout, and transactional numbered migrations. The minimal
records are:

- conversations;
- ordered user, assistant, system, and tool messages; and
- model-requested tool calls and sanitized results embedded in typed messages;
- explicit note/profile/task memories with provenance and deletion;
- approval records for later approval-capable policy; and
- metadata-only tool audit records.

Phase 3 migrations add exact action requests, approval decisions, one-use grants, execution
receipts, broker events, control-intent outcomes, and a sanitized append-only lifecycle projection.
Canonical authority data is private durable state needed for expiry/restart behavior; terminal
operator views never expose its arguments or content.

Phase 4 migration 005 adds host-isolated working, episodic, profile, semantic, and task records;
candidate/committed/corrected/expired/rejected lifecycle; typed provenance and trust; confidence,
sensitivity, retention, correction lineage, conflicts, derivation edges, content-free tombstones,
append-only memory events, and synchronized SQLite FTS5. Legacy Phase 1 note/profile/task records
are preserved in a quarantined legacy host scope during migration.

Phase 5 migrations 006–007 add separate host-isolated research sources, active-source FTS5, claims,
citations, reports, unanswered questions, approval records, conflicts, content-free tombstones, and
append-only lifecycle events. They are additive and do not reinterpret Phase 4 memory as research
evidence.

Phase 6 migration 008 adds host-scoped immutable task graphs, versioned runtime state, exact approval
bindings, content-minimized effect checkpoints, append-only lifecycle events, and deletion
tombstones. `TaskPlanValidator` resolves authority and resource metadata from a fixed handler
registry. `TaskScheduler` reserves hard budgets before dispatch, parallelizes only independent
read-only nodes up to four, serializes effects, and requires explicit foreground execution.
Interrupted effects enter reconciliation and are never blindly replayed. See
`docs/BOUNDED_TASKS.md`.

Short-term context remains a bounded projection over recent messages. Durable retrieval adds only
committed, unexpired records through relevance/recency/confidence/trust scoring and strict item/
character caps. Extracted statements remain untrusted candidates until exact local confirmation.
Private or unknown projected memory forces local routing. FTS5 met the fixed Phase 4 benchmark, so
no embedding model, vector extension, or external vector database is present.

Runtime data defaults to the Windows local application-data directory. A
validated `JARVIS_DATA_DIR` override exists for testing and advanced deployment.

### Tool boundary

Tools are registered explicitly at composition time. Each tool has:

- a stable name and description;
- a Pydantic argument schema and bounded normalized result; and
- an asynchronous execution method.

Definitions carry permission level, approval rule, risk, side-effect class, sensitivity,
capabilities, timeout/result limits, idempotency/retry/concurrency, postcondition, and recovery.
Phase 1 policy permits only read-only tools without approval requirements.

The registry is not a dynamic Python-module loader. Unknown tools are rejected. Phase 1 exposes
clock, bounded system status, and UTF-8 file reads inside configured roots. Phase 3 optionally adds
a second immutable registry: model-facing side-effect adapters are inert and can only ask
`ComputerProposalPolicy` to persist an exact proposal. A separate `ActionCoordinator` reviews
policy, and `LocalActionBroker` alone owns fixed Windows handlers and one-use grant consumption.

The broker runs as the current non-elevated Windows user. It is an authorization and dispatch
boundary, not an administrator service. It revalidates actor/session/interface/capabilities, policy
epoch and full policy fingerprint, executable/file identity, grant expiry/replay state, audit
availability, result caps, postconditions, and recovery state. No generic process, shell, UI
automation, overwrite, delete, or elevation adapter exists.

### Interfaces

CLI supports diagnostics, interactive/one-shot chat, role override, browser-server, voice, trusted
computer controls, Phase 4 memory workflows, and Phase 5 volatile run/explicit store/list/show/
search/revalidate/export/delete/question workflows. FastAPI exposes typed health, chat, SSE event
streaming, host-bound memory controls, and Phase 5 loopback run/approve/inspect/search/revalidate/
delete controls; it exposes no Phase 3 approval or execution endpoint. Configuration rejects
non-loopback browser binding.

### Voice and vision

Phase 2 implements provider-neutral `AudioInput`, VAD, STT, TTS, wake-word, acoustic-event, and
audio-output ports. `VoiceSessionController` owns deterministic
idle/listen/transcribe/think/speak/interrupted/error/disabled transitions. Speech submits the same
validated text turn as CLI/API; closing a stream cancels in-flight provider work. Phrase output,
barge-in, render-reference suppression, device persistence, diagnostics, and text fallback remain
outside the core assistant.

The router may fail over only before visible provider output. Once output starts, that provider
owns the response, so TTS never speaks competing answers. Normal voice is latency-classed local
first. Current voice speaks the single completed response and emits no generic filler; any future
acknowledgement must be short, natural, and conditional on exceeding the configured normal-voice
speech-start budget for a genuinely long cloud task.

The concrete default uses local CPU Silero VAD, faster-whisper `base.en` int8, and Windows SAPI.
openWakeWord ONNX and double-clap foundations emit typed events but continuous listening is hard
disabled. Voice models/settings live in private application data, raw PCM is ephemeral, and the
optional `voice` dependency extra is never imported by a text-only installation. Blocking speech
inference runs via bounded worker threads/subprocesses so the async runtime remains cancellable.

Camera and screen capture remain future adapters. Images will be referenced as bounded artifacts
rather than embedded as arbitrary database blobs.

## Configuration and files

Configuration precedence is command-line option, environment variable, optional
local `.env`, then safe application default. Settings use the `JARVIS_` prefix
and are validated at startup.

Repository contents are reproducible source and metadata. These are never normal
Git contents:

- SQLite databases and logs;
- `.env` or credentials;
- GGUF, ONNX, safetensors, checkpoints, or Ollama blobs;
- generated speech, camera frames, and screenshots; and
- virtual environments and build artifacts.

Model setup scripts document the logical model name and report local diagnostics,
but model weights remain managed by Ollama.

## Dependency and concurrency policy

Use the standard library where it is sufficient. Direct runtime dependencies are
limited to validated configuration, HTTP, SQLite, and the CLI. Development tools
are locked with the project.

The runtime is asynchronous at I/O boundaries. SQLite operations and authority transitions are
transactional; one grant claim wins under concurrency and all registered side effects are globally
serialized or otherwise explicitly bounded. The CLI runs one turn/action at a time. Provider and
action requests have explicit timeouts. A distributed queue or event bus is not needed.

Windows APIs invoked in worker threads cannot always be forcibly stopped once native dispatch has
begun. Cancellation before dispatch records zero effect. Cancellation/timeout after dispatch with
no returned effect is recorded as uncertain with unknown postcondition/manual recovery; it is never
reported as proof that nothing happened.

## Testing strategy

- Unit tests exercise the runtime with fake providers, stores, clocks, and tools.
- Integration tests use a temporary SQLite database.
- Contract tests mock model, research-search, and fetch HTTP responses and malformed payloads.
- Scenario tests cover privacy, role override, fallback, quota, outage, catalog removal,
  streaming, deletion, and zero-spend enforcement.
- Policy tests prove unknown and unauthorized tools cannot execute.
- Live model tests are explicit and opt-in; they are not part of ordinary CI.
- Windows CI checks the lock file, formatting, linting, types, tests, dependency
  vulnerabilities, and committed secrets.
