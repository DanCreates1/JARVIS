# Phase I Email Progress Report

Status: `blocked-external` (aggregate I); IA local read/prepare complete
Started / updated: 2026-10-05
Active subphase: IB — Live provider integration (not started; authority pending)
Recommended model / reasoning: `gpt-6-astra`, `xhigh`
Session start / five-hour stop: 2026-10-05 20:10 / 2026-10-06 01:10 America/Toronto

## Objective

Provider-neutral bounded email read/thread, extractive summary, candidate extraction and volatile
draft preparation. Explicit local CLI email context uses existing private model routing. IB live
provider access remains separate and requires fresh provider/credential/disclosure authority.

## Baseline

- Clean `main` at `b4cb77d`, matching local `origin/main`; no remote authentication attempted.
- G published; E/H/K baselines complete. C/D ownership preserved; Wikimedia
  `authentication_required` remains separate and unchanged.
- Windows 10.0.26300; CPython 3.11.9, locked `.bootstrap-venv`, 119 locked packages.
- No email implementation, provider selection or authorized mailbox credentials exists.

## Acceptance checklist

- [x] Typed read/thread/summary/extraction/draft contracts and used local export adapter.
- [x] Default-off explicitly configured local root; no automatic mailbox discovery.
- [x] Isolated bounded MIME text parsing; no HTML execution, attachment/link fetch or send.
- [x] Cited untrusted private projection <=8,000 chars; drafts remain volatile and unsent.
- [x] CLI controls and runtime composition; sticky conversation privacy across restart/follow-up.
- [x] Path/link/size/malformed/timeout/cancellation/restart/injection/override/removal tests.
- [x] Frozen 100 synthetic read/prepare cases, 100% provenance/oracle correctness, p95 <=1,000 ms,
  zero research/cloud/effect calls; maximum 16 messages/thread, 128 KiB/message.
- [x] Synthetic Windows CLI/runtime smoke and built-wheel packaging check.
- [x] Full lock/sync/format/lint/type/pytest/vulnerability/secret/doctor/whitespace gates.
- [x] Architecture/security/setup/status/checkpoint docs and local safe source commit.
- [ ] IB live provider authorization and provider smoke (external blocker; not IA exit).

## Milestones

1. Audit / fixed acceptance / threat boundary: complete.
2. Contracts / adapter / isolated parser / prepare service: complete. Explicit local export root,
   provider-neutral bounded models, plain-text-only MIME worker, cited digest and volatile drafts.
3. CLI / private runtime / failure and adversarial coverage: complete. Default-off composition,
   migration 016 sticky private state, local CLI, malformed/adversarial/restart/override tests.
4. Benchmarks / full gates / docs / handoff: complete locally. IA passes full repository gates,
   fixed benchmarks, Windows production smoke and installed-wheel checks. IB and Git publication
   require fresh authority; no credentials or external effects transferred.

## Decisions

- IA accepts owner-exported email only, rooted outside tracked source; no OAuth/IMAP/SMTP client,
  account discovery, credentials, polling, remote API, provider drafts or sending.
- Explicit folder IDs define export threads; no inferred subject-based thread merging.
- Summary is an extractive digest; action/date extraction yields quoted candidates, not tasks,
  calendar entries or commitments. Draft recipients/body are explicit owner inputs.
- Existing conversation store owns sticky email privacy; no second memory/approval/scheduler.
- Source content is never stored by adapter. Chat replies may contain private derived content and
  remain under existing conversation retention/deletion/backup policy.

## Verification evidence

Commands use the established locked Windows `.bootstrap-venv` launcher:

```text
rtk uv lock --check
PASS: 119 locked packages
UV_PROJECT_ENVIRONMENT=.bootstrap-venv; rtk uv sync --locked
PASS: locked environment synchronized; no dependency-version or lock changes
rtk proxy .bootstrap-venv\Scripts\python.exe -m ruff format --check .
PASS: 398 files
rtk proxy .bootstrap-venv\Scripts\python.exe -m ruff check .
PASS
rtk proxy .bootstrap-venv\Scripts\python.exe -m mypy src
PASS: 163 source files
rtk proxy .bootstrap-venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp runtime/phase-i-release-evidence --cov-report=term:skip-covered --cov-report=json:runtime/phase-i-release-coverage.json --tb=short --show-capture=no
PASS: 1,306 passed, 3 prior skips, 85.41% coverage, 111.91 seconds
rtk proxy .bootstrap-venv\Scripts\python.exe -m pip_audit --strict
PASS: no known vulnerabilities
rtk gitleaks detect --source . --redact --no-banner
PASS: 72 baseline commits / 6.26 MB, no leaks; staged source scan recorded below
rtk gitleaks protect --staged --redact --no-banner
PASS: 83.41 KB reviewed safe source; no leaks
rtk proxy .bootstrap-venv\Scripts\python.exe -m jarvis doctor
PASS: local runtime ready
rtk proxy .bootstrap-venv\Scripts\python.exe scripts/phase-i-email-benchmark.py --enforce
PASS: 100/100 cases, zero oracle failures
rtk proxy .bootstrap-venv\Scripts\python.exe scripts/phase-i-email-smoke.py
PASS: production private local-model chat, denied cloud override, draft unsent, restart/delete
rtk uv build --offline --wheel --out-dir runtime/phase-i-dist-closeout
PASS
rtk uv pip install --offline --no-deps --python .bootstrap-venv/Scripts/python.exe --target runtime/phase-i-wheel-closeout runtime/phase-i-dist-closeout/jarvis_assistant-0.1.0-py3-none-any.whl
PASS: separately installed wheel
rtk proxy .bootstrap-venv\Scripts\python.exe -I runtime/phase-i-wheel-check.py
PASS: installed-wheel imports, isolated email worker, migration 016, sticky privacy/deletion
rtk proxy .bootstrap-venv\Scripts\python.exe scripts/phase-c-automatic-research-benchmark.py --enforce
PASS: 100/100 cases, zero privacy/authority/persistence failures; p95 0.0634 ms (<5 ms)
rtk git diff --check
PASS
```

First full run exposed a stale Phase 9 expected migration count, corrected from 15 to 16.
Encrypted backup/restore now also proves sticky email privacy preservation. Required threshold
unchanged. Existing Starlette/httpx deprecation warning and three prior skips remain.
Final email models/contracts: 100% coverage; exports 87%, processor 90%, service 93%.

## Benchmarks

- Frozen 100 synthetic single-message threads, four read/prepare operations per case and 400 real
  isolated parser processes; no message/model cache. Entire four-operation case is timed.
- Latest p50/p95: 591.888/652.601 ms, below frozen 1,000 ms p95; largest projection 490 chars.
- Earlier run p50/p95: 553.392/661.705 ms, also passing. Zero oracle/provenance failures.
- Maximum 16-message Unicode projection tested separately within 8,000 chars; full-sized thread
  throughput is not represented by the single-message performance benchmark.
- Windows / CPython 3.11.9. Real synthetic production inference uses installed `qwen3:0.6b`.
- Live provider credentials, cloud calls, email effects, cost and live Wikimedia retries: zero.

## Security and privacy

Threats: hostile MIME/depth/size/headers, path traversal/links/reparse/hardlinks, source injection,
cloud override, follow-up research leakage, invalid adapter projection, missing/removed exports.
No send port is registered. Any future external write must reuse exact Phase 3 approval and
provider authorization; chat text and drafts confer neither.

Tests cover actual hardlinks, simulated reparse/mapped network drive denial, absolute/UNC/path ID
checks, MIME nesting/part/size/charset/header defects, HTML/attachment/forwarded-body exclusion,
minimal credential-free worker environment, parser timeout/cancel/reap, invalid projection scope/
public label/size, disable during acquisition, unavailable exports, explicit recipients/header
injection, restart/follow-up/metadata spoof/cloud override, unknown send tool denial and store
recovery after failed privacy update. No new execution/discovery owner, grant or email audit
content is added. MIME text is data only, with primary documentation linked in [Email](../EMAIL.md).

## Blockers

IB: provider/account/credential scopes and private-data access authority absent. No live login or
message allowed. Git publication also held at fresh external-effect authority boundary.

## Known limits and deferred scope

Live provider reads/writes, remote/mobile email transport, attachments, HTML-only extraction,
automatic thread inference, durable/provider drafts, semantic extraction, background polling.
Plain-text prefixes and keyword/date-shaped candidates are bounded, not exhaustive semantic
summaries. Export order is lexical; headers/dates/digests do not authenticate senders. No atomic
multi-message filesystem snapshot or OS-level parser sandbox is claimed. Started filesystem
reads cannot be forcibly canceled. Existing SQL retention/deletion does not securely erase WAL,
backups, terminal output or storage. No live mailbox acceptance or mobile email delivery claim.

## Recovery and rollback

Disable email; remove selection. Exports are never modified. Delete conversations with existing
lifecycle controls for derived chat content. Preserve privacy migration during source rollback.

## Final handoff

IA local implementation/functional/privacy/performance/Windows/packaging gates pass. Aggregate
Phase I remains `blocked-external`; retain this progress report instead of a Phase I completion
report until IB passes. Files changed: email package and migration, core/store/runtime/CLI/settings,
focused functional/security tests, Phase 9 backup assertion, benchmark/smoke and setup/state docs.
Safe source commit and report form one local commit; receipt recorded in chat after gates.
No authenticated remote verification or push occurred. Next: IB — provider selection and fresh
credential/private-read authority; never initiate live access or writes automatically. Preserve
Phase C/D boundaries and Wikimedia `authentication_required`. Git publication needs fresh
external-effect authority under this session's instruction.
