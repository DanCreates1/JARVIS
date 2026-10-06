# Phase G Attachments Completion Report

Status: `complete` (local release and Git publication)
Started / completed: 2026-10-05
Active subphase: Phase G — Attachments (published)
Recommended model / reasoning: `gpt-6-astra`, `xhigh`
Session start / five-hour stop: 2026-10-05 19:00 / 2026-10-06 00:00 America/Toronto

## Objective

Ship default-off local conversation attachments with typed metadata/status, bounded durable
upload storage, isolated text/PDF/image processing, chunk retrieval, deletion/expiry, and
capability-checked local vision. Preserve Phase C public-only acquisition and Phase D discovery.

## Baseline

- Clean `main` at `38dcff4`, matching tracking ref; Phase F complete and pushed.
- Windows CPython 3.11.9; locked `.bootstrap-venv`; 119 locked packages.
- Pillow 12.3.0 already locked as optional vision dependency; promoted to required dependency
  for attachment image normalization. No package version changes; 69 packages in base/dev install.
- No credential use, paid service, new model download, remote upload/deployment or OS effect.
- Phase C Wikimedia `authentication_required` remains external and separate.

## Acceptance checklist

- [x] Typed conversation/host-bound metadata, states and content integrity.
- [x] Transactional aggregate byte/count quotas, exact repeat-upload deduplication, retention.
- [x] Isolated allowlisted UTF-8/PDF/PNG/JPEG extraction with bounds and sanitized errors.
- [x] Bounded query-relevant chunks with attachment/chunk provenance; content stays untrusted.
- [x] Default-off runtime wiring and local CLI/loopback browser upload/use/inspect/delete.
- [x] Local-only capability-checked vision; missing dependency/model degrades explicitly.
- [x] Cross-conversation/host, spoofed type, malicious PDF/image, injection and abuse gates.
- [x] Cancellation, timeout, failure, restart, duplicate, quota and deletion/recovery tests.
- [x] Fixed 100 text retrieval cases: 100% expected-chunk hits, projection <=8,000 chars,
  retrieval p95 <=100 ms; 20 isolated parses p95 <=2,000 ms; zero disclosure/authority failures.
- [x] Workstation synthetic upload/restart/retrieve/delete smoke; full release gates/docs.
- [x] Built-wheel/fresh locked dependency reproduction and encrypted attachment backup/restore.

## Milestones

1. Baseline / contracts / threat model: complete. Clean baseline, current primary parser/OS/provider
   docs reviewed, fixed quantitative gates established before implementation.
2. Durable store / isolated processing / local vision adapter: complete. Migration 015, quota
   reservation/dedup, digests, retention, restart recovery, bounded worker and local capability port.
3. Runtime / CLI / local browser: complete. Private cited context, local controls, sticky privacy,
   adversarial/failure suites, synthetic production CLI/browser streaming smoke. Fixed pre-existing
   Python/JavaScript newline escaping that prevented local browser script execution.
4. Benchmarks / full gates / docs: complete. Safe local source commit permitted by standing
   authorization; publication completed after fresh owner Git credential authority on 2026-10-05.

## Decisions

- Original bytes, normalized image and derived chunks live in existing private SQLite database;
  no user filename becomes a filesystem path. Migration 015 adds attachment tables and sticky
  conversation privacy; existing conversation ownership remains unchanged.
- Exact conversation and host scope required for every operation. IDs alone grant no access.
- Raw/derived attachments never become trusted memory, automatic research input or execution tools.
- Upload sets sticky private conversation state. Follow-ups cannot turn source-derived terms into
  automatic research queries or cloud requests after deletion/restart. Client metadata cannot clear
  this state. Automatic memory-candidate capture is suppressed; explicit approved memory is separate.
- Uploads and attachment chat require local interfaces; remote/PWA attachment transport deferred.
- Vision configured separately, restricted to loopback Ollama, no cloud fallback or auto-download.
- TTL enforcement occurs during explicit operations; no background worker. SQL deletion is logical
  removal, not secure erasure of WAL, backups, transcripts or underlying storage.

## Verification evidence

Commands used the established locked `.bootstrap-venv` on this Application Control workstation:

```text
rtk uv lock --check
PASS: 119 locked packages
UV_PROJECT_ENVIRONMENT=.bootstrap-venv; rtk uv sync --locked
PASS: 69 installed packages checked
rtk proxy .bootstrap-venv\Scripts\python.exe -m ruff format --check .
PASS: 384 files
rtk proxy .bootstrap-venv\Scripts\python.exe -m ruff check .
PASS
rtk proxy .bootstrap-venv\Scripts\python.exe -m mypy src
PASS: 156 source files
rtk proxy .bootstrap-venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp runtime/phase-g-browser-final --cov-report=json:runtime/phase-g-final-coverage.json --tb=short --show-capture=no
PASS: 1,250 passed, 3 existing skips, 85.31% coverage, 127.65 seconds
rtk proxy .bootstrap-venv\Scripts\python.exe -m pip_audit --strict
PASS: no known vulnerabilities
rtk gitleaks detect --source . --redact --no-banner
PASS: 70 prior commits / 6.12 MB, no leaks; staged source checked separately before commit
rtk git diff --check
PASS
rtk proxy .bootstrap-venv\Scripts\python.exe scripts/phase-g-attachments-smoke.py
PASS: production doctor, private attachment chat, denied Fast/cloud override, lifecycle cleanup
rtk uv build --offline --wheel --out-dir runtime/phase-g-dist
PASS: worker and migration included in wheel
UV_PROJECT_ENVIRONMENT=runtime/phase-g-clean-env; rtk uv sync --locked --offline --link-mode copy
PASS: fresh 69-package locked install (cached CPython 3.11.16; no download)
rtk uv pip install --offline --no-deps --python .bootstrap-venv/Scripts/python.exe --target runtime/phase-g-wheel-installed runtime/phase-g-dist/jarvis_assistant-0.1.0-py3-none-any.whl
PASS: built wheel installed separately
rtk proxy .bootstrap-venv\Scripts\python.exe -I runtime/phase-g-wheel-smoke.py
PASS: trusted CPython 3.11.9, fresh dependency roots, installed-wheel imports; text/image worker,
      migration, private retrieval, unavailable vision, deletion
```

One existing Starlette/httpx deprecation warning remains. Worker source is omitted from parent
coverage like existing research worker; real subprocess tests exercise parser/security behavior.
Attachment models/contracts 100%, processing 93%, service 92%, local vision adapter 82%.
Encrypted backup/restore test preserves BLOB payload, chunks and sticky privacy with exact logical
content digest. Required gates passed; no gate or threshold weakened.

## Benchmarks and workstation acceptance

- Frozen 100 retrieval queries over 100 synthetic chunks: 100/100 expected hits, zero failures,
  maximum projection 6,655 chars. Latest run p50/p95 3.859/4.890 ms (p95 gate 100 ms).
- 20 real isolated text parses: p50/p95 129.908/151.496 ms (p95 gate 2,000 ms).
- Lifecycle benchmark closes/reopens store, retrieves and deletes; no remaining source rows.
- Optional installed `qwen3.5:0.8b` synthetic red-image oracle: warm pass at 1,348.504 ms.
  Initial cold call timed out at 60,004.474 ms and safely reported `vision_unavailable`; retained
  as cold latency limitation, not hidden or accepted as a successful interpretation.
- Synthetic production runtime used existing `qwen3:0.6b`, local-only policy, temporary data,
  disabled current context/research/computer/coding paths and no API credentials.
- Real loopback browser upload displayed ready; selected source streamed correct synthetic oracle
  and `local / private` route. Node.js 24.20.0 syntax check and browser console checks passed.
  Test tab/server/private data cleaned; synthetic screenshot remains ignored in `runtime/`.
- Windows 10.0.26300, Intel64 Family 6 Model 141, CPython 3.11.9, Pillow 12.3.0, pypdf 6.19.0.
  No cloud/research/effect calls, credential use, model download or cost.

## Security and privacy

Threats: filename/path injection, type confusion, compressed/parser resource abuse, worker hang,
credential inheritance, cross-host/conversation access, source/model prompt injection, cloud
override, automatic research disclosure, replay/quota races, corrupt/restarted state.

Tests include resource-bomb image/PDF rejection, animated/type-spoofed media, inert PDF URI,
missing dependency, malformed/flooded worker output, timeout/cancellation/child reap, minimal
environment, quota race across instances, deletion during vision, scope failures, invalid public/
oversized/provenance projection, and follow-up privacy after restart/deletion. SQL debug sentinel
test verifies uploaded content does not enter logs. Vision rejects remote profiles/tool calls and
malformed/oversized answers before unsafe use. No new model tool, grant or action owner is added.

## Blockers

No Phase G release or publication blocker. Phase C smoke remains `authentication_required`; no
retry or credential workaround. Fresh owner authority on 2026-10-05 permitted existing Git
credentials only for origin verification and normal main pushes, including this publication
receipt. No credential changes or application-provider credentials were used.

## Git publication receipt

- Publication session began with clean `main` at `1cfde91`, one commit ahead of tracking ref
  `38dcff4`; fresh `git ls-remote origin refs/heads/main` confirmed remote baseline.
- Implementation commit: `1cfde910b8b23e78034b21f1e70f35417445d477`.
- `rtk git push origin main`: PASS, `38dcff4..1cfde91 main -> main` on 2026-10-05.
- Post-push local HEAD, `origin/main` and remote `refs/heads/main` matched implementation SHA;
  worktree was clean before this documentation receipt.
- Fresh Gitleaks scan: PASS, 71 commits / 6.25 MB, no leaks. Implementation diff whitespace: PASS.
- Existing full local gate evidence above remains applicable; publication changes documentation
  only. No runtime data, generated artifacts, force-push, deployment or Phase I work included.

## Known limits and deferred scope

Remote upload scopes, mobile UI, cloud vision, OCR binaries and real vision-model downloads
require separate scope/authority. No credentials or paid services without fresh authority.
Vision can time out cold; no automatic retry. Process boundary is not an OS filesystem/network
sandbox. Logical payload quota is not a physical DB/WAL disk quota. Browser reload does not restore
selection/list automatically; CLI exposes durable lifecycle. SQL deletion does not securely erase
backups, transcripts or storage. Full settings/limits: [Attachments](../ATTACHMENTS.md).

## Recovery and rollback

Disable attachments to stop new upload/projection; explicit lifecycle CLI remains available to
inspect/delete owned state. Delete exact attachment or conversation to remove original and derived
rows. Preserve migration and private database during source rollback.

## Final handoff

Local release and Git publication complete. Implementation published as `1cfde91`; this
documentation receipt is a separate safe source commit under the same Git publication authority.
Stop before Phase I — Email; fresh phase authority is required and H memory baseline is complete.
No email account, application credential, deployment, message or paid service authority transfers
from this report. Phase C/D ownership boundaries and the Wikimedia blocker remain unchanged.
