# Phase 7 Vision and Gestures Completion Report

Status: `complete`
Completed: 2026-09-09
Scope: Phase 7A capture/privacy/contracts; Phase 7B detector/gestures/calibration; Phase 7C typed
intent mapping/closeout

## Outcome

Phase 7 is complete. JARVIS now has an explicit default-off camera/screen capture boundary, a
pinned local OpenCV DNN palm/hand-landmark detector, deterministic calibrated temporal gestures,
and a closed observation-to-Phase-3 proposal bridge. Gesture data cannot approve or directly
execute work. No continuous camera listener, biometric identity, raw-command mapping, retained
media, or cloud vision path ships.

The required target camera performance/resource/no-hand soak, public diverse real-image matrix,
synthetic classifier/negative gates, integrated mapping/adversarial gates, security checks, and
documentation closeout pass. The laptop stream was effectively black; it is classified only as
target camera no-hand/performance/resource evidence. Real-human condition evidence comes from
approved public HaGRID examples processed locally on the target laptop.

## Delivered architecture

- `CaptureRequest` binds source, stable ID, purpose, exact region, RGB24 format, FPS, optional
  exposure, frame count, duration, timeout, and ephemeral retention.
- Capture requires a process-start environment gate, persistent software enable, and explicit
  foreground command. Indicator-on precedes source open; source close precedes indicator-off.
- Native capture and document parsing use isolated Python children with sanitized environments and
  explicit resolved import roots. Application Control remains enforced.
- `vision setup` is the sole model-download path. It downloads two pinned OpenCV Zoo ONNX files,
  caps each at 8 MiB, verifies committed SHA-256 values, writes atomically, and stores outside Git.
- OpenCV DNN emits owned local-only 21-landmark observations. Pixel buffers and landmark frames are
  released after each bounded consumer call.
- Temporal recognition covers closed fist, open palm, thumb/index pinch, and clockwise/
  counter-clockwise finger roll with confidence, freshness, ordering, debounce, cooldown,
  release/re-arm, motion consistency, handedness, mirroring, and fail-closed uncertainty.
- Phase 7C maps only `cancel`, `media_play_pause`, `mute_toggle`, `volume_up`, and `volume_down` into
  the existing Phase 3 actor/session/freshness/replay/rate/permission gate. Actions remain Level 1,
  unapproved, default-off proposals; fist cancellation grants no authority.

## Acceptance evidence

### Phase 7A capture/privacy

- Camera and screen-region bounded smokes passed on the target laptop with visible indicators and
  ephemeral buffer clearing.
- Camera-off prevents capture; gate/settings/indicator/source/worker/protocol/cancellation errors
  fail closed.
- Abuse corpus covers unauthorized source opens, region/purpose misuse, concurrency, stale frames,
  consumer failure, environment-secret stripping, and rollback.
- Both persistent capture settings and process-start gates were disabled after live work.

### Phase 7B synthetic gesture core

Final artifact: ignored local `runtime/phase7b-gesture-core-final/benchmark.json`.

| Gate | Result | Target |
| --- | ---: | ---: |
| Labeled sequences | 1,000 | >= 1,000 |
| Macro precision / recall | 1.000 / 1.000 | >= 0.95 / 0.95 |
| Each gesture precision / recall | 1.000 / 1.000 | >= 0.90 / 0.90 |
| Negative frames | 36,000 | >= 36,000 |
| False activations/hour | 0.0 | <= 0.1 |
| Classifier frames | 10,000 | >= 10,000 |
| Classifier p50 / p95 | 0.0106 / 0.0110 ms | p95 <= 5 ms |
| RSS growth | 0.492 MiB | <= 50 MiB |
| Invalid emissions / proposals / effects | 0 / 0 / 0 | 0 / 0 / 0 |

The corpus spans all five gestures, handedness, scale, mirror state, occlusion/drop, similar motion,
conflicts, no-hand, stale/replay, low confidence, and release/re-arm behavior.

### Diverse public real-image matrix

Final artifact: ignored local `runtime/phase7-detector-eval/recorded-matrix-final.json`.

- Sources: public HaGRID gesture/sample overview images, CC BY-SA 4.0, pinned in the evaluator by
  SHA-256. Pixels remain under ignored `runtime/` and are not retained by JARVIS.
- Coverage: two lighting levels, two distances, mirrored/unmirrored input, left/right handedness,
  partial occlusion, 25 diverse real-human/background/camera-position crops, four similar gesture
  labels, and five no-hand frames.
- 56 labeled condition cases: 49 correct, condition-case recall 0.875, zero incorrect labels, zero
  similar-movement false events, and zero no-hand detections.
- All three static output classes were observed. Detector p95 was 14.8721 ms, below 100 ms.
- Seven resampled/mirrored/low-light `ok` cases emitted nothing. This is fail-closed and documented:
  guided per-user calibration is recommended; clear well-lit pinch geometry is required. The public
  still fixture has no finger-roll motion sequence, so both roll directions retain strict synthetic
  temporal evidence rather than a false real-motion claim.

### Target 30-minute camera/detector/mapping soak

Final artifact: ignored local `runtime/phase7-detector-eval/soak-20260909-1844.json`.

Authorization was limited to the sole healthy `camera:0` (`USB2.0 HD UVC WebCam`), 640x480 RGB24,
10 FPS, 30 minutes, local ephemeral processing, visible indicator, aggregate output only, no saved
pixels/landmarks, no cloud call, and no OS action effect. Manual exposure `-4` was explicit because
automatic exposure limited this camera to about 7 FPS.

| Gate | Result | Target |
| --- | ---: | ---: |
| Duration / frames | 1,800.25 s / 17,891 | >= 1,800 s / 1,800 frames |
| Processed FPS | 9.938 | >= 9 |
| Detector p50 / p95 | 6.8839 / 7.7342 ms | p95 <= 100 ms |
| Pipeline p50 / p95 | 6.9067 / 7.7568 ms | <= 75 / 150 ms |
| Average total CPU | 7.999% | <= 35% |
| RSS growth | 12.191 MiB | <= 50 MiB |
| False activations/hour | 0.0 | <= 0.1 |
| Events / proposals / cancels | 0 / 0 / 0 | no storm |
| Authority violations / OS effects | 0 / 0 | 0 / 0 |
| Saved frames / landmarks / cloud calls | 0 / 0 / 0 | 0 / 0 / 0 |

GPU was not required. Windows exposed no reliable thermal sensor; stable throughput, bounded CPU,
and bounded RSS are the recorded thermal proxies. The near-black stream produced no hand frames,
so it proves the no-hand, privacy, performance, resource, and integration gates only.

### Phase 7C mapping and authority

Final artifact: ignored local `runtime/phase7c-intent-final/benchmark.json`.

- 10,000 observation-to-gate evaluations: exact 5/5 mappings, zero wrong mappings, direct effects,
  or authority escalations; p50/p95 0.1310/0.1365 ms; RSS growth 1.465 MiB.
- 36,000 stale/conflict/replay/storm events produced only one rate-bounded proposal and zero direct
  effects. Bound-session cancel blocked all later proposals.
- Gesture observations contain no action, arguments, approval, permission, grant, actor secret, or
  tool field. Detector output is untrusted data, never authorization.

## Security, privacy, and dependency decisions

- OpenCV Zoo model revision: `47534e27c9851bb1128ccc0102f1145e27f23f98`.
- Palm model SHA-256:
  `78ff51c38496b7fc8b8ebdb6cc8c1abb02fa6c38427c6848254cdaba57fcce7c`.
- Hand-pose model SHA-256:
  `db0898ae717b76b075d9bf563af315b29562e11f8df5027a1ef07b02bef6d81c`.
- OpenCV/OpenCV Zoo/model directories are Apache-2.0; wrapper and Pillow license disclosures are
  documented. No third-party source or model artifact is committed.
- MediaPipe Tasks is not installed or initialized. The owned provider-neutral contract permits a
  later reviewed replacement without changing privacy, recognition, or authority boundaries.
- Runtime model weights, downloaded public fixtures, benchmark JSON, capture bytes, settings,
  databases, logs, and private data remain outside Git.

## Quality and release gates

- `uv lock --check`: pass.
- `uv sync --locked`: pass; optional vision packages absent and ordinary camera-independent import
  and tests work.
- `ruff format --check .`: pass.
- `ruff check .`: pass.
- `mypy src`: pass for 110 source files.
- Full pytest: 808 passed, 2 skipped; 85.34% coverage, above 85%.
- An initial full run had 805 passes and three runner-path security failures because uv's
  convenience interpreter directory is a name-surrogate junction. The canonical versioned
  interpreter rerun passed all 808 tests without weakening path protections.
- `pip-audit --path .venv/Lib/site-packages`: no known vulnerabilities.
- `gitleaks detect --source . --redact --no-banner`: 30 commits / 3.45 MB scanned, no leaks.
- `git diff --check`: pass.
- Final vision doctor: all topology, privacy, adapter, model-integrity, software-kill, and host-gate
  checks pass. Host and persistent capture controls are disabled; capture is inactive.

Windows Application Control blocks `uv run`/virtual-environment executable trampolines with OS
error 4551. Exact lock/sync commands succeed. Python gates run through uv's trusted canonical
versioned CPython with `.venv/Lib/site-packages` and repository import roots. This changes only the
runner path, not locked packages, code, tests, or security policy.

## Recovery and rollback

- Run `jarvis vision disable`; keep `JARVIS_VISION_CAPTURE_ENABLED=false`.
- Close the foreground process to clear detector/recognizer state; use the physical camera shutter
  or Windows camera privacy setting as independent kill paths.
- Remove the optional vision extra and private model directory to roll back detection. No model
  artifact is required by base text/voice/memory/research/task features.
- Disable all Phase 3 gesture mapping flags. Existing action permission, approval, broker, audit,
  and postcondition rules remain unchanged.

## Deferred work and known limitations

- Persisted guided calibration UI is deferred; current calibration is in-memory and the CLI uses
  default thresholds.
- Pinch is conservative and can miss under aggressive resampling, mirroring, distance, or poor
  lighting. Uncertainty emits nothing.
- OCR, object/scene understanding, cloud multimodal disclosure, navigation gestures, continuous
  camera listening, biometric identity, and gesture-based approval are outside Phase 7.
- Current laptop camera's physical stream was unusable for live human-pose validation. Approved
  public real-human fixtures satisfy the recorded diversity gate; no claim is made about this
  user's hand accuracy until a clear live session is run.

## Final handoff

Phase 7A, 7B, and 7C implementation, acceptance, security, documentation, and release gates are
complete. Phase 8 may consume only the documented provider-neutral observation and Phase 3 intent
boundaries; it gains no hidden capture or action authority.
