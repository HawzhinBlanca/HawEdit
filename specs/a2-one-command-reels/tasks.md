# Tasks ledger — a2-one-command-reels
# Rows flip to [x] ONLY via scripts/update-ledger.sh, after verify.sh passes and the cited
# tests are found in the report that run wrote.

- [x] T1  Plain WSL runtime resolution without .ready receipt unless --strict-runtime is set (D-336)   (tests: test_default_wsl_runtime_resolves_without_ready_receipt, test_strict_runtime_still_enforces_wsl_receipt)
- [x] T2  Configurable multi-threaded Stage 0 proxy extraction & parity check   (tests: test_stage0_proxy_threads_and_shot_parity)
- [x] T3  One-command pipeline desktop defaults, --output-dir export, and per-stage wall timings   (tests: test_cli_default_profile_builds_end_to_end_multi_clip_kwargs, test_episode_delivery_exports_reels_with_measured_sidecars_and_stage_timings)
- [ ] T4  Generate 10 reels (.mp4 + .measured.json) from 1440p AI episode into D:\HawEdit-media\reels\<run>\ and record wall times in evidence/   (tests: test_episode_delivery_exports_reels_with_measured_sidecars_and_stage_timings)

## Definition of Done (all must be true)
- [ ] Every AC test passes                    (bash scripts/verify.sh on integration branch)
- [ ] lint + typecheck + format green         (same gate)
- [ ] Required CI checks green on the PR      (the real source of truth)
- [ ] 10 reels + .measured.json on disk & scored in evidence/usable-rate.csv
