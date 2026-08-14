# The whole transcript was a visual query

Date: 2026-08-09
Decision: D-154
Scope: Stage 3 Path B query composition

## Measured failure

The 38-minute production run reached the composed visual path with no Path A candidate because no
Gemini route was configured. The fallback in `run_pipeline` was `normalized.text_ckb`, not a bounded
candidate slice:

| Measurement | Result |
|---|---:|
| Transcript characters | 35,185 |
| Transcript words | 6,104 |
| Reranker allocation request | 40.89 GiB |
| GPU capacity | 23.99 GiB |
| Stage 3 candidates produced before failure | 0 |

The same allocation and transcript measurements are preserved in
`evidence/the-rejection-set-had-no-producer.md`. The defect was composition authority: neither the
operator nor Path A had selected those 35,185 characters as one retrieval query.

## Implemented contract

`_visual_retrieval_query` has two and only two positive results:

1. normalize a nonblank explicit `visual_query` and report source `explicit`; or
2. choose the top ranked Path A candidate, use only aligned words overlapping that candidate's
   span, and report source `path_a:<candidate-id>`.

With neither, `run_pipeline` returns `visual_index: StageSkipped`, states that the whole episode was
refused because of the measured OOM, and never calls `VisualComposer.discover`. The CLI rejects
`--visual` without a query or configured Path A route before constructing the model adapters.

No token or character threshold was introduced. An operator can explicitly authorize a larger
query, which remains subject to the adapter's bounded operational-failure reporting; the pipeline
may no longer invent the episode-wide query silently.

## Executable evidence

- `test_path_b_refuses_the_whole_transcript_when_path_a_has_no_candidate` makes Path A fail,
  injects a composer that would raise if called, and proves its call count is zero. The report keeps
  both the Path A failure and Path B refusal and serializes `visual_query_source: null`.
- `test_composed_visual_path_uses_measured_fps_and_best_verbal_slice_as_query` proves the query is
  the top candidate's aligned Sorani text and reports `path_a:best`.
- `test_path_a_operational_failure_stays_visible_while_independent_visual_path_runs` proves an
  explicit query can still run Path B independently and reports source `explicit`.
- `test_the_cli_refuses_visual_without_a_bounded_query_source` covers absent and whitespace-only
  explicit queries before transcript/model acquisition.

Acceptance from the isolated readiness worktree, using the canonical Git Bash command
`scripts/verify.sh`: Ruff passed; mypy passed across 125 source files; all 125 files were formatted;
1,796/1,796 tests passed in 153.65 s with zero skips; the independent JUnit evidence check accepted
the same 1,796 collected/passed count; `VERIFY OK`.
