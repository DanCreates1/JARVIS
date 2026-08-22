# JARVIS Technology Decisions

Status: recommended defaults for staged implementation  
Planning date: 2026-08-20

These are architectural defaults, not permanent vendor commitments. Revisit a decision when representative benchmarks or security requirements contradict its assumptions.

## Decision summary

| Subsystem | Recommended default | Alternatives | Why now |
| --- | --- | --- | --- |
| Architecture | Python modular monolith, ports/adapters | Microservices, framework-led agents | Simple deployment with strong replaceable seams |
| Runtime language | Python 3.11 | 3.12, TypeScript, Rust/C# | Current locked project plus strongest ML/automation ecosystem |
| Dependency management | `uv` + committed lock | pip/venv, Poetry, Conda | Reproducible and fast; already adopted |
| Core API | Owned typed contracts; loopback FastAPI + SSE adapter | Flask, Django, gRPC | Implemented async schemas/streaming without putting framework in core |
| Streaming | Internal typed event stream; SSE first, WebSocket for duplex | Polling, message broker | Minimal infrastructure; browser friendly |
| Local LLM runtime | Ollama adapter | llama.cpp direct, vLLM | Best initial Windows operation; replaceable provider port |
| Model strategy | Privacy-aware hybrid roles: `FAST`, `PRIMARY`, `REASONING`, `LOCAL` | Fully local, unrestricted cloud-first | Hosted speed for non-sensitive work; local privacy/offline fallback |
| Fast cloud role | Groq `openai/gpt-oss-20b` | Local classifier, other hosted small model | Production model, about 1,000 tokens/s, tools and structured outputs |
| Primary cloud role | Groq `qwen/qwen3.6-27b` | GPT-OSS 20B, replacement from provider catalog | About 500 tokens/s, vision/tools/parallel calls; preview lifecycle requires fallback |
| Reasoning role | NVIDIA `nvidia/nemotron-3-ultra-550b-a55b` | Gemini, Groq reasoning models | Hosted 1M-context text/tool reasoning for difficult public work |
| Local role | Ollama `nemotron-3-nano:4b` | Qwen/Gemma 1B–4B candidates | Installed private/offline path on current 4 GB GPU |
| Cloud cost policy | Hard `$0` development budget | Explicit future paid policy decision | Free-tier exhaustion falls back or fails; never enters paid quota |
| Primary data store | SQLite WAL + migrations | PostgreSQL, document DB | One host/user and simple backups; already adopted |
| Text retrieval | SQLite FTS5 | Elasticsearch, hosted search | Built in, sufficient for early corpus |
| Vector retrieval | Defer; small in-process scoring then optional extension | Dedicated vector DB, pgvector | Require measured retrieval benefit first |
| STT | faster-whisper candidate | whisper.cpp, cloud STT | Python/CTranslate2 integration, quantization and VAD support |
| VAD | Silero VAD ONNX/CPU | WebRTC VAD | Strong lightweight streaming candidate; benchmark noise/latency |
| Wake word | openWakeWord ONNX | Porcupine, microWakeWord | Local Windows support and custom-model path; licensing review required |
| TTS | Piper local CPU behind provider port | Cloud neural TTS, OS voices | Fast/offline; voice quality and GPL boundary require review |
| Vision/gesture | MediaPipe Hand Landmarker + OpenCV capture | YOLO/custom classifier | Fast landmarks; temporal classifier remains project-owned |
| Remote access | Tailscale/private network + TLS + app authentication | Public reverse proxy, custom VPN | Default-deny device connectivity; avoids direct public exposure |
| Web/control panel | Responsive web UI/PWA after local API | Native desktop/mobile first | One client across laptop and phone |
| Observability | Structured events and OpenTelemetry-compatible fields | Full hosted stack | Measurable without premature infrastructure |
| CI/security | GitHub Actions, Ruff, mypy, pytest, pip-audit, Gitleaks | Larger platforms | Already present, adequate for current scale |

## TD-001 — Modular monolith

**Decision**  
Keep one installable Python product with explicit internal ports and adapters. Use worker processes only for privileged isolation or blocking inference.

**Reason**  
One deployment is appropriate for one host and current scale; owned boundaries preserve future extraction.

**Alternatives considered / why rejected**

- Microservices: networking, auth, deployment, and failure complexity before scale exists.
- One large script: untestable coupling and repeats legacy failure mode.
- Agent framework as architecture: would outsource core message/tool/memory semantics before requirements stabilize.

**Replaceable later?**  
Yes. Extract measured hot or security-sensitive ports behind the same contracts.

## TD-002 — Python 3.11 and `uv`

**Decision**  
Continue Python `>=3.11,<3.13` and use `uv` with committed `uv.lock`.

**Reason**  
Current project and tests use it; ML, audio, vision, Windows, and API libraries are strongest here. Python 3.11 has broad binary-package compatibility.

**Alternatives considered / why rejected**

- System Python 3.14: outside current constraint and likely less compatible with ML wheels.
- TypeScript: good UI/API ecosystem, weaker local ML/device integration as sole backend.
- Rust/C#: useful for later broker/device components, unnecessary for core rebuild now.

**Replaceable later?**  
Individual adapters can use another language across a narrow authenticated IPC boundary.

## TD-003 — Owned core contracts, FastAPI adapter

**Decision**  
Keep core independent of HTTP. Phase 1 implements a loopback FastAPI adapter with
typed JSON and SSE runtime events; use WebSocket only when bidirectional realtime
audio/control requires it.

**Reason**  
Pydantic integration, async support, generated schemas, and easy browser/PWA consumption.

**Alternatives considered / why rejected**

- Flask: workable but less natural for the existing async/typed design.
- Django: too much application framework for a local service.
- gRPC: useful between mature services, worse browser and local-debug ergonomics now.
- Message broker: no current distributed consumer requirement.

**Replaceable later?**  
Yes; HTTP is an adapter over the application service and internal event models.

## TD-004 — Hybrid, role-based model routing

**Decision**  
Configure provider-neutral `FAST`, `PRIMARY`, `REASONING`, and `LOCAL` roles. A deterministic local gate classifies sensitivity and obvious commands before cloud use. Difficult public work can use NVIDIA; normal, sensitive, uncertain, offline, or cloud-failed work uses Ollama in the active setup. Optional Groq/Gemini roles remain supported. Initial cloud spend is hard-capped at `$0`.

**Reason**  
RTX 2050 4 GB/16 GB RAM cannot deliver consistently strong large-model reasoning at JARVIS latency. Hosted inference improves responsiveness, but private JARVIS context cannot be disclosed indiscriminately and free capacity is not guaranteed.

**Alternatives considered / why rejected**

- Fully local: best privacy, but difficult reasoning quality/latency is inadequate on this laptop.
- Unrestricted cloud-first: discloses unclassified content before policy can protect it and depends on external availability.
- Cloud model as first router: privacy classification would occur only after disclosure.
- One model for all requests: wastes latency and power on deterministic/simple work.

**Replaceable later?**  
Yes. Roles map to provider/model configuration, live capability catalogs, and benchmark data. User overrides cannot weaken sensitivity or zero-spend policy.

## TD-005 — Ollama as first local adapter

**Decision**  
Retain Ollama for first Windows local serving behind `ModelProvider`.

**Reason**  
Already implemented, operationally simple on Windows, and supports the selected quantized candidates without model files in Git.

**Alternatives considered / why rejected**

- Direct llama.cpp: more low-level control but more packaging/operational work now.
- vLLM: suited to larger GPUs and server throughput, not this 4 GB Windows laptop.
- Embedded Python transformer runtime: increases process memory and couples model lifecycle to core.

**Replaceable later?**  
Yes. llama.cpp or vLLM can implement the provider contract on future hardware.

## TD-006 — Initial provider/model portfolio

**Decision**  
Use NVIDIA `nvidia/nemotron-3-ultra-550b-a55b` for difficult public `REASONING` and Ollama `nemotron-3-nano:4b` for active `LOCAL` work. Retain Groq `FAST`/`PRIMARY` and Gemini as optional configuration-driven adapters rather than required credentials.

**Reason**  
As verified on 2026-08-22, NVIDIA Nemotron 3 Ultra exposes a 1,000,000-token context, a 32,768-token maximum output, tools, and configurable thinking through NVIDIA's OpenAI-compatible endpoint. Ollama Nemotron 3 Nano 4B is installed locally as a 2.8 GB Q4_K_M model with tools and thinking. The NVIDIA catalog and both live response paths passed.

**Alternatives considered / why rejected**

- Local models for every role: insufficient interactive quality/latency on current hardware.
- Gemini as default reasoning role: retained as an optional adapter, but NVIDIA Ultra is active.
- Hard-coded provider IDs in orchestration: prevents catalog-driven replacement and safe deprecation handling.
- Qwen preview without fallback: unacceptable lifecycle risk.

**Replaceable later?**  
Yes. Selection is entirely configuration- and capability-driven. Startup diagnostics verify live model IDs. NVIDIA failure falls back local; optional Groq/Gemini paths retain bounded fallback. No fallback may cross a sensitivity boundary or enter paid quota.

**Privacy and cost conditions**
Use free/trial credentials and treat every cloud call as external disclosure. Never send sensitive, confidential, personal, credential, file, memory, communication, or device content to NVIDIA trial service. A provider `429` triggers bounded local fallback, not paid execution.

Verified sources: [Groq models](https://console.groq.com/docs/models), [Groq limits](https://console.groq.com/docs/rate-limits), [Groq data controls](https://console.groq.com/docs/your-data), [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), and [Gemini terms](https://ai.google.dev/gemini-api/terms).

## TD-007 — SQLite, WAL, FTS5; PostgreSQL later

**Decision**  
Use SQLite as canonical store with foreign keys, WAL, busy timeout, transactional numbered migrations, backup API, and FTS5.

**Reason**  
Single-host early deployment needs transactions and searchable text, not database operations overhead. Current core already has SQLite persistence.

**Alternatives considered / why rejected**

- PostgreSQL: excellent when server concurrency or multi-user scale exists; premature now.
- Dedicated vector/document databases: multiple backup, privacy, and consistency surfaces without proven need.
- Redis: not durable canonical memory and no distributed coordination need yet.

**Replaceable later?**  
Yes. `MemoryStore` and migration/export formats enable PostgreSQL/pgvector migration.

## TD-008 — Retrieval before large context

**Decision**  
Use bounded recent context, FTS5, metadata filters, summaries, and later measured embeddings. Do not pass all history or rely on advertised huge contexts.

**Reason**  
Long contexts increase KV memory, latency, distraction, and privacy exposure. Retrieval provides inspectable provenance.

**Alternatives considered / why rejected**

- Transcript dump: poor relevance and unbounded cost.
- Vector-only retrieval: exact terms, dates, names, and filters need lexical/structured search.
- Dedicated vector DB immediately: packaging complexity before retrieval evaluation.

**Replaceable later?**  
Yes. Hybrid scoring/index adapters can evolve under a golden test set.

## TD-009 — faster-whisper STT, Silero VAD

**Decision**  
Use faster-whisper as first STT candidate and Silero VAD ONNX on CPU. Begin push-to-talk, then streaming endpointing.

**Reason**  
faster-whisper supports quantized CTranslate2 inference and established Whisper accuracy; Silero is a small streaming VAD with sub-frame CPU cost. CPU-first speech avoids fighting the 4B LLM for 4 GB VRAM.

**Alternatives considered / why rejected**

- whisper.cpp: strong alternative, especially for C++/CPU packaging; compare if Windows/CTranslate2 friction appears.
- Cloud STT: optional quality/latency fallback but not privacy default.
- WebRTC VAD: very fast baseline; may be less robust, keep as benchmark alternative.

**Replaceable later?**  
Yes. Separate STT and VAD ports with recorded-audio contract tests.

## TD-010 — openWakeWord after push-to-talk

**Decision**  
Evaluate openWakeWord ONNX on Windows only after push-to-talk is stable.

**Reason**  
It is local, designed for streaming frames, and supports custom wake-word models. Always-listening introduces privacy and false-activation risk that must not block first voice value.

**Alternatives considered / why rejected**

- Porcupine: mature commercial option, but license/key/vendor constraints.
- Speech-to-text always running: much higher compute and privacy cost.
- Hardcoded audio keyword logic: inadequate robustness.

**Replaceable later?**  
Yes. Wake-word provider owns scores/events. Review pretrained model licenses before distribution.

## TD-011 — Piper as first local TTS candidate

**Decision**  
Evaluate current Open Home Foundation Piper package on CPU behind `TTSProvider`, with phrase streaming and cancel support.

**Reason**  
Fast, local, and suitable for low-resource synthesis. It keeps GPU free.

**Alternatives considered / why rejected**

- Windows system voices: easy baseline but usually lower personality/quality.
- Cloud neural TTS/realtime audio: higher quality, but privacy, network, cost, and vendor dependence.
- Large neural voice cloning: too heavy and raises consent/licensing concerns for V1.

**Replaceable later?**  
Yes. Review Piper GPL integration and each voice model license before packaging; process separation may simplify compliance and failure isolation.

## TD-012 — Deterministic typed tools, no arbitrary shell

**Decision**  
Only explicitly registered, schema-validated tools execute. Every side-effecting tool has risk metadata, approval rules, postcondition checks, and bounded results. No general shell tool.

**Reason**  
Model text is not authorization or safe command syntax. Narrow tools are testable and auditable.

**Alternatives considered / why rejected**

- Model-generated PowerShell/shell execution: injection and privilege risk is unacceptable.
- UI click automation for everything: brittle and hard to verify; use only when APIs are unavailable.
- Plugin auto-discovery: expands code execution surface without review.

**Replaceable later?**  
Tool implementations can change. The security invariant cannot.

## TD-013 — Separate permission engine and privilege broker

**Decision**  
Core runs unprivileged. Policy creates exact, expiring grants; a minimal broker performs only allowlisted privileged actions using OS controls.

**Reason**  
Limits blast radius and prevents a prompt/model compromise from inheriting administrator authority.

**Alternatives considered / why rejected**

- Always-admin JARVIS: critical persistent attack surface.
- Confirmation only in prompt: model-controlled and not an authorization mechanism.
- Per-tool ad hoc checks: inconsistent and difficult to audit.

**Replaceable later?**  
Broker transport/OS implementation may change; grant semantics and fail-closed behavior remain.

## TD-014 — Durable state-machine planning, few agents

**Decision**  
Persist bounded task DAGs and use one orchestrator plus specialized research/computer/vision/communication contexts only when their tools and security scopes differ.

**Reason**  
Reliability comes from explicit state, budgets, verification, and recovery—not agent count.

**Alternatives considered / why rejected**

- Large agent swarm: high cost, context duplication, unclear accountability.
- In-memory chains: cannot safely resume or reconcile side effects after restart.
- Fully deterministic workflow only: insufficient for open-ended planning/research.

**Replaceable later?**  
Yes. Planner/model implementations can change under persisted task/event contracts.

## TD-015 — MediaPipe/OpenCV fast vision path

**Decision**  
Use OpenCV for bounded capture/preprocessing and MediaPipe Hand Landmarker for hand landmarks. Project-owned temporal logic maps landmarks to configurable gesture intents.

**Reason**  
Simple gestures need low-latency CV, not a multimodal LLM. Landmark output permits customization and confidence/debounce.

**Alternatives considered / why rejected**

- Multimodal model per frame: slow, expensive, and unnecessary.
- Permanently hardcoded gesture/action pairs: unsafe and inflexible.
- Custom detector training first: no dataset or demonstrated need.

**Replaceable later?**  
Yes. Vision providers emit normalized observations; mapping remains separate.

## TD-016 — Tailscale plus application authentication

**Decision**  
Use Tailscale/private networking as default remote transport, with TLS and JARVIS per-device authentication/authorization above it.

**Reason**  
Avoids direct public exposure and supplies identity-aware, default-deny connectivity. Network membership alone is not enough to approve JARVIS actions.

**Alternatives considered / why rejected**

- Public port/reverse proxy first: larger attack and operations surface.
- Custom VPN: unnecessary cryptographic/network engineering.
- LAN-only access: does not satisfy away-from-home phone use.

**Replaceable later?**  
Yes. Network transport is outside the application identity/device registry.

## TD-017 — PWA before native apps

**Decision**  
Build a responsive browser control panel and installable PWA against the versioned API before native mobile/desktop apps.

**Reason**  
One client delivers chat, status, approval, memory, and settings on laptop and phone quickly.

**Alternatives considered / why rejected**

- Native iOS/Android immediately: duplicate platform work before API/product workflows stabilize.
- Heavy desktop framework: no requirement that a local browser cannot initially satisfy.

**Replaceable later?**  
Yes. Native clients can reuse the same API/device model when platform APIs justify them.

## TD-018 — Structured local observability first

**Decision**  
Emit structured events with correlation IDs and OpenTelemetry-compatible names. Store bounded local audit/metric data; add a backend only on measured need.

**Reason**  
Latency, reliability, and security decisions need evidence, but a hosted stack is unnecessary for one laptop.

**Alternatives considered / why rejected**

- Plain unstructured logs: poor correlation and testing.
- Full Prometheus/Grafana/collector deployment now: operational overhead before need.
- Log full prompts/tool data: privacy and secret leakage.

**Replaceable later?**  
Yes. Exporters can send the same events to a server stack later.

## TD-019 — Generic wearable/device interface

**Decision**  
Treat Meta glasses as a later `WearableClient` adapter or phone-bridged device. Core knows capabilities, not Meta-specific APIs.

**Reason**  
Meta’s Wearables Device Access Toolkit now enables third-party work, but access, supported capabilities, policies, and hardware can change.

**Alternatives considered / why rejected**

- Build directly around Meta: unacceptable vendor dependency and P3 priority.
- Ignore wearables entirely: loses a desired future interface; a generic contract is cheap once device architecture exists.

**Replaceable later?**  
Yes. Wearable adapters are optional device clients.

## Review triggers

Re-open a decision when any occurs:

- p95 target missed by more than 25% on representative tests;
- local model tool accuracy cannot meet the release threshold;
- SQLite lock/concurrency behavior affects real users;
- a dependency loses maintenance, compatible licensing, or Windows support;
- privacy policy prohibits a chosen provider path;
- dedicated server hardware changes model/runtime economics;
- a new client requires capabilities absent from current transport.
