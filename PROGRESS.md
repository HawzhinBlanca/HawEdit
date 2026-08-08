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
| **M0** | ASR benchmark harness + labelled Sorani audio set | Everything | **harness built and gated (M0.1–M0.10) · M0.10 PARTIAL, see the ledger · every measurement BLOCKED (M0.11–M0.13, M0.16)** |
| **M1** | Stage 0 + Stage 1 → raw/normalized transcript with word timings | M2 | **WIP — Stage 0 runs on real media (minus diarization); §4.2 aligner, segmentation and §4.1's last collision DONE; Stage 1 models blocked** |
| **M2** | Vertical slice: transcript → BM25 → Gemini → manual boundary → one rendered clip | Proves the concept | **WIP — index, boundary fusion, §5 contract and a real rendered clip DONE; only Gemini (Stage 3) is still missing from the slice** |
| **M3** | Stage 6 render path with verified RTL captions + golden test | Client delivery | **WIP — §4.3 DONE incl. golden test; encode runs (M3.3 PARTIAL — static crop, no NVENC); §8.3's shipped-clip invariant, the caption timeline and §2's full delivery set DONE (M3.4–M3.6)** |
| **M4** | Stage 3 Path A (full-transcript discovery) | Verbal recall | **DONE — delivered in M2.3 (`path_a.py`, 21 tests). The milestone row said TODO while its own ledger row said DONE; the drift is the point of the status legend and is corrected here.** |
| **M5** | Stage 2 visual index + Stage 3 Path B | Visual recall | **WIP — Stage 2's contract + scene-window plan and Stage 3 Path B's contract are DONE; the union runs two-sided on real media given a reader. Every model needs weights** |
| **M6** | Stage 5 TimeLens2 + sentence-hard fusion | Boundary precision | **WIP — sentence-hard fusion DONE (M2.2); the TimeLens2 contract and its relevance gate DONE; the model needs weights** |
| **M7** | Repurposing eval set + threshold tuning | Quality gates | **WIP — §8.2 metrics DONE; the 200–500 labelled candidates need humans** |
| **M8** | Auto-reframe (SAM 3 / Molmo2) | Vertical formats | **BLOCKED — `BLOCKED.md` #9. Neither SAM 3 nor Molmo2 is in §7, and §3 Stage 6 says to add SAM 3 *only if* face-centred cropping proves insufficient on real footage. Not startable, which is a different fact from not started.** |

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
| **Where §3 Stage 1 runs** (`BLOCKED.md` #11) | M0.11, M0.13, M1.4 — still the one thing between this and a runnable product, and now for a fourth reason. Not the GPU (#2, resolved), not the network (#6, resolved), not the repository id (#10, answered): the two canonical checkpoints are raw fairseq2 `.pt` files and `fairseq2n` ships no Windows wheel. WSL2 on this box has both GPUs and 740 GB free |
| The §3 ZDR governance answer (credentials themselves are now handled) | confidential material only — `gemini.Governance` refuses it until ZDR is configured and attributed |
| The gated `pyannote/speaker-diarization-community-1` repo | M0.10, M1.3, the speaker-tracked reframe in M3.3 — measured **401** from here, so the network opening did not touch it |
| Human annotators + real footage | M7.2, and M7.3 behind it |
| Hawa, one decision each | `BLOCKED.md` #7 (required CI check) · #9 (M8 names two models §7 does not contain) · #11 (where Stage 1 runs) · #8 and #10 answered, with `BLUEPRINT.md` §5 and §7 both needing the matching amendment (D-033, D-046) |

**Now available and simply not started** — no external dependency, ordinary work: M5.2, M5.4
and M6.3, the three model integrations, whose weights are downloading. **Not** M0.16: it was
listed here this morning and is BLOCKED again, because the hosts answering 200 turned out not
to be the question — the interim corpus itself is no longer publicly distributed. And M7.3
sits behind M7.2. The contracts they plug into are built and tested ahead of them, so landing each
is a matter of producing the type its stage already expects.

## M0 — task ledger

M0 decomposed from §8.1 (ASR benchmark) + §4.1 (normalization is a prerequisite of
"normalized CER"). Decomposition is task breakdown, not architecture change.

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M0.1 | Package skeleton + gate script; gate refuses a no-op command instead of printing green | DONE | `tests/test_gate.py` (9 tests) · gate green: `VERIFY OK — hawedit gate green` · found + fixed 2 real gate defects, see D-005 |
| M0.2 | §7 model registry in code; model outside §7 rejected; NC licence hard-rejected | DONE | `src/hawedit/registry.py` + `tests/test_registry.py` (15 tests). The tests **parse §7 out of `BLUEPRINT.md`** and assert exact set equality both ways, so a model added in code but not in the blueprint fails the gate. |
| M0.3 | §4.1 Sorani normalization via KLPT; every §4.1 collision asserted in a test | DONE | `src/hawedit/normalize.py` + `tests/test_normalize.py` (13 tests) + `tests/test_waw.py` (18 tests). **All five §4.1 collisions are now handled**: four by KLPT (D-003), the fifth — conjunctive `و` — by M1.7 against KLPT's dictionary (D-026). Promoted from PARTIAL, which it was marked after audit #10. |
| M0.4 | Kurdish invariants #1 and #3 in code: `transcript.raw.json` write-once, model inputs read `norm` | DONE | `src/hawedit/transcripts.py` + `tests/test_transcripts.py` (17 tests). #1 enforced three ways (refuse-rewrite, frozen types, SHA-256 tamper evidence); #3 enforced by distinct types (mypy) + `assert_model_input` (runtime) + stale-norm detection. ASR provenance is validated against §7 at construction. |
| M0.5 | §8.1 accuracy metrics: normalized CER, spacing-free CER, named-entity error, code-switch error | DONE | `src/hawedit/metrics.py` + `tests/test_metrics.py` (26 tests). Definitions §8.1 left open are recorded in D-008. Unmeasured returns `None`, never 0.0. |
| M0.6 | Labelled-corpus manifest + §8.1 coverage validation (3 dialects × 7 conditions), per-dialect never aggregated away | DONE | `src/hawedit/corpus.py` + `tests/test_corpus.py` (19 tests). Missing cells are named, not counted; hours are reported per dialect per §4.4; the hours floor is D-009. |
| M0.7 | ASR adapter interface + throughput harness: RTF, peak VRAM, long-audio failure rate | DONE | `src/hawedit/asr.py` + `tests/test_asr.py` (14 tests). `Hardware` is required and cross-hardware comparison is refused per §3 Stage 1; failures are recorded not raised; every measurement names its adapter class. |
| M0.8 | Alignment-accuracy metric against CTC emissions (§8.1 last metric) | DONE | `src/hawedit/alignment.py` + `tests/test_alignment.py` (12 tests). Kurdish invariant #5 enforced at construction in `AsrProvenance`/`RawTranscript`, not just at scoring. |
| M0.9 | Benchmark runner → comparable report JSON + §8.1 decision rule (LLM-7B stays canonical unless material gain) | DONE | `src/hawedit/bench.py` + `tests/test_bench.py` (16 tests). Five clauses enforced, per-dialect always reported alongside the aggregate, thresholds recorded in D-010. |
| M0.10 | Diarization benchmark: Community-1 vs 3.1 DER on Kurdish multi-speaker material | PARTIAL | `src/hawedit/diarization.py` + `tests/test_diarization.py` (16 tests). DER with optimal speaker mapping and a reported breakdown, plus §8.1's boundary-reconciliation metric against word alignment. Control-model handling: D-011. **Shortfall (audit #10):** this is the *metric*, not the benchmark. No DER has been computed on Kurdish multi-speaker material — that needs the gated Community-1 weights (`BLOCKED.md` #4) and multi-speaker audio (`BLOCKED.md` #1, #6). The task as written is not done and cannot be until both clear. |
| M0.11 | Real-model adapters (`LLM_7B_v2`, `CTC_3B_v2`, `LLM_Unlimited_3B_v2`, `rzgar-ckb-v1`, Gemini native audio) | BLOCKED | `BLOCKED.md` #11 (the checkpoints have no loader on Windows), #3 (Gemini). #10 is answered — both repos are identified and configured. The GPU is no longer a reason — #2 is resolved, this checkout is on hawapc01. `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` is fetchable today (measured, `evidence/hawapc01-environment.md`) but it is §3 Stage 1's *validator*, not a canonical transcript, so it does not unblock the row on its own. |
| M0.12 | Labelled Sorani audio set — several hours, per §8.1 category list | BLOCKED | `BLOCKED.md` #1 |
| M0.13 | Benchmark executed on real Kurdish audio on hawapc01; numbers recorded | BLOCKED | `BLOCKED.md` #1 (no labelled audio), #11 (the canonical weights have no loader on this OS). **The hawapc01 half is done**: this checkout is on it — 2×24 GiB, `evidence/hawapc01-environment.md` — so §8.1's "RTF measured on hawapc01" is now a matter of having something to measure. |
| M0.14 | Public-corpus importer (Common Voice `ckb`) producing an interim, unlabelled manifest | DONE | `src/hawedit/corpus_import.py` + `tests/test_corpus_import.py` (12 tests). Refuses to invent dialect, condition or duration. Authorised in D-012. |
| M0.15 | Measure §4.1 collision incidence on real Sorani | DONE | `evidence/collision-incidence.md` — 24,894 real entries; 0.21% of distinct forms would have failed to match. Surfaced a collision §4.1's table omits (D-013). |
| M0.16 | Download the interim audio corpus | BLOCKED | `BLOCKED.md` #1 — the route itself is gone, not merely unreachable. #6 tracked whether the hosts answered, and from here they do; the corpus does not. Common Voice moved to Mozilla Data Collective in October 2025 (account + accepted terms, which is Hawa's to click, not mine); OpenSLR has **0 Kurdish resources of 156**; `facebook/omnilingual-asr-corpus` is CC-BY-4.0 and ungated but ships **349 configs with no `ckb`**; the two ungated ckb candidates that remain have **no licence** — a D-002 hard reject — and one of them has no audio column at all. Measured, see `BLOCKED.md` #1 §"Option 3 closed". I marked this TODO earlier today on the strength of the hosts answering 200; that was true and it was the wrong question. The importer (M0.14) is built, tested, and has nothing to import. |

**M0 cannot be closed while M0.12/M0.13 are blocked.** The harness is buildable and testable
without the audio; the *measurement* — which is what M0 exists to produce, and what every
downstream threshold depends on — is not. See `BLOCKED.md`.

## M1 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M1.1 | §4.2 Viterbi forced alignment on CTC emissions, in-house per §7 | DONE | `src/hawedit/forced_alignment.py` + `tests/test_forced_alignment.py` (22 tests). Monotone non-overlapping spans, every token framed, infeasible input refused rather than guessed. No new dependency. |
| M1.2 | §4.2 sentence segmentation (Kurdish punctuation **plus** VAD pauses) + §5 anchors | DONE | `src/hawedit/sentences.py` + `tests/test_sentences.py` (17 tests). Pause path works on wholly unpunctuated input; `anchors_for` returns `None` rather than a guess when nothing is complete. Threshold: D-014. |
| M1.3 | Stage 0 ingest: ffmpeg demux, PySceneDetect, Silero VAD, diarization | PARTIAL | `src/hawedit/ingest.py` + `tests/test_ingest.py` (20 tests) run against real media: `tests/fixtures/kurdish-speech-3cuts.mp4`, built from three 1.4 s segments so the cuts are known. Measured: shot detection on the **source** finds both cuts with **0 ms** error; on the 1 fps proxy it finds **none** (D-023). VAD returns the two utterances, returns nothing on silence, and every segment of a 62 s file stays under the 38 s ceiling. **Shortfall:** diarization is not run — `IngestResult.diarization` is `None`, never `[]` — pending the gated Community-1 repo (`BLOCKED.md` #4). |
| M1.6 | Model provisioning: readiness report + registry-driven fetcher | DONE | `src/hawedit/models.py` + `tests/test_models.py` (21 tests) + `scripts/fetch-models.sh`. `python -m hawedit.models` reports all 15 §7 components. Sources §7 leaves open are refused, not guessed (D-022). |
| M1.7 | §4.1 conjunctive `و` separation (the collision KLPT does not cover) | DONE | `normalize.separate_conjunctive_waw` + `tests/test_waw.py` (18 tests). Rule: split `و`+R only if R is a valid Sorani word **and** `و`+R is not — a refusal, not a prediction. Measured over all 24,894 dictionary entries (`evidence/waw-separation.md`, D-026): **0 words damaged**, 98.91% of joined forms recovered, 19 `و`-initial words permanently unsplittable because they are words themselves. The 1.09% shortfall has one cause — bare medial `ه` U+0647 — which is D-013's finding seen through a second instrument. |
| M1.4 | Stage 1 speech: LLM-7B + CTC-3B in parallel, validator escalation | BLOCKED | `BLOCKED.md` #11. Three reasons have now fallen in sequence and each exposed the next: the GPU is here (#2), the Hub is reachable (#6), the repos are identified and Apache-2.0 (#10 answered) — and the two canonical checkpoints turn out to be raw fairseq2 `.pt` files whose loader needs `fairseq2n`, published for manylinux and macOS only. hawapc01 is Windows. WSL2 here has both GPUs visible and 740 GB free, so the route exists; which environment Stage 1 runs in is an architecture decision, and §8.1's "RTF measured on hawapc01" makes it a measurement-provenance one too. D-046. |
| M1.5 | Escalation rule: bottom log-prob quartile + LLM/CTC disagreement (§3 Stage 1) | DONE | `src/hawedit/escalation.py` + `tests/test_escalation.py` (16 tests). §3's "never escalate on duration or word-count" prohibition asserted directly. Threshold: D-015. |

## M2 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M2.1 | §2 text index: BM25 + character 3-grams over normalized Sorani | DONE | `src/hawedit/index.py` + `tests/test_index.py` (25 tests). The clitic-attachment failure §2 describes is measured: word BM25 scores the stem query **0.0**, n-grams retrieve it. Invariant #3 enforced at the index boundary. Weighting: D-016. |
| M2.2 | §5 clip contract + §3 Stage 5 boundary fusion + Kurdish invariant #2 | DONE | `src/hawedit/boundary.py` (31 tests) + `src/hawedit/clip.py` (20 tests). Invariant #2 checked exhaustively over 3,125 soft-input combinations and enforced again at an explicit render gate. Contract choices: D-017. |
| M2.5 | §3 Stage 3 dual-path candidate merge — "union, never intersect" | DONE | `src/hawedit/discovery.py` + `tests/test_discovery.py` (27 tests). Nothing is dropped (property test over 200 generated inputs); per-path attribution survives so §8.2's `recall_at_k_by_path` and `path_unique_wins` still mean something; overlap does not chain; a path never dedupes itself; spans are the anchor's, never widened — §3 Stage 5 owns boundaries. Refuses to invent a cross-path score. D-029. Built ahead of both producers (`BLOCKED.md` #2, #3). |
| M2.6 | §3 Stage 4 editorial judge contract: routing interface, verdict, cost model, shadow rule | DONE | `src/hawedit/judge.py` + `tests/test_judge.py` (40 tests). The shadow is refused at `route()` and again at `to_editorial()` and again at §5's `Editorial`; promotion needs a clear win on ≥20 real items, never a tie or an empty set, and `decide_judge` takes no date argument by design; the 200K tier ceiling is enforced as arithmetic against §3's own 360K with-video figure; a survivor Path A already scored cannot be re-sent for discovery. Kurdish title/description/hashtags are refused if they contain no Kurdish script. D-030, D-031. The call itself is `BLOCKED.md` #3. |
| M2.7 | End-to-end runner: one command over §3, reporting every stage it could not run | DONE | `src/hawedit/pipeline.py` + `tests/test_pipeline.py` (18 tests). `python -m hawedit.pipeline VIDEO.mp4` runs Stage 0 on real media and exits **1** naming the four blocked stages. Given a transcript and a verdict as stand-ins it runs six stages end to end — ingest → §4.1 → §2 index → §4.2 segmentation → Stage 5 fusion → Stage 6 render — with Stage 5 fusing against the shot cuts Stage 0 found *on that video*. A skipped stage is a `StageSkipped` naming its blocker, never an empty result. D-032. |
| M2.8 | Gemini credential panel + the real §3 Stage 4 judge | DONE | `src/hawedit/credentials.py` (20 tests) + `src/hawedit/gemini.py` (26 tests). `python -m hawedit.credentials` verifies a key against Google before storing it, refuses any target git tracks, and never prints it. `GeminiJudge` implements `EditorialJudge` with schema-enforced output, real `countTokens` before the billed call, temperature 0, bounded retries on transient failures only, and §3's ZDR gate as a required value. Every check in `JudgeVerdict` applies to model output. D-034, D-035. |
| M2.3 | Stage 3 Path A (Gemini reads the full transcript) | DONE | `src/hawedit/path_a.py` + `tests/test_path_a.py` (21 tests). Sends the **whole** normalized transcript — a test asserts every fragment reaches the judge, because sending a subset is the exact failure §3 built the dual path to prevent and would be invisible in the output. Refuses to split a too-long transcript rather than choosing which parts the Kurdish judge reads. Invariant #3 at the door; every returned span checked against the transcript's own range; ranks dense and ordered for §8.2. Wired into `pipeline.py`. D-036. |
| M2.4 | One rendered clip | DONE | `evidence/m2-4-rendered-clip.mp4` (1080×1920, 2.2 s) + `evidence/m2-4-frame.png` — a real vertical clip with Kurdish captions burned in, rendered by `src/hawedit/render.py` + `tests/test_render.py` (21 tests). Was marked BLOCKED behind `BLOCKED.md` #5 for two days after #5 was resolved; `tests/test_claims.py` now fails on a BLOCKED row whose every blocker is resolved. |

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
| M3.1 | §4.3 caption generation: shaping, stack check, font coverage, own line breaks | DONE | `src/hawedit/captions.py` + `tests/test_captions.py` (33 tests). Font coverage asserted against the real OFL-1.1 Noto Naskh Arabic shipped in `assets/fonts` — full Kurdish coverage measured (D-018). |
| M3.2 | §4.3.6 golden-file render compared per build | DONE | `tests/golden/kurdish-caption.png` rendered on a verified libass build; compared on decoded pixels every gate run. `shaping=simple` must fail the same comparison — without that control the test measures nothing. D-021, `evidence/rtl-shaping.md`. |
| M3.3 | Stage 6 encode: crop/reframe + NVENC burn-in | PARTIAL | `src/hawedit/render.py` + `tests/test_render.py`. Cut, 9:16 crop, `shaping=complex` burn-in and encode all run and are verified on decoded pixels: a captioned render must differ from an uncaptioned one, and a `shaping=simple` render must differ from the shipped one. **NVENC now runs** — a real 1080×1920 clip encoded on hawapc01's 3090 Ti with captions verified in the NVENC pixels (`evidence/m3-3-nvenc.md`, `evidence/m3-3-nvenc-clip.mp4`). Getting there found a defect in the check itself: `encoder_available` probed at **64×64**, below NVENC's minimum frame, so the function written because a capability listing cannot be trusted called a working encoder unavailable — and `render_clip` refuses rather than substitutes, so NVENC would have raised on the one machine §6 puts it on. It probes at Stage 6's own output size now, and a GPU-free test pins that. D-045. **Shortfall (one, was two):** §3 Stage 6 reframes by tracking the active speaker from diarization plus face detection; neither runs — Community-1 measured **401** from here (`BLOCKED.md` #4) — so the crop is static and says so by name, `Reframe.STATIC_CENTRE`, never `SPEAKER_TRACKED`. |

## M5 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M5.1 | §3 Stage 2 visual index: scenes segmented to the reference settings, retrieval, and the top-50 → rerank → keep-5–10 contract | DONE | `src/hawedit/visual_index.py` + `tests/test_visual_index.py` (51 tests). Runs in `pipeline.py` on real media: Stage 0's own cuts at 1400/2800 ms become three windows tiling 0→4162 ms, `evidence/m5-1-scene-windows.md`. The 64-frame ceiling and ~1 fps are enforced as one setting because either alone is satisfiable while the pair is broken — a 180 s scene at 0.35 fps is 63 frames, under the ceiling, and its embedding is indistinguishable from an honest one. A zero or NaN vector is refused rather than scored 0.0. The reranker may reorder and score; it may not invent a window, duplicate one, drop below the survivor count, or restate the retrieval score it was handed. D-037. **The splitting path is exercised by tests only** — there is no long Kurdish episode here to run it against (`BLOCKED.md` #1). |
| M5.2 | Real `Qwen3-VL-Embedding-2B` / `-Reranker-2B` behind the interfaces above | TODO | **Unblocked 2026-08-08.** GPU present (#2 resolved), repos resolved to `Qwen/Qwen3-VL-Embedding-2B` and `Qwen/Qwen3-VL-Reranker-2B` — exact name, official namespace, Apache-2.0 — configured in `models/sources.json`, and `config.json` fetched from both (`evidence/hawapc01-environment.md`). 2.1B params each, comfortable on 24 GiB. Ordinary unstarted work now. |
| M5.3 | §3 Stage 3 Path B: `VideoChat3-4B` over scenes, producing `Candidate`s the §3 union already accepts | DONE | `src/hawedit/path_b.py` + `tests/test_path_b.py` (26 tests). Found a real defect in `clip.py`: `Sv6d` checked that a label *cites* a timestamp and could not check *which scene* — `speaker gestures at 9999s` (2.78 hours) constructed cleanly for a 12-second window (`evidence/m5-3-path-b.md`). `assert_sv6d_within_window` closes it, requiring *some* cited time inside the window so an honest duration alongside a moment still passes. §3's 256-frame budget is refused **before** the call, since past it the failure is an OOM kill rather than a wrong answer. `run_pipeline(..., read_scenes=…)` makes the union two-sided over the windows Stage 2 planned on that video. D-039. The **model** is still `BLOCKED.md` #2, #6, and the prompt is unwritten. |
| M5.4 | Real `MCG-NJU/VideoChat3-4B` behind the Path B contract, and the SV6D prompt | TODO | **Unblocked 2026-08-08.** §7 names the repo outright; it exists, Apache-2.0, 4472.4M params, and `config.json` fetches (`evidence/hawapc01-environment.md`). GPU present. §3's 256-frame budget (~17.7 GB) fits one 24 GiB card and `path_b.py` already refuses past it. The SV6D prompt is still unwritten — that was always work, never a blocker. |

## M6 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M6.1 | §3 Stage 5 TimeLens2 contract: intervals as evidence, never as cuts, and only where they are about the clip | DONE | `src/hawedit/timelens.py` + `tests/test_timelens.py` (23 tests). Found a real defect in `boundary.py`: `timelens_interval_end_ms` arrived as a bare integer, so §3's "latest of { …, timelens_interval_end }" read as `max()` over the episode — measured, a 4.0 s anchored sentence became a **295 s clip with Kurdish invariant #2 still passing**, because the invariant constrains direction and nothing constrained relevance (`evidence/m6-1-timelens-relevance.md`). Eligibility is now overlap with the anchored sentence, checked in the selector **and** at the fusion site, because `BoundaryInputs` accepting a naked end is what let it happen. D-038. |
| M6.2 | Sentence-hard fusion (the HARD/SOFT rule itself) | DONE | Delivered in M2.2 — `boundary.py`, invariant #2 exhaustive over 3,125 soft-input combinations. |
| M6.3 | Real `MCG-NJU/TimeLens2-4B` behind the contract above | TODO | **Unblocked 2026-08-08.** §7 names the repo outright; it exists, Apache-2.0, 4437.8M params, `config.json` fetches (`evidence/hawapc01-environment.md`). GPU present. The contract and its relevance gate are DONE (M6.1); this is the model behind them. |

| M3.4 | §8.3's third render-regression bullet: the boundary invariant asserted on every **shipped** clip | DONE | `render.py` (`assert_encoded_span`, `frame_duration_ms`) + `boundary.py` (`media_duration_ms`) + `tests/test_render.py`, `tests/test_boundary.py`. The invariant had been asserted on the `Clip` object; `RenderResult.duration_ms` was the request echoed back and the file was never opened. Measured: requesting 8000 ms of a 4162 ms source makes ffmpeg exit 0 and write 4180 ms. The new check immediately caught the runner's own end-to-end fixture — §3 Stage 5's 200 ms tail pushed `final_out` 138 ms past the end of the file, so **every `run_pipeline` render had been silently truncated** while the suite stayed green (`evidence/m3-4-shipped-clip-invariant.md`). D-040. |

| M3.5 | Captions timed to the clip, and a burn that refuses an ASS with nothing to draw | DONE | `captions.py` (`clip_in_ms`, `parse_dialogue_times`, `assert_captions_within_clip`) + `tests/test_caption_timing.py` (13 tests). **The most serious defect found so far.** `build_ass` wrote source-absolute timestamps and `render_clip` burns into a stream already cut at `clip.in_ms`. Measured on a 1.6 s clip taken from source 2000 ms: **0 bytes** differ between a captioned and an uncaptioned render — libass drew nothing, ffmpeg exited 0, and the output is a valid, playable, caption-free MP4. Kurdish invariant #4 was absent from every clip not starting near zero. The existing pixel test is the right test; its fixture cuts at 300 ms with words at 0–1600, the one input where the bug is invisible. `evidence/m3-5-caption-timeline.md`, D-041. |

| M3.6 | §2's delivery set complete: SRT and EDL alongside the MP4, ASS and §5 JSON | DONE | `src/hawedit/delivery.py` + `tests/test_delivery.py` (25 tests) + a `run_pipeline` test. §2's diagram ends `MP4 · SRT/ASS · editing JSON · EDL` and **two of the four had never been built**. The SRT is on the clip's timeline (M3.5's rule, shared); the EDL's source timecodes are the *source's* and only its record timecodes start at zero — an EDL in clip time conforms the wrong footage and looks well-formed. A non-integer frame rate is **refused** rather than rounded: non-drop at 29.97 drifts ~3.6 s/hour and the EDL looks correct throughout. `evidence/m3-6-delivery-set.md`, D-042. |

## M7 — task ledger

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M7.1 | §8.2 metrics: per-path Recall@20, temporal IoU, sentence-completeness, misleading-edit rate, pairwise preference, cost/wall-clock per source hour | DONE | `src/hawedit/repurposing.py` + `tests/test_repurposing.py` (31 tests). `path_unique_wins` answers §8.2's collapse question directly. Definitions: D-020. |
| M7.2 | 200–500 human-reviewed candidates labelled per §8.2 | BLOCKED | Needs human annotators and real footage — same dependency as `BLOCKED.md` #1 |
| M7.3 | Threshold tuning against the labelled set | TODO | Depends on M7.2 — an unstarted task, not an external blocker. Every threshold in `DECISIONS.md` marked "awaiting real data" is tuned here. |

## Deferred with reason

| Item | Deferred to | Reason |
|---|---|---|
| ~~§5 clip contract~~ | ~~M1–M2~~ | **Delivered in M2.2** — boundary fusion gave it a producer. Kurdish invariant #2 is enforced at fusion and again at the render gate. |
| Conjunctive `و` separation (§4.1) | M1 | Not implemented by KLPT `normalize` — measured, see `DECISIONS.md` D-003. |
