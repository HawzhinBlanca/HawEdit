# Specification: A7 — Usable-Rate Scoreboard (`evidence/usable-rate.csv`) & F3 Tally

## Overview
Provide `evidence/usable-rate.csv` and a zero-dependency module CLI (`python -m hawedit.usable_rate`) that appends/updates per-reel human verdicts with SHA-256 + git commit provenance and reports exact usable-rate tallies against the `0.62` OpusClip baseline and `0.80` HawEdit target.

## Constants
- `USABLE_RATE_BASELINE = 0.62` (OpusClip baseline)
- `USABLE_RATE_TARGET = 0.80` (HawEdit Phase F3 target)
- `VALID_VERDICTS = ("publishable", "needs_fix", "unusable")`
- `CSV_COLUMNS = ("episode", "reel", "verdict", "reason", "reel_sha256", "commit", "recorded_at")`

## EARS Acceptance Criteria

### A7-R1: Scoreboard CSV initialization and schema preservation
- **WHEN** `record_verdict()` is called and the target CSV file does not yet exist or is empty, **THE** `hawedit.usable_rate` module **SHALL** create parent directories as needed, write the exact UTF-8 header `episode,reel,verdict,reason,reel_sha256,commit,recorded_at`, and append the validated row.
- **WHEN** `record_verdict()` appends to an existing CSV file whose header does not start with `episode,reel,verdict,reason`, **THE** module **SHALL** raise `ValueError` and leave the existing CSV file unmodified.
- **Mapped tests (`tests/test_usable_rate.py`):**
  - `test_usable_rate_initializes_header_and_appends_row`
  - `test_usable_rate_rejects_mismatched_csv_header`

### A7-R2: Strict verdict validation and canonicalization
- **WHEN** a caller supplies `verdict` as `"publishable"`, `"needs_fix"` (or `"needs-fix"` / `"needs a fix"`, case-insensitive), or `"unusable"`, **THE** `canonicalize_verdict()` function **SHALL** normalize it to `"publishable"`, `"needs_fix"`, or `"unusable"`.
- **WHEN** a caller supplies any other verdict string, **THE** module **SHALL** fail immediately with `ValueError` (CLI exit code non-zero) without modifying `evidence/usable-rate.csv`.
- **Mapped tests (`tests/test_usable_rate.py`):**
  - `test_usable_rate_canonicalizes_and_validates_verdict`
  - `test_usable_rate_rejects_unknown_verdict_without_writing`

### A7-R3: Fail-stop non-empty reason for non-publishable reels
- **WHEN** `verdict` is `"needs_fix"` or `"unusable"` and `reason` is empty or whitespace-only, **THE** module **SHALL** fail immediately with `ValueError` (CLI exit code non-zero) and leave the CSV unmodified.
- **WHEN** `episode` or `reel` is empty or whitespace-only, **THE** module **SHALL** fail immediately with `ValueError`.
- **Mapped tests (`tests/test_usable_rate.py`):**
  - `test_usable_rate_requires_reason_for_non_publishable`

### A7-R4: Provenance capture and duplicate handling
- **WHEN** `record_verdict()` runs with a `reel` pointing to an existing file on disk (or an explicit `--reel-path`), **THE** module **SHALL** compute its lowercase hex SHA-256 into `reel_sha256`; otherwise when no file path exists, **THE** module **SHALL** record `"n/a"` (never inventing a checksum).
- **WHEN** `--replace` is not given and a row with the same `(episode, reel)` already exists in the CSV, **THE** module **SHALL** raise `ValueError` unless `--replace` is explicitly passed, in which case that `(episode, reel)` row is updated in place cleanly.
- **Mapped tests (`tests/test_usable_rate.py`):**
  - `test_usable_rate_records_sha256_and_commit_provenance`
  - `test_usable_rate_guards_duplicate_reel_unless_replace`

### A7-R5: Usable-rate summary and Phase F3 baseline comparison
- **WHEN** `summarize_usable_rate()` or `python -m hawedit.usable_rate summary` runs on a CSV with rows, **THE** module **SHALL** compute `total`, `publishable`, `needs_fix`, `unusable`, `usable_rate` (`publishable / total`), 95% Wilson confidence bounds via `comparison_kit.wilson_score_interval()`, and deltas against `USABLE_RATE_BASELINE` (`0.62`) and `USABLE_RATE_TARGET` (`0.80`), plus per-episode counts.
- **WHEN** the CSV contains zero data rows (header-only or empty), **THE** summary function **SHALL** report `total=0` and `usable_rate=0.0` without raising `ZeroDivisionError`.
- **Mapped tests (`tests/test_usable_rate.py`):**
  - `test_usable_rate_summary_computes_rate_and_baseline_delta`
  - `test_usable_rate_summary_handles_empty_sheet`

### A7-R6: `tests/test_claims.py` and UTF-8 CLI compatibility
- **WHEN** `evidence/usable-rate.csv` is committed in `evidence/`, **THE** repository test `tests/test_claims.py::test_new_evidence_names_its_commit_media_and_host` **SHALL** continue to pass untouched.
- **WHEN** `python -m hawedit.usable_rate` is invoked via subprocess on Windows, **THE** CLI **SHALL** configure UTF-8 streams via `hawedit.cli.use_utf8_streams()`, support Kurdish/Unicode text in `reason`, and support `--json` structured output.
- **Mapped tests (`tests/test_usable_rate.py` & `tests/test_claims.py`):**
  - `test_usable_rate_cli_add_and_summary_utf8_roundtrip`
  - `test_usable_rate_evidence_csv_does_not_trip_claims_gate`
