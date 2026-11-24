# Impact map — C4 Topic-segmentation candidates

Serena MCP was unavailable in this session, so callers were mapped with `rg -n` over `src/` and `tests/`. Re-run `find_referencing_symbols` before implementation if Serena becomes available.

| Symbol touched / reused | Callers / dependents in `src/` | Tests covering them |
|---|---|---|
| `src/hawedit/index.py`: `index_tokens` (`:76`), `character_ngrams` (`:83`), `DEFAULT_NGRAM_SIZE` (`:56`), `DEFAULT_NGRAM_WEIGHT` (`:61`) — **reused read-only** | `Bm25Index` (`index.py`); read-only import in new `topic_segmenter.py` | `tests/test_index.py` |
| `src/hawedit/sentences.py`: `Sentence`, `segment_sentences` (`:155`), `anchors_for` (`:210`) — **reused read-only** | `pipeline.py:211, 1462, 3251`, `assembly.py:28` | `tests/test_sentences.py`, `tests/test_pipeline.py`, `tests/test_assembly.py` |
| `src/hawedit/clip.py`: `DiscoveryPath` (`:108-113`), `MIN_CANDIDATE_SPAN_MS` (`30_000`), `MAX_CANDIDATE_SPAN_MS` (`90_000`) — **reused unchanged** | `discovery.py`, `pipeline.py:97`, `repurposing.py` | `tests/test_clip.py:478` (asserts exact 3-member enum `{verbal, visual, both}`) |
| `src/hawedit/discovery.py`: `Candidate` (`:70-108`), `merge_candidates` (`:189-245`) + new `combine_verbal_candidates` | `pipeline.py:3355`, `path_a.py:262, 381`, `visual_pipeline.py` | `tests/test_discovery.py`, `tests/test_repurposing.py`, `tests/test_pipeline.py` |
| `src/hawedit/pipeline.py`: `run_pipeline` (`:2870`), Stage 3 block (`:3285-3360`), `_build_parser` CLI | `pipeline.py` CLI `main()`, `workflow_control.py`, `web.py` | `tests/test_pipeline.py`, `tests/test_workflow_control.py` |
| `src/hawedit/topic_segmenter.py` *(new module)* | `pipeline.py` Stage 3 (`:3289`) | New `tests/test_topic_segmenter.py`, `tests/test_pipeline.py` |
| `README.md` (`:613-650`), `PROGRESS.md` | Checked by `tests/test_claims.py:496-505, 730-745` | `test_the_module_map_covers_every_module`, `test_the_ledger_accounts_for_every_module` |

## Findings

- **`DiscoveryPath` cannot gain a `"topic"` member without breaking `BLUEPRINT.md` §5 and `tests/test_clip.py:478`:** Keeping `DiscoveryPath.VERBAL` with explicit `candidate_id` prefix `"{media_id}-topic-{rank}"` preserves §5's frozen three-path contract and `merge_candidates` union invariants while keeping C4 outputs clearly identifiable in `MergedCandidate.sources` and `report.json`.
- **Rank precedence inside `merge_candidates` (`discovery.py:221`):** Both Path A and C4 emit `DiscoveryPath.VERBAL`. Because `merge_candidates` sorts verbal anchors by `(c.rank, c.candidate_id)` and `"topic"` sorts lexicographically before `"verbal"`, merging Path A + C4 via `combine_verbal_candidates` offsets C4 ranks past Path A's ranks when both run, preventing C4 from stealing visual partner pairing from Path A rank #1.
- **`discovery_skipped` truthfulness (`pipeline.py:3302-3359`):** If `--gemini` Path A was requested and failed operationally, Stage 3 MUST still populate `discovery_skipped` even if C4 topic candidates succeeded, ensuring operational failure is never masked.
- **No `pyproject.toml` `[project.scripts]` change:** Respects the 16-script cap audited in `AUDIT_REPORT.md` / `tests/test_claims.py`.
- **`assembly.py` compatibility:** C4 emits contiguous complete-sentence spans inside `[30_000, 90_000]` ms where possible, feeding cleanly into `_judgeable_plans` (`pipeline.py:1426`) and `AssemblySpan` (`assembly.py:44`).
