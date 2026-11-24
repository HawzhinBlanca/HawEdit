# Plan — C4 Topic-segmentation candidates

Read `research.md` first.

## Approach

Implement a clean-room, CPU-only, MIT TextTiling topic segmenter in `src/hawedit/topic_segmenter.py` that acts as a zero-API verbal candidate producer for Stage 3 alongside Path A (and C3 when implemented):

1. **Clean-room TextTiling module (`src/hawedit/topic_segmenter.py`):**
   - Zero AGPL code copied anywhere; zero new external dependencies (`math`, `re`, `dataclasses`, reusing `hawedit.normalize.normalize_sorani`, `hawedit.index.index_tokens`, `hawedit.index.character_ngrams`, `hawedit.sentences`, `hawedit.transcripts.assert_model_input`, `hawedit.discovery.Candidate`, `hawedit.clip.DiscoveryPath`).
   - Define `SentenceEmbedder` (`Protocol` with `embed(texts: Sequence[str]) -> tuple[tuple[float, ...], ...]` or L2-normalized sparse/dense vectors) plus default `SoraniTfIdfEmbedder` (IDF-weighted normalized word tokens + `DEFAULT_NGRAM_WEIGHT * character_ngrams(..., size=3)`).
   - Compute TextTiling block-similarity profile over complete sentences (`block_size: int = 3`, 3-tap smoothing `[0.25, 0.50, 0.25]`, Hearst 1997 depth scores `(hl - s) + (hr - s)`).
   - Split at topical valleys where `depth >= mean + alpha * std` (and recursively split segments exceeding `max_span_ms` at deepest internal gaps; greedily merge adjacent sub-segments `< min_span_ms` across shallowest depth valleys if union `<= max_span_ms`). Ignore/stop cleanly at `complete == False` sentences (`BLUEPRINT.md` §5).
   - Emit dense 1-based ranked `Candidate` objects (`candidate_id=f"{transcript.media_id}-topic-{rank}"`, `path=DiscoveryPath.VERBAL`, `score` in `[0.0, 1.0]`).
2. **Conflict-free verbal union (`src/hawedit/discovery.py`):**
   - Keep `DiscoveryPath` frozen at `{"verbal", "visual", "both"}` (`tests/test_clip.py:478`).
   - Add small helper `combine_verbal_candidates(*groups: Sequence[Candidate]) -> tuple[Candidate, ...]` (or merge in `pipeline.py`) that validates unique `candidate_id`s and offsets secondary groups' `rank` sequentially after earlier groups so `"topic-1"` cannot preempt `"verbal-1"` in `merge_candidates`'s `(c.rank, c.candidate_id)` tie-breaker (`discovery.py:221`), while `merge_candidates` still keeps 100% of unique candidates from every source.
3. **Pipeline opt-in / additive wiring (`src/hawedit/pipeline.py`):**
   - Add `topic_candidates: bool = False` (and optional `topic_segmenter` dependency injection) parameter + `--topic-candidates` CLI flag to `run_pipeline` / CLI parser (preserving existing default call behavior for tests expecting `_STAGE_3_NOTHING_FOUND` when no producer flags are passed, and allowing zero-API discovery when `--topic-candidates` is set — no console script added to `pyproject.toml`).
4. **Module ledger & doc alignment (`README.md`, `PROGRESS.md`, `DECISIONS.md`):**
   - Record ADR `D-345` in `DECISIONS.md`, register `topic_segmenter.py` in `README.md` module map and `PROGRESS.md` ledger row (`test_claims.py:730-745`).
5. **Teaser-overlap offline diagnostic:**
   - Once real transcripts (`cooking`/`ep54`) are available on disk from Lane 2, measure C4 candidate temporal overlap against the 33 gold source intervals in `evidence/teaser-gold-timestamps.md` (`cooking` 17 + `ep54` 16) and log in `evidence/`.

No new third-party dependencies.

## Files and symbols

| File | Symbol | Change |
|---|---|---|
| `src/hawedit/topic_segmenter.py` *(new)* | `SentenceEmbedder`, `SoraniTfIdfEmbedder`, `TextTilerConfig`, `discover_topics`, `text_tile_depths` | New clean-room MIT TextTiling candidate producer (CPU-only, zero API) |
| `src/hawedit/discovery.py` | `combine_verbal_candidates` *(new)* | Preserves unique IDs and explicit rank ordering when uniting Path A + C4 (+ C3) before `merge_candidates` (`:189`) |
| `src/hawedit/pipeline.py` | `run_pipeline` (`:2870`, `:3285-3360`), CLI parser (`_build_parser`) | Add `topic_candidates: bool = False` / `--topic-candidates` and unite C4 candidates cleanly with `discover` before `merge_candidates` (`:3355`) |
| `tests/test_topic_segmenter.py` *(new)* | AC1–AC6 tests | Deterministic unit & Sorani clitic tests covering all EARS criteria |
| `tests/test_pipeline.py` | `test_pipeline_discovers_topic_candidates_without_api` | End-to-end no-API discovery integration test |
| `README.md`, `PROGRESS.md`, `DECISIONS.md` | Module map row, ledger row, ADR `D-345` | Satisfy `test_claims.py` module accounting and document MIT TextTiling design choice |

## Divergence and ADR

- Implements `BLUEPRINT.md` §3 Stage 3 (additional additive verbal discovery candidate source) without touching `DiscoveryPath` (`{"verbal", "visual", "both"}`) and strictly preserving §4.1/§4.2/§5 invariants. Recorded in new ADR `D-345`.

## Risks & cross-lane notes

- **No silent fallback when Path A fails:** `topic_candidates` runs cleanly as an explicit/additive verbal source; if `discover` (Path A) was requested and failed (`discovery_skipped`), Stage 3 must still report `discovery_skipped` rather than hiding Path A's operational refusal behind C4 results!
- **Module map & VEX pins:** Adding `src/hawedit/topic_segmenter.py` trips both `tests/test_claims.py::test_the_module_map_covers_every_module` / `test_the_ledger_accounts_for_every_module` (resolved by editing `README.md` + `PROGRESS.md` in the same Round 2 PR) and `tests/test_vex.py` `package_digest(src/hawedit)` (resolved by A3 VEX parking or owner re-pin).
- **Zero-API discovery expectations in existing `pipeline.py` tests:** Default `topic_candidates=False` avoids unexpectedly altering existing `tests/test_pipeline.py` tests that assert `_STAGE_3_NOTHING_FOUND` when running with only a stand-in transcript and no Gemini key. Once validated on `cooking`/`ep54` ASR transcripts, owner can decide whether to flip default to `True`.

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"
