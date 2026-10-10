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
