# Impact Map — Provenance in the Contract (`specs/provenance-contract`)

## 1. Symbol Changes
- `src/hawedit/clip.py`:
  - New: `Provenance` (frozen dataclass).
  - Modified: `Clip`: adds `provenance: Provenance | None = None`.
  - Modified: `Clip.to_dict()` and `Clip.from_dict()`.
  - Modified: `Clip.assert_renderable()`: checks `self.provenance is not None`.
- `src/hawedit/delivery.py`:
  - Modified: `reconcile_delivery`: adds Clause 9 (checks `clip.provenance.ffmpeg["version"]` matches `measurement.tool_metadata["ffmpeg_version"]`).

## 2. Callers & Tests Affected
- `tests/test_clip.py`:
  - `a_clip()` helper: adds default `provenance=a_provenance()` so existing render tests continue passing.
  - New test: `test_a_contract_names_every_constant_that_shaped_it`.
  - New test: `test_render_gate_refuses_clip_without_provenance`.
- `tests/test_delivery.py`:
  - New test: `test_delivery_refuses_ffmpeg_version_mismatch`.
- `tests/test_timeline.py`:
  - `a_clip()` helper: adds `provenance=a_provenance()`.
- `tests/test_render.py`, `tests/test_reframe.py`, `tests/test_pipeline.py`:
  - All use `a_clip()` from `test_clip.py` or create valid clips.
