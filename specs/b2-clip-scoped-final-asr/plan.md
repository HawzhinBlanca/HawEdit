# Plan: Clip-Scoped Final ASR (`specs/b2-clip-scoped-final-asr`)

Research: `research.md`. Spec: `spec.md`. Callers & tests: `impact-map.md`.

**Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"**

## 1. Decision to Record as D-340

Add an explicit two-pass clip-scoped final ASR path (`--clip-scoped-asr` + `--clip-asr-pad-ms`, default `4000`, allowed `[3000, 5000]`) that uses a fast draft transcript (via `--transcript PATH` today, or a future fast draft stage such as Phase B3) for Stage 2 indexing, Stage 3 discovery, Stage 4 judging, and initial Stage 5 anchor planning, and then invokes canonical OmniASR v12 + CTC-3B **once** across the sorted, deduplicated union of Stage 0 `_contextual_speech_regions(ingested.speech)` overlapping the padded chosen clip spans `[in_ms - pad_ms, out_ms + pad_ms]`.

Key guarantees:
1. **Whole-episode parity:** Regions are never sliced arbitrarily at `[in_ms - pad_ms, out_ms + pad_ms]`. Snapping to whole episode `_ContextSpeechRegion` boundaries guarantees identical acoustic WAV slices, decoder outputs, and CTC-3B Viterbi word clocks as a whole-episode run on the same spans (under uniform per-region validation mode, e.g., B6 validator-off).
2. **Batch amortisation:** Multi-clip episode delivery (`_run_episode_delivery`) calls `canonical_asr.transcribe(...)` **once** across all selected clips (paying the ~221 s model load once instead of `max_clips` times).
3. **Zero silent fallback (`GEMINI.md` / `D-260` / `D-278`):** A failure in clip-scoped final ASR halts delivery (`StageSkipped` / failed `EpisodeItemRecord`) rather than silently burning draft captions or unaligned timings onto final reels.
4. **Immutable storage preservation (`D-136` / Kurdish Invariant #1):** Draft transcripts stay untouched in `work_dir/transcripts`; clip-scoped final transcripts persist in an isolated `TranscriptStore(work_dir / "clip_asr" / "transcripts")` keyed on the exact sorted region list digest + `audio_sha256` + `producer_id` + `source_sha256` + `admission_policy`.

## 2. Considered and Not Chosen

- **Cut WAVs directly at `[clip_in_ms - pad_ms, clip_out_ms + pad_ms]`:** Rejected because cutting mid-`_ContextSpeechRegion` alters decoder context and shifts CTC frames, breaking parity with whole-episode runs.
- **Run `asr.transcribe` separately inside `_render_episode_single_clip` per clip:** Rejected because reloading 7B v12 + CTC-3B (`~221 s/load` measured on GPU 1) 10 times adds `~37 min` of pure load overhead.
- **Mutate or overwrite `work_dir/transcripts/{media_id}.transcript.raw.json`:** Violates Kurdish Invariant #1 and `TranscriptStore.write_raw`.

## 3. Implementation Tasks (Test-First, One Task at a Time)

1. **T1 — Padded `_ContextSpeechRegion` planner helper (pure, `src/hawedit/asr.py`):**
   - Extract/expose `select_contextual_regions_for_spans(speech_segments, clip_spans_ms, *, duration_ms, pad_ms=4000) -> tuple[SpeechSegment, ...]`.
   - Enforce `3000 <= pad_ms <= 5000`, call existing `_contextual_speech_regions(speech_segments)`, select deduplicated ordered regions overlapping any padded span `[max(0, in_ms - pad_ms), min(duration_ms, out_ms + pad_ms)]`.
   - Write AC1 & subset-idempotency unit tests first (`tests/test_clip_scoped_asr.py`), verify failure then implement.
2. **T2 — Isolated clip-ASR store + single-pass & batched `pipeline.py` refinement:**
   - Add `--clip-scoped-asr` and `--clip-asr-pad-ms` CLI options in `pipeline.py:4901+`, allowing `--transcript` + `--omni-asr` ONLY when `--clip-scoped-asr` is set (refuse invalid combinations before Stage 0).
   - Wire `clip_asr` refinement helper shared cleanly by single-clip (`run_pipeline`) and multi-clip (`_run_episode_delivery`) paths: batch all chosen candidate spans into one `canonical_asr.transcribe(...)` call, key `TranscriptStore(work_dir / "clip_asr" / "transcripts")` by deterministic region-slice digest + producer + `source_sha256` + `admission_policy`, re-run `segment_sentences(final_raw.words, vad_pauses=vad_pauses)`, remap/re-anchor the clip's complete sentences onto `[anchor_in, anchor_out]`/`fuse_boundary`, and record `clip_scoped_asr_{wall_s,regions,audio_ms}` in `PipelineRun.to_dict()`.
   - Also validate parity (`test_clip_scoped_caption_text_and_word_timings_match_whole_episode_run`) using a deterministic segment-level fake/echo `OmniSegmentBackend` across full-episode vs clip-scoped pipelines.
3. **T3 — ADR `D-340`, `PROGRESS.md` ledger, and real-media measurement (once WSL/CTC-3B/B3 or excerpt `--transcript` unblocked):**
   - Append `D-340` to `DECISIONS.md`.
   - Measure wall time & caption/word parity on `zar-ai-lamo__RO1PmSoqmCM__05m00-10m00.mp4` and the 40-min AI episode `RO1PmSoqmCM` on GPU 1 (`evidence/b2-clip-scoped-asr-YYYY-MM-DD.md`).

## 4. Explicit Owner Decisions / Prerequisites Required Before Implementation

1. **VEX & digest pin update:** Editing `src/hawedit/asr.py` and `src/hawedit/pipeline.py` changes `package_digest(src/hawedit)` (`a7b54139...`), which invalidates `security/wsl-asr-vex.json` and `tests/test_vex.py::REVIEWED_VEX_SOURCE` (or interacts with Lane 1's Phase A3 decision on parking heavy runtime controls). Confirm VEX re-pin / A3 sequencing before landing Round 2 code.
2. **WSL / CTC-3B readiness + draft source:** Running the real-media B2 wall-time measurement on `RO1PmSoqmCM` requires provisioning `wsl-asr` + `omniASR-CTC-3B-v2.pt`, pairing with B6 (`--no-validate-asr` or `rzgar` weights), and either supplying a draft `--transcript` or Phase B3.
