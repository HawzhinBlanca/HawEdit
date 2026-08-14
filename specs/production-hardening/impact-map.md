# Impact map — production-hardening

Every symbol the merge touches, who calls it, and which test covers each caller. Sourced from
the four parallel branch audits recorded in `research.md`. **A caller with no test is a finding,
not a footnote** — those rows are marked ⚠ and each has a test written into `plan.md`.

MINE = HEAD `6a6efca` · READINESS = `origin/codex/production-readiness-20260809` · BASE = `5eba372`

## 1. Conflicted paths (28 total, from `git merge-tree --write-tree HEAD READINESS`)

### Production modules — hand-merge required

| file | conflict | callers to keep working | covering tests |
|---|---|---|---|
| `pipeline.py` | severe — near-rewrite vs +154 | CLI entry, every stage | `test_pipeline.py`, `test_path_a.py`, `test_path_b.py`, `test_smoke.py` |
| `visual_pipeline.py` | severe — MINE's 3 `_EmbeddingCache` hunks sit **inside** a READINESS deletion (modify/delete) | `pipeline.build_visual_composer` | `test_visual_pipeline.py`, `test_visual_index.py` |
| `asr.py` | semantic — both rewrote `OmniAsrBackend.__init__`/`_load` | `asr_worker`, `pipeline` | `test_asr.py`, `test_alignment.py`, `test_forced_alignment.py` |
| `asr_worker.py` | schema v1 vs v2, two different extra fields | `WslOmniAsrProducer.transcribe` (`asr.py:922`) | `test_asr.py` ⚠ *no test asserts both fields coexist* |
| `delivery.py` | import line + `build_srt` prologue; naive resolution drops D-165 | `pipeline` delivery stage | `test_delivery.py`, `test_caption_timing.py` |
| `transcripts.py` | both sides edited | `clip`, `sentences`, `index`, `asr`, `delivery`, 19 test files | `test_transcripts.py` + 18 others |
| `video_input.py` | MINE's stale-purge sits inside READINESS's `mkdtemp` hunk | `visual_pipeline`, `video_reader` | `test_video_input.py` |
| `wsl_setup.py` | trivial — MINE's 8 lines are inside an embedded heredoc | `models._probe_canonical_omni_runtime` | `test_wsl_setup.py` |
| `clip.py` | none textually (D-181 line ~277 vs QC hunk ~459) | `render`, `delivery`, `pipeline` | `test_clip.py`, `test_render.py` |

### Enforcement surface — needs `.codystem-allow-self-edit`

| file | resolution |
|---|---|
| `scripts/test-count.floor` | take READINESS's `2073` **from the merge**; never hand-typed |
| `.github/workflows/gate.yml` | audit verified auto-merge places MINE's `shellcheck` + `guard-test.sh` inside READINESS's `gate` job; re-read the merged blob before trusting |
| `scripts/verify.sh` | auto-merges (MINE +9 / READINESS +112) — **auto-merge is not evidence of correctness**; read line by line, it is the thing that decides done |
| `scripts/build-wheel.sh` | MINE carries the `rm -rf build/bdist.*` wedge fix (commit `d044578`); must survive |

### Docs / other

`pyproject.toml` (load-bearing: `requires-python`, `[project.scripts]` the smoke job iterates,
`build-system.requires` that `release.py:519 _locked_build_contract` refuses to build without),
`BLOCKED.md`, `DECISIONS.md`, `PROGRESS.md`, `README.md`,
`evidence/adversarial-pass-24-2026-08-10.md` (add/add), and 13 `tests/test_*.py`.

## 2. Clean adds — no MINE counterpart, no conflict

`models.py` (+887, MINE == BASE so it applies straight), `model_fetch.py`, `omni_assets.py`,
`atomic_fs.py`, `artifact_bundle.py`, `gpu_runtime.py`, `windows_security.py`, `vex.py`,
`wsl_asr_locks.py`, `wsl_audit_locks.py`, `wsl_vex_gate.py`, `release.py`, `environment.py`,
`host_lock_hashes.py`, `ffmpeg_setup.py`, `models/integrity.json`, `requirements/host-*.txt`,
`scripts/lock_host_dependencies.py`, `scripts/install-host.sh`,
`.github/workflows/{release,gpu-readiness}.yml`.

## 3. Coupling that forbids selective merging

These are the traps. Each is a case where taking one file without another breaks the tree.

| if you take | you must also take | because |
|---|---|---|
| `pipeline.py` (READINESS) | `artifact_bundle.py`, `atomic_fs.py` | `pipeline.py:52` imports `ArtifactBundle`; used at `:913`, `:1523` |
| `pipeline.py` (READINESS) | `transcripts.py` (`validate_media_id`), `keyframes.py` | `pipeline.py:849 _candidate_work_component` imports `validate_media_id` at `:88`; candidate-id validation comes from nowhere otherwise |
| `models.py` (READINESS) | `omni_assets.py`, `wsl_setup.py` | `models.py:356 _probe_local_omni_runtime` imports `omni_assets`; `:403 _probe_canonical_omni_runtime` calls `wsl_setup.probe_wsl_runtime` |
| `release.yml` | `release.py`, `environment.py`, `host_lock_hashes.py`, `requirements/**` | the workflow shells into all of them |
| `gate.yml` (READINESS) | `scripts/install-host.sh`, `requirements/host-*.txt` | READINESS's install step replaces MINE's `requirements/gate-linux-py311.txt` path, which the merge deletes |
| `visual_pipeline.py` (READINESS) | `video_reader.py` (`release_cuda_model_memory`) | `_release_after` calls it ⚠ *presence on MINE not established* |

## 4. Symbols deleted by the merge that MINE still references

⚠ Each of these is a live break if unresolved.

| symbol | deleted from | still referenced by | resolution |
|---|---|---|---|
| `_write_atomic`, `_delivery_record_path`, `_delivery_is_complete`, `_write_delivery_record`, `DELIVERY_RECORD_SUFFIX`, `_file_digest` | `pipeline.py` (READINESS replaces with `ArtifactBundle`) | MINE's delivery tests | rewrite tests against the bundle; D-166's `UndeliverableOrder` except-clause re-carried |
| `_embedding_revision` | `pipeline.py` (READINESS deletes) | `build_visual_composer` | **re-add** — plan.md §A row 7; without it an unpinned checkpoint aborts the run |
| `_file_digest` (visual) | `visual_pipeline.py` → `_source_digest` | MINE's cache-key hunk | re-apply row 8 into READINESS's `_body()` **and** `load()`'s exact key-set literal |
| `assert_deliverable_order` call | `delivery.build_srt` (READINESS) | D-165 | re-add; the symbol still exists in MINE's `sentences.py:73/77` |
| adapter path: `_load_adapted_llm`, `adapter_fingerprint`, `adapter_name`, `_ctc_hypothesis` | `asr.py` (READINESS deleted entirely) | `pipeline.py --omni-asr-adapter`, `asr_worker` | hand-merge into READINESS's `_load` |
| `requirements/gate-linux-py311.txt`, `scripts/lock-gate-deps.sh` | clean-deleted by the merge | MINE's `gate.yml` install step | fine — READINESS's `install-host.sh` supersedes; verify no dangling reference |

## 5. Fragile external coupling

`release.py:81-90 _REQUIRED_GATE_STEPS` hard-codes **eight gate step names as strings**. Any
rename in `.github/workflows/gate.yml` breaks every release with no compile-time signal. MINE's
ffmpeg step is named `"fetch the pinned, checksummed ffmpeg (libass + HarfBuzz + FriBidi)"`;
READINESS's is `"fetch the pinned ffmpeg …"`. The merge keeps READINESS's, which matches its own
table — but a later revert to MINE's wording breaks releases silently. ⚠ *no test asserts the
two lists agree* — one is written into `plan.md` T3.

## 6. Not established

Carried forward honestly rather than assumed:

- Whether READINESS's gate is green. Not run — no worktree was created, no environment installed.
- Whether READINESS's 2073 tests subsume MINE's 1748, or overlap partially.
- Whether `KeyframeError` exists on MINE (READINESS's `pipeline.py` imports it alongside
  `extract_judge_frames`).
- Whether `release_cuda_model_memory` exists on MINE.
- Licence audit for READINESS's new runtime dependencies (`peft`, release-build tooling). D-002
  makes NonCommercial a hard reject; this has **not** been checked.
- Whether `merge-tree`'s clean auto-merge of `scripts/verify.sh` and `gate.yml` is semantically
  correct — only that it is textually clean.
