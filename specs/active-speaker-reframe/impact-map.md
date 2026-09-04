# Impact Map: Active-Speaker Reframe (Task T2.1)

| File / Symbol | Change Type | Impact & Rationale |
|---|---|---|
| `src/hawedit/reframe.py` (`MotionSpeakerTracker`) | [NEW] Class | Implements `SpeakerSubjectTracker` candidate associator (a) using mouth-region pixel-motion energy at >= 5 fps correlated with exclusive diarization turns. |
| `src/hawedit/pipeline.py` (`_build_and_run`) | [MODIFY] | Wires `MotionSpeakerTracker` as `speaker_tracker` when diarization is active and static crop is not requested. |
| `tests/test_reframe.py` | [MODIFY] | Adds unit tests for `MotionSpeakerTracker`: single speaker, multi-speaker mouth motion discrimination, ambiguity hold, and timestamp monotonicity. |
| `tests/test_pipeline.py` | [MODIFY] | Adds end-to-end integration tests with `MotionSpeakerTracker` verifying `Reframe.SPEAKER_TRACKED` and `crop_target="speaker_face"`. |
| `specs/active-speaker-reframe/tasks.md` | [NEW] | Master ledger for flipping T1 and T2 via `scripts/update-ledger.sh`. |
