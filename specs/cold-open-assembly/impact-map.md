# Impact Map — Cold-Open Assembly (Task T4.9)

## Files Touched
- `src/hawedit/assembly.py`:
  - Add `assemble_cold_open(setup_sentences, payoff_sentence) -> AssembledReel`.
  - Add `assembled_splice_filter(...) -> str` for FFmpeg trim/concat filtergraph generation.
  - Add `render_assembled_reel(...) -> Path` rendering physical 9:16 vertical MP4 with spliced media, re-timed ASS subtitles, and punch-ins.
  - Add `judge_assembled_reel_multimodal(...) -> JudgeVerdict` extracting frames from the assembled video and gating `misleading_edit_risk <= 0.10`.
- `tests/test_assembly.py`:
  - Add unit tests for cold-open assembly, filtergraph construction, physical rendering, punch-in re-timing, and multimodal frame-based judging.
  - Add canonical test `test_an_assembled_reel_is_rendered_and_judged_with_its_own_frames`.
- `security/wsl-asr-vex.json`:
  - Update `source_sha256` matching updated `src/hawedit` package digest.
- `specs/pro-grade-program/tasks.md`:
  - Mark Task T4.9 as `[DONE]`.

## Downstream Callers & Non-Interference
- Standard single-span pipeline operations remain fully intact.
- Multi-moment assembly builds on top of `assembly.py`, `render.py`, and `keyframes.py` without modifying single-clip render contracts.
