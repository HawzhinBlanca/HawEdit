# Plan — production-hardening

Depends on `specs/production-hardening/research.md` (branch topology + four parallel audits).
**No production code has been edited.** This plan stops at `Approved-by:` per AGENTS.md and the
brief's Rule 6.

## The decision this plan exists to make

`origin/codex/production-readiness-20260809` is the stronger **production** tree and HEAD is the
stronger **harness** tree. Neither is a superset. The audits establish that:

- Every P0 the brief names in Phases 2, 3 and 4 is **already implemented on readiness**, and
  HEAD is byte-identical to the merge-base for `gemini.py`, `judge.py`, `render.py` and
  `models.py`. Writing those fixes on HEAD would be rewriting existing work, which Phase 1
  forbids.
- Thirteen things exist **only on HEAD** and a naive merge deletes them silently.

So: **merge readiness into this branch, direction readiness→HEAD, resolving every conflict by
hand against the preservation list below.** Not a fast-forward, not `-X theirs`, not `-X ours`.

## A. The preservation list — what a naive merge destroys

Each row is a merge-resolution requirement. A merge that loses any row is wrong even if green.

| # | lives on HEAD | why it must survive | file |
|---|---|---|---|
| 1 | CODYSTEM harness: `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json`, `guard-pretooluse.sh`, `guard-test.sh`, `claude-stop-verify.sh`, `update-ledger.sh` | readiness has none of it; it is the rule surface this work runs under | root, `scripts/` |
| 2 | LoRA/PEFT path: `_load_adapted_llm`, `adapter_fingerprint`, `adapter_name`, `_ctc_hypothesis`, `lora_adapter` ctor param | readiness **deleted** the adapter path entirely | `asr.py` |
| 3 | `--omni-asr-adapter` flag + mutual-exclusion check + `lora_adapter=` pass-through | the CLI half of row 2 | `pipeline.py` |
| 4 | `"adapter": self.asr.adapter` in `ClipTranscript.to_dict` (D-181) | absent on readiness — a delivered clip claims stock weights whichever adapter ran | `clip.py:277` |
| 5 | `assert_deliverable_order(sentences)` in `build_srt` (D-165) | readiness drops it; overlapping/backwards cues stop being refused | `delivery.py` |
| 6 | `PipelineRun.skipped()` derived from `fields(self)` (D-171) | readiness still carries the hand-written 9-tuple that can drop a stage silently | `pipeline.py` |
| 7 | `_embedding_revision()` → `""` on `SourceNotConfigured`/`RevisionNotPinned` (D-140) | readiness deletes it and passes the revision straight in, so an unpinned checkpoint **aborts the run** instead of degrading to no-cache | `pipeline.py`, `visual_pipeline.py` |
| 8 | `temporal_patch_frames` in the embedding-cache record key | real correctness key readiness lacks: 34 frames at patch 2 vs 32 at 4, otherwise byte-identical | `visual_pipeline.py` |
| 9 | `_anchor`/`_POINT`/`_SPAN` SV6D span parsing (D-182) | readiness only *tolerates* the bug its own docstring documents (D-156) | `video_reader.py` |
| 10 | `UndeliverableOrder` in the delivery `except` tuple (D-166) | must be re-carried into readiness's `ArtifactBundle` path | `pipeline.py` |
| 11 | stage-3 `N rejected` report line (D-183) | no readiness counterpart | `pipeline.py` |
| 12 | adapter-propagation refusal (request naming an adapter with an injected backend) | readiness's schema v2 has no adapter field at all | `asr_worker.py` |
| 13 | `peft==0.19.1` + `from peft import PeftModel` smoke in the WSL bootstrap | supports rows 2/12 | `wsl_setup.py` |
| 14 | this session's 24 commits of guard-coverage tests + 6 `evidence/` records | the coverage the floor is built on | `tests/`, `evidence/` |

## B. What readiness brings that HEAD lacks (do not re-implement — merge)

P0/P1 severity as assessed against the brief's phases.

| sev | finding on HEAD today | fixed on readiness at |
|---|---|---|
| P0 | `gemini.py` retries a **billed** `generateContent` up to 3× on 429/5xx → double-bill, two verdicts | `gemini.py:524-534` single `_post`, ambiguous-retry refusal |
| P0 | Stage 4 work dir built from raw `candidate_id`, **no validation** | `pipeline.py:849 _candidate_work_component` → `transcripts.py:245 validate_media_id` |
| P0 | `auto_pass` substitutes for `human_reviewed` in `assert_renderable` | `clip.py:462 if not self.qc.human_reviewed:` |
| P0 | render duration checked one-sided; over-long encode publishes trailing source footage | `render.py:348` + `assert_encoded_span` at `:327` |
| P0 | `models.py` == merge-base: no `verify_checkpoint`, no manifest, no lock, no `trust_remote_code` gate | `models.py` +887 lines; `models/integrity.json`; `model_fetch.py`; `omni_assets.py` |
| P0 | no atomic delivery publication | `artifact_bundle.py`, `atomic_fs.py:19 rename_directory_noreplace` |
| P1 | `judge.py` accepts `True` as `hook_score=1.0`, NaN passes every comparison, `payoff_at_ms` may be float | `judge.py:183-231` |
| P1 | unbounded Gemini response bodies and error messages | `gemini.py:266/296`, caps at `:80/:81` |
| P1 | keyframes written into the caller's `work_dir`, not a private per-attempt dir | `keyframes.py:66` `mkdtemp(prefix=".judge-")`, non-masking cleanup at `:28-42` |
| P1 | no GPU release ordering anywhere | `visual_pipeline._release_after`, `video_reader.VideoChat3Reader.close`, `gpu_runtime.py` |
| P1 | operational failures raise instead of producing `StageSkipped` | `pipeline.py:459 _operational_failure` at 9 call sites |
| P1 | `requires-python = ">=3.11"` — dishonest | `pyproject.toml:5 ">=3.11,<3.13"` |
| P1 | 0 of 2 GitHub Actions SHA-pinned | readiness: 15 of 15 |
| P1 | no release machinery, no SBOM/provenance/attestation, no wheel-reproducibility check | `release.py` (1238), `release.yml`, `environment.py` (974) |

## C. Genuinely new work — on neither branch

| sev | gap | brief |
|---|---|---|
| P1 | **Unknown fields are never rejected** in the Gemini verdict. `gemini.py:552` checks only `VERDICT_SCHEMA["required"]`; extra keys in the model's object are silently ignored on both branches. | Phase 3.3 |
| P2 | `gemini.py` keeps `max_attempts`/`sleep` as dead constructor params (`:369-370`, `:634-635`) — misleading API surface, no behavioural effect | Phase 3.7 hygiene |
| P2 | clause-level uncovered guards carried from the coverage work: `boundary.py:259`, `judge.py:305/:395/:501`, `clip.py:364`, `visual_index.py:333` | — |

## D. Merge plan — one bounded task at a time, gate after each

`scripts/test-count.floor` and `.github/**` are enforcement surface: create
`.codystem-allow-self-edit` before touching them, delete it after. Take readiness's floor value
(2073) from the merge — do **not** hand-type it.

- **T0** Licence audit, ahead of the merge. **COMPLETE — D-200 and D-201.** Twelve dependencies
  audited, all permissive, no NonCommercial term; `BLOCKED.md` #23 closed. Seven read from
  installed wheel metadata, five (`peft`, `google-auth`, `fairseq2`, `fairseq2n`, `qwen-asr`)
  read from published metadata at the **exact pinned version**, which installing could not have
  given. Two pyproject annotations are wrong and are corrected at T4, not here, because
  `pyproject.toml` is a conflicted path: `fairseq2` is MIT and annotated BSD-3-Clause; `torch`
  is a six-term conjunction annotated BSD-3-Clause. **T1 is unblocked.**
  *(tests: `test_every_runtime_dependency_has_a_licence_record`)*
- **T0b** Renumber the incoming branch's colliding ADRs. D-200 established that the merge-base
  tops out at D-154 and both branches then assigned **D-155…D-191 independently** — 37 numbers,
  each naming a different decision per side, including all four this plan's §A cites (D-165,
  D-171, D-181, D-182). Readiness's collide-range moves to D-201+ with its in-code citations
  rewritten. Independent of T0; blocks T13.
  *(tests: `test_no_d_number_names_two_decisions`)*
- **T1** Merge preparation. Create the merge commit with `git merge --no-commit --no-ff` and
  leave it unstaged. Record the conflict set. No resolution yet. *(tests: none — no tree change
  is committed)*
- **T2** Resolve the clean-add files (`models.py`, `model_fetch.py`, `omni_assets.py`,
  `atomic_fs.py`, `artifact_bundle.py`, `gpu_runtime.py`, `windows_security.py`, `vex.py`,
  `wsl_*_locks.py`, `wsl_vex_gate.py`, `release.py`, `environment.py`, `host_lock_hashes.py`,
  `ffmpeg_setup.py`, `models/integrity.json`, `requirements/**`). No hand-merge needed.
  *(tests: `test_models.py`, `test_model_fetch.py`, `test_omni_assets.py`, `test_release.py`,
  `test_environment.py`, `test_vex.py`, `test_wsl_vex_gate.py`, `test_gpu_runtime.py`)*
- **T3** Resolve `.github/workflows/gate.yml` — the audit verified auto-merge lands HEAD's
  `shellcheck` and `guard-test.sh` steps inside readiness's `gate` job correctly. Re-read the
  merged blob rather than trusting it. *(tests: `test_fetch_scripts.py`, `test_supply_chain.py`)*
- **T4** `pyproject.toml` — take readiness's `requires-python` and `[project.scripts]` and
  `build-system.requires` (load-bearing for `release.py:519 _locked_build_contract`).
  *(tests: `test_build.py`, `test_environment.py`)*
- **T5** `asr.py` + `asr_worker.py` + `wsl_setup.py` — hand-merge rows 2, 12, 13: readiness's
  `_load` body wrapping HEAD's `_load_adapted_llm` branch; a request schema carrying **both**
  `validator_model_dir` and `lora_adapter`. *(tests: `test_asr.py`, plus a new
  `test_the_adapter_and_the_validator_both_survive_the_worker_request`)*
- **T6** `visual_pipeline.py` — take readiness wholesale, then re-apply row 8 into `_body()`
  **and** into `load()`'s exact key-set literal, and row 7's `_embedding_revision` tolerance.
  *(tests: `test_visual_pipeline.py`, plus
  `test_an_unpinned_checkpoint_degrades_to_no_cache_rather_than_aborting`)*
- **T7** `video_input.py` — take readiness's `mkdtemp` hunk wholesale (it subsumes HEAD's
  stale-glob purge); keep HEAD's `__all__` re-export. *(tests: `test_video_input.py`)*
- **T8** `video_reader.py` — disjoint hunks, both sides apply. Verify row 9 survives.
  *(tests: `test_video_reader.py`)*
- **T9** `delivery.py` + `sentences.py` — readiness's rate handling and SRT validation, plus row
  5 re-imported and re-called. *(tests: `test_delivery.py`, `test_sentences.py`)*
- **T10** `clip.py` — readiness's `human_reviewed` gate plus row 4. *(tests: `test_clip.py`)*
- **T11** `pipeline.py` — the largest. Readiness's structure; re-carry rows 3, 6, 7, 10, 11.
  *(tests: `test_pipeline.py`)*
- **T12** `transcripts.py`, `keyframes.py`, and the 13 conflicted test files.
  *(tests: the conflicted files themselves)*
- **T13** Docs: `BLOCKED.md`, `DECISIONS.md`, `PROGRESS.md`, `README.md`,
  `evidence/adversarial-pass-24-2026-08-10.md` (add/add). Record every semantic merge decision
  as an ADR. *(tests: `test_claims.py`, `test_gate_evidence.py`)*
- **T14** Phase 3.3 — reject unknown fields in the Gemini verdict container (section C, the one
  genuine gap). *(tests: `test_an_unknown_field_in_the_verdict_is_refused`)*
- **T15** Clause-level uncovered guards from section C. *(tests: one per guard)*

## E. Risks

1. **Silent loss.** The whole of section A. Mitigation: after the merge, one test per row, and
   a grep-based checklist run before the final gate.
2. **`release.py:81-90 _REQUIRED_GATE_STEPS` hard-codes eight gate step names.** Renaming a step
   in `gate.yml` breaks every release. HEAD's ffmpeg step name differs from readiness's; the
   merge keeps readiness's, which matches — a later revert to HEAD's wording breaks releases
   silently. Worth an ADR.
3. **`scripts/verify.sh` auto-merges** (HEAD +9, readiness +112). Auto-merge is not evidence of
   correctness here; the merged file must be read line by line before it is trusted, because it
   is the thing that decides done.
4. **`models.py` imports `omni_assets` and `wsl_setup.probe_wsl_runtime`**, so the
   readiness-only modules are load-bearing for readiness reporting and cannot be merged
   selectively.
5. **Scale.** 254 files, +33,274/−12,467, 28 conflicted paths. This is not one sitting.

## F. Divergences from BLUEPRINT.md / new dependencies

None proposed by this plan itself. Readiness adds runtime dependencies (`peft`, release-build
tooling, WSL ASR locks); each needs its licence audited in `DECISIONS.md` at T2/T4, and
NonCommercial is a hard reject per D-002. **Not yet audited — this is an open item, not a
clearance.**

## G. Definition of done for this feature

- `bash scripts/verify.sh` green, 0 skipped, floor not hand-edited.
- Every row of section A provably present, each by a named test.
- Hosted CI green on the exact committed SHA.
- No P0/P1 from section B or C outstanding.

Approved-by: Hawa — 2026-08-14, in session, plan approved as written.

Three decisions recorded with it, all binding on the tasks above:

1. **Plan approved as written.** T1–T15 proceed, one bounded task at a time, full
   `bash scripts/verify.sh` after each.
2. **Land via a pull request to `main`.** Opened, not merged. This is also what makes CI run
   under the `pull_request` event, which is the trigger AGENTS.md's definition of done names —
   `workflow_dispatch` has been standing in for it and cannot.
3. **Licence audit runs BEFORE the merge, not after.** Every runtime dependency readiness adds
   is audited and recorded in `DECISIONS.md`. D-002 makes NonCommercial a hard reject: a
   NonCommercial finding blocks that dependency and is reported rather than merged. This
   promotes the audit ahead of T1 — it is now **T0**, and the merge does not start until it is
   clean.
