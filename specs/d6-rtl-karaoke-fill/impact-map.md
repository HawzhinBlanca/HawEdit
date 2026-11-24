# Impact map — Right-to-left intra-word karaoke fill (D6 / d6-rtl-karaoke-fill)

Serena MCP was unavailable in this session, so all symbol callers were mapped using `rg` over `src/`, `tests/`, and living docs (`DECISIONS.md`, `BLOCKED.md`, `PROGRESS.md`). Re-run `find_referencing_symbols` before implementation if Serena becomes available.

| Symbol / artifact | Callers / references | Expected effect & test coverage |
|---|---|---|
| `captions.build_ass` (`src/hawedit/captions.py:1557`) | `src/hawedit/pipeline.py:2410, 4300`; `src/hawedit/assembly.py:308`; `src/hawedit/proposals.py:596, 767, 949`; `src/hawedit/captions.py:2721` (`mobile_caption_layout`) | Signature unchanged; `WORD_HIGHLIGHT` emits Layer 0 + Layer 1 `\clip` events instead of `\kf`. Covered by `test_pipeline.py`, `test_assembly.py`, `test_render_caption_revision.py`, `test_candidate_publication.py`, `test_delivery.py` |
| `captions._karaoke` (`src/hawedit/captions.py:1469`) | Internal to `build_ass` (`src/hawedit/captions.py:1832`) | Replaced/retired by `_clip_karaoke_events` |
| `captions.verify_caption_text` (`src/hawedit/captions.py:2439`) | `verify_caption_integrity` (`:2670`), `pipeline.py:2447, 4334`, `proposals.py:605, 955` | Unchanged; consecutive-line deduplication (`:2495-2508`) handles Layer 0 + Layer 1 identical text lines |
| `measure._parse_ass_dialogue_cues` (`src/hawedit/measure.py:490`) | `measure.probe_face_tracking` (`:526`), `measure.probe_caption_ink` (`:791`) | Reads start/end timestamps of all `Dialogue:` lines; Layer 1 events fall strictly inside Layer 0 `[ev_start, ev_end]`, so intervals remain valid |
| `sanity_gate.check_subtitles` (`src/hawedit/sanity_gate.py:74`) | `SanityGate` (`src/hawedit/sanity_gate.py`) | Reads first `Style:` row (`Kurdish`) and strips `{...}` tags; unaffected |
| `content_type.CONTENT_TYPE_PROFILES` (`src/hawedit/content_type.py:61,70,88`) | `pipeline.py:2950`, `edit_plan.py:169` | `PODCAST`, `INTERVIEW`, `SOCIAL` keep `CaptionStyle.WORD_HIGHLIGHT` and automatically gain RTL sweep |
| `tests/test_captions.py:411, 1352, 1359` | Unit assertions on `\kf` and raw `Dialogue:` count | Update assertions to `\clip` and `Dialogue: 0,` base event counts |
| `tests/test_audit_regressions.py:208` | Asserts `{\kf100}` in `WORD_HIGHLIGHT` | Update to assert Layer 1 word-2 timestamp honors the 1 s gap (`0:00:01.50`) |
| `tests/test_caption_context.py:40, 80` | Asserts `len(events)` on `WORD_HIGHLIGHT` | Update to count `Dialogue: 0,` base events |
| `tests/test_render_caption_revision.py:336` | Asserts `"\\kf" in original_ass` | Update to assert `"\\clip(" in original_ass` |
| `tests/golden/kurdish-caption-fixture.png` + `tests/test_captions.py:548` | `test_the_render_matches_caption_over_fixture_video_golden` | Re-render & re-pin SHA-256 after `[HAWA]` approval |
| `DECISIONS.md` (`:13864` D-269, `:16548` D-334) | Living ADR record | Append `## D-348` superseding D-269's `\kf` retention; note `PROGRESS.md:477,654` and `BLOCKED.md` (no blocker) |
