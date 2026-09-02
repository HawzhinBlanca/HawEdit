# Plan — Frontier Rating & DaVinci Resolve Editorial Handoff (September 2026)

Approved-by: Hawa

> **The North Star Architecture**:
> HawEdit is the **Sorani Kurdish editorial brain plus proof**.
> DaVinci Resolve Studio is the **finishing room**.
> Per episode, HawEdit delivers:
> 1. **N sentence-complete clips** (validated with exact Kurdish boundary invariants).
> 2. **An OpenTimelineIO (`.otio`) timeline** with cuts and colored markers for Hook (Red), Payoff (Blue), Punch-In cut points (Yellow), Speaker Turns (Cyan), and Sentence Boundaries (Green).
> 3. **SRT and ASS** subtitle tracks with complex HarfBuzz RTL text shaping.
> 4. **An editing JSON** carrying the face-tracked camera reframe keyframe path.
> 5. **A preview render MP4** for immediate review.
> 6. **The measured sidecar (`<clip>.measured.json`)** produced by independent Level B measurement that reconciles every contract claim at the Level C gate.
>
> Drop from HawEdit what DaVinci Resolve does better: final color grading, manual mix, brand kits, eased transitions. Keep and finish what nobody else on earth has: OmniASR Sorani champion, sentence-hard boundaries, multimodal frame-judging, speaker diarization + Light-ASD markers, and the strict reconciliation gate.

---

## 1. Architecture: The Editorial Handoff Engine (`hawedit.timeline`)

Create `src/hawedit/timeline.py` implementing zero-dependency, standard OpenTimelineIO (`.otio`) schema serialization:

### Schema Elements:
- `OTIO_SCHEMA`: `Timeline.1`
- `global_start_time`: `RationalTime.1` at source video `fps`.
- `tracks`: `Stack.1` containing:
  - `Track.1` (Video): Clips conform source media range (`TimeRange.1`).
  - `Track.1` (Audio): Synchronized dialogue audio.
- Markers (`Marker.1`):
  - **Hook Marker** (`color="RED"`): 0 to 3,000 ms hook window.
  - **Payoff Marker** (`color="BLUE"`): Verdict payoff point (`payoff_at_ms`).
  - **Punch-In Marker** (`color="YELLOW"`): Punch-in schedule points and scene cuts.
  - **Speaker Turn Marker** (`color="CYAN"`): Diarization speaker boundaries (`SPK_01`, `SPK_02`).
  - **Sentence Boundary Marker** (`color="GREEN"`): Sentence start/end timestamps.

### Module Interface:
```python
def build_otio_timeline(
    clip: Clip,
    source_media_path: str,
    fps: float,
    punch_ins: tuple[int, ...] = (),
    speaker_turns: tuple[tuple[int, int, str], ...] = (),
) -> dict[str, Any]:
    ...

def build_episode_otio_timeline(
    clips: list[Clip],
    source_media_path: str,
    fps: float,
    episode_title: str,
) -> dict[str, Any]:
    ...
```

---

## 2. Delivery Bundle Update (`src/hawedit/delivery.py`)

Extend `publish_delivery_bundle` to produce the `.otio` timeline alongside the `.edl`, `.srt`, `.ass`, `.json`, `.mp4`, and `.measured.json`.
Both per-clip `.otio` and episode-level `timeline.otio` are emitted atomically into the delivery directory.

---

## 3. Verification & Proof Standard

1. **Level A (Unit)**: `tests/test_timeline.py` asserting schema conformity:
   - Valid `OTIO_SCHEMA` tags (`Timeline.1`, `Track.1`, `Clip.1`, `Marker.1`, `TimeRange.1`, `RationalTime.1`).
   - Marker color mapping and non-overlapping conforms.
   - Round-trip JSON deserialization.
2. **Level B (Real Media)**: An OTIO export of `ep29-VbX8UWwl1c4-s25-25` conforming back to the source media file.
3. **Level C (Reconciliation)**: `reconcile_delivery` validates timeline marker duration and count against contract and measured cuts.
4. **Full Gate Pass**: 3,360+ tests passing with zero errors.
