# Impact Map — Golden Coverage (`specs/golden-coverage`)

## Symbols Touched

1. `hawedit.captions.render_caption_png`:
   - Extend signature with optional `source_video: Path | None = None` and `timestamp_s: float = 0.0`.
   - Callers affected:
     * `tests/test_captions.py` (all existing callers remain 100% compatible; new tests use the new parameters).
     * Source inspection test `test_the_golden_render_burns_productions_own_filter_string`: preserves `"subtitle_filter(" in body` and `'f"ass=' not in body`.

2. `tests/golden/`:
   - Existing: `kurdish-caption.png`
   - Added:
     * `tests/golden/kurdish-viral-karaoke.png`
     * `tests/golden/kurdish-hook-card.png`
     * `tests/golden/kurdish-caption-fixture.png`

3. `tests/test_captions.py`:
   - Add pinned SHA256 mapping: `GOLDEN_DIGESTS: Final[dict[str, str]]`.
   - Add `test_golden_files_match_their_pinned_digests`.
   - Add pixel test and `shaping=simple` negative control for `kurdish-viral-karaoke.png`.
   - Add pixel test and `shaping=simple` negative control for `kurdish-hook-card.png`.
   - Add pixel test and `shaping=simple` negative control for `kurdish-caption-fixture.png`.
