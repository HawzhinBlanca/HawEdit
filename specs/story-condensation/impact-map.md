# Impact Map: Multi-Part Story Condensation & Automated Sanity Gate

> **Feature:** `story-condensation`
> **Target:** Narrative story extraction, semantic non-contiguous speech pruning, story summaries, and automated fail-safe sanity verification.

---

## Affected Symbols & Modules

### 1. New Core Modules
- **`src/hawedit/condenser.py`**:
  - `BeatKind(str, Enum)`: Narrative arc beat types (`HOOK`, `SETUP`, `CONFLICT`, `CLIMAX`, `RESOLUTION`).
  - `StoryBeat`: Strongly typed narrative beat anchored to canonical sentences.
  - `StorySummary`: Story headline, narrative summary, virality score, and core topic.
  - `CondensedStoryPlan`: Complete multi-part story condensation plan with non-contiguous timeline segments.
  - `condense_story(...)`: Deterministic and LLM-assisted semantic pruner extracting high-importance sentences while preserving 100% meaning.
  - `remap_words_to_condensed_timeline(...)`: Re-indexes forced-aligned word timestamps across non-contiguous cut points with zero drift.

- **`src/hawedit/sanity_gate.py`**:
  - `QualityAuditReport`: Structured multi-dimensional inspection results.
  - `SanityGate`: Automated pre-delivery quality verification suite:
    - `check_face_presence(...)`: Verifies speaker face detection across all cropped 9:16 shots (0 dead frames allowed).
    - `check_subtitles(...)`: Verifies font size $\ge 100\text{pt}$, max chars/line $\le 20$, margin $\ge 240\text{px}$, and sync drift $\le 40\text{ms}$.
    - `check_audio_compliance(...)`: EBU R128 loudness ($-24$ to $-16\text{ LUFS}$), True Peak $\le -1.0\text{ dBFS}$, 0 digital clipping.
    - `check_narrative_integrity(...)`: Validates Kurdish headline, summary, duration (30–60s), and grammar integrity.
    - `run_full_sanity_audit(...)`: Aggregates all checks; strictly fail-stops with non-zero exit and diagnostic messages on any defect.

### 2. Existing Modules Touched / Integrated
- **`src/hawedit/story.py`**:
  - Integrate story relation models with narrative arc beats and story summaries.
  - Callers: `tests/test_story.py`.
- **`src/hawedit/sentences.py`**:
  - Anchor pruning at sentence and punctuation boundaries (`KURDISH_SENTENCE_FINAL`).
  - Enforce `assert_deliverable_order` across remapped condensed sentences.
  - Callers: `pipeline.py`, `boundary.py`, `captions.py`, `tests/test_sentences.py`.
- **`src/hawedit/timing_continuity.py`**:
  - Provide multi-segment mapping (`source_to_output_ms`, `output_to_source_ms`) for audio crossfades and video cut transitions.
  - Callers: `render.py`, `tests/test_timing_continuity.py`.
- **`src/hawedit/captions.py`**:
  - Ensure 115pt bold `Vazirmatn` kinetic pop subtitles are generated using remapped condensed timestamps.
  - Callers: `pipeline.py`, `delivery.py`, `tests/test_captions.py`.
- **`scripts/render_pro_reel_master.py`**:
  - Fix the 7 mypy strict typing errors.
  - Integrate multi-part condensation and the automated sanity gate directly into the pipeline script.

---

## Caller Impact & Regression Surface

| Component | Risk Level | Mitigation |
|---|---|---|
| Sentence Segmentation | Low | Pruner consumes already-verified `Sentence` tuples; no modifications to raw ASR or alignment. |
| Timestamp Continuity | Medium | Mathematical unit tests for `remap_words_to_condensed_timeline` asserting strict monotonicity and positive durations. |
| Subtitle Render & HarfBuzz | Low | Uses existing HarfBuzz `shaping=complex` and ASS generator; tests verify RTL Kurdish rendering. |
| Gate Verification | Zero | `scripts/verify.sh` runs lint + mypy + format + pytest; all new code adheres to `mypy --strict`. |
