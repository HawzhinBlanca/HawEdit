# research — pyannote diarization adapter (§3 Stage 0)

Scope: a concrete `Diarizer` behind the existing protocol, the CLI flag to enable it, and the
`SPEAKER_TRACKED` reframe path it unblocks. No code written.

## What the blueprint asks for
- §3 Stage 0 (`BLUEPRINT.md:108`): `pyannote/speaker-diarization-community-1` on **pyannote.audio
  4.x**, chosen for *"exclusive speaker diarization, which makes reconciliation with transcript
  timestamps materially easier"*. CC-BY-4.0, gated, *"factor the access-acceptance step into
  deployment automation"*. Keep 3.1 (MIT) as the §8.1 control.
- §3 Stage 6 (`BLUEPRINT.md:214`): *"Vertical reframing tracks the active speaker from
  diarization plus face detection."*
- §7 table (`BLUEPRINT.md:375`) lists the same checkpoint, CC-BY-4.0, attribution required.

## The seam is already built — this is the last mile, and it is named as such
D-240 closed the composition seam and says explicitly: *"The production adapter, exact
authenticated bytes, CC-BY attribution, Kurdish DER/boundary benchmark, speaker-to-face
association and crop-quality review remain **AC-9** work."* That is exactly this feature.

| symbol | file | state |
|---|---|---|
| `Diarizer` (Protocol, `@runtime_checkable`) | `ingest.py:107` | **no implementation anywhere** |
| `attach_diarization` | `ingest.py:688` | done — coerces nothing, sorts, `assert_exclusive`, range-checks |
| `Segment` | `diarization.py:55` | exact-int ms, printable one-line speaker, `end > start` |
| `assert_exclusive` | `diarization.py:89` | refuses overlap (D-243: production may not overlap) |
| `turn_bounds_for_anchors` | `diarization.py:109` | Stage 5 `speaker_turn_start/end` |
| `SpeakerSubjectTracker` (Protocol) | `reframe.py:87` | **no implementation anywhere** |
| `validate_speaker_focus_points` | `reframe.py:103` | done — binds each point to the active turn |
| `run_pipeline(diarizer=…, speaker_tracker=…)` | `pipeline.py:1149,1164` | wired, **never passed by the CLI** |
| `PipelineRun.complete` | `pipeline.py:329` | requires `ingest.diarization is not None` |

Consequence, measured this session: with no CLI flag the runner **can never exit 0**, on any
input. Every run reports INCOMPLETE.

## Provisioning
- Registry entry exists (`registry.py:179`), `gated=True`, `Provisioning.WEIGHTS`, CC-BY-4.0.
- Revision **is** pinned: `models/revisions.json` →
  `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee`. D-073 refused to pin it; the correction ADR
  (~`DECISIONS.md:2983`) reversed that — gating covers downloads, not metadata.
- `ModelStore.assert_available` (`models.py:991`) is the refusal point; `path_for` /
  `verify_checkpoint` are the load path (`asr.py:740,1144` is the working example).
- Attribution is already automatic: `registry.attribution_notices()` (`registry.py:570`) emits
  it from `licence.attribution_required`. Nothing to add.
- `create_omni_asr_producer` (`asr.py:1231`) is the factory shape to mirror.

## Risks
- **BLOCKED.md #4 is live.** `HF_TOKEN` unset here and the weights are not downloaded
  (`hawedit.models` → MISS). Downloads 401 until Hawa accepts the licence. **Nothing about this
  feature can be verified against the real model until then** — every number would be invented.
- **New runtime dependency.** `pyannote.audio` (MIT) + `torch` is not in any extra
  (`pyproject.toml:12-34`); `media` pins CPU `torch==2.13.0`. Needs an ADR per AGENTS.md, and a
  licence audit line (model CC-BY-4.0, code MIT — neither is NonCommercial).
- **No test can cover the model itself.** Every existing diarization test uses hand-built
  `Segment` values. The adapter's own conversion (pyannote `Annotation` → `Segment`) is testable
  with a stub; its *accuracy* is not, and must not be claimed. D-241 already forbids that.
- **Float→int ms rounding** is where an exclusive model becomes non-exclusive: pyannote yields
  float seconds, `Segment` demands exact ints, and two turns that abut at 1.2345 s can round into
  a 1 ms overlap that `assert_exclusive` then refuses. Needs a deliberate rule, not `round()`.
- `diarization_acceptance.py` already pins `COMMUNITY_REVISION` (line 66) — the adapter must
  agree with it or the acceptance kit and the runtime disagree about which bytes ran.

## Answers to
§3 Stage 0, §3 Stage 6, §7, §8.1 · D-240 (AC-9 remainder), D-241 (speaker-tracked provenance),
D-243 (exclusive production / overlap-aware control), D-011 (3.1 outside the registry) ·
BLOCKED.md **#4**.
