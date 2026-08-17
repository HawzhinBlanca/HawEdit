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
