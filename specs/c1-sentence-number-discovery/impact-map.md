# Impact map — C1 Sentence-number discovery

Serena MCP was unavailable in this session (`list_resources` / symbol tools not exposed), so callers were mapped with `rg -n` over `src/` and `tests/`. Re-run `find_referencing_symbols` before implementation if Serena becomes available.

| Symbol touched | Callers in `src/` | Tests covering them |
|---|---|---|
| `CANDIDATE_SCHEMA` (`src/hawedit/path_a.py:70-88`) | `PathADiscovery._discover_single` (`path_a.py:300`) | `tests/test_path_a.py:42` |
| `_timing_table` (`src/hawedit/path_a.py:120-132`, **deleted**) | `PathADiscovery._prompt` (`path_a.py:195`) | `tests/test_path_a.py:120, 147` (asserts `"0-900" in api.prompt` — must be updated to check numbered sentence lines `[0]` and non-truncation) |
| `PathADiscovery` (`src/hawedit/path_a.py:135-391`) | `src/hawedit/pipeline.py:3289` (`verbal = tuple(discover(normalized))`), `:5497, 5514` (`PathADiscovery(client=judge)`); `src/hawedit/smoke.py:31, 132, 144` | `tests/test_path_a.py:103-390`, `tests/test_review_findings.py:212, 681, 694`, `tests/test_smoke.py:36, 56, 87, 101, 111`, `tests/test_pipeline.py` (all tests supplying fake `discover=`) |
| `discover_verbal` (`src/hawedit/path_a.py:394-400`) | None in `src/` (public convenience API) | `tests/test_path_a.py:42, 359` |
| `segment_sentences`, `anchors_for` (`src/hawedit/sentences.py:155, 210` — **read-only consumer**) | `pipeline.py:211, 3251`; `_judgeable_plans` (`pipeline.py:1462`) | `tests/test_sentences.py`, `tests/test_pipeline.py` |
| `AssemblySpan`, `assemble_spans` (`src/hawedit/assembly.py:44, 86` — **downstream check**) | `pipeline.py:57, 1335, 1551` | `tests/test_assembly.py`, `tests/test_pipeline.py:6414` |
| `run_pipeline` (`src/hawedit/pipeline.py:2870, 3289`) | `pipeline.py:5514` (CLI), `episode.py` (downstream), tests | `tests/test_pipeline.py`, `tests/test_episode.py` |

## Findings

- **Custom `discover` callables in tests:** `run_pipeline(..., discover=...)` is injected in `tests/test_pipeline.py` with lambdas/functions taking one positional arg `(normalized: NormalizedTranscript)`. `pipeline.py:3289` must only pass `sentences=sentences` when `discover` accepts it (or bind via `PathADiscovery.discover` keyword support), so single-arg test doubles do not break with `TypeError`.
- **Fixture & `words` alignment assumptions in `tests/test_path_a.py`:** `a_transcript()` in `test_path_a.py` must produce valid complete `Sentence`s from `words` (including sentence-final punctuation or >= 500 ms pauses) so `_to_candidates` resolves valid `(start_ms, end_ms)` pairs cleanly.
- **`assembly.py` impact:** None directly — `Candidate` continues to carry exact `(in_ms, out_ms)` integers and `.span`, now guaranteed to start and end on complete `Sentence` boundaries. `AssemblySpan.__post_init__` (`assembly.py:53-64`) requires non-empty complete `Sentence` tuples, which C1 now guarantees earlier at Stage 3.
- **Documentation & gate constraints (`tests/test_claims.py`, `tests/test_vex.py`):**
  - No new module file is created (`path_a.py` modified in-place), so `README.md` module map (`test_claims.py:730`) and `pyproject.toml` `[project.scripts]` are unaffected.
  - Modifying `src/hawedit/path_a.py` / `pipeline.py` changes `package_digest(src/hawedit)` tested by `tests/test_vex.py` (`security/wsl-asr-vex.json`), requiring either A3 VEX parking or owner re-pin to clear full gate.
  - `DECISIONS.md` gets new ADR `D-344` (within Lane 3's assigned range `D-344..D-347`).
