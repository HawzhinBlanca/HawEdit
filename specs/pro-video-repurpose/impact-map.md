# Impact Map: Pro Video Repurposing Upgrade

## Affected Symbols & Modules

| Module | Symbol | Change Type | Callers / Impact |
| :--- | :--- | :--- | :--- |
| `tests/test_broadcast_studio.py` | Full file | Restore missing 11 tests from D-272 | Full test suite, gate floor recovery to 3,578 tests |
| `src/hawedit/captions.py` | `CaptionStyle` | Add `KINETIC_POP = "kinetic_pop"` | `build_ass`, `pipeline.py`, tests |
| `src/hawedit/captions.py` | `build_ass` | Support kinetic word pop scaling tags & `hook_banner` | `pipeline.py`, `render.py`, tests |
| `src/hawedit/render.py` | `render_clip` | Add `music_bed_path`, `music_bed_ducking_db`, B-roll overlay | `pipeline.py`, render tests |
| `src/hawedit/pipeline.py` | CLI args | Add `--music-bed`, `--hook-banner`, `--two-person-split` | CLI consumers, pipeline tests |
| `tests/test_pro_video_repurpose.py` | New file | Add test coverage for kinetic pop, music ducking, and split wiring | Gate test suite |
