# Impact Map: E1 — Per-Reel Contact Sheet (`<clip_id>.contact-sheet.jpg`)

> **Discovery method note:** Serena MCP is unavailable in this environment; all symbol definitions, callers, and file references below were mapped via regex/text grep across `src/`, `tests/`, `scripts/`, and root markdown docs.

## 1. Caller & Dependency Analysis

| Target / Existing Symbol | Exact Location | Relationship to E1 | Impact / Required Action |
|---|---|---|---|
| `ArtifactBundle._SUFFIXES`, `_validate()` | `src/hawedit/artifact_bundle.py:25, 243-270` | Rejects extra files inside staging dir before atomic `publish()` | **Keep untouched.** Write `<clip_id>.contact-sheet.jpg` to `bundle.final_dir` *after* `bundle.publish()`, matching `.cover.png`. |
| `REVIEW_SUFFIXES` | `src/hawedit/candidate_review.py:29` | Expected sidecar suffixes inside review cache | **Keep untouched.** Prevents breaking candidate review cache tests. |
| `_ensure_clip_cover_image` | `src/hawedit/pipeline.py:2058-2078` | Existing post-publish asset helper (`episode.py:550-558` consumes `.cover.png`) | Template pattern for writing post-publish image assets into `bundle.final_dir`. |
| `_render_episode_single_clip` | `src/hawedit/pipeline.py:2561-2569` | Calls `bundle.publish()` then `_ensure_clip_cover_image(...)` | **Edit in Round 2:** Invoke `render_reel_contact_sheet(...)` immediately after `bundle.publish()`, passing `edit_plan` and `.ass` path. |
| `run_pipeline` (single-clip flow) | `src/hawedit/pipeline.py:4652` | Post-`bundle.publish()` in single-clip pipeline | **Edit in Round 2:** Invoke `render_reel_contact_sheet(...)` immediately after `bundle.publish()` so standalone pipeline runs also get a contact sheet. |
| `VisualEditPlan` | `src/hawedit/edit_plan.py:324-573` | Holds exact `SourceTimeMapping` / output segments serialized to `.edit_plan.json` | Read-only dependency used to extract exact internal cut timestamps in output timeline coordinates. |
| `probe_container`, `probe_scene_cuts`, `_parse_ass_dialogue_cues` | `src/hawedit/measure.py:1-1235` | Independent FFmpeg/ffprobe container & scene-cut probes + ASS parser | Reused directly by `contact_sheet.py` (read-only dependency; no duplication). |
| `find_ffmpeg` | `src/hawedit/captions.py` | Resolves pinned FFmpeg executable | Reused directly by `contact_sheet.py` for frame extraction. |
| `use_utf8_streams` | `src/hawedit/cli.py:1-82` | Windows UTF-8 console helper | Reused by `hawedit.contact_sheet.main()`. |
| `tests/test_claims.py` (README / PROGRESS / console scripts) | `tests/test_claims.py:496-505, 730-745, 1363-1406, 1655-1668` | Requires `README.md` + `PROGRESS.md` row per module and fixed 16 `[project.scripts]` | Add `contact_sheet.py` to `README.md` (`L580-752` region) and `PROGRESS.md` (`L1250-1314` region); do **not** add a new `[project.scripts]` entry. |
| `tests/test_vex.py` digest pin | `tests/test_vex.py:27-30, 140-163` | Pins `package_digest(ROOT / "src" / "hawedit")` | Adding `src/hawedit/contact_sheet.py` + editing `pipeline.py` updates the digest; requires A3 VEX parking or re-pin. |
| Living docs | `DECISIONS.md` (`D-333` `:16485`), `PROGRESS.md` (`M9.27` `:1273`), `BLOCKED.md` (tail `#24`–`#26`) | Shared governance logs | Coordinate `PROGRESS.md`, `README.md`, and optional ADR `D-353` at Round 2 integration. |

## 2. Blast Radius Summary
- **Pipeline blast radius:** Two strictly post-publish calls in `src/hawedit/pipeline.py` (`:2561-2569` and `:4652`); does not mutate rendered MP4, ASS/SRT/EDL/JSON artifacts, `reconcile_delivery`, or `ArtifactBundle`.
- **Standalone utility:** Safe CPU-only execution via `python -m hawedit.contact_sheet` on any reel path.
