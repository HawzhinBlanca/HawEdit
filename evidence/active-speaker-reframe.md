```yaml
commit: 44acf4d6e4a966d2a6cdf7dd07deff2aacf1e443
media_sha256: 6ceba45fade2c32e7b546e4f4c94f760fdc2827e315a075061cc6b4d97e50ae1
host: HAWAPC01
command: python -m pytest tests/test_reframe.py tests/test_pipeline.py -k speaker_tracker
```

# Evidence: Active-Speaker Reframe (Task T2.1, Candidate Associator A)

## Context & Spec Grounding
- **Task**: Task T2.1 from `specs/pro-grade-program/tasks.md` (re-opening pro-edit T7 per ADR D-262 and `evidence/two-rows-flipped-for-features-that-did-not-exist.md`).
- **Blueprint Reference**: `BLUEPRINT.md` §3 Stage 6, `HANDOFF.md` §5.
- **Implementation**: `src/hawedit/reframe.py` (`MotionSpeakerTracker`), `src/hawedit/pipeline.py`.

## Candidate Associator (a) Architecture & Findings
1. **Zero External Neural Model Dependency**:
   Operates strictly via OpenCV Haar cascades (frontal + profile + mirrored profile) sampled at $\ge 5.0$ fps. For each detected face meeting `MIN_FACE_AREA`, extracts the lower third (mouth region) and computes inter-frame pixel-motion energy:
   $$\Delta_{mouth} = \text{mean}(|I_t^{mouth} - I_{t-1}^{mouth}|)$$
   Correlates the peak moving mouth with active exclusive diarization turns.

2. **Strict Fail-Stop & Monotonicity Invariants**:
   - Only emits `SpeakerFocusPoint` instances during active exclusive diarization turns.
   - Timestamps are strictly monotonic and strictly bounded within $[in\_ms, out\_ms)$.
   - All points validate against `validate_speaker_focus_points`.

3. **Ambiguity Hold (Anti-Wander Invariant)**:
   When motion difference is ambiguous (ratio $< 1.25$ or quiet breath/pause), holds the speaker's confirmed position rather than erratic camera jumping ("on ambiguity hold, never wander").

4. **Pipeline & Level C Reconciliation Verification**:
   - `run_pipeline` with `MotionSpeakerTracker` reframes in `Reframe.SPEAKER_TRACKED` mode.
   - Outputs `crop_target = "speaker_face"` in the contract.
   - Successfully satisfies Level C reconciliation and atomic delivery bundling.
