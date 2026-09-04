# Research: Active-Speaker Reframe (Task T2.1, re-opened pro-edit T7)

## Problem Statement

In `specs/pro-grade-program/tasks.md`, Task T2.1 addresses the single largest visible gap in podcast framing:
> "Active-speaker reframe (re-opened pro-edit T7). Diarization turns (`--diarize`, pyannote Community-1) + a face↔speaker associator. Two candidate associators, decided by measurement:
> (a) no new model — per-face mouth-region pixel-motion energy (lower third of the Haar box, sampled at >= 5 fps) correlated with the active turn;
> (b) an audio-visual ASD model (e.g. Light-ASD / TalkNet), which needs a §7 registry row, licence audit and ADR.
> Build (a) first; measure; add (b) only if (a) fails the bar. Crop follows the associated face; on ambiguity hold, never wander."

Prior status:
1. `SpeakerSubjectTracker` protocol was introduced in `src/hawedit/reframe.py`, but remained abstract without a concrete implementation anywhere in `src/`.
2. Pro-edit T7 had previously flipped on `test_an_unavailable_diarizer_never_claims_speaker_tracking`, which only verified that unavailable diarization did not falsely claim speaker tracking in the contract.
3. In Task T0.2 (ADR D-262), T7 was formally re-opened as T2.1 because no visual speaker-to-face associator existed.
4. Candidate associator (a) uses no new external weights: it operates directly on the lower third of OpenCV Haar face detections sampled at >= 5 fps, measuring inter-frame pixel-motion energy and correlating it with active exclusive diarization turns.

## Target Architecture

1. **`MotionSpeakerTracker` in `src/hawedit/reframe.py`**:
   - Implements `SpeakerSubjectTracker`.
   - `track_speakers(self, source: Path, in_ms: int, out_ms: int, turns: Sequence[Segment]) -> tuple[SpeakerFocusPoint, ...]`.
   - Validates spans and exclusive turns.
   - Samples source video at `sample_fps >= 5.0` (default: 5.0 fps, 200 ms).
   - Detects all candidate faces at each sample frame using Haar cascade classifiers (frontal + profile + mirrored profile).
   - For each detected face, extracts the mouth region (lower third: `y + 2*h//3 .. y + h`).
   - Computes pixel-motion energy $\Delta_{mouth} = \text{mean}(|I_t - I_{t-1}|)$ in grayscale.
   - For each timestamp $t$ with an active speaker turn:
     - If one face exhibits dominant mouth-motion energy above floor and ratio, binds that face to the active speaker.
     - Maintains a speaker-to-face spatial affinity memory across turns.
     - On ambiguity or detection dropout, holds the last confirmed face position for that speaker ("on ambiguity hold, never wander").
   - Returns strictly increasing `SpeakerFocusPoint(at_ms, center_x, speaker)` instances strictly matching active turn timestamps.

2. **Pipeline Integration**:
   - In `src/hawedit/pipeline.py`, when `speaker_tracker` is provided (or when `--diarize` is enabled and not `--static-crop`), `run_pipeline` passes `MotionSpeakerTracker()`.
   - The returned points pass through `validate_speaker_focus_points`.
   - Camera steadying applies and sets `reframe_mode = Reframe.SPEAKER_TRACKED` and `crop_target = "speaker_face"`.
