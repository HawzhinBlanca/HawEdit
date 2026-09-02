# Research — Provenance in the Contract (`specs/provenance-contract`)

## 1. Problem Statement
Under §7.6 and Task T1.6 of `specs/pro-grade-program/tasks.md`:
"A clip must say what made it."
Today, `Clip.to_dict()` and `Clip.from_dict()` serialize the editorial decision, boundary, transcript, output, and QC blocks. However, the exact constants, model hashes, prompt hashes, environment hashes, and git commits that shaped the clip are omitted or scattered:
- Git SHA of the rendering engine
- `models/revisions.json` digest
- Judge prompt SHA-256 and judge response ID
- Threshold values in force (`MIN_HOOK_SCORE`, `MAX_MISLEADING_EDIT_RISK`, `MIN_MEANING_FIDELITY`, `MIN_CULTURAL_LANDING`)
- VAD/scene cut thresholds (`SCENE_CUT_THRESHOLD`, `VAD_ONSET_MS`, `SHOT_CUT_GUARD_MS`)
- Crop geometry constants (`TARGET_WIDTH=1080`, `TARGET_HEIGHT=1920`, `FACE_COMPOSITION_LINE=0.38`, `MAX_VERTICAL_ZOOM=1.20`)
- FFmpeg version and build configuration hash
- Execution profile (`profile`, e.g. `"production"`)

Without this provenance, two identical-looking contracts cannot be verified for reproducibility, and a clip cannot prove at the render gate that it was produced under production standards.

## 2. Codebase Grounding
- `src/hawedit/clip.py`:
  - `Clip` dataclass: needs `provenance: Provenance | None = None`.
  - `Clip.to_dict()`: serializes `provenance`.
  - `Clip.from_dict()`: parses `provenance` when present.
  - `Clip.assert_renderable()`: render gate before Stage 6. Must refuse if `self.provenance is None`.
- `src/hawedit/measure.py`:
  - `ClipMeasurement.tool_metadata`: records `"ffmpeg_version"`.
- `src/hawedit/delivery.py`:
  - `reconcile_delivery`: Clause 9 checks that `clip.provenance.ffmpeg["version"]` agrees with `measurement.tool_metadata["ffmpeg_version"]`.
- `models/revisions.json`:
  - Visual checkpoints revision pinning.
- `src/hawedit/render.py` / `src/hawedit/pipeline.py`:
  - Where the clip contract is assembled and rendered.

## 3. Provenance Schema
A new frozen dataclass `Provenance`:
```python
@dataclass(frozen=True, slots=True)
class Provenance:
    git_commit: str
    revisions_digest: str
    judge_prompt_sha256: str
    judge_response_id: str
    thresholds: dict[str, float]
    vad_scene: dict[str, float | int]
    crop_constants: dict[str, float | int]
    ffmpeg: dict[str, str]
    profile: str = "production"
```

## 4. Invariants & Refusal Rules
1. `Clip.assert_renderable()`:
   - If `self.provenance is None`, raises `ValueError("clip ... carries no provenance block...")`.
   - Validates that `thresholds`, `vad_scene`, `crop_constants`, `ffmpeg` contain non-empty entries.
2. `reconcile_delivery`:
   - Checks contract ffmpeg version matches measured ffmpeg version.
3. Unit tests in `tests/test_provenance.py` or `tests/test_clip.py`:
   - `test_a_contract_names_every_constant_that_shaped_it`
   - `test_render_gate_refuses_clip_without_provenance`
   - `test_reconcile_delivery_verifies_ffmpeg_version_agreement`
