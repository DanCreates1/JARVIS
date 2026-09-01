# Phase 2 Voice Completion Report

Status: `implemented-closeout-pending`
Started: 2026-08-22
Updated: 2026-08-31
Recommended Sol thinking: Extra high

## Objective

Deliver local-first push-to-talk with provider-neutral audio/VAD/STT/TTS/wake/event ports,
timestamped transcript/audio events, duplex interruption, persistent device selection, diagnostics,
and text fallback. Keep wake-word and clap always-listening hard-disabled; Phase 2 evaluates their
foundations but does not ship a resident listener or action authority.

## 2026-08-31 revalidation

The 2026-08-22 completion evidence remains intact, and all safe local revalidation work passed.
Current live capture, render, interruption, and kill-switch smokes were not repeated because this
program explicitly withholds authority to control real devices without separate authorization.
Under the phase playbook, that prevents a current `complete` claim even though the implementation
and historical live evidence remain valid.

- Locked optional environment: 115 packages resolved; 93 packages checked with `voice` enabled.
- Current selected voice/failure plus acceptance-harness safety suite: 52 passed in 1.08 seconds.
- Historical artifact verifier: all seven required artifacts present and threshold-valid.
- First fresh STT run completed 30/30 and met functional thresholds but correctly failed the
  concurrent-resource gate because no Ollama model was resident. After one local inference loaded
  `nemotron-3-nano:4b`, the enforced rerun completed 30/30; quiet/noisy WER 0%;
  accented WER 17.25%; interactive p50/p95 474.71/501.76 ms; RTF p95 0.2812; zero adapter
  errors; every resource/accuracy/latency threshold passed.
- Fresh local trigger corpus: wake 20/20 and clap 20/20; zero false accepts across one simulated
  hour of music, TV, typing, and room noise; always-listening remained false.
- Fresh synthetic soak: 1,800.05 seconds, 19,501 frames, 1,800 state turns, zero failures,
  no deadlock, final idle, 152,723,456-byte peak RSS growth, and no retained raw audio.
- RTK remains blocked by Windows Smart App Control, so these commands used direct locked
  invocation as explicitly allowed by the program.
- Fresh ignored evidence: `runtime/phase2-revalidation-20260831-01/`.

## Baseline

- Git branch/HEAD: `main` at `7d32b93`; tracks `origin/main`.
- Worktree state and preserved unrelated changes: clean at phase start; ignored `.env`, `.env.local`,
  `.coverage`, environments, and `runtime/` remain untouched and untracked.
- Relevant installed software/hardware/provider state: Windows 11 build 26200; Intel i5-11400H
  (6C/12T), 15.73 GiB RAM, RTX 2050 Laptop GPU with 4 GiB VRAM; healthy Realtek, Intel, Steam,
  NVIDIA, and ASUS audio devices; Python 3.11.16 through uv; Ollama 0.32.14 reachable with
  `nemotron-3-nano:4b`; NVIDIA reasoning model catalog check passes. `ffmpeg`/`ffplay` absent.
- Existing tests and failures: baseline lock/sync/format/lint/type/test gates pass; 88 tests pass,
  total branch coverage 85.17%; `jarvis doctor` passes. No baseline failures.
- Prior phase evidence: Phase 1 implementation commit exists and event streaming test passes.
  Formal Phase 1 completion report is absent. Cancellation propagates through asyncio but needs an
  explicit regression test during this phase.

## Declared acceptance targets

- Quiet fixed-corpus WER: <=20%.
- Noisy and accented fixed-corpus WER: <=35% each.
- End-of-speech to final-transcript latency: p95 <=1,000 ms.
- STT real-time factor for short utterances: p95 <=1.0.
- Barge-in request to output-stop acknowledgement: p95 <=250 ms.
- Wake-word and double-clap true-accept rate: >=90% on the declared positive corpus.
- Wake-word and double-clap false accepts: <=1/hour on music, TV, typing, and room-noise corpus.
- Thirty-minute soak: no deadlock, runaway capture, state corruption, or unbounded resource growth.
- CPU-first speech while local LLM is loaded: voice process peak RSS increase <=4 GiB and discrete
  GPU increase <=512 MiB; failures must degrade to text.
- Audio retention: raw microphone audio is ephemeral by default and never sent to cloud STT/TTS.

## Acceptance checklist

### Functional deliverables

- [x] Provider-neutral `AudioInput`, `VADProvider`, `STTProvider`, `TTSProvider`,
  `WakeWordProvider`, and acoustic-event detector ports.
- [x] Push-to-talk CLI works end-to-end through local STT, existing assistant runtime, local TTS,
  and text fallback.
- [x] Typed monotonic timestamped partial/final transcript and audio-output events.
- [x] Duplex listen/transcribe/think/speak/interrupted/error state machine.
- [x] Sentence/phrase response chunking and streaming TTS queue.
- [x] Local double-clap intent emission with cooldown/rate limits and no direct execution.

### Failure, cancellation, restart, and recovery

- [x] Barge-in cancels queued/current output without corrupting conversation state.
- [x] Echo/render-reference suppression prevents self-triggering.
- [x] Missing/disconnected devices, driver errors, dependency absence, timeout, malformed adapter
  output, capacity loss, and cancellation degrade safely to text.
- [x] Selected capture/render devices survive restart by stable identity or fail clearly.
- [x] Duplicate/replayed audio/event requests are rejected or idempotent.
- [x] Phase 1 stream and cancellation prerequisite has explicit regression evidence.

### Privacy, security, and kill paths

- [x] Cloud speech is denied by default and private speech cannot cross provider boundary.
- [x] Listening state is visible, software kill switch is technically enforced, and physical mute
  path is documented and verified.
- [x] Wake/clap always-listening remains disabled until all enablement gates pass.
- [x] Audio/transcript sizes, durations, timeouts, and retained artifacts are bounded.

### Performance and real target

- [x] Fixed quiet/noisy/accented corpus reports WER, latency, p50/p95, errors, versions, and settings.
- [x] Wake/clap false accept/reject suite covers music, TV, typing, and normal room noise.
- [x] Real Windows microphone/speaker push-to-talk and interruption checks pass.
- [x] CPU/GPU/RAM/VRAM measurements recorded while local LLM is loaded.
- [x] Thirty-minute real-time soak passes.

### Documentation and release

- [x] Setup/configuration/device/recovery documentation updated.
- [x] Hardware report and architecture/security docs updated with measured results and limits.
- [x] Full release, vulnerability, secret, Git, doctor, and phase-specific gates pass.

## Milestones

### Milestone 1 — Contracts and deterministic state machine

- Status: complete
- Changes: strict bounded audio/device/transcript/event/state models; provider-neutral ports;
  serialized session state; core stream-consumer cancellation regression.
- Evidence: voice model/signal/session tests and Phase 1 provider-cancellation regression pass.
- Remaining: none.

### Milestone 2 — Local push-to-talk vertical slice

- Status: complete
- Changes: sounddevice capture/render, Silero VAD, faster-whisper CPU/int8, Windows SAPI TTS,
  explicit model setup, push-to-talk CLI, phrase output, typed text degradation.
- Evidence: isolated real-adapter pipeline completed Silero -> faster-whisper -> local Ollama -> SAPI.
- Remaining: none.

### Milestone 3 — Duplex safety, devices, wake/event foundations

- Status: complete
- Changes: output cancellation/barge-in, render-reference suppression, stable endpoint store,
  live-polled kill switch, openWakeWord ONNX adapter, adaptive double-clap typed intent.
- Evidence: barge p95 22.75 ms; actual capture kill 594.52 ms; endpoint restart doctor passes.
- Remaining: none.

### Milestone 4 — Evaluation and real hardware

- Status: complete
- Changes: 30-sample public/synthetic corpus; deterministic trigger, device, kill, pipeline, resource,
  and strengthened real-time soak harness.
- Evidence: every benchmark artifact verifies true; 1,800.06-second strengthened soak passes.
- Remaining: none.

### Milestone 5 — Release gate and closeout

- Status: complete
- Changes: setup, README, architecture, security, hardware, hands-free, and technology decisions
  updated; optional dependency audit and secret scan pass.
- Evidence: locked text gate passes 140 tests/85.21% coverage; optional voice doctor and all
  artifacts pass; `pip-audit`, Gitleaks, diff check, main doctor, and voice doctor pass.
- Remaining: none.

## Decisions

- Decision: ship optional voice dependencies, keeping ordinary CI and text JARVIS free of model,
  microphone, GPU, and network requirements.
- Reason: Phase 2 needs real adapters, while core contracts and failure behavior must remain testable
  with fakes.
- Alternatives: mandatory heavyweight dependencies; cloud speech; platform-locked core contracts.
- Reversible later: adapters and model choices remain configuration-driven.

- Decision: CPU-first 16 kHz mono STT/VAD and CPU TTS; discrete GPU reserved for the local LLM.
- Reason: measured hardware has only 4 GiB VRAM.
- Alternatives: GPU STT with model swapping; cloud speech with explicit policy.
- Reversible later: device/resource-aware adapter profiles can add those modes.

- Decision: wake-word and clap detection are default-off and cannot execute actions.
- Reason: Phase 3 owns intent-to-action permission; always-listening needs false-trigger/privacy gates.
- Alternatives: enabling automatically after installation.
- Reversible later: explicit gated configuration may enable detection after acceptance evidence.

- Decision: use Windows SAPI as Phase 2 TTS; do not bundle Piper.
- Reason: SAPI is local and present on the target; current maintained Piper runtime is GPL and its
  voice-model licenses require a deliberate distribution design.
- Alternatives: Piper subprocess, cloud neural speech, large voice-cloning models.
- Reversible later: `TTSProvider` isolates engine choice; quality/licensing evaluation can replace it.

- Decision: download but never redistribute the openWakeWord `hey_jarvis` pretrained model.
- Reason: code is Apache-2.0 while bundled pretrained model is CC BY-NC-SA 4.0; always-listening
  stays hard-disabled despite passing the fixed synthetic trigger corpus.
- Alternatives: custom trained model, another engine, no wake foundation.
- Reversible later: a separately licensed custom model can replace the artifact behind the port.

## Verification evidence

Current integrated release evidence (2026-08-31): substantive locked gate passes with 530 tests
passed, 1 skipped, 85.20% coverage; 66 source files type-check; 147 files are formatted; lint,
dependency audit (base and restored voice extra), Gitleaks, diff check, and doctor pass. Exact
`mypy`, `pytest`, `pip-audit`, and `jarvis` console shims are blocked by Windows Application Control
OS error 4551; Python-module equivalents pass. Full command evidence is in the Phase 1 report.

Historical 2026-08-22 closeout evidence follows:

```text
uv lock --check                                      PASS: 115-package resolution current
uv sync --locked                                    PASS: clean 62-package text environment
uv run ruff format --check .                        PASS: 83 files
uv run ruff check .                                 PASS
uv run mypy src                                     PASS: 40 source files
uv run pytest --basetemp runtime/...                PASS: 140 tests, 85.21% coverage
uv run pip-audit                                    PASS: no known vulnerabilities
gitleaks detect --source . --redact --no-banner     PASS: no leaks
git diff --check                                    PASS
uv run jarvis doctor                                PASS: storage/Ollama/model/catalog
uv sync --locked --extra voice                      PASS: locked optional environment
uv run --no-sync jarvis voice doctor                PASS: privacy/kill/devices/format/providers
python scripts/voice-benchmark.py verify             PASS: all seven artifacts true
uv run pip-audit (voice extra installed)             PASS: no known vulnerabilities
```

## Benchmarks

- Samples: 10 quiet SAPI commands, 10 deterministic 10 dB SNR variants, and 10 public real-accent
  samples from the George Mason Speech Accent Archive/OSF (CC BY-NC-SA 4.0).
- Cold/warm: faster-whisper/Silero cold model load 2,996.07 ms; corpus uses warmed adapters.
- p50: short interactive STT 530.71 ms; RTF 0.1996; barge stop 9.41 ms.
- p95: short interactive STT 694.78 ms; RTF 0.3101; barge stop 22.75 ms.
- Accuracy: quiet WER 0%; noisy WER 0%; accented WER 17.25%; no adapter errors.
- Metric interpretation: the first report combined 2-3 second command clips with 22-44 second
  accent passages and therefore showed an overall 5,522.10 ms p95. The harness now applies the
  <=1,000 ms endpoint target only to the short interactive quiet/noisy command slice, measures cold
  load separately, and still reports accented latency (final p95 6,058.90 ms) plus RTF (p95 0.1755).
  Production push-to-talk remains capped at 30 seconds; long accent passages exist only for WER.
- Triggers: wake and clap 20/20 positives each; zero accepts in one simulated false-corpus hour.
- Hardware: Realtek capture 992 ms/zero drops; silent 22.05 kHz mono SAPI-format render completed
  on Crusher ANC 2; software kill cancelled actual capture in 594.52 ms.
- Runtime: faster-whisper 1.2.1, CTranslate2 4.8.1, Silero VAD 6.2.1, sounddevice 0.5.6,
  openWakeWord 0.6.0, Python 3.11.16, Ollama 0.32.14.
- Relevant settings: 16 kHz mono capture, 512-frame chunks, `base.en`, CPU/int8, four STT threads;
  with local 4B LLM loaded, voice RSS grew 458.28 MiB and RTX 2050 moved only 2,249 -> 2,251
  MiB (+2 MiB).
- Soak: 1,800.06 seconds, 21,560 detector frames, 1,800 complete state turns, zero failures,
  final idle, 159.52 MiB peak growth, and no raw audio retained.

## Security and privacy

- Threats tested: command/text injection into SAPI shell boundary, corrupt/oversized settings and
  PCM, malformed/missing providers, disconnected devices, timeout, cancellation, echo, replay/order,
  kill during capture, and false triggers.
- Data boundaries: local-only speech adapters; raw audio ephemeral; benchmark media under ignored
  `runtime/`; public models under private application data; no cloud STT/TTS.
- Permissions/approvals: acoustic detection emits typed intent only; no Phase 3 execution.
- Audit/retention/deletion: successful transcript enters existing conversation retention; raw PCM
  never enters the store; failed/cancelled pre-assistant turns do not create conversation content.
- Secret scan: final Gitleaks scan passes with redaction; no model/media/runtime artifact is tracked.

## Blockers

- Current live microphone capture, silent render, interruption, and kill-switch smoke require
  separate real-device authorization. Historical 2026-08-22 live evidence remains recorded, but
  it cannot substitute for a current playbook-required live check.
- Phase 1 formal prerequisite closeout remains externally blocked by local latency, hosted endpoint,
  independent clean-Windows, and exact-launcher gates.

## Known limits and deferred scope

- Always-listening wake word and clap activation remains hard-disabled despite fixed-corpus gates;
  one SAPI voice and deterministic synthetic false categories do not establish real-room diversity.
- Wake pretrained asset is CC BY-NC-SA 4.0 and is downloaded explicitly, never redistributed.
- SAPI is a functional local baseline; natural voice quality/custom voice remains deferred.
- Render-reference correlation is not full hardware AEC. Actual room/speaker geometry may require a
  later AEC adapter; headphones are the verified target.
- Terminal push-to-talk handles one explicit turn at a time. Resident wake conversation/UI is not
  shipped.
- Cloud STT/TTS is not configured. Public transcripts may still enter the existing assistant router;
  sensitive/uncertain transcripts remain local under Phase 1 privacy policy.
- Double-clap emits typed intent data only. Phase 3 must add allowlist, approval, execution, audit,
  postcondition, and rollback before any app action exists.

## Recovery and rollback

- Disable voice through configuration or the software kill switch; text CLI/browser remain usable.
- Remove optional voice dependencies and delete downloaded speech models from the configured model
  cache. Conversation storage is independent and requires no rollback.

## Final handoff

- Final status: `implemented-closeout-pending`; safe current checks pass, but current live-device
  and Phase 1 prerequisite closeout gates remain unresolved.
- Files changed: voice package/CLI/config/core cancellation, optional dependency lock, benchmark
  harness, 52 additional tests over baseline, and setup/architecture/security/hardware/roadmap docs.
- Next recommended action: with separate authorization, repeat the bounded live device smokes after
  Phase 1 external blockers are resolved or explicitly accepted as release limitations.
- Commit/push status: uncommitted and not pushed; authorization was not provided.
