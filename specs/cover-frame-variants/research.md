# Research — Cover Frame and Title Variants (Task T4.10)

## Problem Statement
A high-retention vertical social media reel (Instagram Reels, TikTok, YouTube Shorts) requires two critical packaging assets beyond the video file itself:
1. **The Cover Thumbnail (`cover.png`)**: Platforms allow setting a specific cover frame from the video. If chosen mechanically (e.g. at $t=0$), the cover often catches the speaker with closed eyes (mid-blink), an unflattering mouth shape, or blurred due to motion. Choosing the cover frame using an objective heuristic—evaluating face height share, image sharpness (Laplacian variance), and an open-eyes check—ensures the reel's thumbnail is consistently professional and clickable.
2. **Kurdish Title Variants (`title_variants_ckb`)**: High-performing social workflows test 3 title variants (e.g., question hook, direct punchy claim, and intrigue/story opener) to optimize click-through rate across platforms.

## Codebase Findings
1. **OpenCV Haar Cascades**:
   - `src/hawedit/measure.py` already imports and loads `haarcascade_frontalface_default.xml` and `haarcascade_profileface.xml` from `cv2.data.haarcascades`.
   - `cv2.data.haarcascades` also bundles `haarcascade_eye.xml`.
   - `cv2.Laplacian(gray, cv2.CV_64F).var()` is standard in the codebase for focus/sharpness measurement.
2. **Contract Representation**:
   - `src/hawedit/clip.py:548`: `class Output` contains deliverable settings (`title_ckb`, `description_ckb`, `crop_target`, `caption_style`, `durations`, `hashtags_ckb`, `silence_removed_ms`, `loudness`).
   - `Output` can be extended with:
     - `title_variants_ckb: tuple[str, ...] = ()`
     - `cover_frame_ms: int | None = None`
   - This cleanly preserves backward compatibility with existing JSON files while fulfilling §5 and Task T4.10.
3. **Delivery Bundle**:
   - `src/hawedit/delivery.py`: `publish_delivery_bundle` emits EDL, SRT, JSON, OTIO, and measured.json. Adding `cover.png` creates a complete 7-file delivery package.
   - `reconcile_delivery`: can verify that if `cover_frame_ms` is specified in `clip.output`, it falls strictly within `[0, duration_ms]`.

## Real Media Telemetry
In `work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.mp4`:
- Face is present in 56.2% of frames.
- Median face height share is 23.7%.
- Evaluating frames across the 56.6s clip with face share + sharpness + eyes detection will identify an optimal cover frame without blinking or motion blur.
