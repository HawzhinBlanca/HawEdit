# Research — Cold-Open Assembly (Task T4.9, Re-opened Pro-Edit T6)

## 1. Problem Context

Task **T4.9** from `specs/pro-grade-program/tasks.md` re-opens Pro-Edit Task T6:
> "Cold-open assembly (re-opened pro-edit T6). Render a real reel: payoff sentence first, then the setup, media concatenated with `xfade`/`acrossfade`, ASS regenerated on the assembled timeline, punch-ins re-timed; judge the **assembly** with frames from the assembled render; `misleading_edit_risk` gated on the assembly. Reconcile."

In standard social reel production, viral Kurdish reels often employ a "cold open":
- The single most punchy, controversial, or revealing sentence (the payoff/climax) is placed right at the beginning (0–3s hook).
- The narrative then cuts to the contextual setup and chronological explanation.
- While `src/hawedit/assembly.py` introduced timestamp re-offsetting and text judging, it was strictly text-only: it did not render actual media, did not splice video/audio streams with crossfades, did not re-time punch-ins, did not extract frames from the assembled render, and did not pass real assembled video frames to the multimodal judge.

## 2. Requirements & Invariants

### 2.1 Timeline Assembly & Splicing
- Cold-open order: Payoff span placed first $[0, D_{\text{payoff}}]$, followed by setup span $[D_{\text{payoff}}, D_{\text{payoff}} + D_{\text{setup}}]$.
- Words and sentences re-offset onto continuous timeline starting at $t=0$, preserving Kurdish invariant #1 (exact surface words) and invariant #2 (complete sentences).
- Audio and Video spliced via FFmpeg filtergraph:
  * Audio crossfade (`acrossfade=d=0.15:c1=tri:c2=tri`) or clean cuts on zero-crossings.
  * Video cuts or dissolve transitions (`xfade=transition=fade:duration=0.15:offset=...`) maintaining 1080x1920 9:16 vertical framing.

### 2.2 Re-Timed Subtitles and Punch-Ins
- ASS subtitles generated directly on `reel.assembled_sentences`, ensuring zero caption drift across the splice boundary.
- Punch-ins scheduled on sentence boundaries of the assembled timeline, resetting scale to 1.00x across the splice boundary to give a motivated visual cut.

### 2.3 Frame-Based Multimodal Judging
- Keyframes extracted directly from the *assembled render* (not the source file), covering both the cold-open hook and the setup progression.
- Evaluated with `EditorialJudge` using real frame evidence.
- Strict gate: `verdict.misleading_edit_risk <= MAX_MISLEADING_EDIT_RISK` (0.10) to ensure the non-chronological splicing has not distorted the speaker's true intent.

## 3. Integration Points
- `src/hawedit/assembly.py`: Extend with `assemble_cold_open`, `render_assembled_reel`, `judge_assembled_reel_multimodal`.
- `src/hawedit/render.py`: Re-use filtergraph generators, two-pass loudnorm, and NVENC/CPU encoding logic.
- `src/hawedit/captions.py`: Re-use `build_ass` with RTL Sorani shaping.
- `src/hawedit/keyframes.py`: Re-use bounded keyframe extraction.
