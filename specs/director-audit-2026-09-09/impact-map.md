# Provisional caller and integration map

Source anchor: `7f499f53560b94c398c8c4d526e1c44e37ca4f5e`.
Method: `rg` across `src`, `scripts`, `tests`, then direct source inspection. Serena was not callable; refresh semantic references before editing. No symbols were edited during this audit.

| Area / symbols | Current callers or consumers inspected | Planned consequence / regression surface |
|---|---|---|
| `web.JobManager.submit_job`, `_run_job_stages` | `HawEditWebHandler.do_POST`; browser Generate/poll code | Replace simulated completion with real workflow; test no-source validation, progress, restart, distinct candidate preview/download and errors. |
| `condenser.condense_story`, `condense_multiple_arcs` | Internal condenser calls; `tests/test_condenser.py`, `tests/test_soak.py`; no production pipeline caller found | Introduce semantic decision producer and whole-source coverage; preserve source mappings, avoid treating positional heuristics as semantic ground truth. |
| `story.build_story_map`, `StoryMap` | `tests/test_story.py`; no producer in `pipeline.py` found | Infer and verify relations; support speech-only evidence and mandatory context; test all relation consumers after contract changes. |
| `shot_plan.build_shot_plan`, `PlannedShot` | Shot-plan tests; types consumed by composition, captions, timing, critic and repair modules | Generate plans from observed shots and meaning; preserve every dependent timebase/region contract. |
| `render_critic.generate_critique_windows`, `inspect_rendered_sequence` | `tests/test_render_critic.py`; `visual_repair.py:367`; no canonical pipeline invocation found | Split planned windows from actual media observations; missing evidence must invalidate repair and packaging approval. |
| `episode_package.build_episode_package` | `tests/test_episode_package.py`; accepts external quality scores and critique result | Integrate real candidate processing and actual artifact identities; ensure quota/dedup cannot hide failures or force weak clips. |
| `sanity_gate.check_narrative_integrity`, `check_face_presence`, `SanityGate.run_full_audit` | `scripts/render_pro_reel_master.py`; sanity-gate tests | Replace semantic claims based on nonempty text and frame presence based on max sample count; test absent detector, valid reaction, crop loss and actual spoken continuation. |
| `pipeline.run_pipeline` / tournament | CLI construction, durable workflow and agent orchestration | Connect one authoritative editorial route without regressing real Path A, visual discovery, accounting, sentence protection, refusal or source identity. |
| `assembly.assemble_spans`, `assembled_splice_filter`, `judge_assembly`, multimodal assembly judge | Assembly tests, helper render functions, episode-specific `work` scripts | All multi-span outputs require whole-sequence judgment and semantic closure; preserve re-timed audio/video/captions. |
| `reframe` trackers / `render.render_clip` | Pipeline, renderer, render agent, proposal/revision paths | Fix source-shot transitions and final framing; preserve exact output identity and re-review after revisions. Optional YuNet already exists: do not claim it needs to be added from scratch. |
| `captions.build_ass` / `CaptionStyle.KINETIC_POP` | Canonical render, assembly, custom episode scripts | Judge actual RTL layout, readability and word coverage; custom styling may not bypass meaning/clock checks. |
| `edit_plan.SourceTimeMapping`, `VisualEditPlan` | Assembly/visual helper contracts, custom master renderer | Make plan authoritative for all render and sidecar outputs; do not create a second incompatible timeline. |
| `visual_scorecard`, `editorial_acceptance`, `comparison_kit`, `learning` | Existing evaluation and decision-record machinery | Bind independently acquired outcomes to exact source/output versions; retain episode-level uncertainty, all failures, interventions and contamination controls. |
| `tests/conftest.py`, `scripts/verify.sh`, required CI | Canonical gate and media-tier collection | Enforcement-surface changes need the self-edit marker and approved plan. Preserve gate authority and expose which real-media tests actually ran. |

Do not implement every row as a new module. First trace and connect existing data producers to consumers. Track custom `work` scripts as development examples, not as the accepted app path. Preserve historical documents and use contradiction notes when status claims disagree.
