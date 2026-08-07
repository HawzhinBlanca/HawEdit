# PROGRESS — Kurdish Video Repurposing System

Generated from `BLUEPRINT.md` §9 (Build order). **The agent never marks a task DONE by
judgment**: DONE requires code + test + the gate green + evidence linked below.

- Gate: `bash hawedit2/scripts/verify.sh` (lint + format + typecheck + tests)
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
| **M0** | ASR benchmark harness + labelled Sorani audio set | Everything | **harness built and gated (M0.1–M0.10) · M0.10 PARTIAL, see the ledger · every measurement BLOCKED (M0.11–M0.13, M0.16)** |
| **M1** | Stage 0 + Stage 1 → raw/normalized transcript with word timings | M2 | **WIP — Stage 0 runs on real media (minus diarization); §4.2 aligner, segmentation and §4.1's last collision DONE; Stage 1 models blocked** |
| **M2** | Vertical slice: transcript → BM25 → Gemini → manual boundary → one rendered clip | Proves the concept | **WIP — index, boundary fusion, §5 contract and a real rendered clip DONE; only Gemini (Stage 3) is still missing from the slice** |
| **M3** | Stage 6 render path with verified RTL captions + golden test | Client delivery | **WIP — §4.3 DONE incl. golden test; encode runs (M3.3 PARTIAL — static crop, no NVENC)** |
| **M4** | Stage 3 Path A (full-transcript discovery) | Verbal recall | TODO |
| **M5** | Stage 2 visual index + Stage 3 Path B | Visual recall | TODO |
| **M6** | Stage 5 TimeLens2 + sentence-hard fusion | Boundary precision | TODO |
| **M7** | Repurposing eval set + threshold tuning | Quality gates | **WIP — §8.2 metrics DONE; the 200–500 labelled candidates need humans** |
| **M8** | Auto-reframe (SAM 3 / Molmo2) | Vertical formats | TODO |

## M0 — task ledger

M0 decomposed from §8.1 (ASR benchmark) + §4.1 (normalization is a prerequisite of
"normalized CER"). Decomposition is task breakdown, not architecture change.

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M0.1 | Package skeleton + gate script; gate refuses a no-op command instead of printing green | DONE | `tests/test_gate.py` (9 tests) · gate green: `VERIFY OK — hawedit2 gate green` · found + fixed 2 real gate defects, see D-005 |
| M0.2 | §7 model registry in code; model outside §7 rejected; NC licence hard-rejected | DONE | `src/hawedit2/registry.py` + `tests/test_registry.py` (15 tests). The tests **parse §7 out of `BLUEPRINT.md`** and assert exact set equality both ways, so a model added in code but not in the blueprint fails the gate. |
| M0.3 | §4.1 Sorani normalization via KLPT; every §4.1 collision asserted in a test | DONE | `src/hawedit2/normalize.py` + `tests/test_normalize.py` (13 tests) + `tests/test_waw.py` (18 tests). **All five §4.1 collisions are now handled**: four by KLPT (D-003), the fifth — conjunctive `و` — by M1.7 against KLPT's dictionary (D-026). Promoted from PARTIAL, which it was marked after audit #10. |
| M0.4 | Kurdish invariants #1 and #3 in code: `transcript.raw.json` write-once, model inputs read `norm` | DONE | `src/hawedit2/transcripts.py` + `tests/test_transcripts.py` (17 tests). #1 enforced three ways (refuse-rewrite, frozen types, SHA-256 tamper evidence); #3 enforced by distinct types (mypy) + `assert_model_input` (runtime) + stale-norm detection. ASR provenance is validated against §7 at construction. |
| M0.5 | §8.1 accuracy metrics: normalized CER, spacing-free CER, named-entity error, code-switch error | DONE | `src/hawedit2/metrics.py` + `tests/test_metrics.py` (26 tests). Definitions §8.1 left open are recorded in D-008. Unmeasured returns `None`, never 0.0. |
| M0.6 | Labelled-corpus manifest + §8.1 coverage validation (3 dialects × 7 conditions), per-dialect never aggregated away | DONE | `src/hawedit2/corpus.py` + `tests/test_corpus.py` (19 tests). Missing cells are named, not counted; hours are reported per dialect per §4.4; the hours floor is D-009. |
| M0.7 | ASR adapter interface + throughput harness: RTF, peak VRAM, long-audio failure rate | DONE | `src/hawedit2/asr.py` + `tests/test_asr.py` (14 tests). `Hardware` is required and cross-hardware comparison is refused per §3 Stage 1; failures are recorded not raised; every measurement names its adapter class. |
| M0.8 | Alignment-accuracy metric against CTC emissions (§8.1 last metric) | DONE | `src/hawedit2/alignment.py` + `tests/test_alignment.py` (12 tests). Kurdish invariant #5 enforced at construction in `AsrProvenance`/`RawTranscript`, not just at scoring. |
| M0.9 | Benchmark runner → comparable report JSON + §8.1 decision rule (LLM-7B stays canonical unless material gain) | DONE | `src/hawedit2/bench.py` + `tests/test_bench.py` (16 tests). Five clauses enforced, per-dialect always reported alongside the aggregate, thresholds recorded in D-010. |
| M0.10 | Diarization benchmark: Community-1 vs 3.1 DER on Kurdish multi-speaker material | PARTIAL | `src/hawedit2/diarization.py` + `tests/test_diarization.py` (16 tests). DER with optimal speaker mapping and a reported breakdown, plus §8.1's boundary-reconciliation metric against word alignment. Control-model handling: D-011. **Shortfall (audit #10):** this is the *metric*, not the benchmark. No DER has been computed on Kurdish multi-speaker material — that needs the gated Community-1 weights (`BLOCKED.md` #4) and multi-speaker audio (`BLOCKED.md` #1, #6). The task as written is not done and cannot be until both clear. |
| M0.11 | Real-model adapters (`LLM_7B_v2`, `CTC_3B_v2`, `LLM_Unlimited_3B_v2`, `rzgar-ckb-v1`, Gemini native audio) | BLOCKED | `BLOCKED.md` #2 |
| M0.12 | Labelled Sorani audio set — several hours, per §8.1 category list | BLOCKED | `BLOCKED.md` #1 |
| M0.13 | Benchmark executed on real Kurdish audio on hawapc01; numbers recorded | BLOCKED | `BLOCKED.md` #1, #2 |
| M0.14 | Public-corpus importer (Common Voice `ckb`) producing an interim, unlabelled manifest | DONE | `src/hawedit2/corpus_import.py` + `tests/test_corpus_import.py` (12 tests). Refuses to invent dialect, condition or duration. Authorised in D-012. |
| M0.15 | Measure §4.1 collision incidence on real Sorani | DONE | `evidence/collision-incidence.md` — 24,894 real entries; 0.21% of distinct forms would have failed to match. Surfaced a collision §4.1's table omits (D-013). |
| M0.16 | Download the interim audio corpus | BLOCKED | `BLOCKED.md` #6 — every corpus host is denied by the container's network policy |

**M0 cannot be closed while M0.12/M0.13 are blocked.** The harness is buildable and testable
without the audio; the *measurement* — which is what M0 exists to produce, and what every
downstream threshold depends on — is not. See `BLOCKED.md`.

## M1 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M1.1 | §4.2 Viterbi forced alignment on CTC emissions, in-house per §7 | DONE | `src/hawedit2/forced_alignment.py` + `tests/test_forced_alignment.py` (22 tests). Monotone non-overlapping spans, every token framed, infeasible input refused rather than guessed. No new dependency. |
| M1.2 | §4.2 sentence segmentation (Kurdish punctuation **plus** VAD pauses) + §5 anchors | DONE | `src/hawedit2/sentences.py` + `tests/test_sentences.py` (17 tests). Pause path works on wholly unpunctuated input; `anchors_for` returns `None` rather than a guess when nothing is complete. Threshold: D-014. |
| M1.3 | Stage 0 ingest: ffmpeg demux, PySceneDetect, Silero VAD, diarization | PARTIAL | `src/hawedit2/ingest.py` + `tests/test_ingest.py` (20 tests) run against real media: `tests/fixtures/kurdish-speech-3cuts.mp4`, built from three 1.4 s segments so the cuts are known. Measured: shot detection on the **source** finds both cuts with **0 ms** error; on the 1 fps proxy it finds **none** (D-023). VAD returns the two utterances, returns nothing on silence, and every segment of a 62 s file stays under the 38 s ceiling. **Shortfall:** diarization is not run — `IngestResult.diarization` is `None`, never `[]` — pending the gated Community-1 repo (`BLOCKED.md` #4). |
| M1.6 | Model provisioning: readiness report + registry-driven fetcher | DONE | `src/hawedit2/models.py` + `tests/test_models.py` (21 tests) + `scripts/fetch-models.sh`. `python -m hawedit2.models` reports all 15 §7 components. Sources §7 leaves open are refused, not guessed (D-022). |
| M1.7 | §4.1 conjunctive `و` separation (the collision KLPT does not cover) | DONE | `normalize.separate_conjunctive_waw` + `tests/test_waw.py` (18 tests). Rule: split `و`+R only if R is a valid Sorani word **and** `و`+R is not — a refusal, not a prediction. Measured over all 24,894 dictionary entries (`evidence/waw-separation.md`, D-026): **0 words damaged**, 98.91% of joined forms recovered, 19 `و`-initial words permanently unsplittable because they are words themselves. The 1.09% shortfall has one cause — bare medial `ه` U+0647 — which is D-013's finding seen through a second instrument. |
| M1.4 | Stage 1 speech: LLM-7B + CTC-3B in parallel, validator escalation | BLOCKED | `BLOCKED.md` #2 (GPU), #6 (weights unreachable) |
| M1.5 | Escalation rule: bottom log-prob quartile + LLM/CTC disagreement (§3 Stage 1) | DONE | `src/hawedit2/escalation.py` + `tests/test_escalation.py` (16 tests). §3's "never escalate on duration or word-count" prohibition asserted directly. Threshold: D-015. |

## M2 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M2.1 | §2 text index: BM25 + character 3-grams over normalized Sorani | DONE | `src/hawedit2/index.py` + `tests/test_index.py` (25 tests). The clitic-attachment failure §2 describes is measured: word BM25 scores the stem query **0.0**, n-grams retrieve it. Invariant #3 enforced at the index boundary. Weighting: D-016. |
| M2.2 | §5 clip contract + §3 Stage 5 boundary fusion + Kurdish invariant #2 | DONE | `src/hawedit2/boundary.py` (31 tests) + `src/hawedit2/clip.py` (20 tests). Invariant #2 checked exhaustively over 3,125 soft-input combinations and enforced again at an explicit render gate. Contract choices: D-017. |
| M2.3 | Stage 3 Path A (Gemini reads the full transcript) | BLOCKED | `BLOCKED.md` #3 — credentials + the Vertex ZDR governance decision |
| M2.4 | One rendered clip | DONE | `evidence/m2-4-rendered-clip.mp4` (1080×1920, 2.2 s) + `evidence/m2-4-frame.png` — a real vertical clip with Kurdish captions burned in, rendered by `src/hawedit2/render.py` + `tests/test_render.py` (21 tests). Was marked BLOCKED behind `BLOCKED.md` #5 for two days after #5 was resolved; `tests/test_claims.py` now fails on a BLOCKED row whose every blocker is resolved. |

## Kurdish invariants — where each is enforced

| # | Invariant | Enforced in |
|---|---|---|
| 1 | `transcript.raw.json` never mutated after write | `transcripts.py` — refuse-rewrite, frozen types, SHA-256 tamper evidence |
| 2 | `final_in <= anchor_in` and `final_out >= anchor_out`; `sentence_complete == false ⇒ reject` | `boundary.py` — by construction in `fuse_boundary`, and again at `assert_boundary_invariant` / `Clip.assert_renderable` |
| 3 | Indexes, embeddings and model inputs read `norm`, never raw | `transcripts.py` (types + `assert_model_input`), `index.py` (index boundary) |
| 4 | Captions render `shaping=complex`; build asserts libass has HarfBuzz; golden-image test in CI | `captions.py` — **fully enforced**. Shaping, stack check on a real build, font coverage on the real font, our own line breaks, and a golden render compared per gate run with `shaping=simple` as a failing negative control. Evidence: `evidence/rtl-shaping.md`. |
| 5 | Word timings from OmniASR CTC Viterbi alignment only | `alignment.py` + `transcripts.py` — refused at construction |

## M3 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M3.1 | §4.3 caption generation: shaping, stack check, font coverage, own line breaks | DONE | `src/hawedit2/captions.py` + `tests/test_captions.py` (33 tests). Font coverage asserted against the real OFL-1.1 Noto Naskh Arabic shipped in `assets/fonts` — full Kurdish coverage measured (D-018). |
| M3.2 | §4.3.6 golden-file render compared per build | DONE | `tests/golden/kurdish-caption.png` rendered on a verified libass build; compared on decoded pixels every gate run. `shaping=simple` must fail the same comparison — without that control the test measures nothing. D-021, `evidence/rtl-shaping.md`. |
| M3.3 | Stage 6 encode: crop/reframe + NVENC burn-in | PARTIAL | `src/hawedit2/render.py` + `tests/test_render.py` (21 tests). Cut, 9:16 crop, `shaping=complex` burn-in and x264 encode all run and are verified on decoded pixels: a captioned render must differ from an uncaptioned one, and a `shaping=simple` render must differ from the shipped one. **Shortfall:** §3 Stage 6 reframes by tracking the active speaker from diarization plus face detection; neither runs (`BLOCKED.md` #4), so the crop is static and says so — `Reframe.STATIC_CENTRE`, never `SPEAKER_TRACKED`. NVENC needs hawapc01 (`BLOCKED.md` #2) and is refused here rather than substituted. |

## M7 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M7.1 | §8.2 metrics: per-path Recall@20, temporal IoU, sentence-completeness, misleading-edit rate, pairwise preference, cost/wall-clock per source hour | DONE | `src/hawedit2/repurposing.py` + `tests/test_repurposing.py` (31 tests). `path_unique_wins` answers §8.2's collapse question directly. Definitions: D-020. |
| M7.2 | 200–500 human-reviewed candidates labelled per §8.2 | BLOCKED | Needs human annotators and real footage — same dependency as `BLOCKED.md` #1 |
| M7.3 | Threshold tuning against the labelled set | TODO | Depends on M7.2 — an unstarted task, not an external blocker. Every threshold in `DECISIONS.md` marked "awaiting real data" is tuned here. |

## Deferred with reason

| Item | Deferred to | Reason |
|---|---|---|
| ~~§5 clip contract~~ | ~~M1–M2~~ | **Delivered in M2.2** — boundary fusion gave it a producer. Kurdish invariant #2 is enforced at fusion and again at the render gate. |
| Conjunctive `و` separation (§4.1) | M1 | Not implemented by KLPT `normalize` — measured, see `DECISIONS.md` D-003. |
