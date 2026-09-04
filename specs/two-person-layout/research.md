# Research — Two-Person Split Screen Layout (Task T2.12)

## 1. Problem & Motivation
In podcast and interview formats (such as Zar Podcast Episode #29 `ep29-VbX8UWwl1c4`), dialogues frequently feature rapid conversational banter and back-and-forth exchanges where speaker turns are short (< 4.0 seconds).
Under single-subject vertical reframing (`Reframe.FACE_TRACKED` or `Reframe.SPEAKER_TRACKED`):
- Each rapid speaker turn causes either a camera whip-pan or an abrupt jump-cut between the host and guest every 1–3 seconds.
- This creates visual fatigue and whiplash for the viewer on 9:16 mobile feeds.
- The listener's immediate reaction (laughter, nodding, facial expression) is completely lost when the frame cuts away to the other speaker.

## 2. Standard Pro Social Layout Solution
On platforms like TikTok, Instagram Reels, and YouTube Shorts, the standard professional presentation for podcast banter is a **stacked two-person split screen**:
- **Canvas Geometry**: 1080×1920 (9:16 vertical).
- **Top Pane**: 1080×960 (9:8 aspect ratio), centered on Speaker 1 (e.g. Host).
- **Bottom Pane**: 1080×960 (9:8 aspect ratio), centered on Speaker 2 (e.g. Guest).
- **Vertical Seam**: Y=960, optionally cleanly divided with a subtle separator line or seamless stack (`vstack`).
- **Captions**: Positioned in the clear subtitle zone (or across the lower third / seam) without occluding either speaker's face.

## 3. Analysis of Existing Codebase
### 3.1 `src/hawedit/render.py`
- `Reframe` enum defines reframing modes:
  ```python
  class Reframe(Enum):
      STATIC_CENTRE = "static_centre"
      FACE_TRACKED = "face_tracked"
      SPEAKER_TRACKED = "speaker_tracked"
      BLURRED_FILL = "blurred_fill"
  ```
- `blurred_fill_filter` constructs custom FFmpeg filtergraphs using `split`, `scale`, `crop`, `boxblur`, `eq`, and `overlay`.
- `render_clip` accepts `reframe: Reframe` and branches on `Reframe.BLURRED_FILL` to apply `blurred_fill_filter` instead of `_crop_filter`.
- We can add `Reframe.TWO_PERSON_SPLIT = "two_person_split"` and `two_person_split_filter`.

### 3.2 `src/hawedit/reframe.py`
- `MotionSpeakerTracker` (implemented in Task T2.1) associates visible face bounding boxes with diarization turns (`Segment(start_ms, end_ms, speaker)`).
- When multiple speakers are tracked, their face centers `speaker_face_centers: dict[str, int]` are resolved.
- We need a detector function:
  ```python
  def detect_rapid_speaker_exchange(
      turns: Sequence[Segment],
      in_ms: int,
      out_ms: int,
      *,
      max_turn_duration_ms: int = 4000,
      min_alternations: int = 2,
  ) -> bool:
  ```
  which determines if a candidate span contains a rapid exchange of short turns between at least 2 distinct speakers.

### 3.3 `src/hawedit/pipeline.py`
- Integrates `MotionSpeakerTracker` during Stage 6 reframing.
- Can offer `--split-screen` / `--split-screen-rapid-exchanges` CLI option or evaluate `detect_rapid_speaker_exchange` when multi-speaker diarization is present.
- Records `reframe: "two_person_split"` in the output contract and run events.

## 4. Proposed Filtergraph Specification
For source dimensions $(W_s, H_s)$, target 1080×1920:
Each pane is $W_t \times H_p = 1080 \times 960$ (aspect ratio $9:8 = 1.125$).
Crop from source:
- Pane crop height $H_c = \min(H_s, \text{round}(W_c / 1.125))$ or using face height scaling.
- Pane crop width $W_c = \text{round}(H_c \times 1.125)$.
- Top pane crop centered horizontally at $x_1$, vertically at eye/face level $y_1$.
- Bottom pane crop centered horizontally at $x_2$, vertically at eye/face level $y_2$.
FFmpeg filter:
```
[0:v]split=2[top_in][bot_in];
[top_in]crop={top_w}:{top_h}:{top_x}:{top_y},scale={target_width}:{pane_h}{scale_flags}[top_pane];
[bot_in]crop={bot_w}:{bot_h}:{bot_x}:{bot_y},scale={target_width}:{pane_h}{scale_flags}[bot_pane];
[top_pane][bot_pane]vstack=inputs=2[v_split]
```

## 5. Test Coverage Strategy
1. Unit tests in `tests/test_render.py`:
   - `two_person_split_filter` parameter validation (positive dimensions, valid crop boxes).
   - Filter string syntax correctness (contains `split=2`, `vstack`, `crop=`, `scale=`).
   - `render_clip` accepts `Reframe.TWO_PERSON_SPLIT`.
2. Unit tests in `tests/test_reframe.py`:
   - `detect_rapid_speaker_exchange` detects rapid alternations (< 4s).
   - `detect_rapid_speaker_exchange` rejects monologues or long turns (> 4s).
   - `compute_two_person_split_crops` resolves centered top/bottom crops for two speaker positions.
3. Level B Media Verification:
   - Render a rapid dialogue span from Zar Podcast #29 (`ep29-chunk50min.mp4`) with both single-speaker tracking and two-person split screen.
   - Record Level B evidence in `evidence/two-person-layout.md`.
