# Plan — Golden Coverage for What Ships (`specs/golden-coverage`)

Approved-by: Hawa

## Executive Summary
Implement Task T1.8 from `specs/pro-grade-program/tasks.md`:
Add reference golden images for:
1. `VIRAL_THEME` karaoke frame (`kurdish-viral-karaoke.png`)
2. Opening hook card frame (`kurdish-hook-card.png`)
3. Caption over real fixture video (`kurdish-caption-fixture.png`)
Pin the SHA256 digest of each committed golden in the test code to guarantee immutability (anti-cheat).
Provide pixel comparison tests with `compare_golden_render` and strict `shaping=simple` negative controls for each golden.

## Technical Changes

### 1. Engine Extension (`src/hawedit/captions.py`)
- Enhance `render_caption_png`:
  ```python
  def render_caption_png(
      ffmpeg: Path,
      ass_path: Path,
      fonts_dir: Path,
      output: Path,
      width: int = 1080,
      height: int = 1920,
      shaping: str = "complex",
      source_video: Path | None = None,
      timestamp_s: float = 0.0,
  ) -> Path:
  ```
  When `source_video` is provided, reframe the video to 1080x1920 and burn `subtitle_filter(ass_path, fonts_dir)` at `timestamp_s`. Preserve the filter structure tested by `test_the_golden_render_burns_productions_own_filter_string`.

### 2. Golden Reference Generation (`tests/golden/`)
- Using `.codystem-allow-self-edit` sentinel:
  - `tests/golden/kurdish-viral-karaoke.png`
  - `tests/golden/kurdish-hook-card.png`
  - `tests/golden/kurdish-caption-fixture.png`
- Compute and verify their exact SHA256 checksums on the certified FFmpeg 8.1.1 stack with libass/HarfBuzz/FriBidi.

### 3. Test Implementation (`tests/test_captions.py`)
- Define `GOLDEN_DIGESTS: Final[dict[str, str]]` containing pinned SHA256 hashes for all 4 goldens (`kurdish-caption.png`, `kurdish-viral-karaoke.png`, `kurdish-hook-card.png`, `kurdish-caption-fixture.png`).
- Implement:
  1. `test_golden_files_match_their_pinned_digests()`
  2. `test_the_render_matches_viral_karaoke_golden(tmp_path: Path)`
  3. `test_simple_shaping_fails_viral_karaoke_golden(tmp_path: Path)`
  4. `test_the_render_matches_hook_card_golden(tmp_path: Path)`
  5. `test_simple_shaping_fails_hook_card_golden(tmp_path: Path)`
  6. `test_the_render_matches_caption_over_fixture_video_golden(tmp_path: Path)`
  7. `test_simple_shaping_fails_caption_over_fixture_video_golden(tmp_path: Path)`

## Verification Plan
1. Fast gate: `bash scripts/verify.sh --fast`
2. Full test suite: `bash scripts/verify.sh`
3. Flip ledger via `scripts/update-ledger.sh golden-coverage T1,T2`
4. Update `specs/pro-grade-program/tasks.md` row T1.8.
