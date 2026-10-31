# Phase 12 — Foreground voice

- Status: `implemented-closeout-pending`
- Started / updated: 2026-10-31
- Namespace: current numbered roadmap
- Recommended Codex model / reasoning: `gpt-6-astra` / `xhigh`; `ultra` for authority
  (recommendation only; no UI model change claimed)
- Recorded baseline / five-hour stop: 2026-10-31T11:53:27-04:00 / 2026-10-31T16:53:27-04:00

## Objective and scope

Explicit `foreground-voice` PWA profile on the existing Windows Core. Deliberate Record/Stop,
local VAD/STT, editable memory-only transcript, explicit Send, ordinary canonical text reply.
Text replies are the selected reply experience: no automatic or browser-vendor speech output.
Existing local SAPI TTS remains the legacy desktop adapter and synthetic fixture generator;
no new audio-output endpoint, playback grant or second Core is needed for this workflow.

Reuse F13 PCM transport, capture lifecycle, service and host software kill. Profile selection
alone must not enable host voice: retain explicit configuration plus software control and browser
consent. No production activation, microphone capture, model download, cloud speech, wake/clap,
background capture, new scopes, enrollment or Windows actions. Phase 7 prerequisite complete.

## Baseline and preservation

- main `4120a89`; Phase 11 complete. Read full execution/master, current architecture decision,
  F13 contract/receipt, Legacy Phase 2 receipt and hands-free boundaries before implementation.
- 28 held paths copied/hashed under ignored `runtime/phase12/baseline/`, including provider/native
  edits and shared configuration/bootstrap/architecture documents. Publish task hunks only.
- Starting 97-package optional inventory preserved there. Locks/prototype prompts/corpora and
  launchers remain unchanged unless an actual failed security gate requires a documented repair.
- Wikimedia `authentication_required`, legacy NVIDIA latency and native publication hold retained.

## Acceptance checklist

Frozen before implementation and current measurement:

- [x] Profile retains daily local-only model/routing/clock and disables all other integrations,
  tools, remote models and automatic features even with stale dotenv flags. Voice requires both
  explicit `pwa_voice_enabled` and host software control, healthy local adapters, exact identity,
  `client.chat`, origin/CSRF and browser consent. Production controls remain unchanged.
- [x] Real-script/PCM/API matrix covers permission denial/late grant, silence/malformed/oversize,
  busy/rate/deadlines, cancellation/native-worker capacity, offline, device/context loss, stale
  session/conversation/composer, logout/restart/replay and no automatic Send/retry/capture.
  F13 ceilings unchanged: mono 16 kHz s16le, 120–30000 ms, 3840–960000 bytes, one worker,
  six starts/device/minute, 15 s upload, <=90 s STT, 30 s permission wait.
- [x] Current Windows local synthetic SAPI/VAD/STT evidence; exact reference match in PWA service.
  Retain fixed Legacy Phase 2 corpus thresholds: quiet WER <=20%, noisy/accented <=35%,
  short interactive warm p95 <=1000 ms, RTF p95 <=1.0, zero adapter errors, RSS growth <=4 GiB,
  discrete GPU growth <=512 MiB with installed local LLM resident. Cold load reported separately.
  No physical microphone/speaker claim. Missing authorized assets are an explicit external limit.
- [x] Current isolated browser/auth/Core/local speech/review/Send/text reply workflow and canonical
  receipts; no conversation before Send, no private audio/transcript persistence before Send,
  no cloud/model speech, no unauthorized tool effects. Failure leaves typed Send usable.
- [x] Desktop accessibility/reflow/keyboard and profile regressions including `prototype-text`;
  transport benchmark: 100 reconnects/10000 events, zero isolation/replay failures,
  p95 <=25 ms, RSS growth <=50 MiB, shell <=256000 bytes. Phone checks
  **skipped by owner; unverified**.
- [ ] Full working/isolated release gates, >=85% coverage, locked root/base/restored-extra and
  sidecar audits, exact-source/history secrets, whitespace/links, recovery docs, task-only
  publication and fresh exact CI. Held paths preserved by task-hunk recomposition.

## Milestone log

- Baseline saved; current official Media Capture, Web Audio and faster-whisper documentation
  reviewed. Reuse consent/track-stop semantics, actual-rate worklet resampling and local-only
  model loading. No dependency upgrade or host-control change required by design.
- Explicit profile/startup and capability UI implemented. Profile preserves independent host
  gate, local-only daily routing, deterministic clock and disabled integrations. Shell advances
  v19 to v20; worklet format/code remains v12. Voice controls moved out of attachment wrapper;
  current browser checks exposed the otherwise-hidden controls before publication.
- Focused current profile/API/service matrix passes 115 tests; real-script/PCM passes 173.
  Foreground desktop keyboard/worklet/reflow passes 13 groups including twelve capture layouts.
- Disposable real HTTPS/browser/auth/Core/Silero/faster-whisper/Ollama workflow passes four
  groups at `runtime/phase12/acceptance-zyxq8v99/`: exact synthetic draft, no conversation/model
  before Send, edited clock Send/replay, local model text reply, Discard/restart/software-kill
  typed fallback and logout erasure. 769 ms individual browser Stop-to-draft observation;
  one local model call, zero cloud calls/research-source/report/memory rows.
- Direct real local service reference matches exactly: 3374 ms / 107966-byte SAPI fixture,
  readiness 2934.71 ms, transcription 770.51 ms. These are individual Windows observations,
  not percentiles or physical evidence. Existing synthetic script writes ignored F13 evidence.
- Failed harness attempts preserved: rapid readiness polling hit rate limits; corrected to
  one-second bounded polling. Disposable data directory initially lacked model cache; injected
  existing read-only cache, retaining isolated controls. Scripted click lacked browser audio
  activation; changed to trusted keyboard input. Immediate fixture onset lost initial speech;
  added fixed 500 ms leading/trailing silence and reused original standard synthetic sentence.
  Review/edit remains mandatory; short-phrase variation is not disguised as speech perfection.
- Restart/typed fallback exposed an actual routing bug: any old tool message suppressed future
  deterministic clock requests. Router now checks the current request; latest tool result still
  settles directly. Two regression variants plus current real workflow confirm fresh clock
  receipts without a model call. No tool authority or action added.
- First frozen 30-sample quality run meets all accuracy/latency/RSS/residency targets, but GPU
  telemetry is unavailable: current driver temperature `46.84` broke integer-only parsing.
  Memory query itself works. Parser now accepts finite fractional temperature, preserving integer
  memory counters and fail-closed missing/malformed telemetry. Eight benchmark tests pass.
  Original failed artifact is retained separately; unchanged full benchmark rerun underway.
- Repaired full corpus rerun passes every unchanged threshold: quiet/noisy WER 0%, accented
  17.25%, short interactive p50/p95 562.48/833.53 ms, RTF p95 0.4779, cold load 2812.26 ms,
  RSS growth 479072256 bytes, discrete GPU growth 0 MiB (2271 MiB before/after), resident
  `qwen3:1.7b`, zero adapter errors. Long accent passages are accuracy fixtures, not 30-second
  PWA transport fixtures; their latency p95 is 6144.57 ms. No wake/clap or physical gate implied.
- Full working gate passes 1700 tests / 3 existing skips, 86.13% branch coverage, 198.29 s.
  Eight desktop profiles pass; transport has 100 reconnects/10000 events, no isolation/replay
  failures, p50/p95 0.1336/0.4271 ms, 0.773 MiB RSS growth, 137934-byte shell.
- Base/restored optional and sidecar strict audits pass. Exact original 97-package inventory
  restored after base sync; lockfiles unchanged. 232 task-document links/anchors and 580 exact
  publication source files verified; source/history secret scans clean. Five shared task hunks
  recomposed separately from held work, with inverse held recomposition verified.
- Repeated working browser workflow passes at `runtime/phase12/acceptance-3rdlvzd_/` (1612 ms
  individual Stop-to-draft under concurrent release tests). Isolated source passes the same
  real workflow at `runtime/phase12/publication-v3/runtime/phase12/acceptance-9uff4m9l/`
  (785 ms). Each has one local model call and zero cloud/research/memory rows. These individual
  browser observations are not the frozen warm STT percentile benchmark.
- Isolated full gate passes 1701 tests / 3 existing skips, 86.11% coverage, 204.61 s. Extra
  test is the published Groq contract retained in safe source; held provider removal is excluded.
  Windows official-Python bootstrap passes without install/model flags. No OS policy bypass.

## Decisions, authority and blockers

Selected foreground input plus text replies provides review/cancel control without implicitly
disclosing reply text to browser speech vendors or extending remote output authority. Full duplex,
spoken PWA replies and physical acceptance remain outside this selected workflow. Legacy TTS
and historical device evidence remain intact, not relabeled as current evidence.

## Verification and measurements

Raw evidence stays ignored under `runtime/phase12/`; sanitized aggregates only in Git.
Windows build 26300; working CPython 3.11.9, isolated base CPython 3.11.16; Node 24.20.0,
uv 0.12.15, faster-whisper 1.2.1, CTranslate2 4.8.1, Silero 6.2.1. Local model `base.en`,
CPU/int8/four threads/16 kHz, local files only. No speech/model download or physical device use.

Working format/lint/Mypy and synthetic empty-state doctor pass. Isolated format/lint/Mypy,
base and sidecar audits, full tests and 173 PWA/PCM checks pass. Existing Starlette TestClient
deprecation and three platform/capability skips retained. Fresh publication CI pending.

| Gate | Working source | Isolated publication source |
| --- | --- | --- |
| Full strict pytest / 85% floor | 1700 passed / 3 skipped; 86.13%; 198.29 s | 1701 passed / 3 skipped; 86.11%; 204.61 s |
| Format / lint / Mypy | Pass; 171 source files | Pass; 171 source files |
| Root base / optional / sidecar audits | Clean / clean / clean | Clean base/sidecar; same audited optional environment used for live speech |
| PWA lifecycle / PCM | 173 pass | 173 pass |
| Real browser/Core/local speech | 4 groups; 1 local model call | Same |
| Frozen STT corpus | 30 samples; every threshold passes | Same unchanged adapters/lock; isolated application acceptance separate |
| Browser profiles | All eight pass | All eight pass |
| Links / source / history secrets | 232 links; 580 files; clean | Reviewed exact safe tree |

## Known limits, recovery and deferred scope

Text works when speech unavailable; Discard/Escape stops capture, Cancel reply stops generation.
Disable host voice or configuration for new captures; never resume automatically. Native inference
cancellation is cooperative; capacity remains held until actual worker termination. No guaranteed
Python/JavaScript memory zeroization. Laptop must be reachable. Physical/native/MVP/production
acceptance remains unestablished.

## Publication and handoff

- Task-only source/hunks: 26 paths, five shared-file recompositions; held native/provider edits
  excluded. Exact source snapshot: ignored `runtime/phase12/publication-v3/`.
- Commit/tracking/live remote/fresh CI: pending.
- Progress: 11/19 primary receipts closed (~58%), unweighted management count; no physical credit.
- Next current phase remains Phase 12 until this receipt closes. No Phase 13 implementation.
