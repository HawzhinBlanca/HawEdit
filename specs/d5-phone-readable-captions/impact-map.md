# Impact map — Phone-readable captions off faces, tables, and burned-in teaser label (D5 / d5-phone-readable-captions)

Serena MCP was unavailable in this session, so all symbol callers were mapped using `rg` over `src/`, `tests/`, and living docs (`DECISIONS.md`, `BLOCKED.md`, `PROGRESS.md`). Re-run `find_referencing_symbols` before implementation if Serena becomes available.

| Symbol / artifact | Callers / references | Expected effect & test coverage |
|---|---|---|
| `captions.VIRAL_FONT_SIZE`, `VIRAL_THEME`, `POPUP_MAX_CHARS` (`src/hawedit/captions.py:184,303,378`) | `pipeline.py:73-76, 2415-2431, 4305-4321`; `tests/test_captions.py:1384-1436, 1672-1860, 1951-2102, 2314, 2647, 2703` | Larger 72 px ink height, 6 px outline, `margin_v=450`, max 20 chars. Update literal constant assertions in `test_captions.py:1395, 1432` |
| `shot_plan.ProtectedRegionKind`, `ProtectedContentRegion` (`src/hawedit/shot_plan.py:45,57`) | `caption_layout.py:20`, `shot_composition.py:20,364,531`, `render_critic.py:22,693`, `tests/test_shot_plan.py`, `tests/test_shot_composition.py` | New enum member `TABLE_OBJECT` and optional `start_ms`/`end_ms` (default `None`); 100% backward compatible with all callers |
| `caption_layout.plan_caption_layout` (`src/hawedit/caption_layout.py:140`) | `visual_repair.py:20`, `render_critic.py:18`, `tests/test_caption_layout.py:12`; newly wired into `pipeline.py:2410, 4300` | Temporal filtering + `TABLE_OBJECT` + lower-middle `BOTTOM_BAND_BOX`; existing `test_caption_layout.py` remains valid |
| `pipeline.py` caption render sites (`:2410-2451`, `:4300-4338`) | Primary & review render loops | Wire `detect_protected_visual_regions` + `plan_caption_layout` -> `face_intervals` and pass `max_popup_width_px=POPUP_MAX_WIDTH_PX` |
| `assembly.render_assembled_reel` (`src/hawedit/assembly.py:308`) | `tests/test_assembly.py:241, 288` | Receives `VIRAL_FONT_SIZE`, `VIRAL_THEME`, `POPUP_MAX_CHARS`, `POPUP_MAX_WORDS` |
| `sanity_gate.check_subtitles` (`src/hawedit/sanity_gate.py:74`) | `SanityGate` (`sanity_gate.py`), `tests/test_sanity_gate.py` | `POPUP_MAX_CHARS=20`, `VIRAL_FONT_SIZE=128 >= 100`, `outline=6.0 >= 3.0`, `margin_v=450 >= 240` satisfy all checks |
| `tests/golden/*.png` (3 `VIRAL_THEME` goldens) | `tests/test_captions.py:544-550, 695-820` | Re-render and re-pin digests after `[HAWA]` approval |
| `DECISIONS.md`, `PROGRESS.md` (`:1280` M9.34), `BLOCKED.md` | Living docs | Append `## D-350`; note `PROGRESS.md:1280` (`caption_layout` now wired in `pipeline.py`); no `BLOCKED.md` entry |
