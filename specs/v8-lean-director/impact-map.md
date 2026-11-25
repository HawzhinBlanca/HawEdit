# Impact Map: HawEdit V8 Lean Director (`specs/v8-lean-director`)

## New Files (Zero Blast Radius on Existing 6,773 Tests)
- `src/hawedit/v8/__init__.py`
- `src/hawedit/v8/schema.py`
- `src/hawedit/v8/director.py`
- `src/hawedit/v8/tiktok_subs.py`
- `src/hawedit/v8/asd.py`
- `src/hawedit/v8/compiler.py`
- `tests/test_v8_*.py`

## Existing Files Touched (Minimal)
- `src/hawedit/render.py`: Add optional `subtitle_overlay_path: Path | None = None` (transparent RGBA/ProRes viral TikTok subtitle overlay composited before progress bar) and optional `camera_moves: Sequence[CameraMove] | None = None` support in `build_cinema_motion_filter` (strictly opt-in; existing signature/behavior untouched).
- `DECISIONS.md`: ADRs `D-382`–`D-386` (including licence audit for any new MIT/BSD runtime dependency such as `skia-python` / `uharfbuzz` / `python-bidi` and Apache 2.0 `Qwen2.5-Omni` / `Light-ASD`).
- `README.md` & `PROGRESS.md`: Map new `v8` modules for `tests/test_claims.py`.
- `security/wsl-asr-vex.json` & `tests/test_vex.py`: Re-pin `source_sha256` after `src/hawedit/` changes.

## Hard Boundaries Preserved
- `C:\Users\Wareen\.gemini\antigravity\scratch\HawEdit` (`1bedc8e`): Untouched.
- `tests/golden/**`: Byte-identical (existing `libass` §4.3.6 golden path preserved).
- `pipeline.py` (`8,091` LOC): No heuristic bloat added; V8 runs as its own clean lean package (`python -m hawedit.v8`).
