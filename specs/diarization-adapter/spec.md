# Specification — pyannote diarization adapter (§3 Stage 0)

Closes the production-adapter half of the AC-9 remainder D-240 names. Speaker/face association
is **not** in this spec — it has its own seam (D-241) and gets its own plan once diarization can
actually be run and looked at.

## Acceptance criteria

- **AC-1:** WHEN `--diarize` is supplied, THE pipeline SHALL construct a concrete `Diarizer`
  bound to `pyannote/speaker-diarization-community-1` and pass it to `run_pipeline`.
- **AC-2:** WHEN `--diarize` is not supplied, THE pipeline SHALL behave exactly as it does
  today, recording `diarization=None` and the existing Stage 0 skip.
- **AC-3:** WHEN the adapter runs, THE adapter SHALL resolve its checkpoint through
  `ModelStore.assert_available` and SHALL refuse to start if the weights are absent, naming
  `BLOCKED.md` #4.
- **AC-4:** WHEN the resolved checkpoint's revision differs from the revision the acceptance kit
  pins (`diarization_acceptance.COMMUNITY_REVISION`), THE adapter SHALL refuse, so runtime and
  acceptance cannot disagree about which bytes ran.
- **AC-5:** WHEN pyannote yields a turn, THE adapter SHALL convert float seconds to exact
  integer milliseconds by monotonic rounding, and SHALL NOT merge, clamp, pad or reorder turns.
- **AC-6:** WHEN a converted turn would have zero or negative length, THE adapter SHALL refuse
  and name the turn, rather than dropping it.
- **AC-7:** WHEN the model's output overlaps, THE adapter SHALL let `attach_diarization` refuse
  it and SHALL NOT repair the overlap (D-243: the production diarizer may not overlap).
- **AC-8:** WHEN `pyannote.audio` is not installed, THE adapter SHALL raise a
  `DiarizationUnavailable` naming the missing extra, and THE run SHALL continue to a structured
  Stage 0 diarization skip rather than crashing (D-240).
- **AC-9:** WHEN diarization succeeds and every other stage ran, THE run SHALL be able to report
  `complete` — which is unreachable today on any input.
- **AC-10:** WHEN the adapter is enabled, THE project SHALL NOT claim any DER, boundary or
  association accuracy number, because no Kurdish multi-speaker reference exists here
  (`BLOCKED.md` #4, D-241's closing paragraph).
