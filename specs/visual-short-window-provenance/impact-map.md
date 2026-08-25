# Impact map — visual-short-window-provenance

Serena is unavailable; definitions and references were mapped with `rg` before implementation.

## Definitions and callers

| Symbol | Definition | Direct consumers / affected assertions |
|---|---|---|
| `SceneWindow` / `frame_count` | `src/hawedit/visual_index.py` | planner, index, cache identity, all visual adapters, pipeline reporting |
| `extract_window_frames` | `src/hawedit/video_input.py` | `visual_pipeline._FrameCache`, `QwenVisualEmbedder.embed_video`, pipeline TimeLens factory |
| `WindowFrames` | `src/hawedit/video_input.py` | Qwen embedder/reranker, VideoChat3 reader, TimeLens grounder, cache and cleanup tests |
| `window_video_metadata` | `src/hawedit/video_input.py` | shared `window_batch` used by every model adapter |
| `assert_timestamps_span_window` | `src/hawedit/video_input.py` | shared `window_batch`; prompt-clock tests |
| `assert_frames_reached_model` | `src/hawedit/video_input.py` | shared `window_batch`; exact-arrival tests |
| `_FrameCache` | `src/hawedit/visual_pipeline.py` | composed embedding, reranking, reader phases and pixel cleanup |
| `_EmbeddingCache` | `src/hawedit/visual_pipeline.py` | per-window vector reuse; D-140/D-193 identity tests |
| `QwenVisualEmbedder` / `QwenVisualReranker` | `src/hawedit/qwen_visual.py` | Stage 2 composed path, direct evidence CLI/helper tests |
| `VideoChat3Reader` | `src/hawedit/video_reader.py` | Stage 3 Path B survivor reading |
| `TimeLens2Grounder` | `src/hawedit/video_grounding.py` | Stage 5 interval evidence |
| `VisualComposer.discover` | `src/hawedit/visual_pipeline.py` | `run_pipeline`, full CLI, composed cache/lifecycle tests |

## Likely implementation surface

The experiment decides the smallest correct source surface. At minimum it will affect
`video_input.py`, `visual_pipeline.py`, and their tests. A still-image policy would additionally
touch all three adapter modules; an explicit video representation may stay behind the shared
`WindowFrames`/`window_batch` boundary. No caller is allowed to construct representation metadata
independently.

## Regression surfaces

* D-060 exact frame arrival and hidden-padding refusal.
* D-063 checkpoint-declared 2-fps ceiling.
* D-136 raw extraction count before parity trim.
* D-140/D-193 exact embedding-cache reuse identity.
* D-156 per-survivor unreadable accounting.
* D-190 strictest temporal patch across all checkpoints.
* unique private extraction directories and cleanup on every error.
* GPU phase close order before the next model is constructed.
* Path B survivor/score provenance and automatic selection.

Every changed caller gets a named regression; the full canonical gate is mandatory before any
ledger, blocker, or completion claim changes.
