# Security model

JARVIS processes private conversations and will eventually control local devices.
Security therefore belongs in the runtime architecture, not only in prompts.

This document describes implemented Phase 1 controls, including local
sensitivity classification and zero-cost NVIDIA/Groq/Gemini/Ollama routing.

## Trust boundaries

The following inputs are untrusted:

- user messages and future audio, images, files, and web content;
- all language-model output, including structured-looking JSON and tool calls;
- tool arguments derived from model output;
- Ollama and other provider responses;
- API requests; and
- configuration supplied outside the packaged defaults.

A system prompt can guide behavior but cannot grant authorization.

## Tool policy

Tools are deny-by-default and registered explicitly. The Phase 1 runtime locates an exact
registered name, validates arguments, applies policy independently of model text, and persists a
sanitized tool result and metadata audit. Automatically allowed tools are the
read-only clock, bounded system status, and allowlisted UTF-8 file reader.

Before any future side-effecting tool can execute, the runtime must additionally:

1. classify the requested side effect;
2. apply the policy rule for that risk class;
3. request human approval when the class requires it; and
4. record the decision and sanitized outcome.

Implemented risk classes are read-only, reversible, sensitive, and destructive.
Phase 1 policy denies every non-read-only or approval-requiring definition.

There is no arbitrary shell tool. Process tools must use fixed executables and
argument arrays, never `shell=True`, command strings, PowerShell evaluation, or
implicit elevation. Filesystem tools must resolve canonical paths and enforce
allowlisted roots before reading or writing. Timeouts, output limits, and a
bounded number of tool rounds are mandatory.

## Prompt injection and data handling

Retrieved text, file contents, websites, images, and tool results remain data;
instructions inside them do not change tool policy. Tool descriptions should
state their narrow purpose and should not expose unnecessary system details.

Do not store hidden reasoning. Persist only user-visible messages, normalized
tool requests/results, timestamps, and the metadata needed for diagnostics.
Logs should default to operational metadata and redact authorization headers,
tokens, environment values, and private tool results.

Conversation databases, logs, screenshots, audio, and models belong outside the
repository under user's local application-data directory. Conversation and
explicit-memory deletion are implemented; richer-media retention remains deferred.

## Secrets

- Never commit `.env`, tokens, passwords, cookies, private keys, certificates,
  or provider credentials.
- `.env.example` contains safe defaults, role IDs, confirmations, and commented key placeholders.
- Prefer environment variables or an operating-system credential store for
  future secrets.
- Never print the entire process environment during diagnostics.
- Rotate a secret immediately if it enters Git; ignoring it afterward does not
  remove it from history.

CI scans repository history for secrets. Local quality checks use Gitleaks when
it is installed.

## Model and network security

Ollama defaults to `http://127.0.0.1:11434`. Remote Ollama requires explicit opt-in and HTTPS.
Groq/Gemini activate only after mandatory free-tier/data-term confirmations. A local
deterministic gate scans full candidate disclosure context; sensitive or uncertain content
routes local, and free-tier exhaustion cannot enter paid service.
HTTP clients use bounded request timeouts and narrowly constructed URLs. An explicit wire-level
response-size limit is required before JARVIS accepts remote or multimodal provider payloads.

Cloud credentials must come from billing-disabled/free-tier projects and secure process
injection or an OS credential store. Enable Groq Zero Data Retention, while treating every cloud
call as external disclosure. Never send sensitive or confidential content through unpaid Gemini.

Model weights are downloaded only through an explicit setup command and are not committed. Phase
1 diagnostics report the selected name and whether it is installed. Recording Ollama's local
model digest is a future hardening step so changed weights become visible.

## API security

Implemented browser/API service binds to loopback, sets restrictive browser
headers, omits permissive CORS, and validates typed request sizes. Configuration
rejects non-loopback binding. Authenticated remote access remains deferred.

An API caller cannot approve its own privileged tool request without a separate,
user-visible approval flow.

## Supply chain and release checks

- Python dependencies are resolved in `uv.lock`; CI rejects a stale lock.
- GitHub Actions and Python dependencies are updated through reviewed Dependabot
  pull requests.
- CI runs Ruff, mypy, pytest, `pip-audit`, and Gitleaks.
- Model binaries, build output, and generated artifacts are excluded from Git.
- Published history is not force-pushed; releases are normal reviewed commits.

Before a release or major checkpoint, run `./scripts/quality.ps1`, inspect
`git status` and `git diff`, verify no private data is present, and confirm the
exact branch and pushed commit.

## Reporting a security issue

Do not open a public issue containing credentials or private conversation data.
Use the repository owner's private security-reporting channel when one is
published. Until then, remove sensitive evidence from any reproduction and
notify the owner privately.
