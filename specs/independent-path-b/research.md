# Research — independent-path-b (T4.2)

Parent task: `specs/pro-grade-program/tasks.md` row `T4.2` (`Path B as independent discovery`).
Blueprint specification: `BLUEPRINT.md` §3 (Dual-Path Discovery), §8.2 (Path Recall).

## Context & Background

In `BLUEPRINT.md` §3:
> "Neither path filters the other: Path A proposes shippable narrative arcs from speech, Path B proposes visually compelling scenes from frames. Their union is the candidate pool."

In the initial implementation of Path B query scoping (D-154), the pipeline prevented an out-of-memory failure on the 38-minute episode caused by using the entire 35,185-character transcript as a visual query. To bound the query, D-154 fell back to the words of Path A's rank-1 candidate:
`best = min(verbal, key=lambda item: (item.rank, item.candidate_id), default=None)`
`query = _candidate_slice_text(transcript, best.in_ms, best.out_ms)`
`visual_query_source = f"path_a:{best.candidate_id}"`

This created two critical architectural defects identified in `specs/pro-grade-program/research.md` §6:
1. **Path Coupling**: Path B could only run if Path A succeeded and yielded at least one candidate, or if the operator supplied `--visual-query` manually.
2. **Visual Echo**: When Path A ran, Path B was searching for scenes matching Path A's verbal transcript slice. Consequently, Path B was biased toward illustrating Path A's spoken topic, rather than discovering independent non-verbal moments (laughter, reactions, gestures, action) that Path A's transcript analysis missed.

## Target Symbols & Call Sites

### 1. `src/hawedit/pipeline.py`
- `DEFAULT_NONVERBAL_VISUAL_QUERY`:
  New constant defining the canonical fixed Sorani query set for non-verbal beats per T4.2:
  `"پێکەنین، کاردانەوە، سەرسوڕمان، جووڵە"` (Laughter, reaction, surprise, movement/gestures).
  Normalized via `normalize_sorani`.
- `_visual_retrieval_query`:
  Lines 1407–1432:
  Signature updated to support `seed_path_a: bool = False`.
  - When `explicit` query is provided: returns `(normalize_sorani(explicit), "explicit")`.
  - When `seed_path_a` is True: falls back to top verbal candidate words if available, else `None`.
  - When `explicit` is None and `seed_path_a` is False (the default under T4.2): returns `(DEFAULT_NONVERBAL_VISUAL_QUERY, "default:nonverbal")`.
- `run_pipeline`:
  Lines 1967–2015:
  - Accepts `visual_seed_path_a: bool = False`.
  - Passes `seed_path_a=visual_seed_path_a` to `_visual_retrieval_query`.
  - Independent Path B executes retrieval even when Path A is absent or failed.
  - Merges Path A and Path B candidates via `merge_candidates`.
  - Computes and logs `by_path` breakdown and "found by B only" (`visual` count).
- CLI Argument Parsing (`_build_argument_parser` / validation):
  - Add `--visual-seed-path-a` option (default `False`).
  - `--visual` without Path A and without `--visual-query` is now valid (it uses `DEFAULT_NONVERBAL_VISUAL_QUERY`).
  - `stage_3_can_produce = bool(args.gemini or args.vertex_project) or bool(args.visual)` enables `--auto-select` to run with `--visual` alone.

### 2. `src/hawedit/discovery.py`
- `merge_candidates`:
  Lines 187–278 already preserves `discovery_path` as `VERBAL`, `VISUAL`, or `BOTH`.
  Candidates discovered by Path B only have `discovery_path == DiscoveryPath.VISUAL`.

### 3. Tests to Add & Update
- `tests/test_pipeline.py`:
  - `test_path_b_runs_without_a_path_a_seed`:
    Proves Path B runs independently with `DEFAULT_NONVERBAL_VISUAL_QUERY` when no explicit query and no Path A candidate exist, producing `DiscoveryPath.VISUAL` candidates and `visual_query_source="default:nonverbal"`.
  - Update `test_path_b_refuses_the_whole_transcript_when_path_a_has_no_candidate` to pass `visual_seed_path_a=True`, verifying the explicit opt-in seed behavior preserves D-154's refusal.
  - `test_the_cli_accepts_visual_without_path_a_using_default_nonverbal_query`:
    Proves CLI accepts `--visual --auto-select` without `--visual-query` or `--gemini`.
