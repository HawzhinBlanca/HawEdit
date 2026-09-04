# Research — Episode Plan: N Clips Per Run (Task T4.1)

## Context & Problem Statement
Currently, `run_pipeline` in `src/hawedit/pipeline.py` selects exactly one winner clip (`winner, winning_run, verdict = max(shippable, key=_shippable_sort_key)`). In real-world social media operations (e.g. producing viral TikTok / Instagram reels from a 40-minute Kurdish podcast like episode 29), a content team ships 3 to 10 distinct clips per long-form episode, not just one.

Simply running the pipeline $N$ times independently from scratch is prohibitive:
1. Re-running Stage 0 (ingest, audio extraction, scene detection, diarization) and Stage 1 (OmniASR transcription, forced alignment) takes 5–15 minutes per run.
2. Independent runs have no awareness of each other, risking redundant clips covering overlapping speech spans or the same talking point.

## Specification Requirements (§ BLUEPRINT.md & Task T4.1)
Task T4.1 establishes:
- **Shared Ingest & Discovery**: Stages 0–2 run once; Stage 3 Path A and Path B discover candidates across the entire episode.
- **Budget / Cost Cap**: Judge candidates up to a per-episode budget or top-$K$ limit.
- **Diversity Constraints**:
  1. **Zero Temporal Overlap**: No two clips share any time interval.
  2. **Minimum Separation (`MIN_SEPARATION_MS`)**: Enforce at least 15,000 ms (15 s) between adjacent clips, preventing clipped runs that abut without breathing room.
  3. **Topic / Lexical Diversity**: Lexical overlap (Jaccard / BM25 over normalized Sorani vocabulary words) must not exceed threshold (0.50), preventing two clips from repeating the same talking points or punchlines.
  4. **Speaker Diversity**: When diarization is available, prioritize clips from different speakers where possible.
- **Deliverables**:
  - Independent delivery bundle per clip (`clip_id.mp4`, `.ass`, `.srt`, `.edl`, `.json`, `.measured.json`, `.cover.png`).
  - Consolidated `episode.json` manifest listing all delivered clips, ranked by score, with total run cost and reconciliation proofs.
  - Manifest reconciliation: verify all $N$ clips exist, durations match, and zero overlap.

## Architectural Seam
We introduce `src/hawedit/episode.py` owning:
1. `EpisodePlanConfig`: parameters ($N$, `min_separation_ms`, `max_text_similarity`, `cost_cap_usd`).
2. `select_episode_plan`: greedy diverse candidate selector with strict non-overlap, separation, and lexical diversity guards.
3. `EpisodeManifest` & `EpisodeClipSummary`: dataclasses with serialization.
4. `reconcile_episode_manifest`: verifies that all clips in the manifest are present on disk and satisfy mutual non-overlap.
