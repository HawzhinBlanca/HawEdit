# Stage 2 embedding resume — measured 2026-08-10

## Claim

The composed Stage 2 path computes each source/window/model/revision embedding once and reuses the
atomic record on a later run. A cache mismatch never licenses reuse, and the run report exposes
hits and misses.

## Exact measured environment

- source code: the readiness worktree with D-215, forced through `PYTHONPATH=src`
- dependency profile: the fresh hash-locked Windows GPU profile produced by
  `requirements/host-gpu-windows-py311.txt`
- Python: 3.11.15
- Torch: 2.13.0+cu130
- CUDA devices visible: 2; embedding ran on `cuda:1`
- source: `ZAR38MinTest.mp4`, five consecutive 1,000 ms windows at 2 fps
- model: `Qwen3-VL-Embedding-2B`
- pinned revision: `9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`
- checkpoint bytes: the existing 18-file/4.3 GB tree accepted by `ModelStore` before the probe

The probe used the real extractor and real Qwen frame/text embedder. A deterministic in-process
reranker and reader kept this measurement scoped to the embedding cache; neither is evidence for
reranker or VideoChat3 quality.

## Result

```json
{
  "cuda_devices": 2,
  "embed_frame_calls_total": 5,
  "first_hits": 0,
  "first_misses": 5,
  "first_seconds": 36.176,
  "python": "3.11.15",
  "records": 5,
  "records_unchanged_second_pass": true,
  "revision": "9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda",
  "second_hits": 5,
  "second_misses": 0,
  "second_seconds": 8.266,
  "torch": "2.13.0+cu130",
  "windows": 5
}
```

Only five calls reached `embed_frames` across both passes. The second pass did not replace any of
the five records: both each file's SHA-256 and nanosecond mtime were unchanged. Its 8.266 seconds
include integrity-bound model reload and the query embedding, which intentionally still runs in
the current checkpoint's vector space.

## Adversarial controls in the canonical suite

`tests/test_visual_pipeline.py` requires:

- a clean second pass to report five hits and make zero new frame-embedding/extraction calls;
- a different pinned revision or replaced source to re-embed all windows;
- one truncated record to re-embed only that window;
- a JSON boolean vector to be rejected even when its record digest is recomputed;
- failed atomic publication to leave neither a shared record nor a private temporary file;
- an arbitrary revision such as `main` to be refused.

`tests/test_pipeline.py` separately proves that the production composer receives the exact
revision from trusted model metadata. The canonical gate remains CPU-only by design; this live
probe is additive hardware evidence, while the gate carries all deterministic controls.
