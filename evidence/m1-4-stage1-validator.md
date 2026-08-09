# M1.4 — real Stage 1 validator composition

Measured on hawapc01, 2026-08-09. This file proves execution and composition. It does **not**
claim Sorani accuracy: the repository has no labelled Sorani benchmark corpus.

## Runtime provisioning

The Windows route provisions one source-fingerprinted WSL2/Python 3.12 environment. The resolved
Stage 1 graph is:

| Component | Version |
|---|---:|
| Torch | 2.8.0 |
| torchaudio | 2.8.0 |
| omnilingual-asr | 0.2.0 |
| qwen-asr | 0.0.6 |
| Transformers | 4.57.6 |
| Accelerate | 1.12.0 |

The setup imports both ASR libraries, checks the exact matched Torch/torchaudio versions and
refuses fewer than two CUDA GPUs. Result:

```text
OmniASR import OK; CUDA GPUs visible: 2
READY: OmniASR WSL2 runtime at C:\Users\Wareen\AppData\Local\HawEdit\wsl-asr
```

The first real setup caught three deployment defects before this result:

1. passing a multiline script as `bash -lc` through `wsl.exe` lost argument boundaries;
2. switching to stdin without a login shell hid user-installed `uv` and Python 3.12;
3. the unconstrained resolver paired Torch 2.8 with torchaudio 2.11, whose binary required
   `libcudart.so.13` and failed during the mandatory import probe.

The final provisioner uses `bash -l -s` and pins the matched 2.8 pair. An `uv pip compile` of
`.[asr]` resolves 137 packages; `.[asr,gpu]` is intentionally not supported because the separate
visual stack is verified on Torch 2.13.

## Real rzgar adapter

Input: the checkpoint's shipped `demo_04.wav`. Loader: `Qwen3ASRModel.from_pretrained`, exactly
as the model card specifies. Device: RTX 3090 Ti GPU 1.

```json
{
  "elapsed_s": 128.013045546,
  "peak_vram_bytes": 4250408448,
  "model_id": "rzgar/qwen3-asr-sorani-kurdish-ckb-v1",
  "audio": "demo_04.wav"
}
```

The emitted Sorani text matched the model card's full reference string exactly. This is a
positive control for checkpoint/loader/device/output correctness, not an independent accuracy
sample.

## Real composed CLI

Command shape:

```powershell
python -m hawedit.pipeline tests/fixtures/kurdish-speech-3cuts.mp4 `
  --work-dir .gate/real-pipeline-m1-4-pcm --omni-asr --json
```

Observed on the final warm-cache run:

| Fact | Result |
|---|---:|
| Wall clock, whole CLI | 212.9 s |
| Stage 0 VAD regions | 2 |
| Final aligned words | 13 |
| Canonical provenance | `omniASR_LLM_7B_v2` |
| Aligner provenance | `ctc_viterbi` |
| Validator provenance | `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` |
| Mean aligned log-probability | -12.49715594480495 |

The run downloaded/loaded the official 31.2 GB LLM and 12.3 GB CTC model-card assets, invoked
one WSL worker, ran LLM and CTC forwards in parallel per segment, selected disagreement via the
production policy, loaded rzgar lazily, re-aligned its final text with CTC, persisted the raw
transcript, normalized it and built the text index. Downstream stages were explicitly skipped
because visual/Gemini were not enabled; the CLI reported them and remained incomplete.

The fixture is deliberately Kurmanji synthetic speech. Its own test documentation forbids using
it for §8.1 accuracy. The output therefore proves that the real components and runner join work;
it supplies no CER, dialect, named-entity or code-switch result.

## Remaining clock edge

The source video duration is 4162 ms, while its extracted audio and Silero's second speech span
end at 4180 ms. The final aligned word therefore ends at 4180 ms. Stage 1 now reads the exact PCM
duration after every cut, which prevents scaling to a requested duration when ffmpeg truncates;
here ffmpeg did not truncate because the audio stream genuinely outlives the video. The pipeline's
boundary fusion clamps to media duration, but Stage 0/pipeline should reconcile speech spans to
the visual media clock so raw word timings cannot exceed shippable video. This is recorded, not
misrepresented as fixed.

## Adversarial controls

Four exact mutations were applied one at a time and restored before the final gate:

| Mutation | Caught by |
|---|---|
| return before every escalation | bottom-quartile and disagreement integration tests |
| call rzgar but align the original LLM text | final-text/alignment assertions |
| scale alignment to requested instead of emitted PCM | shortened-cut regression |
| remove the torchaudio 2.8 install pin | WSL setup contract test |

Result: 4/4 caught. Final canonical gate: 1,175 passed, zero skipped; Ruff, formatting and strict
mypy clean.
