# Plan — Broadcast Studio Pipeline & Agency Reel Upgrade

## Status
Approved-by: User (Auto-approved via review policy)

## Tasks

### Task 1: Subtitle Position & Margin Upgrade in `captions.py`
- Add configurable `margin_v` parameter to `build_ass(...)` (defaulting to 380-480 for mobile safe zone).
- Support `CaptionStyle.BROADCAST_STUDIO` / clean bold styling with high-contrast outline and clean Kurdish line breaking.
- Ensure subtitles sit at Y ≈ 1380-1440 (chest height), well above table props and mobile app interface overlays.

### Task 2: Wide Shot Tightening & Upper-Body Framing in `render.py`
- Enhance `vertical_framing` and `crop_filter` to support tight upper-body crop mode for wide shots:
  - When a wide shot is detected or when `tight_framing=True`, compute crop height `min(source_height, int(crop_w * 16/9 / zoom))` with `zoom=1.35x-1.50x`.
  - Clamp Y so headroom is optimal (face center in upper third, cutting out floor and table legs).

### Task 3: Agency Lower-Third Speaker Badge & Clean Logo Asset
- Recreate clean, high-resolution Zar Podcast logo without missing font tofu boxes (`work/zar_logo.png`).
- Upgrade speaker lower-third layout in `brand.py` with glassmorphic semi-translucent styling, Kurdish gold accent line (`#FFE500`), clean typography, and proper vertical positioning (Y ≈ 1250).

### Task 4: Pipeline Preset CLI Wiring in `pipeline.py`
- Add `--preset {broadcast,viral,split}` to `hawedit.pipeline`.
- When `--preset broadcast` is selected:
  - Sets safe subtitle margin (`margin_v=440`).
  - Activates broadcast line/keyword subtitles.
  - Automatically loads and binds brand kit with speaker tags.
  - Applies tight upper-body framing to wide shots.

### Task 5: Testing & Verification
- Add automated regression tests in `tests/test_broadcast_studio.py`.
- Run `bash scripts/verify.sh` to ensure lint, strict typecheck, and test suite pass.
- Render new production master of Zar Podcast Episode 29 and produce inspection contact sheet.
