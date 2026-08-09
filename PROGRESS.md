# PROGRESS — Kurdish Video Repurposing System

Generated from `BLUEPRINT.md` §9 (Build order). **The agent never marks a task DONE by
judgment**: DONE requires code + test + the gate green + evidence linked below.

- Gate: `bash hawedit/scripts/verify.sh` (lint + format + typecheck + tests)
- Blocked items: `BLOCKED.md` · Deviations: `DECISIONS.md`

## Status legend

| Mark | Meaning |
|---|---|
| DONE | Gate green **and** evidence recorded below **and** the task's stated Definition of Done met in full |
| PARTIAL | Gate green on what was built, but the Definition of Done is *not* met — the shortfall is named in the evidence column. Introduced after the 2026-08-07 audit found DONE marks that were really this. |
| WIP | In progress this iteration |
| TODO | Not started |
| BLOCKED | Needs Hawa / hardware / credentials — see `BLOCKED.md` |

## Milestones (§9)

| Milestone | Deliverable | Blocks | Status |
|---|---|---|---|
| **M0** | ASR benchmark harness + labelled Sorani audio set | Everything | **harness and canonical adapter built and gated; real Sorani measurements remain blocked by the absent labelled corpus** |
| **M1** | Stage 0 + Stage 1 → raw/normalized transcript with word timings | M2 | **WIP — Stage 1 is complete and has run through the CLI with LLM+CTC, validator routing and Viterbi timings; Stage 0 remains partial because diarization is gated** |
| **M2** | Vertical slice: transcript → BM25 → Gemini → manual boundary → one rendered clip | Proves the concept | **WIP — index, boundary fusion, §5 contract and a real rendered clip DONE; only Gemini (Stage 3) is still missing from the slice** |
| **M3** | Stage 6 render path with verified RTL captions + golden test | Client delivery | **WIP — §4.3 and NVENC run; dynamic face-continuity crop is wired; active-speaker association remains gated; delivery set DONE** |
| **M4** | Stage 3 Path A (full-transcript discovery) | Verbal recall | **DONE — delivered in M2.3 (`path_a.py`, 21 tests). The milestone row said TODO while its own ledger row said DONE; the drift is the point of the status legend and is corrected here.** |
| **M5** | Stage 2 visual index + Stage 3 Path B | Visual recall | **DONE in code — one composed owner extracts once, retrieves top 50, reranks, keeps 5–10 and sends only survivors to VideoChat3; the unranked injection seam is refused. Quality still needs M7.** |
| **M6** | Stage 5 TimeLens2 + sentence-hard fusion | Boundary precision | **DONE in code — the runner grounds the selected transcript against overlapping windows, shifts intervals to media time and fuses only relevant evidence. Quality still needs M7.** |
| **M7** | Repurposing eval set + threshold tuning | Quality gates | **WIP — §8.2 metrics DONE; the 200–500 labelled candidates need humans** |
| **M8** | Auto-reframe (SAM 3 / Molmo2) | Vertical formats | **BLOCKED — `BLOCKED.md` #9. Neither SAM 3 nor Molmo2 is in §7. §3 Stage 6 says to add SAM 3 *only if* face-centred cropping proves insufficient on real footage, and that prerequisite is now built and has its own row (M8.1, PARTIAL) — so the accurate statement is no longer "not startable": the step §3 asks for first is taken, and the *decision* it is supposed to inform cannot be made, because judging "insufficient on real footage" needs real footage (`BLOCKED.md` #1) as much as it needs Hawa's answer on the two models.** |

## Where this stops, and why

Everything that does not require credentials, model weights, a GPU, human annotators, or a
decision from Hawa is built, tested and gated. `bash scripts/setup.sh` takes a clone to a green
gate; `python -m hawedit.pipeline VIDEO.mp4` runs §3 as far as the available models allow and
exits non-zero naming every stage it could not.

**Re-assessed 2026-08-08: this checkout moved to hawapc01, and two of those six went away.**
The GPU is here (2×24 GiB, §6's own figure) and `huggingface.co` is reachable, both measured in
`evidence/hawapc01-environment.md`. That is a change of desk, not of code — but it makes three
rows startable that had been marked impossible, and it exposed one blocker the other two were
hiding.

| Waiting on | Blocks |
|---|---|
| ~~`huggingface.co` reachable~~ | **Resolved** — every §7 repo that has an id now serves files; measured per repo, not per host |
| ~~A GPU (hawapc01)~~ | **Resolved** — this *is* hawapc01, so NVENC in M3.3 and every model row lose their hardware reason |
| ~~Where §3 Stage 1 runs (`BLOCKED.md` #11)~~ | **Resolved** — Windows uses the explicit WSL2 bridge; Linux runs locally; setup and runtime selection are scripted and tested (D-064) |
| The §3 ZDR governance answer (credentials themselves are now handled) | confidential material only — `gemini.Governance` refuses it until ZDR is configured and attributed |
| The gated `pyannote/speaker-diarization-community-1` repo | M0.10, M1.3, the speaker-tracked reframe in M3.3 — measured **401** from here, so the network opening did not touch it |
| Human annotators + real footage | M7.2, and M7.3 behind it |
| Hawa, one decision each | `BLOCKED.md` #7 (required CI check) · #9 (M8 names two models §7 does not contain) · #8, #10 and #11 resolved, with `BLUEPRINT.md` §5 and §7 still needing matching amendments |

**All model stages are now composed in the runner.** Query → retrieve → rerank → bounded
VideoChat3 → automatic sentence anchors → keyframed judge → TimeLens → dynamic face crop is one
auditable route, and Windows Stage 1 has a WSL2 worker. What remains is measurement, not another
join. **Not** M0.16: it was
listed here this morning and is BLOCKED again, because the hosts answering 200 turned out not
to be the question — the interim corpus itself is no longer publicly distributed. And M7.3
sits behind M7.2. The contracts they plug into are built and tested ahead of them, so landing each
is a matter of producing the type its stage already expects.

## M0 — task ledger

M0 decomposed from §8.1 (ASR benchmark) + §4.1 (normalization is a prerequisite of
"normalized CER"). Decomposition is task breakdown, not architecture change.

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M0.17 | Local gate binds the canonical interpreter, installation and dependency identity to this checkout | DONE | `src/hawedit/environment.py` + `tests/test_environment.py` + `scripts/verify.sh`. External/token-forging `PY`, wrong-root/duplicate editable metadata, unsupported Python/project versions and active dependency drift are refused before grading. D-117; `evidence/environment-identity.md`. |
| M0.18 | Measured dual-3090-Ti CUDA dependency and hardware identity | DONE | `src/hawedit/gpu_runtime.py`, `requirements/host-gpu-windows-py311.txt`, and `tests/test_gpu_runtime.py`. The 46-wheel Windows/Python 3.11/CUDA 13.0 graph is hash-locked, packaged and exact-inventory audited; a fresh environment passed `pip check`, imported Torch 2.13.0+cu130/Torchvision 0.28.0+cu130/Torchaudio 2.11.0+cu130, and executed bfloat16 work on both 24 GiB RTX 3090 Ti cards. This qualifies the deployment runtime, not VideoChat3's 64-frame application path; that measured OOM remains M5.4/BLOCKED #17. `evidence/gpu-dependency-lock.md`. |
| M0.1 | Package skeleton + gate script; gate refuses a no-op command instead of printing green | DONE | `src/hawedit/gate.py` + `tests/test_gate.py` · gate green: `VERIFY OK — hawedit gate green` · found + fixed 2 real gate defects, see D-005. The floor compares `evidence.passed`, never `collected`: the two differ by exactly the skips, which is the case the ratchet exists to catch. `README.md` described it as *collected* until D-069. **Correction 2026-08-09:** the "refuses a no-op command" guarantee had a hole the size of the whole gate — the override refusal covers `LINT_CMD`/`FORMAT_CMD`/`TYPECHECK_CMD`/`TEST_CMD`, but `PY` prefixes all four *and* the evidence step, so `PY=/usr/bin/true.exe bash scripts/verify.sh` printed `VERIFY OK` in 1s, exit 0, with no report written. An interpreter now proves it can import `hawedit` before it is trusted to grade it (exit 3); mutation-audited 5/5. D-104, `evidence/py-override-bypassed-the-whole-gate.md`. |
| M0.2 | §7 model registry in code; model outside §7 rejected; NC licence hard-rejected | DONE | `src/hawedit/registry.py` + `tests/test_registry.py`. The tests **parse §7 out of `BLUEPRINT.md`** and assert exact set equality both ways, so a model added in code but not in the blueprint fails the gate. **Amended 2026-08-09 (D-087), found by the second adversarial pass:** that guarantee had two holes, both invisible to set equality because it compares the *cells each table self-declares*. (1) `resolve` reads `REGISTRY` before `EXCLUDED` and nothing asserted the tables were disjoint, so a model §7 **excludes** could be registered and would resolve — measured, `Whisper` with a cell §7 already contains, no role and an attribution-free licence returned from `resolve()` with no `ModelExcluded` and the full suite at `exit=0, 0 FAILED`; two of §7's nine exclusions are CC-BY-NC-4.0 hard rejects, so this could route work to a NonCommercial model. (2) A **duplicated** cell left the declared set unchanged, which is how that entry hid. `assert_registry_excludes_nothing_it_registers` now enforces both at **import** — a contradiction in the data, so unconstructible beats deciding which table wins, and it fails for library consumers rather than only in the suite. 15 entries / 15 distinct cells, so uniqueness was enforceable. 5/6 mutations; the survivor is the import-time call, redundant with two tests for gate purposes and kept for import-time refusal. Three attempts were needed to measure the defect: two mutations read CAUGHT for reasons unrelated to exclusions (a malformed append caught by mypy, an attribution-requiring licence caught by README bookkeeping) — a mutation caught for the wrong reason reads as protection that is not there. The stale `(15 tests)` count is dropped rather than restated. `evidence/registry-excluded-model-resolvable.md`. |
| M0.3 | §4.1 Sorani normalization via KLPT; every §4.1 collision asserted in a test | PARTIAL | `src/hawedit/normalize.py` + `tests/test_normalize.py` + `tests/test_waw.py`. Four of §4.1's five collisions are handled: ZWNJ, Farsi/Arabic `ی`/`ک` and Numerals by KLPT (D-003), and conjunctive `و` by M1.7 against KLPT's dictionary (D-026). **Demoted from DONE 2026-08-09 (D-076), found by the adversarial pass.** This cell read *"All five §4.1 collisions are now handled … the fifth — conjunctive `و`"*, which reached five by counting §4.1's single Numerals row twice. Read out of the frozen blueprint, `BLUEPRINT.md:228-232`, conjunctive `و` is row **four** and row five is `Diacritics ř / ł` — "Normalize in Latin-script material". **Shortfall (one, named):** row five is unimplemented — measured, `normalize_sorani` leaves `řoj baş` and `łe gułan` byte-identical and no file in `src/` or `tests/` mentions either character — and it is not implementable without a decision, because §4.1 does not say what `ř`/`ł` normalize *to* and in Kurdish Latin orthography they are distinct phonemes rather than decorated variants. Refused rather than guessed: `BLOCKED.md` #13. `evidence/adversarial-pass-2026-08-09.md`. |
| M0.4 | Kurdish invariants #1 and #3 in code: `transcript.raw.json` write-once, model inputs read `norm` | DONE | `src/hawedit/transcripts.py` + `tests/test_transcripts.py`. #1 enforced three ways (refuse-rewrite, frozen types, SHA-256 tamper evidence); #3 enforced by distinct types (mypy) + `assert_model_input` (runtime) + stale-norm detection. ASR provenance is validated against §7 at construction. |
| M0.5 | §8.1 accuracy metrics: normalized CER, spacing-free CER, named-entity error, code-switch error | DONE | `src/hawedit/metrics.py` + `tests/test_metrics.py`. Definitions §8.1 left open are recorded in D-008. Unmeasured returns `None`, never 0.0. **Amended 2026-08-09 (D-089), found by the second adversarial pass:** that last sentence had a hole. `""` is a substring of every string, so a **blank** entity satisfied `entity in hypothesis` and counted as a name that *survived* — `named_entity_error_rate("سەرۆک لە شار", ("",))` returned **0.0**, the same value as a name transcribed perfectly, and `CorpusItem(..., conditions={NAMED_ENTITIES}, named_entities=("",))` constructs without complaint, so one blank label silently inflated §8.1's accuracy. The sibling `code_switch_error_rate` already refused the identical input as "a corpus defect", so the rule was extracted rather than invented: `_normalized_annotation` is shared by both, message shape unchanged. An *empty tuple* still returns `None` — nothing annotated is not malformed data, and a mutation collapsing the two is caught. **Also closed:** D-008 claims all four of its recorded choices are tested; the fourth (exact matching — "a name 90% right is still the wrong name") was not, so a fuzzy 0.34 threshold could have been introduced with the suite green. Now pinned in both directions, since a near-miss must score 1.0 *and* an Arabic-keyboard `كوردي` must still match `کوردی`. 6/6 mutations — 5/6 at first, and the survivor exposed a second unprotected guard: removing the code-switch refusal, the one implemented correctly all along, also left the suite green. The stale `(26 tests)` count is dropped rather than restated. `evidence/blank-annotation-scored-as-found.md`. |
| M0.6 | Labelled-corpus manifest + §8.1 coverage validation (3 dialects × 7 conditions), per-dialect never aggregated away | DONE | `src/hawedit/corpus.py` + `tests/test_corpus.py`. Missing cells are named, not counted; hours are reported per dialect per §4.4; the hours floor is D-009. **Amended 2026-08-09 (D-091), found by the second adversarial pass:** the grid **certified itself**. `tests/test_corpus.py` referenced `BLUEPRINT.md` nowhere and compared the `Dialect`/`Condition` enums against literal sets typed into the test, so an eighth §8.1 condition or a fourth dialect was invisible — while this row claims "(3 dialects × 7 conditions)" implements §8.1's list. §8.1's coverage line is now parsed out of the frozen blueprint with set equality both ways, as `test_registry.py` has always done for §7. The phrase→member mapping is **explicit** rather than counted, because §8.1 yields **nine** items against a **seven**-member enum: "Kurdish–English and Kurdish–Arabic code-switching" is one phrase covering two members — the same shape as §4.1's single "Numerals" row, which is exactly how M0.3 came to claim five collisions handled when four were (D-076). Separately, `MINIMUM_HOURS` was referenced by **no test**, so D-009's recorded 3.0 could drift from the code — 3.0→1.0 left the whole suite green; the value is now parsed from D-009's heading, so changing the floor requires amending the record. 4/5 mutations on the grid plus the floor drift caught; the survivor is D-078's neutral class (retyping the parse is unobservable while the blueprint is frozen). `BLUEPRINT.md` was touched to simulate §8.1 growing and restored, verified by sha256 and `git status`. The stale `(19 tests)` count is dropped rather than restated. `evidence/section-8-1-grid-self-certifying.md`. |
| M0.7 | ASR adapter interface + throughput harness: RTF, peak VRAM, long-audio failure rate | DONE | `src/hawedit/asr.py` + `tests/test_asr.py`. `Hardware` is required and cross-hardware comparison is refused per §3 Stage 1; failures are recorded not raised; every measurement names its adapter class. |
| M0.8 | Alignment-accuracy metric against CTC emissions (§8.1 last metric) | DONE | `src/hawedit/alignment.py` + `tests/test_alignment.py`. Kurdish invariant #5 enforced at construction in `AsrProvenance`/`RawTranscript`, not just at scoring. |
| M0.9 | Benchmark runner → comparable report JSON + §8.1 decision rule (LLM-7B stays canonical unless material gain) | DONE | `src/hawedit/bench.py` + `tests/test_bench.py`. Five clauses enforced, per-dialect always reported alongside the aggregate, thresholds recorded in D-010. |
| M0.10 | Diarization benchmark: Community-1 vs 3.1 DER on Kurdish multi-speaker material | PARTIAL | `src/hawedit/diarization.py` + `tests/test_diarization.py`. DER with optimal speaker mapping and a reported breakdown, plus §8.1's boundary-reconciliation metric against word alignment. Control-model handling: D-011. **Shortfall (audit #10):** this is the *metric*, not the benchmark. No DER has been computed on Kurdish multi-speaker material — that needs the gated Community-1 weights (`BLOCKED.md` #4) and multi-speaker audio (`BLOCKED.md` #1, #6). The task as written is not done and cannot be until both clear. |
| M0.11 | Real-model adapters (`LLM_7B_v2`, `CTC_3B_v2`, `LLM_Unlimited_3B_v2`, `rzgar-ckb-v1`, Gemini native audio) | PARTIAL | Canonical LLM-7B + CTC-3B/Viterbi and the rzgar validator are composed behind official loaders and have run through the Windows WSL2 CLI route on hawapc01. **Shortfall:** Unlimited-3B and Gemini native-audio benchmark adapters remain absent; Gemini also needs `BLOCKED.md` #3. |
| M0.12 | Labelled Sorani audio set — several hours, per §8.1 category list | BLOCKED | `BLOCKED.md` #1 |
| M0.13 | Benchmark executed on real Kurdish audio on hawapc01; numbers recorded | BLOCKED | `BLOCKED.md` #1 (no labelled audio). The executable canonical route now exists through WSL2 on the same 2×24 GiB host; no CER/RTF is claimed until the real corpus run exists. |
| M0.14 | Public-corpus importer (Common Voice `ckb`) producing an interim, unlabelled manifest | DONE | `src/hawedit/corpus_import.py` + `tests/test_corpus_import.py`. Refuses to invent dialect, condition or duration. Authorised in D-012. **Correction 2026-08-09:** the fourth refusal — locale — was skipped for any row whose `locale` was absent or blank, so a Kurmanji split imported clean under a `ckb` provenance built from the parameter rather than the data (measured: 2 items, `reference_ckb='Ev pir bas e'`). Fixed and mutation-audited 3/3; the over-strict direction is held by an honest-`ckb` control. D-103, `evidence/common-voice-locale-bypass.md`. |
| M0.15 | Measure §4.1 collision incidence on real Sorani | DONE | `src/hawedit/collisions.py` + `evidence/collision-incidence.md` — 24,894 real entries; 0.21% of distinct forms would have failed to match. Surfaced a collision §4.1's table omits (D-013). Driven by `scripts/measure_collisions.py`. |
| M0.16 | Download the interim audio corpus | BLOCKED | `BLOCKED.md` #1 — the route itself is gone, not merely unreachable. #6 tracked whether the hosts answered, and from here they do; the corpus does not. Common Voice moved to Mozilla Data Collective in October 2025 (account + accepted terms, which is Hawa's to click, not mine); OpenSLR has **0 Kurdish resources of 156**; `facebook/omnilingual-asr-corpus` is CC-BY-4.0 and ungated but ships **349 configs with no `ckb`**; the two ungated ckb candidates that remain have **no licence** — a D-002 hard reject — and one of them has no audio column at all. Measured, see `BLOCKED.md` #1 §"Option 3 closed". I marked this TODO earlier today on the strength of the hosts answering 200; that was true and it was the wrong question. The importer (M0.14) is built, tested, and has nothing to import. |

**M0 cannot be closed while M0.12/M0.13 are blocked.** The harness is buildable and testable
without the audio; the *measurement* — which is what M0 exists to produce, and what every
downstream threshold depends on — is not. See `BLOCKED.md`.

## M1 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M1.1 | §4.2 Viterbi forced alignment on CTC emissions, in-house per §7 | DONE | `src/hawedit/forced_alignment.py` + `tests/test_forced_alignment.py`. Monotone, non-overlapping words and failures are explicit. |
| M1.4 | Canonical ASR worker, model readiness and reproducible WSL environment | PARTIAL | `src/hawedit/asr_worker.py`, `src/hawedit/models.py`, `src/hawedit/wsl_asr_locks.py`, and `src/hawedit/smoke.py`. The exact CPython 3.12.0 generation is live on Ubuntu WSL with 140 distributions, all 43.5 GB of canonical assets and two CUDA devices revalidated; the dependency/VEX gate accepted that same receipt. **Shortfall:** this exact generation still needs a fresh end-to-end transcript run over representative Sorani audio and the labelled quality corpus remains blocked. `evidence/wsl-asr-live-acceptance-2026-08-09.md`. |
| M2.1 | Stage 0 media ingestion through sentence indexing | DONE | `src/hawedit/ingest.py`, `src/hawedit/sentences.py`, and `src/hawedit/index.py`. Shot/VAD evidence becomes complete sentence-indexed transcript material. |
| M2.2 | Candidate discovery and the immutable clip contract | DONE | `src/hawedit/discovery.py` and `src/hawedit/clip.py`. Discovery provenance, human QC and renderability invariants fail closed. |
| M2.3 | Pixel-grounded confidential editorial judgment | PARTIAL | `src/hawedit/credentials.py`, `src/hawedit/gemini.py`, `src/hawedit/judge.py`, and `src/hawedit/keyframes.py`. Actual keyframe bytes, strict schemas, route governance and no-replay billing are composed. **Shortfall:** live confidential Vertex acceptance remains external. |
| M4.1 | Full-transcript verbal discovery | DONE | `src/hawedit/path_a.py`. Strict hosted-model replies become bounded verbal candidates. |
| M5.1 | Extract-once visual retrieval, reranking and survivor composition | PARTIAL | `src/hawedit/visual_index.py`, `src/hawedit/video_input.py`, `src/hawedit/qwen_visual.py`, and `src/hawedit/visual_pipeline.py`. Top-50 retrieval, keep-5–10 reranking, sequential GPU release and the measured eight-frame reader plan are composed. **Shortfall:** real-episode Recall@K remains M7. |
| M5.2 | VideoChat3 reads only reranked visual survivors | PARTIAL | `src/hawedit/path_b.py` and `src/hawedit/video_reader.py`. Evidence attribution and bounded reader input are enforced. **Shortfall:** diverse real Sorani footage acceptance remains open. |
| M6.1 | TimeLens evidence and sentence-hard boundary fusion | PARTIAL | `src/hawedit/timelens.py` and `src/hawedit/video_grounding.py`. Evidence is shifted to media time and cannot become an unbounded cut. **Shortfall:** real-footage temporal accuracy remains M7. |
| M6.2 | Confidence/disagreement escalation policy | DONE | `src/hawedit/escalation.py`. Exact finite thresholds route only eligible aligned regions to the validator. |

> **M6.3 composition amendment.** The runner now grounds only scene windows overlapping the
> selected candidate, using the selected canonical transcript slice as the non-empty query. It
> fuses only intervals relevant to the sentence anchors. The remaining shortfall is real-footage
> accuracy, not pipeline wiring (`BLOCKED.md` #1).

> **Adversarial production-hardening amendment (D-105–D-110).** Human review can no longer be
> replaced by an automatic QC flag; hosted-model numeric fields are exact-type and finite; every
> frame extraction owns a private namespace; render duration has a one-frame upper as well as
> lower bound; canonical transcript publication is serialized for readers and competing writers;
> and known visual component refusals reach the runner's `StageSkipped` report. Reproductions and
> executable controls: `evidence/adversarial-production-hardening.md`.

| M3.4 | §8.3's third render-regression bullet: the boundary invariant asserted on every **shipped** clip | DONE | `render.py` (`assert_encoded_span`, `frame_duration_ms`) + `boundary.py` (`media_duration_ms`) + `tests/test_render.py`, `tests/test_boundary.py`. The invariant had been asserted on the `Clip` object; `RenderResult.duration_ms` was the request echoed back and the file was never opened. Measured: requesting 8000 ms of a 4162 ms source makes ffmpeg exit 0 and write 4180 ms. The new check immediately caught the runner's own end-to-end fixture — §3 Stage 5's 200 ms tail pushed `final_out` 138 ms past the end of the file, so **every `run_pipeline` render had been silently truncated** while the suite stayed green (`evidence/m3-4-shipped-clip-invariant.md`). D-040. |

| M3.5 | Captions timed to the clip, and a burn that refuses an ASS with nothing to draw | DONE | `captions.py` (`clip_in_ms`, `parse_dialogue_times`, `assert_captions_within_clip`) + `tests/test_caption_timing.py`. **The most serious defect found so far.** `build_ass` wrote source-absolute timestamps and `render_clip` burns into a stream already cut at `clip.in_ms`. Measured on a 1.6 s clip taken from source 2000 ms: **0 bytes** differ between a captioned and an uncaptioned render — libass drew nothing, ffmpeg exited 0, and the output is a valid, playable, caption-free MP4. Kurdish invariant #4 was absent from every clip not starting near zero. The existing pixel test is the right test; its fixture cuts at 300 ms with words at 0–1600, the one input where the bug is invisible. `evidence/m3-5-caption-timeline.md`, D-041. |

| M3.6 | §2's delivery set complete: SRT and EDL alongside the MP4, ASS and §5 JSON | DONE | `src/hawedit/delivery.py`, `src/hawedit/artifact_bundle.py` and real-media pipeline tests. SRT uses the clip timeline; EDL source fields use the source timeline while record fields start at zero. NTSC 30000/1001 writes SMPTE drop-frame labels, including `00:00:59;29 → 00:01:00;02`, tenth-minute/hour boundaries, `FCM: DROP FRAME`, and equal quantized source/record durations; other unsupported fractional rates refuse. **Amended 2026-08-09 (D-083):** the five files are staged privately, flushed, validated as one exact non-empty set, and published by a single directory rename. The public render result is withheld until that succeeds. Write failures leave no public partial set; a two-worker race yields one complete unmixed winner. `evidence/m3-6-delivery-set.md`, `evidence/m3-6-drop-frame-edl.md`, `evidence/atomic-delivery-bundle.md`, D-042/D-082/D-083. |
| M3.7 | Reproducible, provenance-bound wheel publication | PARTIAL | `src/hawedit/release.py` + `tests/test_release.py`. `hawedit-release` requires clean Git `HEAD`, derives `SOURCE_DATE_EPOCH` from the commit, builds twice, refuses unequal wheel bytes, validates runtime data, and atomically publishes a write-once release directory. **Amended 2026-08-09 (D-084):** that directory includes deterministic SPDX 2.3 JSON covering the exact wheel checksum, bundled Noto font checksum/OFL relationship, and every declared base/optional dependency from wheel METADATA. It does not pretend unbundled requirements are resolved. `SHA256SUMS` covers the wheel, SBOM and provenance; the independent `spdx-tools 0.8.5` parser/validator accepts the result. **Amended 2026-08-09 (D-090):** the two builds no longer inherit an ambient backend. The command creates a private builder from exact, official-wheel-hashed Pip 26.2.1 and Setuptools 84.0.0 requirements, refuses drift against `[build-system]`, and records the measured Python/frontend/backend plus lock digest in provenance. Measured on one clean revision, two formerly allowed Setuptools versions emitted different wheel hashes and 68.2.2 could not build at all (`evidence/release-builder-lock.md`). Remote CI actions are full-commit pinned (`evidence/ci-actions.md`, `evidence/release-sbom.md`). **Shortfall:** D-113 defines an isolated GitHub-OIDC attestation path for the exact release set, but a post-merge protected-`main` run has not yet produced and verified its first live attestation. There is no version/tag policy or durable GitHub Release. CPU base/gate/model-fetch transitives are hash-locked; CUDA/GPU and native WSL build outputs are not. Deterministic source-to-wheel output, component disclosure, production-gate binding, project-managed checkpoint bytes and package-managed OmniASR bytes are closed—not the entire external supply chain. |

> **M3.7 dependency amendment (D-094).** Every direct GPU/cloud dependency is exact and the
> vulnerable Pytest 8.3.4 development pin is now 9.1.1. One clean host-extras
> (`dev,media,cloud,gpu`) Python 3.12
> environment passes 1,237/1,237 with zero skips. This closes direct-version drift, **not**
> transitive hash locking; that remains part of M3.7's supply-chain shortfall.

> **M3.7 checkpoint amendment (D-096).** The five accessible project-managed Hugging Face snapshots
> now have an exact packaged byte manifest enforced before load. This reduces that part of the
> external-model supply chain; it does not close gated pyannote identities, release signing,
> or transitive environment locking. Package-managed OmniASR identities are closed separately in
> D-101 below.

> **M3.7 promotion amendment (D-100).** Publication now requires an explicit successful official
> `main` push run of `.github/workflows/gate.yml` for the exact clean release SHA. The API, exported
> Python function and CLI all fail closed before creating a builder or output directory when the
> run, repository, workflow, branch, event, SHA, attempt, job or any mandatory step is wrong. The
> exact run/job is recorded in schema-4 provenance. Redirects are refused before authorization can
> cross hosts. Both wheel builds consume separate pristine `git --no-replace-objects archive`
> exports of the verified SHA, so live-worktree races and build-1 residue cannot enter or stabilize
> the artifact. `evidence/release-exact-gate.md`.

> **M3.7 OmniASR amendment (D-101).** The canonical 43.5 GB LLM-7B/CTC-3B/tokenizer set now has
> exact packaged URL/cache-key/size/SHA-256 identities enforced during atomic setup and before every
> model load. Runtime also pins and hashes the official card document, disables system/user card
> sources, validates the effective bare tokenizer reference and refuses extra cache members or a
> tampered ready worker snapshot. Verified descriptors remain open and are the paths consumed by
> both real fairseq2 model loaders; stale readiness is invalidated before setup mutation. Unlimited-3B
> remains absent rather than being claimed from a card name alone.
> `evidence/omniasr-asset-integrity.md`.

> **M3.7 authenticity amendment (D-113).** A successful official `gate` push on `main` now feeds a
> permission-separated release workflow. Repository code builds with a read-only token; fresh
> no-checkout 3.11/3.12 jobs install and execute the exact wheel; a final fresh job independently
> validates the exact four-file transport, binds schema-4 provenance to the event, and alone
> receives GitHub OIDC/attestation authority. Attestation and final upload receive the same
> explicit allowlist. The workflow and actions are locally linted and contract-tested, but the
> live hosted acceptance gate remains open until this workflow is on default `main` and all four
> downloaded files pass `gh attestation verify`. `evidence/release-attestation.md`.

> **M3.7 Python/install amendment (D-116).** The supported host range is honestly capped at Python
> 3.11–3.12 because the pinned base graph and official ASR stack do not resolve on 3.13. The
> required `gate` cannot pass until a full 3.12 zero-skip prerequisite passes, and release
> attestation cannot start until fresh no-checkout 3.11/3.12 venvs install the exact wheel, pass
> `pip check`, resolve package data and start all seven CLIs. Local current-wheel smokes pass; hosted
> execution awaits default `main`. `evidence/python-support.md`.

> **M3.7 host-lock amendment (D-122).** Twelve code-digest-bound locks cover base, canonical
> gate and isolated model-fetch environments on Linux/Windows CPython 3.11/3.12. Setup, both CI
> Python versions and release smoke install only exact wheel hashes and audit the full inventory;
> wheel data is located and authenticated through raw `RECORD`, including real `pip --target`
> relocation. Windows 3.11/3.12 and source/wheel/model-fetch paths are measured; Linux is
> resolver-verified and exercised by CI. CUDA remains a separate open lock.
> `evidence/host-dependency-locks.md`.

| M1.8 | Windows private checkpoint staging and hard-crash resume | DONE | `src/hawedit/windows_security.py` + `src/hawedit/model_fetch.py` + `tests/test_model_fetch.py`. Fresh directories receive protected native DACLs at creation; root/member owner and ACEs are revalidated, `Everyone:F` is refused, and one revision-specific private tree survives hard process death. `evidence/checkpoint-provisioning.md`, D-124. |
| M3.10 | Code-bound host dependency locks | DONE | `src/hawedit/host_lock_hashes.py` + `src/hawedit/environment.py` + twelve `requirements/host-*.txt` locks + `tests/test_host_dependencies.py`. CPU base, gate and model-fetch environments are exact wheel-hash graphs for Linux/Windows Python 3.11/3.12. `evidence/host-dependency-locks.md`, D-122. |
| M3.8 | Package-managed OmniASR model/tokenizer byte and card-policy integrity | DONE | `src/hawedit/omni_assets.py` + `tests/test_omni_assets.py`, integrated by `asr.py` and `wsl_setup.py`. Exact identities, atomic verified first download, no-follow full rehash, descriptor-bound real model loading, private empty card sources, effective metadata equality and atomic ready-worker identity are enforced. `evidence/omniasr-asset-integrity.md`, D-101. |

| M3.9 | WSL-ASR dependency vulnerability disposition gate | DONE | `src/hawedit/vex.py`, `src/hawedit/wsl_audit_locks.py`, `src/hawedit/wsl_vex_gate.py`, `security/wsl-asr-vex.json` and their tests. The protected hardware path installs an exact 29-wheel scanner in an isolated WSL environment, requires pip-audit 2.10's exact object schema, revalidates the canonical receipt/assets, and evaluates captured policy bytes bound to the complete 140-distribution identity, lock digests, assets and HawEdit source digest. On 2026-08-09 the live two-GPU Ubuntu runtime accepted all 12 audited findings against 12 explicit dispositions; this is affected/mitigated evidence, not a vulnerability-free claim, and the policy expires 2026-09-08. `evidence/wsl-asr-live-acceptance-2026-08-09.md`, `evidence/wsl-asr-vex.md`, D-123/D-142. |

> **M1.4/M3.8 runtime-receipt amendment (D-111/D-112).** WSL readiness is now a schema-2
> receipt over one exact worker snapshot and one versioned/revalidated venv generation, not a
> plain flag over a shared mutable environment. Setup is serialized across processes; launch
> re-hashes source and live-probes the recorded interpreter, packages, assets and CUDA route;
> `ModelStore` no longer equates importability with readiness. Predictable transcript/setup/model
> locks refuse link/reparse/replacement attacks and use explicit long Windows retry.
> `evidence/wsl-runtime-receipt.md`.

## M7 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M7.1 | §8.2 metrics: per-path Recall@20, temporal IoU, sentence-completeness, misleading-edit rate, pairwise preference, cost/wall-clock per source hour | DONE | `src/hawedit/repurposing.py` + `tests/test_repurposing.py`. `path_unique_wins` answers §8.2's collapse question directly. Definitions: D-020. **Amended 2026-08-09 (D-077), found by the adversarial pass:** for a gold set with no winners `recall_at_k` returned `None` and `recall_at_k_by_path` returned `{}` — both meaning unmeasured — while `path_unique_wins` returned `{verbal: 0, visual: 0, both: 0}`, which §8.2's collapse test reads as licence to delete a path. Unmeasured now returns `{}`, matching the sibling; a *measured* zero is still reported for every path, because that zero is the collapse finding, and the control pins it. **Gap opened by D-077 and closed by D-080:** every recall surface and the Stage 3 merge now refuse thresholds outside `(0, 1]`, including zero, NaN, infinities, booleans and strings, before any empty-set return; Recall@K also refuses non-positive, boolean and fractional K. Zero is excluded because disjoint spans have IoU zero and would otherwise match. This validates configuration without claiming the threshold is tuned—M7.3 still depends on the labelled set. `evidence/metric-parameter-validation.md`, `evidence/iou-threshold-validation.md`. |
| M7.2 | 200–500 human-reviewed candidates labelled per §8.2 | BLOCKED | Needs human annotators and real footage — same dependency as `BLOCKED.md` #1. **The harness for the set exists and the set does not** (named here as of D-069): `src/hawedit/editorial_bench.py` + `tests/test_editorial_bench.py` load a labelled set, evaluate it and emit a promotion report, exposed as `hawedit-editorial-bench`. Measured: **0 labelled sets on disk**, and `assert_real` refuses an empty one (`editorial set has 0 items; the promotion floor is 20`) and refuses an interim one outright (`an interim editorial set cannot be reported as production evidence`), so the harness cannot be made to print a number it did not measure. Note the two floors are different questions: `MIN_REGRESSION_ITEMS = 20` is §3's bar for *promoting a judge model*, while this row's 200–500 is §8.2's bar for *tuning thresholds* — clearing the first would not close this row. `evidence/unlisted-modules.md`. |
| M7.3 | Threshold tuning against the labelled set | TODO | Depends on M7.2 — an unstarted task, not an external blocker. Every threshold in `DECISIONS.md` marked "awaiting real data" is tuned here. |

## M8 — task ledger

§9's M8 is *"Auto-reframe (SAM 3 / Molmo2)"*, and both models remain `BLOCKED.md` #9. §3 Stage 6
says to add SAM 3 **only if** face-centred cropping proves insufficient on real footage, so the
face-centred attempt is M8's own prerequisite rather than a substitute for it, and it gets a row.

| Task | Deliverable | Status | Evidence |
|---|---|---|---|
| M8.1 | Face-centred vertical tracking — §3 Stage 6's prerequisite for judging whether SAM 3 is needed | PARTIAL | `src/hawedit/reframe.py` + `tests/test_reframe.py`. `OpenCvFaceTracker` samples at 2 fps, picks a continuous dominant face through `choose_face`, smooths the path over 5 samples and drives a time-varying crop expression; `render_clip` labels the result `Reframe.FACE_TRACKED` when points come back and `Reframe.STATIC_CENTRE` when they do not, so the artifact never claims tracking it did not do. Wired into `pipeline.py` behind `--face-reframe`. **This row previously existed only as a prose amendment under M3.3 with no status and no filename** — invisible to the tally and to any test, which is what D-069 closes. **Shortfall (two).** Measured on the only footage in this checkout — `tests/fixtures/kurdish-speech-3cuts.mp4` — the tracker returns **0 focus points**, correctly, because the fixture is coloured digits and contains no face. So the fallback is exercised on real pixels and the tracked path is not; whether the smoothing holds on a real speaker is unmeasured and needs `BLOCKED.md` #1 (`evidence/unlisted-modules.md`). And `choose_face` associates nothing to *speech*: with two faces it follows the larger/more continuous one, which §3 Stage 6 explicitly does not sanction — active-speaker association needs Community-1 (`BLOCKED.md` #4). Not a SAM 3 substitute; §9's M8 stays blocked. |

## Production-hardening amendments - 2026-08-09

- **M0.1 / D-117:** the earlier import-token repair was insufficient: a purpose-built executable
  could forge it. The gate now accepts only this checkout's path-identical canonical `.venv`, then
  verifies editable-root/distribution identity, supported Python/project versions and exact active
  requirements. A clean Python 3.12.13 environment passes; the shared stale venv is correctly
  refused. `evidence/environment-identity.md`.
- **M1.4 / M3.8 / D-119:** the WSL source receipt now includes the exact trusted checkpoint
  manifests used by Qwen-ASR. Prior valid receipts remain usable during/after failed reprovision;
  result publication is random, no-follow, single-link and descriptor-bound.
  `evidence/wsl-runtime-receipt.md`.
- **M1.6 / D-120/D-124:** resumed checkpoint trees are recursively validated before any third-party
  downloader writes through them. Fresh roots are unpredictable, then atomically become a
  revision-specific 0700/protected-DACL resume tree which survives hard process death. Planted
  hardlinks and real Windows `Everyone:F` access are refused before download.
  `evidence/checkpoint-provisioning.md`.
- **M1.6 / D-121:** `hawedit-fetch-models` is now shipped in the wheel. The checkout shell file is
  a thin wrapper around the same transaction; neither path installs or upgrades its own download
  client. Installed-package metadata remains the trust root while the model directory contains
  only mutable weights. `evidence/checkpoint-provisioning.md`.
- **M2.7 / M2.8 / M5.5 / M6.3 / D-118:** expected ASR, Path A, Path B, keyframe, judge, TimeLens,
  render/delivery and tracker failures stop at their named stage. Empty auto-selection performs no
  Stage 4 work; candidate traversal is refused before filesystem use; lazy credential/model
  failures make no transport/billed call. Every exception-derived JSON reason is printable and
  bounded, while assertions/schema errors remain visible. `evidence/pipeline-failures.md`.

These amendments close code-solvable failure/reporting gaps. They do **not** close CUDA/GPU
dependency locking, WSL native-build provenance/live VEX enforcement, real Sorani/editorial
measurements, confidential Vertex acceptance, the real 5-or-more-scene visual happy path,
pyannote access, or real-speaker reframing.

## Upstream adversarial-pass amendments - 2026-08-09

- **M0.1 / D-125/D-127:** canonical environment identity is now paired with gate-tool origin
  validation, and the passed-test floor is idempotent when legitimate skips exist. A forged
  `pytest` can neither mint JUnit evidence nor poison the ratchet.
- **M0.4 / D-139:** every claimed write-once transcript enforcement route is reached by its own
  mutation-sensitive regression; the ledger no longer counts prose as an enforcement layer.
- **M0.7/M0.11 / D-135:** one failed ASR region becomes `UnalignedSpeech` instead of deleting a
  completed episode. Successful regions still pass through confidence/disagreement routing and
  preserve validator provenance. Real Sorani accuracy remains blocked on the labelled corpus.
- **M0.9 / D-126/D-130:** serialized benchmark reports must carry the exact per-dialect values that
  justify their aggregate, and decision thresholds are pinned to their executing constants.
- **M1.4 / D-131/D-132:** checkpoint readiness requires both exact verified bytes and a loadable
  architecture runtime; the human report is derived from structured status, including zero sizes.
- **M2/M3 / D-133:** `editing.json` carries the actual verbal/visual/union discovery path rather
  than inferring one from the presence of transcript text.
- **M1.4 / D-134:** every WSL invocation uses the shared `--exec` prefix, including setup, receipt
  probes, Stage 1 worker launch and the live vulnerability gate.
- **M5.4 / D-136/D-137:** raw ffmpeg delivery is checked before parity trimming inside its private
  attempt directory, and the visual phase now assigns VideoChat3 to GPU 0 while Stage 2 and
  TimeLens use GPU 1.
- **M5.4 / D-138 remains PARTIAL on acceptance, not composition:** the production 3090 Ti reads at
  most eight VideoChat3 frames (eight succeeded at 21.57 GiB; nine OOMed). Composed Path B now
  plans gap-free scene windows to that measured capacity while preserving the blueprint's general
  64-frame ceiling; reader-side truncation remains prohibited. The remaining proof is a real
  full-episode rerun measuring retrieval quality, cost and peak memory with the increased window
  count.
- **Ledger / D-128/D-129:** unenforced per-file test counts were removed as claims, and promotion
  evidence distinguishes real reviewed checkpoints from test stubs.

## Deferred with reason

| Item | Deferred to | Reason |
|---|---|---|
| ~~§5 clip contract~~ | ~~M1–M2~~ | **Delivered in M2.2** — boundary fusion gave it a producer. Kurdish invariant #2 is enforced at fusion and again at the render gate. |
| Conjunctive `و` separation (§4.1) | M1 | Not implemented by KLPT `normalize` — measured, see `DECISIONS.md` D-003. |
