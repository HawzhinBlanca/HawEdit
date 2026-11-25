# Impact map — Reel Visual Quality

Found by grep (Serena unavailable this session); re-confirm with `find_referencing_symbols`
before editing.

| Symbol | Callers | Tests to adjust/add |
|---|---|---|
| `reframe.median_face_box` | `pipeline.py:1910`; demo scripts (deleted in T1) | `test_reframe.py:414,420,421` keep; add per-shot test |
| `render.vertical_framing` | `render.py:1013` (`crop_filter`) | `test_render.py:1516-1569`, `test_broadcast_studio.py:394-398` |
| `render.crop_filter` | `render_clip` path | add per-shot sendcmd test |
| `sanity_gate.check_face_presence` | `sanity_gate.py:360` (`run_full_audit`) | `test_sanity_gate.py:189-256`, `test_robustness_audit.py:318` |
| `condenser.GeminiStoryEvaluator.evaluate_story` | `_condense_story_with_evaluator` | `test_condenser.py` add malformed-response test |
| `captions` default `margin_v` / `HookBanner` style | `build_ass` callers | caption tests asserting margin/style; golden render (§4.3.6) may need a deliberate, ADR-backed update |
