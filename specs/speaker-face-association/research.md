# Research — speaker/face association

## Question

How can HawEdit move §3 Stage 6 from face-aware cropping toward active-speaker cropping without
claiming access to a gated diarizer or inventing an unmeasured visual association heuristic?

## Frozen requirements and current blockers

- `BLUEPRINT.md` §3 Stage 6 requires vertical reframing to track the active speaker from
  diarization plus face detection.
- §3 Stage 0 selects exclusive `pyannote/speaker-diarization-community-1` output.
- The 2026-08-15 authenticated Hub check found no logged-in account, and an exact-revision dry-run
  for `3533c8cf8e369892e6b79ff1bf80f7b0286a54ee` was refused because the gated repository requires
  approval (`BLOCKED.md` #4).
- Real multi-speaker footage and labels remain unavailable (`BLOCKED.md` #1), so no association
  threshold or accuracy claim can be derived honestly.
- `BLOCKED.md` #9 still prohibits adding SAM 3 or Molmo2 before real face-centred failures and a
  §7/licence decision exist.

## Current implementation

- `reframe.SubjectTracker.track(source, in_ms, out_ms)` receives no speaker turns and returns only
  unlabeled `FocusPoint` values.
- `OpenCvFaceTracker` follows a large, spatially continuous face. With two faces it can follow the
  listener; it has no speech evidence.
- `pipeline.run_pipeline` invokes that tracker after Stage 5 but does not pass
  `IngestResult.diarization` to it. Any non-empty points become output `crop_target=face_tracked`.
- `render.render_clip` derives its artifact label solely from point presence. It can emit
  `STATIC_CENTRE` or `FACE_TRACKED`; `SPEAKER_TRACKED` is intentionally unreachable.
- `PipelineRun.to_dict` already preserves `RenderResult.reframe`, so a truthful third state can
  travel through the existing report once the render call accepts it explicitly.

## Caller map

Serena is required by `AGENTS.md` but is not available in this Codex tool session. The fallback
mapping used exact `rg` symbol/caller searches and direct source inspection.

| Symbol | Callers/consumers | Impact |
|---|---|---|
| `SubjectTracker.track` | `pipeline.run_pipeline`; injected pipeline tests | Face-only contract remains compatible. |
| `FocusPoint` | `OpenCvFaceTracker`; pipeline tests | Exact integer/time validation can be strengthened centrally. |
| `run_pipeline(... subject_tracker=...)` | CLI `_run_from_args`; pipeline tests | Add a separate speaker-aware dependency; never infer capability from class names. |
| `render_clip(... focus_points=...)` | pipeline; render tests | Accept an explicit truthful reframe mode and reject mode/point contradictions. |
| `RenderResult.reframe` | `PipelineRun.to_dict`; render/pipeline tests | `SPEAKER_TRACKED` becomes reachable only through validated speaker-labelled points. |
| `Output.crop_target` | clip JSON and judge-derived output | Use frozen §2 value `speaker_face` only for validated speaker association. |

## Chosen bounded design

1. Preserve the existing face-only `SubjectTracker` contract.
2. Add a distinct `SpeakerSubjectTracker` contract that receives the exclusive turns overlapping
   the final clip and returns speaker-labelled focus points.
3. Validate every returned point at the pipeline boundary: exact increasing media-clock time,
   inside the final clip, and carrying the label of the exclusive turn active at that instant.
4. A non-empty validated result is the only route to `speaker_face` and
   `Reframe.SPEAKER_TRACKED`.
5. An empty result means explicit ambiguity and may fall back to the existing face-only tracker;
   a runtime/invalid-output failure is reported and never silently relabelled as ambiguity.
6. Rendering accepts an explicit reframe mode and refuses contradictory mode/point combinations.

This composes the missing trust boundary and makes the future production adapter plug-in work
testable. It does not close M3.3/M8.1: production gated bytes, an actual associator, and real
multi-speaker measurements remain required.

## 2026-10-10 Camera Evidence Admission Follow-Up

The preceding implementation inventory is historical, not a description of
current source. At `2fa571038af8c79677f1a12214be9836be1e2b46`, the shared
`pipeline._resolve_camera` serves single-clip and episode rendering. It validates
point shape/clock/turn identity, then treats any nonempty result as usable
speaker evidence. Its split centres aggregate all original observations.
`reframe.layout_policy` checks speaker state, speaking status and its existing
0.6 confidence policy, but seeds an unestablished camera from an ambiguous
point. After a shot cut it can seed again from a listener. Structural validation
is intentionally distinct from editorial evidence admission.

An actual synthetic probe with a zero-confidence, non-speaking listener returns
a nonempty validated point and layout keyframe. This is a contract counterexample,
not measured speaker identity accuracy or proof of an already published failure.
Fresh decoded ZAR source frames also show why an arbitrary centre crop is not
acceptable: the wide shot and late close shot need different subjects/positions.
Source/images/commands and limitations are in
`C:/Users/Wareen/HawEdit-video-rating-20261010/zar-source-framing-research.md`.

Genuine installed Serena definition/reference mapping completed seven pairs at
the current SHA with unchanged source/status. Original first mapping failed on
an incorrect research target `_ClipCameraPlan`; it was corrected to the actual
`_CameraResolution` and re-run, not represented as a successful first attempt.
Full map: `C:/Users/Wareen/HawEditCameraAdmissionMap-retry-20261010/serena-map.json`,
SHA256 `cf7ae09136fb19486a5d142e72ccdace064f878e80fa1d275c043bc441b6aabc`.
Pipeline raw hash `eb800d5a2977f2e73c7b9b32fb78f92e4d38930de31a2e55e9239a09240f1a45`;
reframe raw hash `d985673d71465cbda963a324731065ddc3333faccc84482b3ece4a380135809f`.

Bounded repair within approved Phase 5 and this existing plan: preserve
structural validation and unknown/listener observations for evaluation;
require established usable evidence for a camera, retain confirmed within-shot
holds, refuse an ungrounded initial/post-cut position, and exclude non-speaking/
low-confidence observations from split centres. Preserve preview-only empty
result behavior and production fail-stop behavior. Do not call the existing
heuristic threshold calibrated accuracy, change model policy, relax signatures,
or silently substitute another crop. No new dependency or architectural boundary.

Direct current tracker inspection shows its first frame intentionally has no
motion evidence and is marked unknown. The repair must not refuse every clip
merely because that first observation is unknown: a later usable same-shot
observation can establish the first keyframe, but the earlier unknown location
cannot seed it. Conversely a whole shot without usable evidence cannot borrow
an unrelated pre-cut location. This clarifies AC-11/AC-15 before implementation;
it neither proves first-frame identity nor changes a threshold after evaluation.

Existing positive fixture controls supply sparse known observations, including
no observation after a detected shot cut. Preserve those structural camera
contracts; this bounded repair refuses explicitly ungrounded observations, not
all unobserved frames. Complete per-shot/frame coverage and independently
labelled identity remain separate delivered-media acceptance requirements.
No sparse positive contract test may stand in for that evidence.

Before any source change, an external two-route pytest counterexample exercised
the actual resolver/layout/render on the existing decoded fixture with only
one zero-confidence non-speaking listener observation. Both assertions failed:
both production routes generated private review MP4s labelled speaker_tracked
instead of refusing. Fixture bytes stayed unchanged. This now establishes a
real rendered contract defect, not a final ZAR publication/identity benchmark.
JUnit `C:/Users/Wareen/HawEdit-video-rating-20261010/camera-admission-red.xml`,
SHA256 `91ee29300f36cb115c5c291bb73dd6b772d8fb7385ae2a612b64fbf64b9524a8`,
two failures, 13.58 seconds pytest wall time on HawaPC01/Python3.12.10.
Injected transcript/diarizer/judge/observations are known contract inputs, not
measured provider quality; actual resolver/layout/render were not mocked.
Raw private outputs are preserved in
`C:/Users/Wareen/HawEditCameraAdmissionRedArtifacts-20261010`.
Single output measured 49frames/1080x1920/1960ms by installed ffmpeg8.1.1;
MP4 SHA256 `6fb4af3019d3ccde5bc61de248b3823676b09fea2379ada179cd94760d906912`.
This is not pinned-render acceptance, authenticated approval or publication.

The old plan's security self-rebinding instruction is superseded by the approved
current acceptance program: independent current-package VEX review is required
(BLOCKED #24). No self-renewal/rebinding or old hosted checks can authorize the
new SHA. Model repository access (#4), labelled native identity evidence (#1),
and current runner checks (#25) remain separate prerequisites. BLUEPRINT §3
Stage 6 and §§8.1-8.3 govern output/evaluation claims.

## Fresh Pre-Edit Caller Evidence, 2026-10-10

Actual installed Serena/LSP map at9a7c8169bdd2f005177d52050aec5f68c2edd578:
C:/Users/Wareen/HawEditCameraAdmissionCurrentMap-20261010/serena-map.json,
SHA25609e607030679ff1883d4624fa4ec3c2313da36f1ee2c2fca5eea3bdeabb38bee.
Nine definition/reference pairs, unchanged=true. Pipeline and reframe hashes
still equal the original counterexample baseline above; no intervening edits
to these symbols. The map also includes both actual render routes and the
existing decoded-fixture tracker/run helpers before test edits.

Proceed with approved AC-10 through AC-15, test-first in the existing reframe and
candidate parity modules. Split regression compares real decoded output frames
against uncontaminated labelled inputs, not an invented virality/accuracy score.
Preserve sparse positive contracts and all existing fixtures/goldens/assertions.
The actual private SDK config consumer now separately passes at the same source
baseline; it is not real model admission or ZAR-output quality evidence.

First new98-case cohort:76pass/22fail/0errors/skips, JUnit184.444s. Raw
C:/Users/Wareen/HawEdit-video-rating-20261010/camera-admission-current-red.xml,
SHA25609e4087069d8c421a6ac84d81bdece781825a2a102681e3d5dc580cecb5b4b81.
Three failures used a misspelled test state offscreen; corrected to the actual
existing off_screen enum before production edits, retaining original report.
Other failures include actual wrong-camera renders and unequal decoded split
frames. Episode decoding additionally exposed a stale RenderResult.path:
_render_episode_single_clip publishes/moves the private bundle, but returns the
staged path. The single route already uses dataclasses.replace with the final
review path. Add the same returned-path parity for episodes, without changing
MP4 bytes, measurement hashes, review/publication state or serving permissions.
Fresh Serena maps this function and its sole caller _run_episode_delivery.
This is the existing parent artifact/review parity obligation, not an added
runtime architecture. Add its own measured-byte/path regression before fixing.

Corrected pre-source cohort:100cases/77pass/23fail/0errors/skips,205.945s JUnit.
Raw C:/Users/Wareen/HawEdit-video-rating-20261010/camera-admission-corrected-red.xml,
SHA25648e019868a0f99bf564c64bed688e9aa21367f49015923e5c9738e3c299e12b0.
Preserved its actual outputs under camera-corrected-red-artifacts in that root.
No production source changed before either red cohort or the fresh caller map.

First patched cohort:100pass/0fail/errors/skips,166.285s JUnit; raw
camera-admission-first-green.xml in the same root, SHA256
b6c436a0dc6067e48499e77510cb821b23095c5bc7d1aafc341ba489bee09c7b.
Actual render outputs preserved under camera-first-green-artifacts. Strict
mypy then required explicit variable-length tuple annotations in two new tests;
no runtime assertions or source behavior were changed for that correction.
Final fast lint/typecheck passes389files; fast is not the full gate.
Windows bash resolved to WSL on the first fast attempt and refused a CR-bearing
host-lock path; retained as an environment failure, not a passing check. The
actual installed Git bash runs the unchanged canonical script correctly.

Source package after repair is
f9c3871bb6cd3d32cff0203f8d222b78bce61ed0fc965cfe64a5efe8aefabc6e.
HawaPC01 Windows26300/Python3.12.10/pytest9.1.1/ruff0.9.6/mypy1.15.0,
OpenCV4.12.0 and actual ffmpeg8.1.1-full_build-www.gyan.dev. These runs use
the unchanged decoded fixture (ed038e743a6b1ee167290741ceda926ac1077ff192e4910528017e3183655a15)
and injected known observations, not measured provider accuracy or pinned-render
release acceptance. Broader affected cohorts and exact clean gate remain required.

Affected ten-module cohort:574cases/573pass/1fail/0errors/skips,672.275s JUnit.
Raw camera-admission-affected.xml in that root, SHA256
31aad365c24d07ba5830818e54aed77a7ec5a4e771129c5c3c4de73de97ae3a8.
The existing test_pipeline_integrates_motion_speaker_tracker_for_active_speaker_reframe
expects speaker_face/SPEAKER_TRACKED from the digit fixture with injected Haar
boxes but no established speaking evidence. With repaired admission, its default
preview falls through to correctly labelled static_centre. Keep this original
test, assertions, QC digest and fixture unchanged; do not restore false camera
admission to turn it green. Its expectation conflicts with the stronger approved
AC-10/AC-12 contract and requires a separately researched contract correction,
not an altered golden, fabricated identity or a skipped/deselected test.
The full gate remains required and this unit remains WIP. Strengthen the new
split comparison to every decoded frame and both measured frame counts before
the frozen committed gate; the initial100-pass report checked only first frames.

Final whole-stream cohort:100pass/0fail/errors/skips,165.294s JUnit.
Raw camera-admission-whole-stream.xml, SHA256
9e588d37ead7ad3eab1b171c7d20cfbb6493e1e6b555606852b28664b2c6703f.
Both actual split outputs compare every decoded frame and both independent
measured frame counts. Fast static checks pass389files. Current test-contract
follow-up has its own actual five-pair Serena map and Approved-by:pending plan
under specs/legacy-camera-contract; no legacy assertions/fixtures/QC modified.
