# Impact Map: A7 — Usable-Rate Scoreboard (`evidence/usable-rate.csv`)

> **Discovery method note:** Serena MCP is unavailable in this environment; all symbol definitions, callers, and file references below were mapped via regex/text grep across `src/`, `tests/`, `scripts/`, and root markdown docs.

## 1. Caller & Dependency Analysis

| Target / Existing Symbol | Exact Location | Relationship to A7 | Impact / Required Action |
|---|---|---|---|
| `validate_evidence_header`, `test_new_evidence_names_its_commit_media_and_host` | `tests/test_claims.py:212, 266-308` | Globs `evidence/*.md` after `_EVIDENCE_CUTOFF` (`2026-09-02T23:59:59+03:00`) | `evidence/usable-rate.csv` is `.csv`, not `.md`, so unchanged checks pass. Any future F3 `.md` summary in `evidence/` MUST include `commit`, `media_sha256`, `host`, `command`. |
| `test_every_module_the_readme_maps_exists`, `test_the_module_map_covers_every_module` | `tests/test_claims.py:496-505` | Enforces 1:1 mapping of `src/hawedit/*.py` in `README.md` (`L580-752`) | Adding `src/hawedit/usable_rate.py` in Round 2 requires adding a table row in `README.md`. |
| `test_the_ledger_accounts_for_every_module` | `tests/test_claims.py:730-745` | Enforces every `src/hawedit/*.py` is accounted for in `PROGRESS.md` (`L1250-1314`) | Adding `src/hawedit/usable_rate.py` in Round 2 requires adding a `PROGRESS.md` row. |
| `test_the_audit_report_names_every_console_script_and_no_others` (+ count check) | `tests/test_claims.py:1363-1406, 1655-1668` | Asserts `pyproject.toml` `[project.scripts]` stays at the documented 16 entries | **No impact** because A7 exposes `python -m hawedit.usable_rate` instead of adding a 17th script entry. |
| `test_every_value_the_decision_log_states_is_the_value_the_code_holds` | `tests/test_claims.py:883-940` | Resolves `` `NAME = value` `` expressions in `DECISIONS.md` against `hawedit.*` | Ensure any constants cited in future `DECISIONS.md` entry (if `D-352` is added) match exact names/values in `hawedit.usable_rate`. |
| `REVIEWED_VEX_SOURCE` & `package_digest` check | `tests/test_vex.py:27-30, 140-163` | Hashes all `.py` files under `src/hawedit/` | Adding `src/hawedit/usable_rate.py` invalidates the pinned digest until A3 parks VEX or owner re-pins VEX. |
| `use_utf8_streams`, `program_name` | `src/hawedit/cli.py:1-82` | Existing CLI UTF-8 helper | Reused by `hawedit.usable_rate.main()` (read-only dependency; no change to `cli.py`). |
| `wilson_score_interval` | `src/hawedit/comparison_kit.py:1-300` | Existing statistical helper | Reused by `summarize_usable_rate()` (read-only dependency; no change to `comparison_kit.py`). |
| `run_pipeline`, `_run_episode_delivery` | `src/hawedit/pipeline.py:2050-2950, 3800-4730` | Main orchestration | **Unchanged** by A7 (human review ratings happen post-render via CLI). |
| Living docs | `DECISIONS.md` (`L16341-16660`), `PROGRESS.md` (`L1250-1314`), `BLOCKED.md` (tail `#24`–`#26`) | Shared governance docs | No edits in Round 1. In Round 2 coordinate `README.md` + `PROGRESS.md` edits at merge time; next free blocker (not needed here) is `#27`. |

## 2. Blast Radius Summary
- **Runtime pipeline blast radius:** Zero — `pipeline.py`, `delivery.py`, `render.py`, `captions.py`, and GPU paths are untouched.
- **Test/gate blast radius:** Touches `tests/test_claims.py` invariants (`README.md` + `PROGRESS.md` module accounting) and `tests/test_vex.py` package hash upon adding `src/hawedit/usable_rate.py`. Both are deterministic and explicitly tracked in `tasks.md`.
