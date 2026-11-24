# Tasks: A7 — Usable-Rate Scoreboard (`evidence/usable-rate.csv`) & F3 Tally CLI

## Round 1 (Spec Commit)
- [x] T0.1 Audit `evidence/`, `tests/test_claims.py`, `tests/test_vex.py`, `pyproject.toml`, `cli.py`, and `comparison_kit.py`.
- [x] T0.2 Author `research.md`, `spec.md`, `plan.md`, `impact-map.md`, and `tasks.md`.

## Round 2 (Implemented on `gemini/lane-5` — Ledgers Flipped by Lead `update-ledger.sh`)
- [x] T1 (`A7-R1`..`A7-R6`): Create `tests/test_usable_rate.py` covering CSV schema, verdict normalization/rejection, non-empty reason enforcement, SHA-256 + commit provenance, duplicate protection, summary/Wilson CI math, UTF-8 CLI roundtrip, and `evidence/usable-rate.csv` compatibility.
- [x] T2 (`A7-R1`..`A7-R5`): Implement `src/hawedit/usable_rate.py` reusing `cli.use_utf8_streams()` and `comparison_kit.wilson_score_interval()`, with `add` and `summary` subcommands on `python -m hawedit.usable_rate`.
- [x] T3 (`A7-R6`): Create initial header-only `evidence/usable-rate.csv` (`episode,reel,verdict,reason,reel_sha256,commit,recorded_at`).
- [x] T4 (Docs): Add `usable_rate.py` row to `README.md`, `PROGRESS.md` (`M9.40`), and `DECISIONS.md` (`D-352`), keeping `tests/test_claims.py` green.

## Phase F3 (Follow-on Once Real Reels Exist)
- [ ] T5 (F3 Rollup): Record verdicts for the 15 Zar Podcast test reels via `python -m hawedit.usable_rate add ...` and emit a `tests/test_claims.py`-compliant Phase F3 evidence summary.
