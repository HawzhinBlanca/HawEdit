# Research: fused-checkpoint drafting (v12) + GPU-1-only defaults + :8000 coordination

- **Status:** research only. No code has been written.
- **Branch:** `claude/v12-fused-model`, worktree `D:\HawEdit-worktrees\v12-fused-model`.
- **Base:** `codex/evidence-based-studio` @ `6fe060d` (see "Base branch" below).
- **Date:** 2026-10-08.
- **Requested by:** the owner ("use v12 in HawEdit", fix GPU defaults).
- **Method:** the symbols were mapped by reading and grepping the source. Serena was not available in this session. Every reference below is `path:line` on `6fe060d`.

## Base branch
`origin/main` (`3483554`) does not contain the code this feature changes:
- `asr_completion.py`, `asr_resume.py`, `studio_host.py`
- the 64-hex worker identity regex

All of these exist only on `codex/evidence-based-studio`, which is 100 commits ahead and changes 697 lines of `asr.py`. Building on main would conflict with all of that work. This branch is therefore based on `6fe060d`, and must merge after it or be rebased onto it.

## What v12 is (from the omniasr-v11-audit project)
- **The checkpoint:** one fused fairseq2 checkpoint, arch `wav2vec2_llama`/`7b`, vocab 10288:
  `/home/ai/kurdish_models/omni_7b_v3_continuation/runs/champion_v12_lora64_750_fused/kurdish_omniasr_7b_v12_c750.pt`.
  It is 15,610,646,560 B, with its sha256 in that folder's `SHA256SUMS`.
- **The tokenizer** is byte-identical to the held canonical tokenizer (`8aa11a10…`).
- **It is not a LoRA bundle on the stock base.** It is a rank-64 LoRA trained on fused v11 and then fused, so it cannot be expressed as an adapter folder.
- **Evidence so far:**

  | Model | Setup | FLEURS ckb test (922) |
  |---|---|---|
  | v12 | Beam 5, through the omniasr server | 23.29 WER / 5.50 CER |
  | v11 | Same setup | 25.54 WER / 6.14 CER |

  The difference is significant (paired bootstrap).
  - Hardware: RTX 3090 Ti, GPU 1.
  - Software: fairseq2 0.6, omnilingual-asr 0.2.0.
  - **Not yet measured:** v12 against the current HawEdit champion (v6, `lora:dfa6237a…`) under HawEdit's own decoding (greedy, raw text). That job is queued (`omniasr-v11-audit/scripts/compare_v6_v12_greedy.py`), and its result will be added here.

## Current code (6fe060d)

### Champion resolution
- `asr.py:222-269`: `resolve_champion_adapter` accepts only folders that contain `adapter_config.json` and `adapter_model.safetensors`.
- Callers: `pipeline.py:5439-5453` and `studio_host.py:143-144, 203-204, 228`.

### Identity
- `asr.py:272-395` computes `"lora:" + sha256(schema-2 manifest of config, weights and tokenizer)`.
- **The worker requires `lora:[a-f0-9]{64}`** (`asr_worker.py:110`), refuses a stock request that claims an identity (`:113-114`), and requires the claimed identity to equal `adapter_name` (`:116-118, 154`).
- The identity is also checked or recorded in:
  - `asr.py:1435-1444, 1593-1631`
  - `asr_resume.py:292`
  - `studio_host.py:228`
  - `transcripts.py:544-560` (any non-blank string is accepted)
  - `pipeline.py:3028-3054` (reuse key)

### Loading
- `asr.py:572-646, 719-811`: `open_verified_omni_assets` (`omni_assets.py:292-355`) holds and hashes the stock LLM (31.2 GB), CTC-3B and the tokenizer. The LoRA is then applied with `PeftModel.from_pretrained`.
- `open_verified_omni_assets` already accepts an `assets=` subset.

### Decoder contract
- `asr_completion.py:22-54, 72-156` pins omnilingual-asr 0.2.0, the `beamsearch.py` and `model.py` hashes, `type(model) is Wav2Vec2LlamaModel`, `nbest == 1` and natural EOS.
- A fused checkpoint keeps the same model class and generator. Expected to pass unchanged, but not yet verified on hardware.

### Devices
| Component | Location | Default |
|---|---|---|
| LLM | `asr.py:534`, `asr_resume.py:318` | `cuda:0` |
| CTC | `asr.py:535` | `cuda:1` |
| Validator | `asr.py:450/460` | `cuda:1` |

- `wsl_setup.py:960, 1060-1061, 1402-1403` requires at least 2 visible GPUs.
- `gpu_runtime.py:148-153` refuses `CUDA_VISIBLE_DEVICES`. Device selection must therefore be done with the `HAWEDIT_ASR_*_DEVICE` variables, not by hiding a GPU.

### Memory and ordering
- **Documented in BLUEPRINT** (§3 lines 114-118, §6 lines 343-344), not measured:

  | Component | Memory |
  |---|---|
  | LLM | ~17 GiB |
  | CTC | ~8 GiB |
  | Validator | ~4 GiB |

- No process-VRAM measurement exists in the repo.
- **Ordering:**
  - The LLM and CTC run in parallel threads.
  - `release_draft_model` (D-286) frees the LLM before the validator loads, and CTC stays resident.
- **GPU 1 only means the LLM and CTC sit on one 24 GB card at the same time.** That is about 21–25 GB, borderline and unmeasured.

### External server
- **Nothing in HawEdit knows about the :8000 omniasr server.**
- The server uses about 14.6 GB of GPU 1, so it cannot run while HawEdit drafts there.
- Its watchdog honours `omniasr-v11-audit/app/MAINTENANCE` when that file holds a live PID.
- Stop and restart scripts already exist: `omniasr-v11-audit/scripts/stop_server.sh` and `restart_server.sh`.

## Spec and ADRs this touches
- **BLUEPRINT §2 (45-48), §3 Stage 1 (112-118), §6 (343-344, 356):** "both GPUs run simultaneously". GPU 1 only diverges from this.
- **BLUEPRINT §7 (376-378):** the canonical `omniASR_LLM_7B_v2`. A fused checkpoint replaces those weights rather than sitting beside them.
- **Related decisions:**
  - D-181: adapter beside canonical, arch `7b`, vocab from the tokenizer.
  - D-260: the champion is the LoRA bundle; never divert, an honest halt is allowed.
  - D-281: no model or default change.
  - D-285: schema-2 three-file adapter fingerprint.
  - D-286: release after the draft.
  - D-136: reuse key and request byte-identity.
- **BLOCKED #21:** the champion licence is unknown, and that applies to fused weights as well.
- **A new ADR is required.**

## Open owner questions (not decided by this research)
1. **GPU 1 only overrides BLUEPRINT §2/§3/§6.** Should this be confirmed as an ADR?
2. **Qwen3-ASR validator.** HawEdit uses `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` to *replace* text on escalated segments (`asr.py:98, 280-352`). Cortex canon forbids Qwen-family ASR for ckb. This is out of scope for this feature, but it is a conflict the owner should know about.
3. **FLEURS.** v12's training data includes the FLEURS train split, while the owner's Rights Declaration says "never train on FLEURS". This needs the owner's ruling before v12 becomes the default.

## Measured 2026-10-10: v6 (current champion) vs v12 under HawEdit's decoding
- **Setup:** greedy (nbest=1), raw model text, the same pipeline and clips for both models, length-sorted batches of 8.
- **Hardware:** RTX 3090 Ti on GPU 1, fairseq2 0.6, omnilingual-asr 0.2.0.
- **Reproducer:** `omniasr-v11-audit/scripts/compare_v6_v12_greedy.py`; output in `results/compare_v6_v12_greedy.json`.

| Set (unseen rows) | v6 WER / CER | v12 WER / CER | v12 − v6, WER [95% CI] | v12 − v6, spacing-neutral CER |
|---|---|---|---|---|
| Hawzhin test (473) | 30.02 / 5.65 | **25.19 / 4.66** | **−4.83 [−5.99, −3.80]** | **−0.66 [−0.90, −0.46]** |
| FLEURS test (922) | 25.19 / 5.95 | 25.65 / 6.63 | +0.46 [−1.36, +3.20] (not significant) | +0.49 [−0.12, +1.31] (not significant) |

**Greedy runaway loops** (hypothesis longer than 1.6× the reference words):

| | v6 | v12 |
|---|---|---|
| FLEURS | 0 | **5** |
| Hawzhin | 2 | 1 |

- **Without those clips:** FLEURS v12 23.38 vs v6 25.19; Hawzhin 25.02 vs 29.72.
- **Implication:** under greedy decoding, v12's only deficit is a handful of runaway loops. Fix that, by making the model loop-proof or by an honest length-cap halt, before T7.
- **Caveat:** v6's training provenance is unverifiable (its deployment manifest says so), so overlap between its training data and these test sets cannot be checked.

## Measured 2026-10-13: what a v12 greedy loop does inside HawEdit, and whether beam 5 fixes it

**Upstream stops a loop without EOS.** The upstream decoder (omnilingual-asr 0.2.0 `beamsearch.py`) checks the zlib compression ratio of the last `compression_window=100` tokens every 250 steps and ends the hypothesis when it exceeds `compression_threshold=4.0`. A repetition loop therefore ends **without a natural EOS**.

**HawEdit already refuses that.** `require_natural_completion` (`asr_completion.py:72-156`, D-281) raises `DecodeIncomplete` for any segment that lacks a natural EOS, and D-281 forbids continuing a failed production batch.

**So with v12 as the greedy champion, a loop does not ship bad text. It halts the run.**

**How often:**

| Set | Greedy v12 loops |
|---|---|
| FLEURS test | 4 of 922 clips (0.4%) |
| Mining output (`omniasr-v11-audit/data/v12_greedy_mining.jsonl`, 2,264 unique training clips skewed to long ones; the file has duplicate rows) | 121 (5.3%) match the loop rule below, almost all Zainab read speech |

Because one halt stops the whole run, a long video with hundreds of segments is at real risk of halting. v6 had 0 such loops on FLEURS. **This blocks T7 independently of accuracy.**

**Detecting loops that did end naturally.** Rule tested: "a unit of 1 to 4 words repeated at least 4 times in a row".
- **References:** 0 of 3,726 references across every frozen benchmark match it.
- **Greedy v12 on FLEURS:** it catches all 4 genuine loops.
- **"At least 3 times" is too loose:** it also flags a correctly spelled-out acronym (`ئی ئی ئی`, IEEE) twice.
- **Text rate:** reference characters per second of audio are at most 14.9 (FLEURS) and 19.3 (Hawzhin TTS). Two of the loops ran at 32–37 chars/s, but one ran at only 18.8, so a rate guard alone misses loops.
- **v6 for comparison:** 0 loops on both FLEURS and Hawzhin under the same rule.

**Does beam 5 fix the clips where greedy looped?**
- **Method:** the flagged mining clips (258 rows, 160 unique clips) sent through the production v12 beam-5 server.
- **Script:** `omniasr-v11-audit/scripts/beam_on_greedy_loops.py`; output `results/beam_on_greedy_loops.json`.
- **Result:** 113 unique clips are genuine greedy loops (the hypothesis matches the 4-repeat rule and the reference doesn't).
  - **Beam 5 removes the loop on 97 of 113 (86%).** Median CER drops from 89.6 to 10.8, and 74 clips end at CER ≤ 15.
  - **16 still loop under beam (14%)**, all of them Zainab long read speech.
- **Correction:** an earlier claim, "beam 5 has zero loops", holds on the frozen benchmarks only, not on long Zainab-style clips.
- **Implication for T8:** a beam retry turns most loops into usable text, but roughly 1 in 7 looping segments will still halt honestly.
  - A stronger second check is available for free: HawEdit already runs CTC-3B on every segment.
  - Literature: a CTC-length guard ("LLM text more than 1.5× the CTC text") removed repetition entirely in arXiv 2408.09491.
  - **Caveat:** HawEdit's CTC is the stock multilingual model decoded unconditioned (D-xxx at `DECISIONS.md:6291`), so its length is only a rough reference. Measure it before relying on it.
- **Caveat on the 4-repeat rule:** genuine stuttering ("هەر هەر هەر هەر") can match it. References are typically disfluency-cleaned, so the 0 false positives on references may understate this for conversational audio.

## T0 measured 2026-10-15 (omniasr side, GPU 1 only)
- **Setup:** `omniasr-v11-audit/scripts/hawedit_t0_measure.py`, output `results/hawedit_t0_measure.json`.
  - Fused v12 LLM in bf16 with the upstream greedy decoder (nbest=1), as HawEdit pins it.
  - CTC-3B in bf16 in a parallel thread on the same segment.
  - RTX 3090 Ti, torch 2.8.0+cu128, fairseq2 0.6, omnilingual-asr 0.2.0. The :8000 server was stopped.
- **Resident after loading both:** 20.29 GiB allocated (LLM 14.55 + CTC 5.74).

| Segment | Wall time | Peak allocated | Peak reserved |
|---|---|---|---|
| 9.1 s | 4.8 s | 20.63 GiB | 22.23 GiB |
| 19.2 s | 7.9 s | 21.00 GiB | 22.50 GiB |
| 33.9 s (close to the 34.5 s union ceiling, D-283) | 13.0 s | 21.90 GiB | **23.41 GiB** |
| 10.0 s Zainab clip that loops under greedy | 5.4 s | 20.73 GiB | 22.25 GiB |

- **Gate verdict (plan T0, "peak above ~22.5 GiB → STOP and re-plan"):** **exceeded by about 0.9 GiB reserved** on segments near the ceiling. Allocated stays under the limit (21.9). Everything ran with no OOM; on WDDM the overflow spills to shared RAM rather than failing.
- **Caveat:** the Windows-level shared/dedicated counters for the second pass were contaminated, because the watchdog restarted :8000 between passes. The per-process torch peaks above are unaffected.
- **Re-plan options, for the owner:**
  - **(a) T0b:** when the LLM and CTC share one device, run CTC after the LLM instead of in parallel. This costs about the CTC forward time (Meta RTF 0.003, under 0.2 s per segment) and removes the concurrent-activation peak.
  - **(b)** Accept the measured margin; the 24 GiB card holds 23.4 GiB reserved.
  - **(c)** Call `torch.cuda.empty_cache()` between segments. This trims caching slack but not the concurrent peak.
- **Related omniasr finding (2026-10-14):** on WDDM, fairseq2's KV cache growth (16-step copies) plus PyTorch's caching allocator can spill heavily for long or batched beam decoding. HawEdit decodes one segment at a time, greedy, at 40 s or less, and the measurements above show that case is bounded. The T8 beam-5 retry decodes one segment with 5 rows, which raises KV memory about 5×, and that path is **unmeasured**. Measure it before T7.

### T8 beam-5 retry path measured 2026-10-15
- **Setup:** same as T0, with `T0_NBEST=5`; output `results/hawedit_t0_measure_nbest5.json`.

| Segment | Wall time | Peak allocated | Peak reserved |
|---|---|---|---|
| 9.1 s | 6.1 s | 21.36 GiB | 23.15 GiB |
| 19.2 s | **126.9 s** | 22.01 GiB | **24.38 GiB** |
| 33.9 s | **586.2 s** | 22.94 GiB | **31.04 GiB** (WDDM spill of about 6 GB seen while it ran) |
| 10 s loop clip | 21.3 s | 21.48 GiB | 23.78 GiB |

- **Verdict:** with CTC-3B resident on the same 24 GB card, the T8 beam-5 retry overflows into shared RAM and is 15–45× slower. **T7 must not ship until the retry has its own memory plan.**
- **Options:**
  1. Move CTC-3B to the CPU for the retry only, then back.
  2. Drop the retry and keep the honest halt.
  3. Retry only on segments of 10 s or less.
