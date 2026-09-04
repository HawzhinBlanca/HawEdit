# Plan — Episode Plan: N Clips Per Run (Task T4.1)

## Architecture & Implementation Steps

1. **`src/hawedit/episode.py`**:
   - `compute_text_similarity(text_a: str, text_b: str) -> float`: computes Jaccard word similarity over normalized Sorani words (stripping Kurdish punctuation and whitespace).
   - `EpisodePlanConfig`:
     - `max_clips: int = 3`
     - `min_separation_ms: int = 15_000`
     - `max_text_similarity: float = 0.50`
     - `cost_cap_usd: float | None = None`
   - `select_episode_plan(candidates: Sequence[tuple[MergedCandidate, tuple[int, ...], JudgeVerdict]], config: EpisodePlanConfig, normalized_transcript: NormalizedTranscript) -> list[tuple[MergedCandidate, tuple[int, ...], JudgeVerdict]]`:
     - Ranks shippable candidates by composite editorial score (`hook_score`, `payoff_strength`, `ends_on_a_beat`, `visual_variety`).
     - Greedily selects up to `max_clips` candidates.
     - Rejects any candidate with temporal overlap ($[A_0, A_1] \cap [B_0, B_1] \neq \emptyset$) or separation $< \text{min\_separation\_ms}$.
     - Rejects any candidate with `compute_text_similarity > max_text_similarity`.
     - Tracks estimated cost and stops if `cost_cap_usd` is reached.
   - `EpisodeClipSummary`:
     - `clip_id: str`
     - `in_ms: int`
     - `out_ms: int`
     - `duration_ms: int`
     - `hook_score: float`
     - `hook_type: str | None`
     - `title_ckb: str`
     - `title_variants_ckb: tuple[str, ...]`
     - `cover_frame_ms: int | None`
     - `delivery_dir: str`
   - `EpisodeManifest`:
     - `episode_id: str`
     - `media_id: str`
     - `media_sha256: str`
     - `clips_count: int`
     - `total_duration_ms: int`
     - `clips: tuple[EpisodeClipSummary, ...]`
     - `reconciled: bool`
     - `to_dict()`, `from_dict()`, `write_json(path)`
   - `reconcile_episode_manifest(manifest: EpisodeManifest, base_dir: Path) -> None`:
     - Clause 12: checks each clip directory contains required sidecars (`.mp4`, `.ass`, `.srt`, `.edl`, `.json`, `.measured.json`, `.cover.png`).
     - Checks that no two clips overlap in time.
     - Raises `EpisodeReconciliationError` on any mismatch.

2. **Tests in `tests/test_episode.py`**:
   - Test text similarity on Kurdish words.
   - Test temporal non-overlap and minimum separation.
   - Test lexical diversity filtering.
   - Test cost cap enforcement.
   - Test manifest serialization and round-trip.
   - Test episode manifest reconciliation with valid and corrupted delivery directories.

Approved-by: Hawa
