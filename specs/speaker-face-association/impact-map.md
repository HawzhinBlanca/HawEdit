# Impact map — speaker/face association

## Planned source changes

| File | Symbols | Reason |
|---|---|---|
| `src/hawedit/reframe.py` | `FocusPoint`, new speaker-labelled point/protocol/validator | Define and validate the association evidence at one boundary. |
| `src/hawedit/pipeline.py` | `run_pipeline`, Stage 6 tracking block, render call | Pass final overlapping turns, select truthful fallback, and preserve structured failure. |
| `src/hawedit/render.py` | `render_clip` | Accept and validate the explicit reframe provenance attached to the artifact. |

## Planned tests

| File | Coverage |
|---|---|
| `tests/test_reframe.py` | strict point fields, turn/time association, ambiguity, invalid output |
| `tests/test_pipeline.py` | speaker success, face/static fallback, missing diarization, failure reporting, output label |
| `tests/test_render.py` | mode/point consistency and reachable `SPEAKER_TRACKED` artifact |

## Compatibility and non-goals

- The `--face-reframe` CLI remains face-only until a production speaker tracker exists.
- Existing injected `SubjectTracker` implementations keep their three-argument method.
- No new dependency, model, registry entry, threshold, network download, or licence claim is added.
- `BLUEPRINT.md` remains frozen; the implementation follows §3 rather than amending it.
- `PROGRESS.md` and evidence will describe a composed seam, not a measured production feature.

## Current Follow-Up Caller Map (2026-10-10)

Actual Serena nine-pair refreshed map and original source hashes are in research.md.

| Symbol | Actual callers | Repair/coverage |
|---|---|---|
| `pipeline._resolve_camera` | `_render_episode_single_clip`, `run_pipeline` | Both routes require usable camera evidence; decoded fixture regression is parameterized over both. |
| `reframe.layout_policy` | `_resolve_camera`, `test_layout_policy_holds_on_ambiguity_and_switches_on_verified_turn` | No ambiguous initial/post-shot seed; preserve verified holds and sustained-turn moves. |
| `validate_speaker_focus_points` | `_resolve_camera`, `diarization_acceptance._ReferenceItem.from_dict`, `_item_metrics`, existing reframe tests | Leave structural unknown/listener validation unchanged; add an explicit unchanged-contract control. |
| `_CameraResolution` | `_resolve_camera` return construction | No signature change; no speaker-labelled render with an empty/unusable layout. |
| `SpeakerFocusPoint` | trackers, pipeline, diarization acceptance, existing tests | No schema/default/identity threshold change. |

Add regressions in existing `tests/test_candidate_framing_parity.py` for both
production routes and split-centre contamination; unit controls in
`tests/test_reframe.py`. Preserve all existing assertions, fixtures and golden
media. The decoded-media contract tests inject known labelled observations to
exercise the real resolver/layout/render; they do not measure the tracker or
prove native identity accuracy. Full affected cohorts include pipeline, episode,
candidate framing, reframe, render and diarization acceptance.

Current9a7 actual nine-pair refresh is recorded in research.md. References are
unchanged: `_resolve_camera` has exactly the two production render callers;
`layout_policy` is called there and in the existing reframe policy test;
structural validation additionally serves acceptance reference ingestion and
metrics, so it will not filter evidence. `_Tracker.track_speakers` and `_run`
support all decoded parity tests and receive only additive outcomes/coverage.
No provider, renderer, model, canonical transcript or review signature contract
is changed by this unit.

Decoded parity additionally exposed `_render_episode_single_clip`'s stale
staging path after bundle promotion. Its sole actual caller is
`_run_episode_delivery`; returned RenderResult is propagated into PipelineRun
and CLI/status serialization. Reuse the existing single-route final-path
replacement, keeping measured bytes and review-only state unchanged. Cover
both routes with `test_review_render_path_names_the_measured_private_bytes_in_both_routes`
and the unchanged episode/pipeline/delivery cohorts.

The whole pipeline cohort exposes the existing motion-tracker integration test's
conflicting unknown-only positive expectation (details and raw failure in research).
Leave that test's source/QC/fixture/assertions unchanged in this unit. A future
test-contract correction must map it and its helpers before any edits; current
local focused passes cannot claim compatibility or full-gate acceptance.
