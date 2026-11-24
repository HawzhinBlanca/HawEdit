# Research — C4 Topic-segmentation candidates (`c4-topic-segmentation-candidates`)

Date: 2026-11-18. Worktree: `HawEdit-lane-3` (`gemini/lane-3`, commit `1714a8b`). Host: `HAWAPC01` (`Windows-11-10.0.26300-SP0`), `.venv` Python `3.12.10`. Serena MCP was unavailable in this session's toolset, so all definitions and callers were mapped with `rg -n` over `src/` and `tests/`.

## Goal and Constraints (C4)

`specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` §3 C4 specifies:
> **C4 A no-API candidate source.** Topic segmentation over sentence embeddings (the ClipsAI `texttiler.py` method, MIT). Merge candidates from C3, the transcript judge and C4.

Mandatory constraints from project governance and task sheet:
1. **Zero AGPL code copied.** ClipsAI (`texttiler.py`) is referenced for the classical **Hearst (1997) TextTiling** block-similarity + depth-score method (which `texttiler.py` itself distributes under MIT, while AGPL components exist in other clip tools). All code in HawEdit must be written clean-room from first principles against `BLUEPRINT.md` and `hawedit` types — never copied from AGPL projects.
2. **Zero external API calls and zero GPU requirement.** Must run deterministically offline on CPU using normalized Sorani transcripts (`NormalizedTranscript`) and `Sentence` spans (`hawedit.sentences`).
3. **Kurdish invariants & contract compatibility:**
   - **Invariant #3 (`transcripts.py`):** Embedder and topic segmenter consume `NormalizedTranscript` / `assert_model_input(transcript)` and normalize each `Sentence.text` via `normalize_sorani` (`hawedit.normalize`) — never raw ASR strings.
   - **Invariant #2 (`sentences.py`, `BLUEPRINT.md` §5):** Every topic segment consists of a contiguous span of **complete** sentences `[start_idx..end_idx]` bounded cleanly by CTC timestamps `(sentences[i].start_ms, sentences[j].end_ms)` (skipping/not terminating inside `complete == False` fragments).
   - **`DiscoveryPath` contract (`clip.py:108-113`, `tests/test_clip.py:478`):** `DiscoveryPath` MUST remain `{"verbal", "visual", "both"}` (only 3 members). Topic candidates are transcript-derived verbal proposals, so they emit `Candidate(..., path=DiscoveryPath.VERBAL, candidate_id=f"{media_id}-topic-{rank}", rank=rank, score=depth_score)`.
   - **`merge_candidates` rank tie-break (`discovery.py:221`):** `merge_candidates` sorts verbal candidates by `(c.rank, c.candidate_id)` before claiming visual partners. Because `"topic" < "verbal"` alphabetically, combining Path A (`...-verbal-1`) and C4 (`...-topic-1`) both at `rank=1` would let C4 out-tie Path A. Combining verbal sources must preserve dense per-producer standalone ranks when run alone AND rank-offset or order primary verbal proposals cleanly when merged with Path A (while dropping nothing).

## Algorithm Design: Clean-Room TextTiling over Sorani Sentence Embeddings

Following Hearst (1997) TextTiling over sentence embeddings (same mathematical family as MIT TextTiling, zero copied code):

1. **Sentence representation & Sorani embedder (`SentenceEmbedder` Protocol):**
   - Expose a pluggable `SentenceEmbedder` Protocol (`embed(sentences: Sequence[str]) -> list[list[float]]`, L2-normalized dense or sparse cosine-comparable vectors) so future local dense models can drop in behind §7 if approved, while shipping a fast, zero-dependency, CPU-only default `SoraniTfIdfEmbedder` reusing `hawedit.index.index_tokens` (`index.py:76`) and `hawedit.index.character_ngrams` (`index.py:83`, `DEFAULT_NGRAM_SIZE=3`, `DEFAULT_NGRAM_WEIGHT=0.5`, matching `D-016`!).
   - Reusing `index_tokens` + boundary-padded character 3-grams gives morphological sensitivity for Sorani clitics (`کتێب` vs `کتێبەکەم`) with sub-millisecond runtime on CPU (~200–1,500 sentences per episode) and zero model downloads or non-MIT/AGPL dependencies.
2. **Sliding block similarity & TextTiling depth scoring:**
   - Given `N` complete contiguous sentences (indices `0..N-1`) and block size `k` sentences (default `k = 3`, configurable), at every candidate gap `i` between sentence `i` and `i+1`:
     - Left block vector `L_i` = mean embedding of `[max(0, i - k + 1) .. i]` (L2-normalized).
     - Right block vector `R_i` = mean embedding of `[i + 1 .. min(N - 1, i + k)]` (L2-normalized).
     - Lexical/semantic similarity `s_i = cosine(L_i, R_i)` in `[-1.0, 1.0]`, optionally smoothed once over a 3-point window (`[0.25, 0.50, 0.25]`) to suppress single-sentence noise.
   - **Depth score `d_i` (Hearst 1997):**
     `d_i = (hl_i - s_i) + (hr_i - s_i)`, where `hl_i` is the monotonically non-decreasing left peak moving left from `i`, and `hr_i` is the monotonically non-decreasing right peak moving right from `i`. Higher `d_i` means a deeper topical valley between coherent neighboring blocks.
   - Select natural topic boundaries where `d_i > mean(d) + alpha * std(d)` (fallback threshold `0` positive depths when `std == 0` on tiny transcripts, or deterministic peak-picking) producing disjoint candidate topic intervals over sentences.
3. **Duration bounds for social clips (`[MIN_CANDIDATE_SPAN_MS, MAX_CANDIDATE_SPAN_MS]` = `30_000..90_000 ms`, `D-254`):**
   - TextTiling raw topic segments on 1-hour podcasts can span 2–5 minutes (too long for a 30–90 s reel) or 8 seconds (too short, violating `D-254`'s 30 s floor).
   - Post-segmentation span shaping strictly along sentence boundaries:
     - **Split over-long segments (`> max_span_ms`):** Greedily split at the highest internal TextTiling depth gap `i` whose resulting sides stay >= `min_span_ms` (or deepest internal valley >= half `min_span_ms` if needed, stopping if indivisible single sentences already exceed `max_span_ms`, matching `D-254` line 13364!).
     - **Merge under-short segments (`< min_span_ms`):** Merge adjacent segments across the *shallowest* intervening depth valley `d_i` when the combined span fits `<= max_span_ms` (or up to `min_span_ms + single_sentence_slack` only if no smaller boundary exists, dropping residual `< min_span_ms` segments that cannot reach `min_span_ms` rather than emitting sub-30 s fragments!).
   - Score each valid candidate segment in `[0.0, 1.0]` deterministically from flanking boundary depths + internal block cohesion (`min(1.0, max(0.0, ...))`), rank densely `1..M` by `(-score, in_ms)` for `§8.2` `Recall@K`.

## Baseline Evaluation Plan Using Opening Teasers

Per owner instruction: *"Use the teasers that open each episode (README) as a first check: do selected moments overlap the human editor's picks? Mark the teaser source times by hand before scoring."*
- `evidence/teaser-gold-timestamps.md` provides **33 verified gold human-editor teaser regions** (`cooking`: 17 source regions, `ep54`: 16 source regions; plus notes why `ai` `0..14.04 s` is not spliced teaser material).
- Once ASR transcripts exist for `cooking` and `ep54` (Lane 2), `C4` runs strictly CPU-only over each normalized transcript (`0` Gemini cost, `< 1 s`) and measures temporal overlap (`Recall@K`, IoU >= 0.3 / any overlap against those 17 + 16 teaser source spans) into a new `evidence/` report before threshold tuning.

## Existing Repo Accounting Note

`tests/test_claims.py:496-505, 730-745` requires **every** module under `src/hawedit/*.py` to appear in `README.md`'s module table (`test_the_module_map_covers_every_module`) and in a `PROGRESS.md` ledger row (`test_the_ledger_accounts_for_every_module`). Also `pyproject.toml` `[project.scripts]` is capped at 16 scripts (`AUDIT_REPORT.md`). Therefore `src/hawedit/topic_segmenter.py` will add NO console script entry point (usable via `python -m hawedit.pipeline --topic-candidates`), and Round 2 will update `README.md` + `PROGRESS.md` together with the module.

References: `BLUEPRINT.md` §2, §3 Stage 3, §4.1, §4.2, §5, §8.2; `DECISIONS.md` `D-016`, `D-029`, `D-254`; `specs/pro-grade-program/gemini-task-sheet-2026-11-18.md` C4; `evidence/teaser-gold-timestamps.md`.
