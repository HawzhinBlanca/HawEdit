# Plan — Reconciliation Gate in Delivery (T1.2)

> **Approved-by:** Hawa

## 1. Goal & Architectural Overview
Implement the Level C Reconciliation Gate to ensure the HawEdit delivery bundle cannot publish any clip whose contract claims disagree with the independently measured reality of the delivered media. 
Widen the atomic delivery bundle from 5 files to 6 files by including `<clip>.measured.json`.

## 2. Proposed Changes

### 2.1 `DECISIONS.md`
- Add **ADR D-263**: Six-file delivery bundle and independent Level C Reconciliation Gate.

### 2.2 `src/hawedit/delivery.py`
- Define `DeliveryRefused(DeliveryError)` carrying `(reason: str, expected: Any, measured: Any)`.
- Define `reconcile_delivery(...)` checking:
  1. Duration (±1 frame tolerance).
  2. Resolution (1080×1920).
  3. Loudness (−14.0 ± 0.5 LUFS, true peak ≤ −0.9 dBFS).
  4. Silence duration math: `abs(clip.silence_removed_ms - (span_ms - measurement.audio.duration_ms)) <= frame_ms + 1`.
  5. Planned punch-in cuts matched within ±1 frame; no rogue cut > 1,500 ms from a source cut.
  6. Caption burn-in ink energy: if `captions_burned_in` is True, `ink_energy_detected_share >= 0.95`.
  7. Face tracking: if `crop_target == "face_tracked"`, `face_detected_share >= 0.90`.

### 2.3 `src/hawedit/artifact_bundle.py`
- Widen `_SUFFIXES: Final = ("ass", "mp4", "srt", "edl", "json", "measured.json")`.

### 2.4 `src/hawedit/pipeline.py`
- In `pipeline.py` delivery publication block:
  - Run `measure_clip(render_path, ass_path=ass_path, ffmpeg=ffmpeg)`.
  - Write `bundle.write_text("measured.json", measurement.to_json())`.
  - Run `reconcile_delivery(clip, measurement, ...)`.
  - Call `bundle.publish()` only upon successful reconciliation.

### 2.5 Tests
- In `tests/test_delivery.py`: 7 refusal unit tests (one per clause) asserting `DeliveryRefused`.
- In `tests/test_artifact_bundle.py`: update `SUFFIXES` to 6 files.
- In `tests/test_pipeline.py`: verify that delivery skips with `DeliveryRefused` when reconciliation fails.

## 3. Verification & Evidence
- Fast checks: `verify.sh --fast`
- Rebind VEX digest: `package_digest(Path('src/hawedit'))` in `security/wsl-asr-vex.json`
- Full test gate: `verify.sh` green (3,341+ tests)
- Ledger flips via `scripts/update-ledger.sh`
- Re-run on canonical clip `ep29-s25-25`: record honest Level B refusal evidence (`evidence/reconciliation-refusal-ep29-s25-25.md`) showing that it passes clauses 1–6 but fails clause 7 (face tracking: 56.2% < 90%) due to wide shots, proving zero silent fallbacks.
