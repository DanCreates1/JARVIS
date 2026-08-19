# Security model

JARVIS processes private conversations and will eventually control local devices.
Security therefore belongs in the runtime architecture, not only in prompts.

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
sanitized tool result. Its sole automatically allowed tool reads the clock.

Before any future side-effecting tool can execute, the runtime must additionally:

1. classify the requested side effect;
2. apply the policy rule for that risk class;
3. request human approval when the class requires it; and
4. record the decision and sanitized outcome.

Suggested risk classes are read-only, local write, application launch, network,
and privileged. The Phase 1 clock tool is the only automatically allowed class.

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
repository under the user's local application-data directory. Deletion and
retention controls will be added before collecting richer media.

## Secrets

- Never commit `.env`, tokens, passwords, cookies, private keys, certificates,
  or provider credentials.
- `.env.example` contains only safe local defaults and empty placeholders.
- Prefer environment variables or an operating-system credential store for
  future secrets.
- Never print the entire process environment during diagnostics.
- Rotate a secret immediately if it enters Git; ignoring it afterward does not
  remove it from history.

CI scans repository history for secrets. Local quality checks use Gitleaks when
it is installed.

## Local model and network security

Ollama defaults to `http://127.0.0.1:11434`. Remote model endpoints require an explicit
configuration change and HTTPS. Phase 1 does not add provider authentication; a remote endpoint
must sit behind a separately reviewed authenticated boundary before private prompts are sent.
HTTP clients use bounded request timeouts and narrowly constructed URLs. An explicit wire-level
response-size limit is required before JARVIS accepts remote or multimodal provider payloads.

Model weights are downloaded only through an explicit setup command and are not committed. Phase
1 diagnostics report the selected name and whether it is installed. Recording Ollama's local
model digest is a future hardening step so changed weights become visible.

## API security

When introduced, the API must bind to loopback by default, disable permissive
CORS, validate request sizes and schemas, and rate-limit expensive operations.
Non-loopback binding must be refused unless authentication is configured. Remote
access should terminate TLS at a reviewed boundary; it is not enabled merely by
changing a host string.

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
