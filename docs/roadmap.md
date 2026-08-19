# Roadmap

The roadmap is capability-driven. A phase advances only after its acceptance
checks pass on Windows and the repository contains reproducible setup and tests.

## Phase 1 — text runtime

Deliver a complete local vertical slice:

- locked Python 3.11 project and Windows bootstrap;
- validated settings and local data directories;
- `jarvis doctor` diagnostics;
- interactive and one-shot terminal chat;
- Ollama chat-provider adapter using `qwen2.5:3b` by default;
- SQLite conversations and transactional migrations;
- schema-validated tool registry with one read-only clock tool;
- deny-by-default policy and durable typed tool-call/result messages;
- fake-provider, SQLite integration, and Ollama contract tests; and
- Windows CI for format, lint, types, tests, vulnerabilities, and secrets.

Acceptance: a new compatible Windows machine can clone, run the documented setup,
pass the quality gate, chat locally, restart, and resume durable conversation
history without placing runtime data or model weights in Git.

## Phase 2 — local service API

- Add a FastAPI adapter around the existing application service.
- Bind to loopback by default and provide liveness/readiness endpoints.
- Version request and response schemas under `/v1`.
- Stream runtime events using SSE or WebSockets.
- Add authentication before any non-loopback deployment.
- Add API contract, request-limit, cancellation, and concurrency tests.

## Phase 3 — voice

- Add push-to-talk before always-listening behavior.
- Introduce speech-to-text and text-to-speech provider ports.
- Package voice dependencies as an optional installation extra.
- Move blocking inference to cancellable workers.
- Benchmark latency, accuracy, CPU/GPU memory, and CPU fallback.
- Add wake-word detection only after false-activation and privacy tests exist.

Legacy VAD thresholds and CUDA fallback behavior may inform benchmarks but should
not be copied as architecture.

## Phase 4 — controlled tools and desktop client

- Add a user-visible approval broker and pending-action interface.
- Introduce narrowly scoped filesystem and application-launch tools.
- Enforce canonical path allowlists and exact executable arguments.
- Add idempotency, timeouts, output caps, and a durable audit viewer.
- Build a small desktop client against the local API.

Arbitrary shell execution, implicit administrator elevation, and unattended
privileged automation remain prohibited.

## Phase 5 — vision and richer memory

- Add bounded screenshot/camera capture adapters with explicit activation state.
- Support provider capability negotiation for image input.
- Define retention and deletion controls before persisting media.
- Add opt-in semantic memory behind a separate interface.
- Benchmark retrieval quality and provide source attribution and deletion.

## Phase 6 — remote and mobile access

- Define a threat model and authenticated device enrollment.
- Require TLS, revocable credentials, rate limiting, and scoped permissions.
- Build mobile/web clients only against a stable versioned API.
- Provide a prominent remote-access kill switch and security audit trail.

## Continuous requirements

Every phase must retain:

- a clean `main` branch and reviewed Git diff;
- reproducible dependencies and model setup metadata;
- no committed secrets, private runtime data, or model weights;
- tests that run without live hardware or model services by default;
- Windows validation and documented recovery steps; and
- ordinary commits without rewriting published history.
