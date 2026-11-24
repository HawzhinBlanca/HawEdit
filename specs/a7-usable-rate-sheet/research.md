# Research: A7 — Usable-Rate Scoreboard (`evidence/usable-rate.csv`) & F3 Tally CLI

## 1. Goal & Scope
Phase A7 (`specs/pro-grade-program/gemini-task-sheet-2026-11-18.md`) calls for:
1. `evidence/usable-rate.csv` tracking reel-level review verdicts against the OpusClip `62%` baseline (`0.62`) and the HawEdit `80%` target (`0.80`).
2. A one-command CLI to record a reel's verdict and compute/report the usable-rate summary for Phase F3 (`15` test reels across the 3 Zar Podcast sources).

Round 1 scope is **research + specification/planning only** (`AGENTS.md` §Workflow 1–2). No files in `src/hawedit/**`, `tests/**`, root living docs, or `evidence/usable-rate.csv` are modified in Round 1.

## 2. Audit of `evidence/` and `tests/test_claims.py`

### 2.1 How `tests/test_claims.py` inspects `evidence/`
Grep and inspection of `tests/test_claims.py` (`L212`, `L266-308`):
- `_EVIDENCE_CUTOFF = "2026-09-02T23:59:59+03:00"` (`tests/test_claims.py:212`).
- `test_new_evidence_names_its_commit_media_and_host()` (`tests/test_claims.py:296-308`) iterates strictly over `evidence_dir.glob("*.md")`.
- For every `evidence/*.md` report dated after `_EVIDENCE_CUTOFF`, `validate_evidence_header()` (`tests/test_claims.py:266-293`) asserts the presence and validity of:
  - `commit` (git commit hash),
  - `media_sha256` (exact SHA-256 of the input media),
  - `host` (e.g., `HawaPC01`),
  - `command` (exact command invoked).
- **Finding:** Placing `evidence/usable-rate.csv` in `evidence/` does **not** trip `test_new_evidence_names_its_commit_media_and_host()` because the test globs `*.md` only. However, any companion Phase F3 markdown summary placed in `evidence/*.md` **must** carry a valid `validate_evidence_header()` header naming `commit`, `media_sha256`, `host`, and `command`.

### 2.2 Other `tests/test_claims.py` structural invariants affecting A7
Inspection of `tests/test_claims.py` identified four repository-wide checks that constrain how A7 exposes its CLI and module:
1. **Console script count cap (`tests/test_claims.py:1363-1406`, `L1655-1668`):**
   - `test_the_audit_report_names_every_console_script_and_no_others`, `test_the_audit_report_states_how_many_console_scripts_there_are`, and `test_audit_report_names_every_declared_console_script_exactly_once` cross-check `pyproject.toml` `[project.scripts]` against `AUDIT_REPORT.md` (currently 16 console scripts; `_NUMBER_WORDS` stops at 16).
   - **Constraint:** Do **not** add a 17th `[project.scripts]` entry in `pyproject.toml`. Use `python -m hawedit.usable_rate` (matching `python -m hawedit.pipeline`, `python -m hawedit.models`, `python -m hawedit.measure`), which provides a true one-command CLI without altering `[project.scripts]` or `AUDIT_REPORT.md`.
2. **README module map (`tests/test_claims.py:496-505`):**
   - `test_every_module_the_readme_maps_exists` and `test_the_module_map_covers_every_module` verify 1:1 parity between `src/hawedit/*.py` (excluding `__init__.py`) and rows matching ``^\| `(\w+\.py)` \|`` in `README.md`.
   - **Constraint:** Adding `src/hawedit/usable_rate.py` in Round 2 requires adding its row to `README.md`.
3. **PROGRESS ledger module coverage (`tests/test_claims.py:730-745`):**
   - `test_the_ledger_accounts_for_every_module` verifies every `src/hawedit/*.py` (excluding `__init__.py`) is named in a ``| Mx.y | ... | STATUS | evidence |`` row in `PROGRESS.md`.
   - **Constraint:** Adding `src/hawedit/usable_rate.py` in Round 2 requires a corresponding `PROGRESS.md` row via `scripts/update-ledger.sh` or approved ledger integration.
4. **`DECISIONS.md` value binding (`tests/test_claims.py:883-940`):**
   - `test_every_value_the_decision_log_states_is_the_value_the_code_holds` parses `` `NAME = value` `` snippets in `DECISIONS.md` and verifies `getattr(hawedit.<mod>, NAME) == value`. Any constants recorded in proposed ADR `D-352` must match exact Python attribute names/values in `hawedit.usable_rate`.

### 2.3 VEX package digest coupling (`tests/test_vex.py`)
Inspection of `tests/test_vex.py:27-30, 140-163`:
- `REVIEWED_VEX_SOURCE = (date(2026, 10, 15), "a7b54139328bd7a9a79c0d62237683ebc517d9e247367fe81928425ac1ea62f2")`.
- `tests/test_vex.py` asserts `policy.source_sha256 == package_digest(ROOT / "src" / "hawedit")`.
- **Constraint:** Adding `src/hawedit/usable_rate.py` in Round 2 changes `package_digest(ROOT / "src" / "hawedit")` and will fail `tests/test_vex.py` unless Lane 1's A3 VEX update lands first or `security/wsl-asr-vex.json` + `tests/test_vex.py` are re-pinned with owner approval.

## 3. Existing Code & Helpers Available for Reuse
- **`src/hawedit/cli.py:1-82`**: Provides `use_utf8_streams()` and `program_name()` for Windows UTF-8 console output and CLI formatting.
- **`src/hawedit/comparison_kit.py:1-300`**: Provides `wilson_score_interval(successes, total)` for computing 95% Wilson confidence bounds on proportions (reusable directly for the usable-rate summary and Phase F3 report).
- **Python standard library (`csv`, `hashlib`, `argparse`, `subprocess`, `datetime`, `pathlib`)**: Sufficient for strict UTF-8 CSV I/O, SHA-256 hashing of reel files, git commit lookup, and CLI subcommands with zero new dependencies.
- **Media workspace (`D:\HawEdit-media\README.md:1-63`)**: Standard test reel paths sit under `D:\HawEdit-media\reels\` derived from the three Zar Podcast sources in `D:\HawEdit-media\sources\`.

## 4. Schema & Calculation Findings
- The task sheet specifies columns `episode, reel, verdict, reason` where `verdict` is one of:
  - `publishable` (counted in numerator of usable rate),
  - `needs_fix` (human-friendly alias `"needs a fix"` / `"needs-fix"` normalized cleanly at the trust boundary),
  - `unusable`.
- To uphold project provenance discipline (`AGENTS.md` and task sheet §0), recording two additional trailing provenance columns (`reel_sha256`, `commit`, `recorded_at`) preserves the exact leading 4-column contract while guaranteeing every row binds a reel to its SHA-256 and git commit when recorded on `HawaPC01`.
- Strict fail-stop validation:
  - Unknown verdict strings fail immediately (non-zero exit / `ValueError`), never silently coerces.
  - Non-publishable verdicts (`needs_fix`, `unusable`) without a non-empty `reason` fail immediately so failures remain actionable for Phase F3 triage.
- Usable rate calculation:
  - `usable_rate = publishable_count / total_count` (when `total_count > 0`, else `0.0`).
  - Baseline comparison deltas reported alongside raw counts: vs OpusClip baseline (`0.62`) and vs HawEdit target (`0.80`).
