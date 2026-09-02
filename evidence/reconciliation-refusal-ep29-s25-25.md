# Reconciliation Gate Refusal Record — ep29-VbX8UWwl1c4-s25-25

```yaml
commit: 50fee6e3923984d5f4fe4a77df3c518b57743d54
media_id: ep29-VbX8UWwl1c4
clip_id: ep29-VbX8UWwl1c4-s25-25
source_sha256: b42da4783cd03f6a27cbe430f72a2a5693330e26712a34cf60f58d56bd8316d4
host: HAWAPC01
command: python -m hawedit.delivery reconcile work/ep29-VbX8UWwl1c4-s25-25
date: 2026-09-02T19:20:00Z
proof_level: Level B (refusal on real delivered media)
```

## 1. Summary of Reconciliation Evaluation

The canonical 57-second delivery clip `ep29-VbX8UWwl1c4-s25-25` was passed through the Level C Reconciliation Gate (`reconcile_delivery`) evaluating its contract claims against independent measurements from `hawedit.measure`.

### 7-Clause Evaluation Result
1. **Duration**: PASS. Contract: 56,572 ms. Measured: 56,600 ms (1,415 frames at 25 fps). Delta: 28 ms (≤ 60 ms tolerance / 1 frame).
2. **Geometry**: PASS. Expected: 1080×1920 vertical. Measured: 1080×1920.
3. **Audio Dynamics**: PASS. Expected: −14.0 ± 0.5 LUFS, TP ≤ −0.9 dBFS. Measured: −14.20 LUFS, TP −0.90 dBFS.
4. **Silence Math**: PASS. Expected: 0 ms removed. Measured: 0 ms removed.
5. **Visual Scene Cuts & Punch-ins**: PASS. All shot cuts aligned with source scene changes (`scdet > 0.3`).
6. **Caption Burn-in**: PASS. Ink energy detected in 100% of dialogue cues (47 / 47 events, share 1.0000 ≥ 0.95).
7. **Face Tracking In-Frame Presence**: **REFUSED**.
   - Contract claim: `crop_target: "face_tracked"`.
   - Reconciled requirement: Face present in ≥ 90% of sampled frames (≥ 0.90).
   - Measured ground truth: 159 / 283 frames = **56.18%** (`face_detected_share: 0.5618`).
   - Failure locus: At 17–25s (wide two-shot across table) and 0–1s (host drinking from mug), subject is uncentered or undetected.

## 2. Refusal Error Record
```python
DeliveryRefused(
    reason="face_tracking_unsubstantiated",
    expected=">= 0.90 face detected share",
    measured=0.5618,
)
```

## 3. Engineering Analysis
The gate performed exactly as specified in `specs/pro-grade-program/tasks.md` row T1.2:
> *"expect it to pass every clause except face_tracked at 17–25 s; record the honest result."*

Before Task T1.2, this clip was published as a valid delivery artifact claiming `crop_target: face_tracked` despite 43.82% of frames lacking any verified face presence. The Level C Reconciliation Gate successfully detected the contract violation and halted publication, verifying zero silent fallbacks under `GEMINI.md` directives.
