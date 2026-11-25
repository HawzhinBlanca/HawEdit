# Impact map — Kurdish caption base direction

Serena was unavailable (connection timeout on 2026-11-17), so callers were found with grep over
`src/` and `tests/`. Re-run `find_referencing_symbols` before implementing if Serena is back.

| Symbol touched | Callers in `src/` | Tests covering them |
|---|---|---|
| `CaptionTheme.style_row`, `plate_style_row` (`captions.py:228, 253`) | `build_ass` and the hook/banner builders in `captions.py` | `test_captions.py`, `test_broadcast_studio.py`, `test_caption_context.py` |
| `measure_rendered_caption_width` (`captions.py:953`) | caption wrapping in `captions.py` (D-307) | `test_captions.py` |
| `build_ass` (`captions.py:1546`), output bytes change, signature does not | `assembly.py:308`, `captions.py:2703`, `pipeline.py:2410, 4300`, `proposals.py:596, 767, 949` | `test_pipeline.py`, `test_render.py`, `test_delivery.py`, `test_caption_timing.py`, `test_candidate_publication.py`, `test_render_boundary_revision.py`, `test_render_caption_revision.py`, `test_pro_video_repurpose.py`, `test_audit_regressions.py` |
| `verify_caption_text` (`captions.py:2421`) | `captions.py` | `test_captions.py`, `test_pro_video_repurpose.py` |
| `verify_caption_integrity` (`captions.py:2643`) | `candidate_publication.py`, `pipeline.py`, `proposals.py` | `test_captions.py`, `test_candidate_publication.py` |
| `verify_caption_glyphs`, `verify_caption_geometry` (`captions.py:2520, 2566`) | `verify_caption_integrity` | `test_captions.py` |
| `_parse_ass_dialogue_cues` (`measure.py`), `check_subtitles` (`sanity_gate.py`) | `measure.py`, `sanity_gate.py` | `test_sanity_gate.py`; **no test feeds either a line with a leading U+200F** — AC3's test adds one |
| `tests/golden/*.png` | four golden comparisons + `test_golden_files_match_their_pinned_digests` | themselves |

## Findings

- Any test that compares whole ASS strings or Style rows byte-for-byte will fail on the first
  run and must be updated to the new bytes. Known so far: `tests/test_captions.py:2193`. The
  gate will name the rest; each one is listed in the commit that changes it.
- Stored `.ass` files from earlier runs are unaffected; nothing re-reads them as input.
