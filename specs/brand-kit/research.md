# Research — Brand Kit (Task T2.13)

## 1. Problem & Motivation
In `BLUEPRINT.md` §3 Stage 6, the rendering pipeline specifies:
> "Reframing, captions, encode. Caption requirements in §4.3 are not optional. Vertical reframing tracks the active speaker from diarization plus face detection..."

While HawEdit achieves state-of-the-art Kurdish transcript alignment, boundary precision, and dynamic 9:16 vertical reframing, high-performing social video reels (Instagram Reels, TikTok, YouTube Shorts) require professional packaging and channel attribution:
1. **Lower-Third Speaker Labels**: Identifying speakers by their actual Kurdish names and titles (e.g., "د. ئاراس عومەر / پسپۆڕی نەخۆشییەکان") when speaker turns begin, rather than anonymous diarization IDs (`SPEAKER_00`, `SPEAKER_01`).
2. **Logo Watermark**: Semi-transparent channel/show branding in an unobtrusive screen location (e.g. top-right corner) that establishes source attribution without occluding faces or subtitles.
3. **2s End Card**: A 2.0-second outro sequence displaying a clear call-to-action in Sorani Kurdish (e.g., "بۆ بینینی تەواوی گفتوگۆکە سەردانی چەناڵی یوتیوب بکەن") and channel handle (`@ZarPodcast`), providing a polished closing beat.
4. **Progress Bar**: An animated progress line along the bottom (or top) margin advancing smoothly from 0% to 100% across the video's duration, proven to increase viewer retention on mobile video platforms.

Because `BLUEPRINT.md` §3 Stage 6 did not explicitly mandate branding overlays, adding these stages requires an Architectural Decision Record (ADR) in `DECISIONS.md` (ADR D-268).

## 2. Strict Fail-Stop & Zero Fallback Constraints
Under `GEMINI.md` and `.agents/rules/strict-fail-stop.md`:
- If `--brand-kit` or `--logo` is specified, the file MUST exist and be valid. Missing logo images or malformed metadata must raise a fatal error immediately rather than rendering without them.
- Kurdish text in lower-thirds and end cards MUST use verified RTL-capable fonts (`Noto Naskh Arabic` / `Vazirmatn`) shaped through libass `shaping=complex` with HarfBuzz. No ASCII or unshaped Arabic text is ever tolerated.
- Lower-third speaker labels and progress bars must respect the 9:16 safe area and must never overlap with or occlude active karaoke subtitles or speaker faces.

## 3. Technical Architecture & Component Design

### 3.1 `hawedit.brand` (New Module)
To preserve separation of concerns and avoid bloating `render.py`, a dedicated `src/hawedit/brand.py` module defines:
- `SpeakerBio`: Dataclass holding `name_ckb: str` and optional `title_ckb: str | None`.
- `ProgressBarConfig`: Dataclass holding `enabled: bool`, `color: str` (e.g. `"#E50914"`), `height_px: int` (default 6), and `position: str` (`"bottom"` or `"top"`).
- `EndCardConfig`: Dataclass holding `enabled: bool`, `duration_s: float` (default 2.0s), `title_ckb: str | None`, `subtitle_ckb: str | None`, `handle: str | None`, and `background_color: str` (default `"#000000"`).
- `BrandKit`: Dataclass aggregating:
  - `speaker_metadata: dict[str, SpeakerBio]`
  - `logo_path: Path | None`
  - `logo_position: str` (`"top_right"`, `"top_left"`, `"bottom_right"`, `"bottom_left"`)
  - `logo_width: int` (default 160 px for 1080×1920)
  - `logo_opacity: float` (default 0.85)
  - `logo_margin: int` (default 40 px)
  - `progress_bar: ProgressBarConfig`
  - `end_card: EndCardConfig`
  - Helpers: `from_dict`, `to_dict`, `from_json(path)`.

### 3.2 Lower-Third Speaker Tags via ASS Subtitles (`hawedit.captions`)
Why render lower-third speaker labels through ASS subtitle events?
1. **HarfBuzz Complex Shaping**: Lower-third speaker names are Sorani Kurdish text. The ASS pipeline in `hawedit.captions` already enforces `shaping=complex`, font coverage verification, and pixel-tested rendering.
2. **Zero Secondary Filter Overhead**: Avoids complex `drawtext` filter escaping bugs on Windows and multi-platform FFmpeg quirks.
3. **Temporal Precision**: By matching diarization speaker turns against `speaker_metadata`, speaker tag events are added to the ASS event stream with precise start and end times, subtle fade-in/fade-out (`\fad(300,300)`), and distinct styling (`SpeakerTag` style).
4. **Collision Prevention**: Placed with vertical margins (`MarginV=280` or top `MarginV=120` when subtitles occupy the bottom), guaranteeing zero occlusion with speech karaoke subtitles.

### 3.3 Logo Watermark & Progress Bar in FFmpeg (`hawedit.render`)
1. **Logo Watermark**:
   - Filter graph:
     `[0:v]...[v_prelogo];[1:v]scale={w}:-1,format=rgba,colorchannelmixer=aa={opacity}[logo];[v_prelogo][logo]overlay={x}:{y}[v_postlogo]`
   - Position coordinates computed based on canvas 1080×1920 and safe margins.
2. **Progress Bar**:
   - Filter graph:
     `drawbox=x=0:y={y}:w='iw*t/{duration_s}':h={h}:color={color}:t=fill`
   - Dynamically tracks playback timestamp `t` and total duration `duration_s`.

### 3.4 2-Second End Card Assembly
1. A 2.0-second outro sequence rendered either by appending a 2-second branded card to the video timeline or overlaying a closing card during the final 2 seconds.
2. For standalone social reels, appending an explicit 2-second outro card with silent audio (`anullsrc`) or gentle audio fade-out allows complete narrative delivery of the speech before presenting the CTA.

## 4. Testing & Verification Strategy
1. **Unit Tests (`tests/test_brand.py`)**:
   - `BrandKit` dataclass validation (positive dimensions, valid opacity 0..1, valid positions, JSON serialization).
   - Validating missing logo file raises `FileNotFoundError` or `BrandKitError` (fail-stop).
   - Filter string generators for logo overlay and progress bar.
2. **Caption & ASS Integration Tests (`tests/test_captions.py`)**:
   - Generating ASS events with speaker lower-third tags for mapped diarization turns.
   - Verifying `SpeakerTag` style definition in ASS header.
   - Ensuring Kurdish text in speaker tags contains valid Arabic-script glyphs.
3. **Render Integration Tests (`tests/test_render.py`)**:
   - Rendering a short clip with logo watermark, progress bar, and speaker tag.
   - Verifying output dimensions (1080×1920) and measured duration.
4. **Gate Verification**:
   - Run `scripts/verify.sh` to ensure full test suite passes and test count ratchets up cleanly.
