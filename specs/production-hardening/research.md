# Research — production-hardening

Status: **Part 1 (branch topology) complete and measured. Parts 2–5 pending parallel audits.**
No code or tests edited. No merge performed.

## 0. Why this document leads with topology

The brief's Phase 1 asks for one authoritative branch and says "do not rewrite work that already
exists". Whether that instruction dominates the other six phases is an empirical question about
what is already on the remote, so it is settled first. It does dominate.

## 1. Branch topology (measured 2026-08-14, `git fetch --all --prune`)

| ref | tip date | vs HEAD (behind / ahead) | merged into HEAD? |
|---|---|---|---|
| `origin/main` = `ff77942` | 2026-08-12 | 0 / 24 | yes — fully contained |
| `origin/codex/production-pipeline-hardening` | 2026-08-08 | 0 / 166 | **yes — fully contained** |
| `origin/codex/production-readiness-20260809` | 2026-08-10 | **173 / 72** | **no — genuinely divergent** |

Two of the three integration targets in the brief are already ancestors of HEAD. Phase 1's real
scope is one branch, not four.

- merge-base with readiness: `5eba372` "the audit document asserted the opposite of the shipped
  behaviour, for two days"
- `git diff 5eba372 origin/codex/production-readiness-20260809 --stat` → **254 files changed,
  33,274 insertions, 12,467 deletions**

No newer production/readiness branch exists on the remote; `git for-each-ref refs/remotes/`
returns exactly the four refs above.

## 2. The two branches are complementary, not competing

### Modules on readiness that do not exist on HEAD

Mapped against the phase that asks for them:

| file | lines added | brief phase it answers |
|---|---|---|
| `src/hawedit/release.py` | 1238 | 6 — release machinery |
| `src/hawedit/environment.py` | 974 | 6.3 — installed-environment inventory |
| `src/hawedit/wsl_vex_gate.py` | 788 | 4.9 — WSL/Windows coordination |
| `src/hawedit/omni_assets.py` | 692 | 4 — model assets |
| `src/hawedit/model_fetch.py` | 671 | 4.1–4.5 — supply chain |
| `src/hawedit/vex.py` | 633 | 4 |
| `src/hawedit/wsl_asr_locks.py` | 324 | 4.9 |
| `src/hawedit/atomic_fs.py` | — | 2.4 — atomic delivery |
| `src/hawedit/artifact_bundle.py` | — | 2.4 — authenticated bundle |
| `src/hawedit/gpu_runtime.py` | — | 5 — GPU lifecycle |
| `src/hawedit/windows_security.py` | — | 4.10 — owner/ACL/mode checks |
| `src/hawedit/host_lock_hashes.py` | — | 6.2 — hash locks |
| `src/hawedit/wsl_audit_locks.py` | — | 4.9 |
| `src/hawedit/ffmpeg_setup.py` | — | — |
| `scripts/lock_host_dependencies.py` | — | 6.2 |
| `scripts/install-host.sh` | — | 6 |
| `models/integrity.json` | 619 | 4.1 — byte manifests |

**Phases 4, 5 and 6 are substantially implemented on readiness already.** Building them on HEAD
would be rewriting existing work, which the brief forbids.

### Files on HEAD that do not exist on readiness

The entire CODYSTEM enforcement surface:

- `AGENTS.md`, `CLAUDE.md`, `.claude/settings.json` — **absent on readiness**
- `scripts/guard-pretooluse.sh`, `scripts/guard-test.sh`, `scripts/claude-stop-verify.sh`,
  `scripts/update-ledger.sh`, `scripts/lock-gate-deps.sh` — absent on readiness
- `scripts/verify.sh`, `src/hawedit/gate.py`, `scripts/test-count.floor` exist on **both**

Plus 24 commits of guard-coverage tests written in this session (`tests/test_ingest.py`,
`tests/test_transcripts.py`, `tests/test_harness_scripts.py`, and the mutation-matrix findings
recorded across `tests/`), and six `evidence/` records.

### Where readiness is unambiguously ahead

| measure | HEAD | readiness |
|---|---|---|
| `scripts/test-count.floor` | 1748 | **2073** |
| test files under `tests/` | 53 | **69** |
| `pyproject.toml` `requires-python` | `">=3.11"` | **`">=3.11,<3.13"`** |

The last row is Phase 6.1 verbatim — readiness already carries the honest bound, HEAD carries
the one the brief asks to correct.

## 3. Consequence for the plan

The merge direction is not symmetric and the evidence points one way: readiness is the stronger
**production** tree (16 modules, +325 tests, honest Python bound, release/supply-chain/GPU
machinery); HEAD is the stronger **harness** tree (CODYSTEM guard, ledger, hooks) and carries
this session's guard-coverage work.

Neither side is strongest wholesale, so this is a semantic integration and not a fast-forward in
either direction. The plan must state, per conflict-sensitive area, which side wins and why —
that is what Parts 2–5 below are being measured to decide.

Conflict is guaranteed in shared test files: readiness changed `tests/test_transcripts.py`
(+461/−224), `tests/test_pipeline.py` (+1250/−789), `tests/test_asr.py` (+563/−213) and
`tests/test_visual_pipeline.py` (+330/−155), and this session changed several of the same files.

## 4. Local state at the time of this audit

- HEAD = `6a6efca`, branch `claude/hawedit-project-setup-cciout`, pushed.
- Local canonical gate green: `1748 passed, 0 skipped`, floor 1748.
- Hosted CI green on the exact SHAs `d044578`, `1320f07`, `6a6efca`
  (`workflow_dispatch` runs 31749578862, 31751094744, 31752026162).
- Worktree clean except untracked `.serena/`.
- `.github/workflows/gate.yml` fires on `pull_request`, `push:[main]`, `workflow_dispatch`.
  Its own note records that marking `gate` a *required* check is an owner-only repository
  setting, so a green run here is evidence and not enforcement.

## 5. Open findings carried in from the guard-coverage work (not yet fixed)

Clause-level guard-revert (an `or` operand replaced with `False`, an `and` operand with `True`)
found these clauses that no test distinguishes. Line-level revert reports all of them HELD.

- `src/hawedit/boundary.py:259` — `inputs.anchor_out_ms < 0`
- `src/hawedit/judge.py:305` — `not isinstance(raw_sv6d, dict)`
- `src/hawedit/judge.py:395` — `not isinstance(self.data, bytes)`
- `src/hawedit/judge.py:501` — `candidate.verbal_score is not None`
- `src/hawedit/clip.py:364` — `not all(isinstance(flag, str) for flag in raw_flags)`
- `src/hawedit/visual_index.py:333` — `if ordered[0].in_ms != 0:` (line-level unheld)

Not measured by either instrument: conditions spanning multiple lines, reported SKIPPED —
`transcripts.py:105`, `judge.py:298`, `clip.py:349`.

---

## Parts 2–5 — four parallel audits (complete)

Method: four read-only agents, one per conflict-sensitive area, each comparing `git show HEAD:X`
against `git show <readiness>:X` and reporting symbol-level deltas with file:line evidence.
Their full findings are compacted into `plan.md` §A/§B/§C and `impact-map.md`; only what does
not fit those tables is recorded here.

### The shape of the divergence, which was not what it looked like

For `gemini.py`, `judge.py`, `render.py` and `models.py`, **HEAD is byte-identical to the
merge-base**. Every difference is readiness moving forward, not two lines competing. That single
fact decides the merge direction: on those four files there is nothing of HEAD's to weigh.

Where both moved, they moved on different axes rather than the same one — readiness on trust,
lifecycle and atomicity; HEAD on the LoRA adapter path, SV6D span parsing (D-182), the derived
`skipped()` (D-171), the unpinned-revision tolerance (D-140) and the embedding-cache key. That
is why this is a semantic integration and neither `-X ours` nor `-X theirs` is admissible.

### Semantic merge decisions recorded here (architectural ones owe an ADR at T13)

1. **Direction: readiness → HEAD.** Readiness is 17 modules and +325 tests ahead on production;
   HEAD carries the harness readiness has never had. Merging into HEAD keeps the CODYSTEM
   surface as the base rather than reconstructing it.
2. **`asr.py`:** readiness's `_load` body, wrapping HEAD's `_load_adapted_llm` branch. Readiness
   is stronger on verified-fd loading and `assert_transformers_config_safe`; HEAD is the only
   side with an adapter path at all.
3. **`asr_worker.py`:** readiness's schema v2, extended with HEAD's `lora_adapter`. Neither
   side's request schema is a superset — the merged one must carry `validator_model_dir` **and**
   `lora_adapter`, and `WslOmniAsrProducer.transcribe` must emit both.
4. **`video_input.py`:** readiness wholesale. Its per-call `mkdtemp` subsumes HEAD's stale-frame
   glob purge — a fresh directory cannot contain a stale tail — and additionally deletes source
   pixels on failure. HEAD's `__all__` re-export is orthogonal and kept.
5. **`visual_pipeline.py`:** readiness wholesale, then HEAD's `temporal_patch_frames` re-applied
   into `_body()` *and* into `load()`'s exact key-set literal, because readiness's hardened
   `load` validates against a closed key set and would reject its own new record otherwise.
6. **`delivery.py`:** readiness's SMPTE drop-frame handling and SRT validation, plus HEAD's
   `assert_deliverable_order` restored. Readiness's `sentences.py` never had that symbol to
   delete, so the naive merge leaves the import valid and the call site gone — a break that
   compiles.

### The one gap on neither branch

`gemini.py:552` checks only `VERDICT_SCHEMA["required"]`. **Unknown fields in the model's
verdict object are silently ignored on both branches.** That is Phase 3.3 and it is new work,
not a merge — the only item in the brief's seven phases for which that is true.

### Corrections to assumptions this session had been carrying

- "Phases 4/5/6 need building" — false. They are implemented on readiness.
- "`models.py` is unmeasurable by the shadow instrument" — true on HEAD, and now beside the
  point: HEAD's `models.py` is the merge-base's, with no integrity machinery to measure.
- "`wsl_setup.py`'s six environment probes are recorded-not-fixed" — readiness rewrites that
  file ~7×, so those findings are about code the merge replaces.
