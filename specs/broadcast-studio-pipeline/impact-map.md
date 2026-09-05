# Impact Map: Broadcast Studio Pipeline Upgrade

## Affected Symbols & Modules

| Module | Symbol | Change Type | Callers / Impact |
| :--- | :--- | :--- | :--- |
| `src/hawedit/captions.py` | `build_ass` | Add `margin_v: int | None = None` | `pipeline.py`, `render.py`, tests |
| `src/hawedit/captions.py` | `CaptionStyle` | Add `BROADCAST_STUDIO = "broadcast_studio"` | `pipeline.py`, `captions.py`, tests |
| `src/hawedit/brand.py` | `build_speaker_tag_events` | Upgrade styling, add configurable Y / margin | `captions.py`, tests |
| `src/hawedit/render.py` | `vertical_framing` | Support zoom / tight upper body framing | `crop_filter`, `render_clip` |
| `src/hawedit/pipeline.py` | CLI args (`--preset`) | Add `--preset` to parser and runner | CLI consumers, pipeline tests |
| `tests/test_broadcast_studio.py` | New tests | Add unit tests for preset, margin_v, and tight crop | Full test suite |
