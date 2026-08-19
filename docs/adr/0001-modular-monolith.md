# ADR 0001: Python modular monolith with ports and adapters

- Status: Accepted
- Date: 2026-08-18

## Context

JARVIS must support a local language model, persistent memory, controlled tools,
and later voice, vision, desktop, mobile, and API interfaces. The previous
implementation placed UI state, audio loops, model calls, configuration, and tool
execution in one large process controller. That made ordinary testing difficult
and tied the application to one laptop configuration.

The new system needs strong internal boundaries but does not yet need distributed
deployment, multiple services, or a polyglot application tree.

## Decision

Build JARVIS as one Python 3.11 package using a modular-monolith architecture.
The application runtime depends on small protocols for chat providers, conversation storage,
tools, and policy. Ollama, SQLite, the terminal, and future device integrations are adapters
composed at the entry point. A separate approval protocol will be added before any side-effecting
tool is released.

Use asynchronous I/O boundaries, explicit dependency injection, normalized core
models, and a `src/` package layout. Keep runtime state outside the repository and
lock dependencies with `uv`.

Do not create empty application directories for planned clients. A new interface
or adapter is added only with working behavior and tests.

## Consequences

Positive consequences:

- Core orchestration can be tested with deterministic fakes.
- Ollama, SQLite, CLI, voice, vision, and API details cannot leak casually into
  each other.
- One Windows process and one setup path remain easy to operate.
- Later interfaces reuse the same policy and persistence behavior.
- Dependencies for heavy capabilities can remain optional.

Costs and constraints:

- Boundaries require a few explicit models and protocols up front.
- In-process adapters share a failure domain.
- Long-running inference must be moved to worker threads or processes when added.
- A future need for independent scaling would require extracting a proven
  boundary, not prematurely simulating microservices inside the repository.

## Alternatives considered

### Continue the legacy structure

Rejected because it couples orchestration, devices, UI, tools, and persistence,
contains machine-specific paths, and lacks reliable seams for tests.

### Microservices

Rejected for Phase 1. They would add service discovery, authentication,
deployment, network failure, and observability work before a stable local runtime
exists.

### Framework-led agent runtime

Rejected initially. A large agent framework would define core message, tool, and
memory semantics for us and make local-provider behavior harder to control. Small
project-owned protocols preserve the option to adopt a library behind an adapter
later.

### Multiple language applications from the start

Rejected until a real desktop, mobile, or web client exists. Python provides the
best common base for the initial local ML and Windows integration requirements.
