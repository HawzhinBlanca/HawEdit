# PROGRESS — Kurdish Video Repurposing System

Generated from `BLUEPRINT.md` §9 (Build order). **The agent never marks a task DONE by
judgment**: DONE requires code + test + the gate green + evidence linked below.

- Gate: `bash hawedit2/scripts/verify.sh` (lint + format + typecheck + tests)
- Blocked items: `BLOCKED.md` · Deviations: `DECISIONS.md`

## Status legend

| Mark | Meaning |
|---|---|
| DONE | Gate green **and** evidence recorded below |
| WIP | In progress this iteration |
| TODO | Not started |
| BLOCKED | Needs Hawa / hardware / credentials — see `BLOCKED.md` |

## Milestones (§9)

| Milestone | Deliverable | Blocks | Status |
|---|---|---|---|
| **M0** | ASR benchmark harness + labelled Sorani audio set | Everything | WIP |
| **M1** | Stage 0 + Stage 1 → raw/normalized transcript with word timings | M2 | TODO |
| **M2** | Vertical slice: transcript → BM25 → Gemini → manual boundary → one rendered clip | Proves the concept | TODO |
| **M3** | Stage 6 render path with verified RTL captions + golden test | Client delivery | TODO |
| **M4** | Stage 3 Path A (full-transcript discovery) | Verbal recall | TODO |
| **M5** | Stage 2 visual index + Stage 3 Path B | Visual recall | TODO |
| **M6** | Stage 5 TimeLens2 + sentence-hard fusion | Boundary precision | TODO |
| **M7** | Repurposing eval set + threshold tuning | Quality gates | TODO |
| **M8** | Auto-reframe (SAM 3 / Molmo2) | Vertical formats | TODO |

## M0 — task ledger

M0 decomposed from §8.1 (ASR benchmark) + §4.1 (normalization is a prerequisite of
"normalized CER"). Decomposition is task breakdown, not architecture change.

| Task | Definition of Done | Status | Evidence |
|---|---|---|---|
| M0.1 | Package skeleton + gate script; gate refuses a no-op command instead of printing green | DONE | `tests/test_gate.py` (9 tests) · gate green: `VERIFY OK — hawedit2 gate green` · found + fixed 2 real gate defects, see D-005 |
| M0.2 | §7 model registry in code; model outside §7 rejected; NC licence hard-rejected | DONE | `src/hawedit2/registry.py` + `tests/test_registry.py` (15 tests). The tests **parse §7 out of `BLUEPRINT.md`** and assert exact set equality both ways, so a model added in code but not in the blueprint fails the gate. |
| M0.3 | §4.1 Sorani normalization via KLPT; every §4.1 collision asserted in a test | DONE | `src/hawedit2/normalize.py` + `tests/test_normalize.py` (12 tests): all 4 KLPT-covered §4.1 collisions, the two-encodings-compare-equal failure mode, idempotence, and the conjunctive-`و` gap pinned per D-003 |
| M0.4 | Kurdish invariants #1 and #3 in code: `transcript.raw.json` write-once, model inputs read `norm` | DONE | `src/hawedit2/transcripts.py` + `tests/test_transcripts.py` (17 tests). #1 enforced three ways (refuse-rewrite, frozen types, SHA-256 tamper evidence); #3 enforced by distinct types (mypy) + `assert_model_input` (runtime) + stale-norm detection. ASR provenance is validated against §7 at construction. |
| M0.5 | §8.1 accuracy metrics: normalized CER, spacing-free CER, named-entity error, code-switch error | TODO | |
| M0.6 | Labelled-corpus manifest + §8.1 coverage validation (3 dialects × 7 conditions), per-dialect never aggregated away | TODO | |
| M0.7 | ASR adapter interface + throughput harness: RTF, peak VRAM, long-audio failure rate | TODO | |
| M0.8 | Alignment-accuracy metric against CTC emissions (§8.1 last metric) | TODO | |
| M0.9 | Benchmark runner → comparable report JSON + §8.1 decision rule (LLM-7B stays canonical unless material gain) | TODO | |
| M0.10 | Diarization benchmark: Community-1 vs 3.1 DER on Kurdish multi-speaker material | TODO | |
| M0.11 | Real-model adapters (`LLM_7B_v2`, `CTC_3B_v2`, `LLM_Unlimited_3B_v2`, `rzgar-ckb-v1`, Gemini native audio) | BLOCKED | `BLOCKED.md` #2 |
| M0.12 | Labelled Sorani audio set — several hours, per §8.1 category list | BLOCKED | `BLOCKED.md` #1 |
| M0.13 | Benchmark executed on real Kurdish audio on hawapc01; numbers recorded | BLOCKED | `BLOCKED.md` #1, #2 |

**M0 cannot be closed while M0.12/M0.13 are blocked.** The harness is buildable and testable
without the audio; the *measurement* — which is what M0 exists to produce, and what every
downstream threshold depends on — is not. See `BLOCKED.md`.

## Deferred with reason

| Item | Deferred to | Reason |
|---|---|---|
| §5 clip contract (`clip_id`/`boundary`/`editorial`/`qc`) | M1–M2 | M0 emits benchmark reports, not clips. Writing the clip contract now would be untested code with no producer. Kurdish invariant #2 (`final_in <= anchor_in`) lands with the first boundary producer, M6, and is asserted before render per §8.3. |
| Conjunctive `و` separation (§4.1) | M1 | Not implemented by KLPT `normalize` — measured, see `DECISIONS.md` D-003. |
