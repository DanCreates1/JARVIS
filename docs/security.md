# Security model

JARVIS processes private conversations and will eventually control local devices.
Security therefore belongs in the runtime architecture, not only in prompts.

This document describes implemented Phases 1–5 controls, including local sensitivity
classification, zero-cost NVIDIA/Groq/Gemini/Ollama routing, local push-to-talk speech, and
default-off controlled computer access, plus candidate-only host-isolated memory, provenance,
conflict visibility, transitive deletion, and bounded cited public research. Independent
clean-Windows bootstrap/repository CI
passes; current latency/provider-capacity and separately authorized live-effect limitations remain
explicit in `docs/PHASE_OVERVIEW.md` and are not security-gate waivers.

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

Before any side-effecting tool can execute, the Phase 3 runtime additionally:

1. classify the requested side effect;
2. apply the policy rule for that risk class;
3. request human approval when the class requires it; and
4. record the decision and sanitized outcome.

Implemented risk classes are read-only, reversible, sensitive, and destructive. The ordinary Phase
1 policy still denies every non-read-only definition. When both Phase 3 gates are enabled, the
computer proposal policy can create durable exact requests, but direct runtime execution remains
prohibited; only the fixed broker can consume an independently approved one-use grant.

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
Visible streaming deltas are transient interface events. Persistence occurs only after one
validated terminal response; cancellation or a mid-stream provider error leaves no partial
assistant message. Provider fallback is prohibited after the first streamed frame.
Logs should default to operational metadata and redact authorization headers,
tokens, environment values, and private tool results.

Conversation databases, logs, screenshots, audio, and models belong outside the
repository under user's local application-data directory. Conversation and
explicit-memory deletion are implemented; richer-media retention remains deferred.

## Durable memory

- Working, episodic, profile, semantic, and task records are partitioned by a pseudonymous local
  user/device host ID. Request content cannot choose that ID; it is not a remote credential.
- Deterministic extraction writes candidate records only. Promotion requires the exact host,
  trusted local interface, candidate version, and content SHA-256. Confidence is never authority.
- Conversation/message/tool/import/explicit/derived provenance, trust, sensitivity, confidence,
  correction lineage, derivation edges, and conflicts remain inspectable.
- Retrieval admits committed, unexpired records only. Relevance, recency, confidence, and trust
  contribute to a visible reason. Conflicts and untrusted sources are warned, not silently merged.
- Private or unknown projected context forces local routing before provider disclosure. Projection
  has hard record and character caps; retrieval failure adds no invented context.
- Forget physically removes canonical content, FTS rows, provenance, conflicts, and sole-source
  derivations. Content-free tombstones/events retain no deleted plaintext or hash.
- Export is explicit, local, and exclusive-create. Retention is configurable per category. Backup
  copies remain separate artifacts and must follow the operator's access and expiry policy.

## Research boundary

- Only public HTTPS destinations pass deterministic URL/DNS checks. Fetching pins a validated
  global IP while retaining original Host/SNI verification and enforces redirect, type, byte,
  source, domain, and total-time limits.
- HTML/plain/PDF extraction runs in a short-lived isolated Python worker with a minimal environment,
  temporary working directory, and strict input/output/page/filter/deadline limits. It has no action
  tools; this process boundary is not a Windows AppContainer.
- Citation review binds each material claim to an exact source span, limits quoted words, and
  rejects fabricated, unknown, inactive, or structurally invalid evidence.
- A run is volatile by default. Durable storage consumes an exact one-use host approval for the
  displayed report digest. No webpage, model response, or conversational instruction can approve
  storage or promote research into trusted memory.
- Host-scoped inspection, revalidation, export, and exact source deletion are available. Changed or
  unavailable sources stale dependent claims; deletion removes dependent reports, claims,
  citations, conflicts, and indexes while leaving only content-free lifecycle evidence.

## Controlled computer access

- The environment master switch and host policy switch both default false. The model receives no
  action authority unless both are true and the entire bounded policy validates.
- Approval is a local CLI surface outside model/chat content. It binds an exact fingerprint and
  accepts only a generated `APPROVE <suffix>` phrase. Conversational agreement is not approval.
- Grants are short-lived, single-use, and bound to actor, Windows session/device, trusted
  interface, capabilities, action/version/arguments/preconditions, policy epoch, nonce,
  idempotency key, approval identity, and expiry.
- The broker is non-elevated and contains a fixed handler registry. It accepts no shell string,
  arbitrary executable path, inherited secret environment, dynamic tool registration, overwrite,
  delete, recursive mutation, or admin operation.
- Executables are enrolled by absolute path, file identity, and SHA-256; child argv is fixed in the
  host policy. File actions stay inside one dedicated root and reject traversal, alternate streams,
  reparse points, hard links, target expansion, cross-volume moves, and TOCTOU identity changes.
- Every action has fixed time/result/item limits, concurrency and retry semantics, a postcondition,
  and explicit recovery limits. Required audit failure before dispatch prevents the effect.
- Private/unknown tool schemas are filtered before every cloud-provider request, and private
  computer tools are denied before invocation on cloud-routed turns. Operator audit views
  omit arguments, private content, actors, fingerprints, and raw adapter results.
- The live policy fingerprint is checked again immediately before claim/dispatch. Disable rotates
  the authority epoch so old grants cannot revive after re-enable.
- Levels 3 and 4 have typed semantics but no enabled Phase 3 handlers. Level 4 is always denied.

Clipboard exact authority is stored only in the private action database for its short lifecycle;
prior clipboard plaintext is captured only after approved dispatch and remains volatile. Printing
accepts only bounded controlled `.txt` content through the Windows `TEXT` datatype; RAW printer
languages and physical-output claims are prohibited.

See [Controlled Computer Access](CONTROLLED_COMPUTER_ACCESS.md) for setup, audit, recovery, action
limits, and Windows-specific uncertainty after cancellation of an in-flight native call.

## Voice privacy and safety

- Voice is software-disabled by default; explicit push-to-talk is the only supported capture mode.
- Always-listening wake-word and acoustic settings are typed as literal `false`; configuration
  rejects attempts to enable them.
- A visible `MIC ON` event accompanies capture. A separate control file is polled during active
  turns so `jarvis voice disable` cancels capture/output without disabling text chat.
- Raw microphone PCM and synthesized PCM are bounded in size/duration and remain ephemeral. Voice
  settings store only stable device IDs and kill state; transcripts follow normal conversation
  retention only after successful core submission.
- VAD, STT, wake inference, and TTS are local CPU paths. No cloud STT/TTS adapter is configured.
- TTS sends untrusted text over subprocess stdin to a fixed encoded PowerShell/SAPI program; model
  text is never interpolated into shell source.
- Wake/clap outputs are typed untrusted intents, not authority. They cannot execute computer actions
  without the later permission broker.
- Render-reference suppression and explicit output cancellation limit self-trigger and barge-in;
  endpoint/model failures return a typed error and preserve text fallback.

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
