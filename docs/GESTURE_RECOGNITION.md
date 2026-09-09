# Phase 7B Local Gesture Recognition

Status: provider-neutral core implemented; detector adoption and live evaluation blocked pending
owner privacy/consent decision  
Updated: 2026-09-08

## Current capability

Phase 7B currently owns strict local-only contracts and deterministic temporal logic for:

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

The pipeline ends there. Phase 7B has no import or call path to Phase 3 mappings, proposals,
approvals, or execution. Gesture-to-intent mapping remains Phase 7C.

## Calibration and privacy

Calibration consumes labeled fist, palm, and pinch samples in memory. It derives only aggregate,
dimensionless separation thresholds and the operator-selected mirrored-input flag. Raw pixels,
landmarks, world coordinates, per-sample hand geometry, camera media, and identity attributes are
not persisted. Reset or process restart clears temporal history and calibration samples.

Default profile bounds:

| Control | Default |
| --- | --- |
| Tracking/handedness confidence | 0.85 / 0.85 |
| Static debounce / release | 3 / 2 frames |
| Cooldown | 1,000 ms |
| Maximum frame gap / observation age | 250 / 300 ms |
| Roll window / minimum motion | 12 frames / 1.4 radians |
| Roll direction consistency | 0.80 |

No calibration CLI is exposed yet because the required real detector is not adopted.

## Detector decision blocker

The current official MediaPipe Hand Landmarker is technically suitable: it supports Python
image/video/live modes, 21 landmarks, handedness, confidence thresholds, and tracking. MediaPipe is
Apache-2.0. Its current API terms and privacy notice also say MediaPipe Solution/Tasks APIs contact
Google servers, send performance/utilization/application/input/system metadata, and require the app
owner to obtain informed consent where required.

JARVIS therefore does not install, initialize, or silently network-block current MediaPipe. Choose
one path before detector work:

1. Explicitly accept MediaPipe API terms and metric disclosure, then design informed consent and a
   visible network/privacy control before any live test.
2. Select and review a no-telemetry detector/model with clear license, provenance, checksum, and
   Windows/Python support.

Official references: [Hand Landmarker Python guide](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker/python),
[MediaPipe API terms](https://developers.google.com/edge/mediapipe/legal/tos),
[repository/privacy notice](https://github.com/google-ai-edge/mediapipe), and
[Apache-2.0 license](https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE).

## Verification

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

Live completion still needs a separately authorized exact protocol covering lighting, distance,
left/right hands, mirrored/unmirrored input, partial occlusion, backgrounds, similar movement,
no-hand periods, latency, FPS, CPU, memory, and a 30-minute soak. No media or raw landmarks may be
retained.

## Recovery

- Keep `JARVIS_VISION_CAPTURE_ENABLED=false` and run `uv run jarvis vision disable`.
- Call recognizer reset or end the foreground process to clear all temporal state.
- Remove the optional detector package/model if one is later adopted and rollback is required.
- Text, voice, memory, research, tasks, and Phase 3 permissions remain independent.
