# Phase 7B/7C Local Gesture Recognition

Status: Phase 7B/7C complete
Updated: 2026-09-09

## Current capability

Phase 7B owns strict local-only contracts, a pinned OpenCV DNN detector, and deterministic temporal
logic for:

- closed fist;
- open palm;
- thumb/index pinch;
- clockwise finger roll; and
- counter-clockwise finger roll.

One landmark frame contains zero, one, or two hand observations. Each observation contains exactly
21 normalized landmarks, left/right handedness, and detector confidence. The recognizer accepts
exactly one fresh, ordered, confident hand. Multiple hands, no hand, stale/replayed/out-of-order
frames, low confidence, malformed geometry, conflicting poses, and uncertain motion emit nothing.

Static poses require consecutive-frame debounce. After one event, a held pose cannot repeat until
the configured cooldown expires and an explicit release is observed. Finger roll requires a
bounded motion window, stable radius, minimum angle, and consistent direction. Mirrored input is a
calibration property, not an inferred identity attribute.

```text
explicit 7A frame -> local landmark detector port -> ephemeral landmark frame
                  -> temporal recognizer -> content-free gesture observation
```

Phase 7B ends there and retains no Phase 3 import. Phase 7C supplies a separate computer-layer sink:

```text
closed_fist -> cancel                 open_palm -> media_play_pause
pinch -> mute_toggle                  clockwise roll -> volume_up
counter-clockwise roll -> volume_down
```

The sink revalidates the observation, supplies no detector-controlled arguments, and enters the
existing Phase 3 actor/session/freshness/confidence/replay/rate gate. Host policy flags remain
default false. A proposal stays Level 1 and requires trusted review; mapping never approves or
executes. Fist cancel closes only the bound session and creates no action authority.

## Calibration and privacy

Calibration consumes labeled fist, palm, and pinch samples in memory. It derives only aggregate,
dimensionless separation thresholds and the operator-selected mirrored-input flag. Raw pixels,
landmarks, world coordinates, per-sample hand geometry, camera media, and identity attributes are
not persisted. Reset or process restart clears temporal history and calibration samples.

Default profile bounds:

| Control | Default |
| --- | --- |
| Tracking/handedness confidence | 0.85 / 0.85 |
| Pinch ratio (normalized 2D thumb/index gap to palm width) | 0.70 |
| Static debounce / release | 3 / 2 frames |
| Cooldown | 1,000 ms |
| Maximum frame gap / observation age | 250 / 300 ms |
| Roll window / minimum motion | 12 frames / 1.4 radians |
| Roll direction consistency | 0.80 |

The current CLI exposes bounded detection with the default profile. Persisted guided calibration
remains optional future usability work; the shipped detector never retains calibration frames.

## Detector decision

JARVIS uses the OpenCV Zoo February 2023 palm and hand-pose ONNX models through local OpenCV DNN.
Both URLs are pinned to OpenCV Zoo revision
`47534e27c9851bb1128ccc0102f1145e27f23f98`, bounded to 8 MiB each, verified by committed SHA-256,
stored outside Git, and downloaded only by explicit `jarvis vision setup`. Detection performs no
network request and returns only owned 21-landmark observations. The model directories and OpenCV
Zoo are Apache-2.0. No third-party source code is copied into JARVIS.

MediaPipe Tasks is not installed or initialized. Its current metrics/consent boundary therefore
does not apply to the shipped runtime path. Official model references:
[palm detector](https://github.com/opencv/opencv_zoo/tree/main/models/palm_detection_mediapipe),
[hand-pose estimator](https://github.com/opencv/opencv_zoo/tree/main/models/handpose_estimation_mediapipe),
and [OpenCV Zoo license](https://github.com/opencv/opencv_zoo/blob/main/LICENSE).

## Verification

Install models and run one bounded foreground session:

```powershell
uv sync --locked --extra vision
uv run jarvis vision setup
uv run jarvis vision enable
# Start a new process with JARVIS_VISION_CAPTURE_ENABLED=true.
uv run jarvis vision gestures --source-id camera:0 --width 640 --height 480 --fps 10 --frames 300 --duration-ms 30000
uv run jarvis vision disable
```

`--exposure -4` is an optional explicit DirectShow control for cameras whose automatic exposure
cannot sustain 10 FPS. Omission preserves device automatic exposure. Gesture output is
content-free; pixels and landmarks are cleared and no action is proposed or executed.

The current synthetic gate generates landmarks in memory; it contains no photos, videos, skin-tone
labels, or real detector claims:

```powershell
uv run python scripts/phase7b-gesture-benchmark.py `
  --output runtime/phase7b-gesture-core-<unique>/benchmark.json
```

Current safe-core result: 1,000 sequences, 100 positive sequences per gesture, macro precision and
recall 1.00; 36,000 negative frames/one simulated hour, zero false activations; 10,000 classifier
frames, p50 0.0119 ms, p95 0.0138 ms, 0.316 MiB RSS growth. These prove deterministic state-machine
behavior only. They do not measure camera robustness or detector accuracy.

Phase 7C synthetic gate:

```powershell
uv run python scripts/phase7c-intent-benchmark.py `
  --output runtime/phase7c-intent-<unique>/benchmark.json
```

Current result: 10,000 observation-to-gate evaluations at 0.1319/0.1421 ms p50/p95 with 1.621 MiB
RSS growth, zero wrong mappings, direct effects, or authority escalations; 36,000 negative/storm/
replay events produced one rate-bounded proposal and zero direct effects; universal cancel produced
no later proposal. This is synthetic policy-path evidence, not a live gesture/action claim.

Final target results: the 30-minute `camera:0` soak processed 17,891 frames at 9.938 FPS. Detector
p50/p95 was 6.884/7.734 ms; full pipeline p50/p95 was 6.907/7.757 ms; average total CPU was 7.999%;
RSS growth was 12.19 MiB. It produced zero false activations, proposals, effects, authority
violations, retained media/landmarks, or cloud calls. The source stream was effectively black, so it
was used only for target performance, resource, privacy, and no-hand evidence.

The approved public HaGRID example matrix exercised two lighting levels, two distances,
mirrored/unmirrored handling, both observed handedness values, partial occlusion, 25 varied
real-human/background/camera-position crops, four similar gestures, and five no-hand frames. It
recognized all three static gesture classes at least once, produced zero incorrect labels, and
correctly handled 49/56 condition cases; detector p95 was 14.872 ms. Seven transformed `ok` pinch
cases emitted nothing rather than a wrong event. Operators should calibrate and use a clear,
well-lit pinch; aggressive resampling/mirroring is a documented fail-closed limitation. Finger-roll
directions remain covered by the strict 1,000-sequence synthetic temporal corpus because the public
still-image fixture contains no equivalent motion sequence.

Recorded fixtures came from the public [HaGRID repository](https://github.com/hukenovs/hagrid) and
are covered by its CC BY-SA 4.0 dataset license; the benchmark pins both input SHA-256 values and
stores the downloaded examples only under ignored `runtime/`. Dataset diversity claims follow the
authors' [WACV 2024 paper](https://openaccess.thecvf.com/content/WACV2024/papers/Kapitanov_HaGRID_--_HAnd_Gesture_Recognition_Image_Dataset_WACV_2024_paper.pdf).

Reproduce after placing the two pinned public overview images under ignored `runtime/`:

```powershell
uv run python scripts/phase7-recorded-benchmark.py `
  --gesture-grid runtime/phase7-detector-eval/hagrid-fixture/gestures.png `
  --diversity-grid runtime/phase7-detector-eval/hagrid-fixture/hagrid_samples.jpg `
  --model-dir runtime/phase7-detector-eval/models/vision `
  --output runtime/phase7-detector-eval/recorded-matrix-<unique>.json
```

## Recovery

- Keep `JARVIS_VISION_CAPTURE_ENABLED=false` and run `uv run jarvis vision disable`.
- Call recognizer reset or end the foreground process to clear all temporal state.
- Remove the optional vision extra and private ONNX model directory to roll back detection.
- Text, voice, memory, research, tasks, and Phase 3 permissions remain independent.
