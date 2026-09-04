# Impact Map — Reproducibility Proof (`specs/reproducibility-proof`)

## Affected Callers & Symbols
- Symbol: `render_clip` (`src/hawedit/render.py`)
  - Callers: `hawedit.pipeline`, `tests/test_render.py`
  - Changes: Non-breaking. Tested for deterministic repeatability.
- Symbol: `build_ass` (`src/hawedit/captions.py`)
  - Callers: `render_clip`, `hawedit.pipeline`
  - Changes: Non-breaking. Verified byte-identical.
- Symbol: `Clip.to_dict` (`src/hawedit/clip.py`)
  - Callers: serialization, delivery manifests
  - Changes: Non-breaking. Verified deterministic minus runtime timestamps.
- Tests:
  - `tests/test_render.py` (`test_two_renders_of_one_edit_agree`)
- Evidence:
  - `evidence/two-renders-of-one-edit.md`
