# Implementation Plan: Multi-Part Story Condensation, Semantic Pruning & Automated Sanity Gate

> **Feature:** `story-condensation`  
> **Status:** PENDING APPROVAL  
> **Approved-by:** ___________________ (STOP: Do not proceed to code execution until signed)

---

## 1. Goal Description

Implement an end-to-end multi-part story condensation system for HawEdit that:
1. **Identifies Stories & Generates Summaries**: Detects macro narrative units in long-form podcasts/interviews, decomposes them into story beats (Hook, Setup, Conflict, Climax, Resolution), and generates a Kurdish headline and 1–2 sentence summary.
2. **Performs Semantic Non-Contiguous Pruning**: Extracts the most important sentences/clauses ("the main words") that convey 100% of the core story meaning, removing rambling preamble, discursive filler, and repetitive clauses across multiple non-contiguous parts ($25\text{ms}–50\text{ms}$ audio crossfade).
3. **Remaps Timestamps for Frame-Locked Kinetic Subtitles**: Perfectly maps word-level alignment across cuts to drive 115pt bold `Vazirmatn` kinetic pop subtitles with zero drift.
4. **Enforces an Automated Sanity Gate**: Implements automated multi-modal checks (face presence in crops, subtitle legibility/sync, EBU R128 audio loudness, and story completeness) with strict fail-stop alerts whenever any check fails.

---

## 2. EARS Acceptance Criteria

- **CRIT-1 (Story Identification & Summary)**:  
  WHEN an episode transcript is analyzed, THE system SHALL extract a complete story arc with a non-empty Kurdish headline, a 1–2 sentence Kurdish summary, and categorized story beats (`HOOK`, `SETUP`, `CONFLICT`, `CLIMAX`).
- **CRIT-2 (Multi-Part Semantic Pruning)**:  
  WHEN a story is condensed, THE system SHALL select non-contiguous essential sentences resulting in an output duration between 30 and 60 seconds and a condensation ratio between 30% and 75%, preserving 100% of the core narrative meaning.
- **CRIT-3 (Acoustic Continuity & Zero Clicks)**:  
  WHEN non-contiguous speech segments are concatenated, THE system SHALL apply an equal-power crossfade ($30\text{ms}–50\text{ms}$) across audio cut boundaries, with zero audio clipping ($TP \le -1.0\text{ dBFS}$) and integrated loudness in $[-24, -16]\text{ LUFS}$.
- **CRIT-4 (Frame-Locked Kinetic Subtitles)**:  
  WHEN subtitles are generated for condensed speech, THE system SHALL remap all word timestamps with $< 40\text{ms}$ maximum alignment drift, using 115pt bold `Vazirmatn` font, $\le 20$ characters per line, and vertical margin $\ge 240\text{px}$.
- **CRIT-5 (Automated Sanity Gate & Fail-Stop)**:  
  WHEN a reel is rendered, THE `SanityGate` SHALL inspect face presence in all 9:16 crops, subtitle specs, audio LUFS, and narrative integrity. If ANY check fails, THE system SHALL HALT immediately and output a structured diagnostic report detailing the failure.

---

## 3. Tasks & Implementation Steps

### Task 1: Semantic Story Condensation Engine (`src/hawedit/condenser.py`)
- Implement `BeatKind`, `StoryBeat`, `StorySummary`, and `CondensedStoryPlan` dataclasses.
- Implement `condense_story(sentences, target_duration_ms=45_000)`:
  - Preserves Hook (first 3s) and Climax/Resolution.
  - Ranks intermediate sentences by information density and narrative necessity.
  - Filters out conversational filler, repetitions, and dangling conjunctions.
- Implement `remap_words_to_condensed_timeline(words, segments)`:
  - Re-indexes forced alignment timestamps into a continuous output timeline.
- Create comprehensive unit tests in `tests/test_condenser.py`.

### Task 2: Automated Sanity Gate (`src/hawedit/sanity_gate.py`)
- Implement `QualityAuditReport` dataclass with pass/fail flags and numeric metrics.
- Implement `SanityGate`:
  - `check_face_presence(video_path, shot_segments)`: Probes frames at 1s intervals using face detection. Zero dead frames allowed.
  - `check_subtitles(ass_path, video_duration_ms)`: Checks font size $\ge 100\text{pt}$, max chars/line $\le 20$, margin $\ge 240\text{px}$, sync drift $\le 40\text{ms}$.
  - `check_audio_compliance(video_path)`: Uses `ebur128` filter to check integrated loudness ($-24$ to $-16\text{ LUFS}$), True Peak $\le -1.0\text{ dBFS}$, and silence gaps.
  - `check_narrative_integrity(plan)`: Checks headline, summary, duration, and grammar.
  - `run_full_sanity_audit(video_path, ass_path, plan)`: Halts with non-zero exit and diagnostic output if any check fails.
- Create comprehensive unit tests in `tests/test_sanity_gate.py`.

### Task 3: Pipeline Integration & Verification
- Resolve the 7 mypy strict typing issues in `scripts/render_pro_reel_master.py`.
- Integrate `condense_story` and `SanityGate` into the master pipeline runner.
- Run `scripts/render_pro_reel_master.py` to produce the newly condensed story reel from ZarPodcast Ep 29 with headline, summary, multi-part cuts, and automated audit report.
- Run full gate verification (`bash scripts/verify.sh`).

---

## 4. Verification Plan

1. **Unit Tests**:
   - `tests/test_condenser.py`: Tests story beat assignment, non-contiguous condensation, pruning ratios, and word timestamp remapping.
   - `tests/test_sanity_gate.py`: Tests passing criteria and verifies that synthetic defects (0 faces, small font, audio clipping, broken story) correctly trigger immediate fail-stop.
2. **Fast Gate**:
   - `bash scripts/verify.sh --fast`: Lint (`ruff check`) and typecheck (`mypy --strict`) across all 235+ source files must exit 0.
3. **Full Gate**:
   - `bash scripts/verify.sh`: Full test suite pass with fresh JUnit test report.
4. **End-to-End Real Render & Sanity Audit**:
   - Run condensed reel render on ZarPodcast Ep 29.
   - Generate `QualityAuditReport` confirming 100% face presence, 115pt kinetic subtitles, -16 LUFS audio, and valid Kurdish headline/summary.
