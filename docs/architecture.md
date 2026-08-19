# Architecture

## Status

This document describes the intended Phase 1 architecture. It is deliberately a
small modular monolith: one installable Python application with internal
boundaries that can be tested and replaced independently.

## Goals

- Run reproducibly on Windows with Python 3.11 and a committed `uv.lock`.
- Use an interchangeable local language-model provider, initially Ollama.
- Persist conversations without putting private runtime data in the repository.
- Treat every model-requested action as untrusted until validated by policy.
- Add voice, vision, an API, and graphical clients without rewriting the core.
- Keep ordinary tests independent of models, microphones, GPUs, and networks.

## Component model

```text
Terminal CLI        Future local API       Future voice / vision adapters
     \                    |                           /
      \                   |                          /
                 AssistantService
                        |
       context -> ChatProvider -> tool-call loop
                        |                |
             ConversationStore      ToolPolicy
                                          |
                                     ToolRegistry
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
3. Load a bounded context window from the conversation store.
4. Ask the configured chat provider for a response.
5. If the response requests a tool, validate its name and arguments, apply the
   tool policy, execute it, and record an audit result.
6. Return the tool result to the provider when another model pass is needed.
7. Persist and return the final assistant response.

The number of tool rounds, model duration, result size, and message size must be
bounded. A provider failure must not corrupt a conversation.

### Provider boundary

`ChatProvider` normalizes provider-specific wire formats. The initial adapter
calls Ollama over loopback HTTP and maps Ollama messages and tool calls to core
models. Core code must not import an Ollama client or depend on Ollama JSON.

Provider capability flags can later describe streaming, native tools, embeddings,
or images. Unsupported capabilities fail explicitly rather than being guessed.

### Memory boundary

Phase 1 uses SQLite for durable transcripts. SQLite should enable foreign keys,
WAL mode, a busy timeout, and transactional numbered migrations. The minimal
records are:

- conversations;
- ordered user, assistant, system, and tool messages; and
- model-requested tool calls and sanitized results embedded in those typed assistant and
  tool messages, providing a durable Phase 1 audit trail.

A separate execution-audit table may be added when side-effecting tools introduce approval,
duration, and actor metadata. Phase 1 does not create a redundant table for its read-only clock.

Short-term context is a projection over recent messages. Long-term semantic
memory and embeddings are a separate future concern; they must not silently
alter the durable transcript or require a vector database in Phase 1.

Runtime data defaults to the Windows local application-data directory. A
validated `JARVIS_DATA_DIR` override exists for testing and advanced deployment.

### Tool boundary

Tools are registered explicitly at composition time. Each tool has:

- a stable name and description;
- a Pydantic argument schema and bounded normalized result; and
- an asynchronous execution method.

Before any side-effecting tool ships, the definition and policy contracts must also carry an
explicit risk classification, side-effect declaration, timeout, result limit, and approval rule.
Those controls are not implied by a model prompt.

The registry is not a dynamic Python-module loader. Unknown tools are rejected.
The Phase 1 clock tool is read-only; filesystem, process, network, and desktop
automation tools remain out of scope until approval and containment exist.

### Interfaces

The CLI is the first interface. It supports diagnostics, an interactive chat,
and one-shot messages. It translates core errors into actionable messages and
nonzero exit codes without exposing secrets or stack traces by default.

A future FastAPI adapter will wrap the same `AssistantService`. It will use a
versioned `/v1` surface, loopback binding by default, typed schemas, liveness and
readiness endpoints, and server-sent events or WebSockets for streaming. Business
logic must not be duplicated in route handlers.

### Voice and vision

Future speech-to-text, text-to-speech, wake-word, camera, and screen-capture
components are input or output adapters. Speech produces the same validated text
turn as the CLI. Images are referenced as bounded artifacts rather than embedded
as arbitrary database blobs.

Heavy or blocking inference runs in a dedicated worker boundary so it cannot
stall the asynchronous runtime. Voice and vision dependencies will be optional
extras and will never be imported by a text-only installation.

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

The runtime is asynchronous at I/O boundaries. SQLite operations are serialized and the Phase 1
CLI runs one turn at a time. Any future concurrent API must add per-conversation coordination
before accepting overlapping turns. Provider requests have explicit timeouts; cancellation is not
swallowed. A distributed queue or event bus is not needed for Phase 1.

## Testing strategy

- Unit tests exercise the runtime with fake providers, stores, clocks, and tools.
- Integration tests use a temporary SQLite database.
- Contract tests mock Ollama HTTP responses and malformed payloads.
- Policy tests prove unknown and unauthorized tools cannot execute.
- Live model tests are explicit and opt-in; they are not part of ordinary CI.
- Windows CI checks the lock file, formatting, linting, types, tests, dependency
  vulnerabilities, and committed secrets.
