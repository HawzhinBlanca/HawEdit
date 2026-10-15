# Plan: fused-checkpoint drafting (v12) + GPU-1-only defaults + :8000 coordination

Research: `research.md`. Callers: `impact-map.md`.

**Approved-by:** Wareen - 2026-10-14, "make v12 fully set and ready to use anywhere" and, when asked to approve T0–T8, chose "Approve all T0–T8": the fused loader, GPU 1 only, the :8000 pause wrapper, the T8 loop guard (beam-5 retry, else an honest halt) and the ADRs. v12 becomes HawEdit's default (T7) only after the real-run gate passes.

## Principles
- **Additive.** The LoRA-bundle path keeps working byte for byte, and stock requests stay byte-identical (D-136).
- **The champion is never diverted** (D-260).
  - Busy GPU, missing `.pt` or hash mismatch: an honest halt with a clear message.
  - Never a fallback to v6 or to the stock model.
- **No default model change until T7**, which happens only after measured evidence and the owner's OK.
- **Each task is test-first,** then `bash scripts/verify.sh` must pass, then a ledger row via `update-ledger.sh`.

## Tasks

**T0. Hardware measurement (no repo code).** On GPU 1 with :8000 stopped:
- load the fused v12 `.pt` with CTC-3B;
- record process-local allocated and reserved bytes and the peak during one parallel LLM+CTC segment.
- Record the hardware and library versions.
- **Gate:** if the peak exceeds about 22.5 GiB, STOP and re-plan. That would need sequential LLM then CTC, which is a larger change.

**T1. Fused loader.** In `OmniAsrBackend`, add `fused_checkpoint: Path | None`, mutually exclusive with `lora_adapter`:
- Load with `open_verified_omni_assets(assets=(CTC, tokenizer))`.
- Load the fused `.pt` through a direct `wav2vec2_llama`/`7b` card, with vocab from the held tokenizer, asserting 10288.
- Reuse the non-PEFT half of `_load_adapted_llm`. No PEFT.
- **Tests:** a fake card and pipeline; mutual exclusion; vocab mismatch → halt.

**T2. Identity `fused:<sha256>`.**
- **Host side:** the expected sha comes from `SHA256SUMS` beside the `.pt` (cheap).
- **Worker side:** verify the actual bytes once under a held descriptor. Cache by stat identity; never re-hash per call.
- **Places to update:**
  - `adapter_name` / `model_identity` (`asr.py:552-570, 1435-1444`);
  - the worker regex (`asr_worker.py:110`), which accepts `fused:[a-f0-9]{64}`, with the stock-cannot-claim rule kept;
  - the request field `fused_checkpoint`;
  - `create_omni_asr_producer`'s early check;
  - `studio_host.py:143-144, 203-204, 228`.
- **Tests:**
  - extend `test_adapter_identity.py:127` with fused cases (a foreign fused identity is refused; lora and fused can't impersonate each other);
  - add `test_studio_host.py` cases.

**T3. CLI and env.**
- `--omni-asr-checkpoint PATH` and `HAWEDIT_CHAMPION_CHECKPOINT`.
- Refused together with `--omni-asr-adapter` or `--stock-decoder`.
- **Tests:** the refusal tables (`test_pipeline.py` around 3435/3510/5280).

**T4. GPU 1 only by default.**
- LLM default `cuda:1` (`asr.py:534`, `asr_resume.py:318`); CTC and validator stay on `cuda:1`.
- `wsl_setup.py:1061` message.
- **Keep the 2-GPU visibility checks.** `gpu_runtime.py` forbids `CUDA_VISIBLE_DEVICES`, and GPU 0 stays visible but unused.
- **Tests:** `test_champion_held_assets.py:225` (expects `cuda:0` today) and the device-env tests in `test_asr.py`.
- **Spec divergence from BLUEPRINT §2/§3/§6:** recorded in the T6 ADR.

**T5. :8000 coordination (operator side, outside the HawEdit core).**
- A wrapper `scripts/run-with-omniasr-paused.sh`:
  1. writes `omniasr-v11-audit/app/MAINTENANCE` with its own PID;
  2. runs `stop_server.sh`;
  3. runs the HawEdit command;
  4. ALWAYS runs `restart_server.sh` and removes the lock (`trap`).
- **In the core:** an up-front `torch.cuda.mem_get_info(1)` check in the worker. Too little free memory → an honest halt naming the busy GPU (D-260 allows halting, never diverting).
- **Tests:** a fake `mem_get_info` triggers the halt; a shell test checks the trap restores the server when the command fails.

**T6. ADR `D-xxx`.** Records:
- fused-checkpoint drafting and its identity format;
- GPU 1 only (diverging from BLUEPRINT §2/§3/§6, the owner's rule);
- the :8000 coordination.

It links D-181, D-260, D-281, D-285, D-286 and BLOCKED #21.

**T8. Loop guard: re-decode one segment with beam 5, or halt honestly. Needs its own ADR, because it amends D-281.**

*Why:* see research.md, "Measured 2026-10-13".
- Greedy v12 loops on about 0.4% of FLEURS segments and more on long read speech.
- Upstream stops a loop by compression ratio without EOS, so D-281 halts the **whole run**.
- v6 does not loop there. Without T8, adopting v12 trades a 4.8-WER gain for halted runs.

*Behaviour (per segment; the greedy path stays byte-identical for every segment that passes):*
1. **Decode greedy as today.** The segment is *suspect* if any of these holds:
   - (a) `DecodeIncomplete`, meaning no natural EOS;
   - (b) the completed text contains a unit of 1–4 words repeated at least 4 times in a row (`loop_suspect()`, a pure function);
   - (c) the text rate exceeds `HAWEDIT_LOOP_MAX_CHARS_PER_S`. Default 30: measured references peak at 19.3.
2. **Suspect → re-decode that one segment** with the same model, same audio and same language, using `nbest=5` (beam 5, the omniasr production setting).
   - The completion contract gains a beam variant: the **selected** hypothesis must end on a sampled natural EOS.
   - Its output must not be suspect under (b) or (c).
   - **Memory (owner "option 1", 2026-10-15):** beam 5 beside a resident CTC-3B overflows the 24 GB card (research.md, "T8 beam-5 retry path measured 2026-10-15"). The retry therefore runs after the segment's greedy and CTC forwards have joined; when LLM and CTC share one CUDA device, CTC-3B moves to the CPU (then `torch.cuda.empty_cache()`) for the retry only and always moves back in a `finally`. If it cannot move back, the run halts with `DecodeIncomplete`. Separate devices: no moves. Greedy segments: no moves.
3. **Still suspect → `DecodeIncomplete`** naming the segment and both attempts: an honest halt (D-260/D-281).
   - Never trim repeats, splice attempts, guess words, or fall back to another model or the stock model.
4. **Provenance:** each segment records `decode_mode: greedy | beam5_retry` and why it was retried.
   - The completion policy ID becomes `omni-natural-eos-greedy-beam5-retry-v1:<decoder sha>:<model sha>`, so cache reuse binds to the new policy, and old records refuse as D-281 already specifies.
   - The run report counts the retries.

*Tests first:*
- `loop_suspect`: positive cases, the IEEE `ئی ئی ئی` negative, an empty string, and the rate threshold.
- A fake generator that loops under greedy and completes under beam → beam text is kept and `decode_mode=beam5_retry`.
- A fake that loops under both → `DecodeIncomplete`.
- A clean greedy segment → no retry, byte-identical request and output.
- Beam completion observation: the selected hypothesis without EOS → refuse.
- The policy-ID change → old cache records refuse.

*Measured on the omniasr side (2026-10-13):* beam 5 fixes **97 of 113** unique genuine greedy loops (86%). Median CER drops from 89.6 to 10.8.
- **16 still loop**, all long Zainab read speech. Those segments would halt honestly.
- **Optional (d), to be measured before adding it:** flag a segment when the LLM text is more than 1.5× the length of the CTC-3B text HawEdit already computes (arXiv 2408.09491).
- **Before T7, add a gate:** run real HawEdit runs on the owner's media with v12 + T8 and report the retry rate and the halt rate.

*ADR content:*
- the retry is a second decode of the same champion, not a model fallback;
- (b) and (c) are admission checks on top of natural EOS;
- the residual risk: beam can still loop, and that case halts.

**T7. Make v12 the default champion. Owner decision, NOT automatic.** Preconditions:
- (a) the queued v6-vs-v12 greedy comparison shows v12 is not worse;
- (b) the owner rules on the FLEURS-train question;
- (c) the owner says go;
- (d) T8 has landed: without the loop guard, v12 halts runs.

Then point the champion default at the v12 `.pt` and record the measured numbers.

## Out of scope (flagged for the owner)
- **The Qwen3 validator vs the Cortex canon "never Qwen ASR for ckb"** (`asr.py:98, 280-352`).
- **Merging or rebasing** onto `codex/evidence-based-studio` once that branch lands.

## Done means
`verify.sh` green **and** the required CI checks green on the PR (AGENTS.md workflow step 4). Never self-declared.
