# Impact Map — Episode Plan (Task T4.1)

## Affected Callers and Modules

### New Module
- `src/hawedit/episode.py`:
  - `EpisodePlanConfig`
  - `EpisodeClipSummary`
  - `EpisodeManifest`
  - `compute_text_similarity`
  - `select_episode_plan`
  - `reconcile_episode_manifest`

### Modified Module
- `src/hawedit/pipeline.py`:
  - Wire `--max-clips` and episode planning mode into pipeline runner / CLI when requested.

### Test Suite
- `tests/test_episode.py`:
  - Unit checks for non-overlap, separation distance, lexical diversity, cost cap, manifest generation, and manifest reconciliation.
  - Multi-clip reality check on real media or synthetic multi-candidate sequences.

### Registries & Documentation
- `README.md`: register `episode.py` in the module table.
- `PROGRESS.md`: register `episode.py` in the ledger.
- `security/wsl-asr-vex.json`: update `source_sha256`.
