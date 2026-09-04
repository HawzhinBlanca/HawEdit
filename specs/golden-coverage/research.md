# Research — Golden Coverage for What Ships (`specs/golden-coverage`)

## 1. Problem Context & Gap Analysis
As documented in `specs/pro-grade-program/tasks.md` Task T1.8 and Threat 7 of `research.md`:
- Currently, the only committed golden in `tests/golden/` is `kurdish-caption.png` (20,830 bytes).
- That reference tests the default proofreading style (`REPORT_THEME` on black at font size 64) with `CaptionStyle.LINE`.
- It does **not** cover what actually ships in social reels:
  1. `VIRAL_THEME` (`primary="&H0000E5FF"`, `secondary="&H00FFFFFF"`, bold, outline 4.0, shadow 2.0, font size 108/64) with animated karaoke word highlighting (`CaptionStyle.WORD_HIGHLIGHT`, `\kf`).
  2. Opening hook cards (`HOOK_CARD_THEME`: font size 84, bold, outline 18.0 box plate with 40% black background, alignment 8 top center, duration 1,800 ms).
  3. Real video composition: subtitles rendered over actual video frames (`kurdish-speech-3cuts.mp4`) rather than purely on black background.
- Furthermore, existing golden files had no pinned SHA256 checksums in the test suite (`test_golden_files_match_their_pinned_digests` missing), leaving the test suite open to silent tampering or drift.

## 2. Technical Grounding

### 2.1 Three Target Goldens
1. **`kurdish-viral-karaoke.png`**:
   - Source sentence: `_golden_sentence()` ("ڕۆژنامەوانی کوردی لە هەولێر.")
   - ASS parameters: `theme=VIRAL_THEME`, `style=CaptionStyle.WORD_HIGHLIGHT`, `font_size=VIRAL_FONT_SIZE`, `clip_in_ms=0`, `clip_duration_ms=2000`.
   - Render target: 1080x1920 black background at t=0.0s. First word "ڕۆژنامەوانی" is active with cyan highlight, subsequent words white.
2. **`kurdish-hook-card.png`**:
   - Source sentence: `_golden_sentence()`
   - Title: `title_ckb="ڕۆژنامەوانی لە هەولێر"`
   - ASS parameters: `theme=VIRAL_THEME`, `font_size=VIRAL_FONT_SIZE`, `title_ckb="ڕۆژنامەوانی لە هەولێر"`, `clip_in_ms=0`, `clip_duration_ms=2000`.
   - Render target: 1080x1920 black background at t=0.0s. Upper third features the semi-transparent black hook card plate with white Kurdish title text.
3. **`kurdish-caption-fixture.png`**:
   - Source sentence: `_golden_sentence()`
   - Fixture video: `tests/fixtures/kurdish-speech-3cuts.mp4` (640x360, 4.1s).
   - Video reframe: 1080x1920 vertical format.
   - Timestamp: 0.500s (during the first cut/speech segment).
   - Render target: 1080x1920 frame with actual video pixels beneath the Kurdish subtitles.

### 2.2 Invariants & Verification
- **Pixel-level comparison**: Uses `decode_to_rgb(ffmpeg, ...)` and `compare_golden_render(reference, candidate, ffmpeg=ffmpeg)`.
- **Negative control per golden**: Each golden must run with `shaping="simple"` and assert that `compare_golden_render` raises `AssertionError`.
- **Digest pinning**: `test_golden_files_match_their_pinned_digests` asserts that the SHA256 of every file in `tests/golden/` matches a dictionary of constants hard-coded in the test.
- **Enforcement path rules**: Creating new files in `tests/golden/` is governed by `scripts/guard-pretooluse.sh`. The sentinel file `.codystem-allow-self-edit` must be used.
