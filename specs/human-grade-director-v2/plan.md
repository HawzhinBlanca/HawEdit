# Implementation Plan — `human-grade-director-v2`

Approved-by: Hawa (per `/goal` directive 2026-11-20: "work hard to make the system as best as ever, and most content awaree system ever developed for this, when we got perfect watchable, human level video fully, ready to post, then we done")

## Parallel Swarm Execution Strategy

Lanes 1, 2, and 3 edit completely disjoint source files in dedicated `workspace:"share"` worktrees branched from `gemini/number-one` (`72180dc`), merged via `--no-ff` in order `hd-audio-cuts` -> `hd-camera` -> `hd-captions`. Lane 4 (`hd-integrate`) runs after Lanes 1–3 merge.

- **Lane 1 (`hd-audio-cuts`, D-360):** `src/hawedit/render.py`, `tests/test_hd_audio_and_cuts.py`
  - T1: Snap `per_shot_boxes` `cut_t` (`-0.002 s`) and `sendcmd` `cut_ms` (`-2 ms`) in `crop_filter()`.
  - T2: Add broadcast `acompressor` + `alimiter` to `SPEECH_CHAIN_FILTERS` and add `two_pass_loudness: bool = False` option on `render_clip()` (preserving `deliverable=False` unit tests while letting episode review renders run two-pass linear `loudnorm` + `speech_chain=True`).
  - T3: Add `content_aware_push_schedule(spans, *, excitement_by_span=(), payoff_at_ms=None)` in `render.py`.
- **Lane 2 (`hd-camera`, D-361):** `src/hawedit/reframe.py`, `tests/test_hd_camera_director.py`
  - T4: Add optional `edge_guard_px: int | None = None` & `edge_settle_ms: int = 250` fast smooth-follow in `stabilize()` so leaning speakers never clip at crop edges while staying jitter-free inside `dead_zone_px`.
  - T5: Add per-shot zero-face cutaway motion framing inside `OpenCvFaceTracker.track()` calling `detect_motion_focus_points()` on shots with zero detected faces.
- **Lane 3 (`hd-captions`, D-362):** `src/hawedit/captions.py`, `src/hawedit/caption_polish.py`, `tests/test_hd_captions_director.py`
  - T6: Face-aware 30-char 2-line hook card placement in `build_ass()` when `face_intervals` is present (byte-identical when `face_intervals is None` so `GOLDEN_HOOK_CARD` stays 100% green), plus `merge_short_orphans: bool = False` and `excited_intervals_ms: Sequence[tuple[int, int]] = ()` subtle karaoke micro-pop.
  - T7: Deterministic `normalize_sorani_digits()` integrated into `caption_polish.py` (preserving exact CTC timestamps and leaving `raw.json` untouched).
- **Lane 4 (`hd-integrate`, D-363):** `src/hawedit/pipeline.py`, `tests/test_hd_pipeline_integration.py`
  - T8: Wire two-pass broadcast mastering (`two_pass_loudness=True, speech_chain=True`), `content_aware_push_schedule`, `edge_guard_px`, `merge_short_orphans=True`, and `excited_intervals_ms` in `pipeline.py` (both episode batch & single-clip paths), re-pin VEX `source_sha256`, run real multi-genre production on `ai` + `cooking-30m`, visually inspect every contact sheet, record `evidence/human-grade-director-v2-2026-11-21.md`, and pass the full `scripts/update-ledger.sh` gate.
