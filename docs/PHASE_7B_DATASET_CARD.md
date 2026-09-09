# Phase 7B Synthetic Landmark Dataset Card

Updated: 2026-09-08  
Scope: deterministic gesture-core verification only

## Purpose

Exercise Phase 7B contracts and temporal state logic without a camera, detector model, network,
stored media, or personal data. The corpus is generated in memory by
`scripts/phase7b-gesture-benchmark.py`; no landmark rows are committed or retained.

## Composition

- 1,000 labeled sequences total.
- 500 positive sequences: 100 each for closed fist, open palm, pinch, clockwise finger roll, and
  counter-clockwise finger roll.
- 500 negative sequences split across no-hand, ambiguous pose, low confidence, two-hand conflict,
  and inconsistent roll-like motion.
- Positive variants alternate left/right handedness, mirrored/unmirrored coordinates, four bounded
  scale/distance transforms, and periodic no-hand/drop prefixes.
- Separate negative soak: 36,000 frames, equal to one simulated hour at 10 FPS.
- Separate classifier performance set: 10,000 frames after 1,000 warm-up frames.

## Labels and scoring

Each positive sequence expects exactly one closed `GestureKind`. A missing or different event is a
false negative; a wrong/negative-sequence event is a false positive. Fixed gates are macro
precision/recall >= 0.95 and per-gesture precision/recall >= 0.90. Negative soak permits at most
0.1 false activations/hour. It structurally contains zero mapping, action proposal, or execution.

## Privacy

All values are authored synthetic coordinates. No person, camera, screen, biometric template,
recording, detector output, private content, or external dataset is used. Output JSON contains only
aggregate counts, timings, memory growth, thresholds, runtime versions, and pass/fail state.

## Known limitations

This corpus cannot validate detector behavior, skin-tone parity, lighting, background, real
distance, true occlusion, camera position, motion blur, thermals, hardware contention, or human
gesture usability. Perfect synthetic accuracy is not a real-world accuracy claim. Those properties
remain mandatory in the separately authorized live/approved-recorded target evaluation.
