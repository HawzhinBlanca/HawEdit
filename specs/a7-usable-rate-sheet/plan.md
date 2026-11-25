# Plan: A7 — Usable-Rate Scoreboard (`evidence/usable-rate.csv`) & F3 Tally CLI

Approved-by: Hawa — in chat, 2026-11-19, "/goal continuw work to real 10/10 highest grade content aware short vlip maker best quality possible , all approved"

## 1. Summary of Approach
Keep A7 minimal, deterministic, and compatible with all `tests/test_claims.py` invariants (`ponytail` principle — zero new dependencies, zero extra `[project.scripts]` entries):

1. **Data File (`evidence/usable-rate.csv`)**:
   - Header-only initial file in Round 2 (rows added as real reels are reviewed during Phase F):
     `episode,reel,verdict,reason,reel_sha256,commit,recorded_at`
   - Preserves the exact 4 requested leading columns while recording immutable provenance (`reel_sha256`, `commit`, UTC `recorded_at`).
   - `.csv` extension avoids breaking `tests/test_claims.py:296-308` (`glob("*.md")`).

2. **Module & CLI (`src/hawedit/usable_rate.py`)**:
   - Exposes pure Python API (`canonicalize_verdict`, `record_verdict`, `load_verdict_rows`, `summarize_usable_rate`, `format_summary_markdown`) and CLI entrypoint (`python -m hawedit.usable_rate add ...` and `python -m hawedit.usable_rate summary ...`).
   - Reuses `hawedit.cli.use_utf8_streams()` for Windows UTF-8 I/O and `hawedit.comparison_kit.wilson_score_interval()` for 95% confidence bounds.
   - Strict fail-stop checks (`ValueError` + non-zero exit): invalid verdict, missing non-empty `reason` for `needs_fix`/`unusable`, duplicate `(episode, reel)` without `--replace`, mismatched CSV header.
   - Does **not** add a `[project.scripts]` entry in `pyproject.toml`, keeping the 16 console scripts checked by `tests/test_claims.py:1363-1406, 1655-1668` intact.

3. **Phase F3 Integration**:
   - Once 15 real test reels are reviewed in `evidence/usable-rate.csv`, `python -m hawedit.usable_rate summary --markdown` emits the per-episode and overall rollup (`publishable / total`, Wilson 95% CI, delta vs OpusClip `0.62` and target `0.80`) ready to embed in a Phase F3 evidence report carrying `tests/test_claims.py`-compliant `commit`, `media_sha256`, `host`, and `command` headers.

## 2. Files to Create or Modify in Round 2 (After Approval)
| Action | File | Purpose |
|---|---|---|
| Create | `src/hawedit/usable_rate.py` | CSV ledger + summary + `python -m hawedit.usable_rate` CLI |
| Create | `evidence/usable-rate.csv` | Initial header-only scoreboard (`episode,reel,verdict,reason,reel_sha256,commit,recorded_at`) |
| Create | `tests/test_usable_rate.py` | Unit + CLI tests mapped to `A7-R1`..`A7-R6` |
| Edit (integration) | `README.md`, `PROGRESS.md` | Map `usable_rate.py` per `tests/test_claims.py:496-505, 730-745` |
| Coordinate | `security/wsl-asr-vex.json`, `tests/test_vex.py` | Re-pin or wait for A3 VEX parking because adding `src/hawedit/usable_rate.py` changes `package_digest(src/hawedit)` (`tests/test_vex.py:140-163`) |

## 3. Verification Plan (Round 2)
1. `.venv\Scripts\python.exe -m pytest tests/test_usable_rate.py tests/test_claims.py -q`
2. `& "C:\Program Files\Git\bin\bash.exe" scripts/verify.sh --fast`
3. Full `bash scripts/verify.sh` executed by lead on `gemini/number-one` after merge (Lane 5 never runs full `verify.sh` directly per swarm directive).

## 4. Open Questions / Risks
- **VEX dependency:** `tests/test_vex.py` pins the SHA-256 of `src/hawedit/`. Lane 1 (A3) or owner must approve/perform the VEX re-pin or retirement before full gate passes.
- **ADR allocation:** No new runtime dependency or frozen spec divergence is needed; optional proposed ADR `D-352` can record the scoreboard schema and `python -m` entrypoint choice if the owner desires an ADR row.
