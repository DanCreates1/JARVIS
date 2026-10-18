# F13 — PWA push-to-talk

Status: **F13A–F13D complete within repository/automated scope**, 2026-10-17.
Baseline `b6fd3fd` on `main`, shell v9 → **v10**. Scope: [F13 contract](../PWA_F13_PUSH_TO_TALK.md).
Only pre-existing dirty files were held native manifests; neither is part of this release.

## Milestones

- [x] F13A: Core-owned transcription-only service; authenticated scope/host boundary, readiness,
  default-off configuration, software kill, upload/deadline/rate limits and worker-owned capacity.
- [x] F13B: deliberate foreground capture, canonical PCM, accessible controls, lifecycle cleanup,
  session/conversation/composer ownership, editable draft and existing explicit Send; shell v10.
- [x] F13C: automated functional/failure/privacy/authentication/lifecycle/accessibility tests,
  actual browser worklet and real local model acceptance with synthetic audio.
- [x] F13D: final full release/security gates, completion documentation and safe-source publication
  under standing authorization; exact published-ref verification is recorded in closing chat.

## Implemented contracts

`voice/pwa.py` composes STT/VAD and host controls into the existing web/Core lifecycle. No second
Core, desktop audio, TTS, wake listener, chat submission, tool or conversation is constructed.
Optional imports remain lazy; local readiness failure leaves text service available. Host gate
`JARVIS_PWA_VOICE_ENABLED` defaults false; software voice control independently fails closed.
Authenticated `GET /api/v1/client/voice` reports bounded availability/format/limits; status includes
availability only for `client.chat`. PWA cannot change controls.

`POST /api/v1/client/voice/transcriptions` accepts only binary canonical 16,000 Hz mono signed
16-bit little-endian PCM. Cookie/CSRF/origin or signed-session token admission precedes body reads;
signed requests still require full final signed-body proof before inference. Existing scope,
same-host checks, identity expiry/revocation, mixed-credential rejection and global limits remain.
Route limits: **3,840–960,000 bytes**, even shape and actual sample-derived duration,
**120–30,000 ms** (lower host capture limit applies), **15-second** middleware read deadline,
**six starts/device/minute**, **one host runtime slot**, no queue, local STT timeout capped at
**90 seconds**. Duplicate/invalid/mismatched length, excess streamed data, slow uploads, unsupported
methods/formats, busy state and invalid identity are rejected safely. API responses are no-store.

Upload reservation has an ownership token. After handoff, only actual adapter completion frees
capacity. Cancellation, disconnect, timeout, kill or revocation requests cooperative cancellation
and discards results; it never cancels the native thread's await to pretend work stopped. Core
revalidates identity/kill during inference and immediately before text exposure, including after
audit I/O. Shutdown drains active native work. Immediate native termination is not claimed.

Browser Record requires connected Chat, empty composer, no uncertain/pending turn and no other
voice operation. Only Record requests permission. Permission wait is bounded to **30 seconds**;
late grants stop all tracks. Worklet streams area-average resampling at actual input rate,
downmixes mono, clamps signed LE PCM, bounds 2,048-byte messages and unacknowledged backlog, and
enforces the exact sample ceiling. Explicitly zero-filled output keeps browser graph processing
without monitoring microphone sound through speakers. Stop closes tracks before upload; Discard,
Escape, navigation/history changes, hidden/pagehide/offline/session/logout and audio failure clean
up tracks, ports, graph, context, timers and buffers. Stale results cannot overwrite another owner.
Success fills the memory-only editable composer and announces **Review transcript, then Send**.
No capture resume, retry or Send is automatic.

Only bounded outcome/timing metadata enters the existing audit. Raw audio/transcript stays in
process/browser memory; no logs, URLs, database, storage, API cache or cloud speech. Memory
zeroization is not guaranteed. Only explicitly sent text enters ordinary Core storage/privacy
routing/approval controls. Worklet joins explicit public shell assets; script/worker/cache advance
together to v10. Online documents fetch current policy; offline cached documents always deny
microphone. Legacy pages and default-off production retain `microphone=()`.

## Automated evidence

Windows, Python **3.11.9**, Node **24.20.0**, Edge **155.0.4283.45**. Tests use fakes/synthetic
signals except the separately identified real local STT acceptance below.

| Gate | Result |
| --- | --- |
| Root lock/base locked sync | Pass; 119 resolved / 69 base packages checked |
| Garmin sidecar lock/locked sync | Pass; 20 resolved / 16 checked |
| Windows bootstrap | Pass, official CPython 3.11 through existing `pwsh` |
| Locked voice extra | Pass; 27 optional packages installed; no lock/dependency-source changes |
| Ruff format/lint | Pass; 423 files |
| Mypy | Pass; 167 source files |
| Initial full strict pytest | **1,503 passed / 3 existing optional skips**, **85.73%** coverage, **136.10s** |
| Final full strict pytest | **1,505 passed / 3 existing optional skips**, **85.76%** coverage, **133.91s**; unchanged 85% threshold |
| Final focused checks | **71 passed**, followed by **27 API tests** after final post-audit safeguard |
| Real-script lifecycle | **96/96** pass: original 73 retained, 23 voice ownership/lifecycle cases |
| PCM/cache tests | **7/7** pass: 16,000/44,100/48,000 Hz, irregular blocks, stereo, exact 30-second cap, silent output, backlog and offline policy |
| Desktop browser | **72/72** existing layout cases, **6/6** short-viewport cases, **12/12** recording layouts; actual browser AudioWorklet with synthetic MediaStream, Enter/Space/Escape, accessible names/hidden controls, draft focus and track-stop-before-upload |
| Contrast | Pass; existing text/boundary/focus ratios unchanged; 44px recording controls pass at six widths and 16/32px fonts |
| Root including voice / sidecar dependency audits | No known vulnerabilities |
| Gitleaks history/staged | Pass; 120 baseline commits (~7MB) and staged safe source (~87KB), no leaks |
| Doctor | Pass; packaged worklet included, production controls unchanged |
| Transport benchmark | **100 reconnects / 10,000 events**, zero duplicates/gaps/cross-session deliveries/offline effects/private state retained |
| Documentation links/whitespace | Pass; **8 documents / 133 relative links / zero missing targets**; worktree/staged whitespace clear |

Final transport sample: p50/p95 **0.0344/0.0621ms**, RSS growth **0.805MiB**, complete shell
**76,768 bytes**, unchanged ceilings **25ms / 50MiB / 256,000 bytes**. Synthetic transport only;
not phone performance. Existing Starlette TestClient deprecation warning remains.

### Real local STT, distinct from fakes

Locked voice packages include faster-whisper **1.2.1**, CTranslate2 **4.8.1**, Silero VAD **6.2.1**,
NumPy **2.4.6**, torch **2.13.0**. Existing explicit `voice setup` succeeded, preparing configured
`base.en` and public setup models in private application storage. Windows Application Control
blocked the generated `jarvis` launcher (OS error **4551**); normal `python -m jarvis` entrypoint
passed. No policy was weakened. A base sync removes extras; voice extra was restored afterward.

`scripts/pwa-voice-acceptance.py` uses locally generated Windows SAPI speech, no microphone,
real Silero VAD and faster-whisper **CPU/int8**, `local_files_only=True`. An isolated ignored
fixture settings file enables only the test service; host controls are unchanged. Final **3,374ms**
clip, **107,966 PCM bytes**, exact normalized reference match; local readiness **6,106.04ms**,
transcription **800.15ms**. Earlier run was **2,948.62/643.13ms**; these are individual
desktop observations, not a percentile or phone measurement. No fixture audio or transcript is
published. Browser harness transcription responses are fakes and establish no model-readiness claim.

Primary specifications rechecked: [Media Capture](https://www.w3.org/TR/mediacapture-streams/),
[Web Audio](https://www.w3.org/TR/webaudio/), [faster-whisper upstream](https://github.com/SYSTRAN/faster-whisper).
Browser evidence caught and fixed a zero-output worklet graph that did not render in Edge. The
final harness waits for actual bounded PCM, avoiding timing-only assumptions under CPU load.

## Commands and publication boundary

All shell work uses RTK. Main release commands:

```powershell
rtk uv lock --check
rtk uv sync --locked
rtk uv lock --project garmin_sync --check
rtk uv sync --project garmin_sync --locked
rtk proxy pwsh -NoProfile -File scripts/bootstrap.ps1
rtk uv sync --locked --extra voice
rtk proxy uv run --extra voice python -X utf8 -m jarvis voice setup
rtk uv run --extra voice ruff format --check .
rtk uv run --extra voice ruff check .
rtk uv run --extra voice mypy src
rtk proxy uv run --extra voice python -m pytest --basetemp runtime/f13-release-final-1 --tb=short
rtk proxy node --test tests/pwa/garmin-lifecycle.test.cjs tests/pwa/pcm-worklet.test.cjs
rtk proxy node scripts/pwa-accessibility-check.cjs
rtk proxy uv run --extra voice python -X utf8 scripts/pwa-voice-acceptance.py
rtk uv run --extra voice python scripts/phase8c-pwa-benchmark.py --output runtime/mvp4-fixes/f13-transport.json
rtk proxy uv run --extra voice python -m pip_audit
rtk proxy uv run --extra voice python -m pip_audit --path garmin_sync/.venv/Lib/site-packages
rtk proxy gitleaks detect --source . --redact --no-banner
rtk proxy uv run --extra voice python -X utf8 -m jarvis doctor
rtk git diff --check
```

Fresh pytest bases resolve within ignored workspace `runtime/`. Desktop JSON/screenshots/profiles,
synthetic acceptance JSON and fixture control files stay ignored under `runtime/mvp4-fixes/`.
Model cache stays outside Git. Production voice remains default off; no server restart, new
credential, account, scope, enrollment, health authority, signing, spend or deployment occurred.
The **$0** limit and consequential-action approvals remain authoritative after Send.

Held SHA-256 baselines, retained and excluded from publication:

- `mobile/package.json`: `f1f34cd63792e55bd4db5293d3e9189eac0470d7a8fc81c58dbd895cf89796c4`
- `mobile/package-lock.json`: `acd08d9aa861f1f047b868a49889f3b8f04041539028f7c5ad793b5c2a66bf57`

Both held hashes verified unchanged; neither file staged or published. Closing chat records exact
HEAD/tracking/live-upstream match after publication. Native dependency hold remains separate;
no native aggregate gate is claimed. M3C health-access authority remains separate.

Manual phone checks: **skipped by owner; unverified**. Desktop synthetic graph/model fixtures do
not establish iPhone Safari/Home Screen permission, interruption, spoken accessibility, phone
performance or physical/MVP acceptance. Aggregate MVP 4 remains incomplete. Active PWA completion
estimate stays **94%**, based on existing MVP milestones; F13 adds optional verified input without
adding physical acceptance credit. Stop at F13; **no next phase queued**.
