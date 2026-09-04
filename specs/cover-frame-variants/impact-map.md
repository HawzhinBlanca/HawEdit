# Impact Map — Cover Frame and Title Variants (Task T4.10)

## Codebase Surface

| Component | File | Nature of Change | Callers / Impact |
|---|---|---|---|
| Cover Frame Selector | `src/hawedit/cover.py` | NEW module | Implements `CoverCandidate`, `CoverSelectionResult`, `score_cover_frame`, `select_cover_frame`, and `generate_title_variants`. |
| Clip Contract | `src/hawedit/clip.py` | MODIFIED `Output` | Adds `title_variants_ckb: tuple[str, ...] = ()` and `cover_frame_ms: int | None = None` with JSON serialization. |
| Judge Output | `src/hawedit/judge.py` | MODIFIED `JudgeVerdict` | Adds `title_variants_ckb: tuple[str, ...] = ()` with validation. |
| Delivery Packaging | `src/hawedit/delivery.py` | MODIFIED | Updates `publish_delivery_bundle` to support `cover.png`; updates `reconcile_delivery` to validate `cover_frame_ms`. |
| Module Map | `README.md` | MODIFIED | Adds `cover.py` to the modules table. |
| Progress Ledger | `PROGRESS.md` | MODIFIED | Adds `M9.27` ledger row. |
| Security Policy | `security/wsl-asr-vex.json` | MODIFIED | Updates `source_sha256` package digest. |
| Pipeline Execution | `src/hawedit/pipeline.py` | MODIFIED | Integrates cover frame extraction and title variants into deliverable bundle staging. |
| Tests | `tests/test_cover.py` | NEW test suite | Unit tests covering heuristic scoring, image extraction, title variants, contract roundtrip, and delivery bundle packaging. |
