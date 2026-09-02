# Plan — Provenance in the Contract (`specs/provenance-contract`)

Approved-by: Hawa

## 1. Overview
Implement Task T1.6: Provenance in the contract.
Add a `Provenance` block to `Clip` and `Clip.to_dict()` naming:
- `git_commit`: git SHA of the renderer
- `revisions_digest`: SHA-256 digest of `models/revisions.json`
- `judge_prompt_sha256`: SHA-256 of judge prompt
- `judge_response_id`: Unique response ID from judge call
- `thresholds`: Pinned threshold constants (`min_hook_score`, `max_misleading_edit_risk`, `min_meaning_fidelity`, `min_cultural_landing`)
- `vad_scene`: VAD onset and scene cut guard constants (`scene_threshold`, `vad_onset_ms`, `shot_cut_guard_ms`)
- `crop_constants`: Reframe and composition constants (`target_width`, `target_height`, `face_composition_line`, `max_vertical_zoom`)
- `ffmpeg`: FFmpeg runtime metadata (`version`, `buildconf_hash`)
- `profile`: Delivery profile name (`"production"` or `"development"`)

## 2. Refusal and Gate Rules
- In `Clip.assert_renderable()`:
  - Refuses with `ValueError` if `self.provenance is None`.
  - Refuses if required threshold, vad/scene, crop, or ffmpeg dictionaries are missing or incomplete.
- In `delivery.reconcile_delivery()`:
  - Clause 9 verifies agreement between `clip.provenance.ffmpeg["version"]` and `measurement.tool_metadata["ffmpeg_version"]`.

## 3. Implementation Tasks
1. Define `Provenance` dataclass in `src/hawedit/clip.py` with `to_dict()` and `from_dict()`.
2. Bind `provenance: Provenance | None = None` in `Clip`.
3. Update `Clip.assert_renderable()` to enforce non-None, complete `Provenance`.
4. Update `reconcile_delivery` in `src/hawedit/delivery.py` to check Clause 9 (FFmpeg version match).
5. Update test helpers `a_clip` / `a_provenance` in `tests/test_clip.py`.
6. Add unit tests: `test_a_contract_names_every_constant_that_shaped_it`, `test_render_gate_refuses_clip_without_provenance`, `test_delivery_refuses_ffmpeg_version_mismatch`.
