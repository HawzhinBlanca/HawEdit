# HawEdit reassessment — visual editorial intelligence

Assessment date: 2026-09-06. Inspected commit: `b134305847936f59c8c88490cfeffe24f66f2236`. The checkout was clean at the beginning of this review. Scope: current-product assessment and a visual-first plan; no application implementation in this task.

## Verdict

**My provisional overall rating remains 6/10.** HawEdit has improved its review mechanics since the earlier snapshot, but there is no new exported clip in the inspected work directory demonstrating better visual results. For the ambition “acts like a careful team of visual editors,” I would currently give it **5/10**. Its Sorani workflow fit remains a promising **7/10**, which is not a speech-accuracy measurement. These are explicitly reviewer judgments, not benchmark scores or mathematical estimates.

The central gap is judgment across time. Seeing selected frames, detecting a face and ranking a transcript passage do not establish that the system understands why a reaction matters, which detail must stay visible, whether the question is needed, or whether the rendered edit tells the intended story. The current architecture contains useful components for these jobs, but it does not yet demonstrate a complete, independently verified observe → decide → render → watch → repair workflow. Additional effects would not establish that capability. The strongest next investment is visual evidence and content-aware decisions connected to the delivered artifact.

## Comparison with three strong current competitors

This keeps the same comparison set as the preceding review: OpusClip, Klap and Submagic. They are relevant leading products, not an objectively proven market-wide top three. Vendor feature documentation was checked today; their internal reliability and comparative Sorani accuracy were not audited. No same-source paid competitor run was performed.

| Product | Provisional product rating | Relevant strength for this request | What is not proven here |
|---|---|---|---|
| OpusClip | 9/10 | ClipAnything advertises multimodal moment discovery, cross-scene reasoning and object/action reframing; its help documents layout editing and manual correction. [Official product](https://www.opus.pro/clipanything), [layout help](https://help.opus.pro/docs/article/layout-and-reframing). | “Every frame” and quality claims are vendor descriptions, not an audited internal architecture or proof of flawless editing. |
| Klap | 8/10 | Content-zone reframing, speaker/saliency focus, transcript editing and batch clips. Its API exposes transcription context such as names and jargon. [Product](https://klap.app/tools/ai-clip-maker), [API](https://docs.klap.app/endpoints/tasks). | Cross-scene editorial correctness, calibration and Sorani results have not been measured here. |
| Submagic | 8.5/10 | Mature visual finishing controls, captions and transcript-driven suggested zoom placement. [Official editor](https://www.submagic.co/features/auto-video-editor). | Visual polish is not evidence of the strongest full-episode narrative understanding. Its music/effects breadth is not a priority for this plan. |
| HawEdit | 6/10 | Sorani-focused source handling, constrained boundaries, explicit model roles, local control, provenance and improving review mechanics. | Connected visual quality repair, consistent released output, current exact-SHA CI and blind superiority are not established. |

Do not interpret a 9 versus 6 as “50% better.” These are rough product judgments with asymmetric evidence: HawEdit's source is inspectable, competitors' source is not. No claim that any competitor is inherently more reliable is justified by this table alone.

## What genuinely changed since the earlier review

The old reference was `508f986e9f0ed5745d9ff46a9bffb9413b8a5456`. Source inspection now shows:

- `clip.py` defines explicit approving/rejecting verdict sets and `Qc.from_record` refuses a rejecting record. Credit this fix; do not repeat the old unsupported-verdict finding as current.
- Both revision render paths invalidate previous human review instead of rewriting its media hash to new bytes. Credit the repaired semantics; this is not yet certification of every revision/publication path.
- The pipeline retains review candidates and has an approved-candidate promotion route; `delivery.promote_candidate` exists.
- Caption-ink detection is more discriminating than the previous single texture-variance rule, and separate text/glyph/geometry checks now exist.
- The feature ledger records local passes for T00–T03. However, `tasks.md` also retains an unchecked copy of the same rows and contradictory introductory wording. Fix document consistency through the normal ledger/doc process; checkbox count is not runtime evidence.

These changes strengthen the foundations. They do not establish a higher visual-output rating without a new output and an appropriate evaluation.

## Current blocking findings

| ID | Finding | Evidence and scope | Priority |
|---|---|---|---|
| F01 | **Missing measurement dependency becomes invented success.** | A direct controlled dependency-failure probe of `measure.probe_caption_ink` returned `ink_energy_detected_share=1.0` and `median_contrast_ratio=5.0` when `cv2` import was unavailable. This is a reproduced function-level fail-open condition, not a claim OpenCV is absent on the normal host or that a whole production run bypassed preflight. | P0 |
| F02 | **New caption-integrity helpers are not connected to delivery.** | `rg` over `src/` and `scripts/` found `verify_caption_integrity` only in exports/definition; its child validators are called by that helper. The current `pipeline` measurement call supplies no matched caption-free reference. Helper tests do not prove enforcement in the main run. | P0 |
| F03 | **Promotion trusts saved measurements too much for a top-grade claim.** | `delivery.promote_candidate` reads saved measurement JSON and compares its media SHA, then reconciles it. It copies ASS/SRT/EDL sidecars. It does not freshly observe all relevant claims or bind every sidecar and effective edit configuration in the inspected route. This is a provenance/validation gap, not a reproduced tampering exploit. | P0 |
| F04 | **Current commit has no returned GitHub Actions run.** | `gh api repos/HawzhinBlanca/HawEdit/actions/runs?head_sha=b134305847936f59c8c88490cfeffe24f66f2236&per_page=10` returned `total_count: 0`. The latest listed gate run was for an older August commit. Exact-SHA hosted acceptance is not established. | P0 for release claims |
| F05 | **No newly demonstrated visual improvement.** | Newest MP4 found under `work/` remains the 00:11 broadcast export. Its sampled frames still have small subtitles and wide shots with substantial table/chair area. No full-clip motion/audio quality claim is made from stills. | P1 |
| F06 | **Sparse source inspection cannot certify temporal editing judgment.** | `keyframes.extract_judge_frames` defaults to 20 evenly spaced JPEGs, bounded to 20. `VisualComposer` embeds windows, retrieves/reranks and sends survivors to VideoChat3. These are legitimate budgeted observations, but events between samples and excluded windows are not thereby understood. | P1 |
| F07 | **Face tracking still lacks robust listener/off-screen identity semantics.** | `MotionSpeakerTracker.track_speakers` still binds a lone detected face to the current diarized speaker and uses mouth-region pixel motion for multiple faces. This can confuse visible listeners, camera motion and speaker identity. Frequency on real footage remains unmeasured. | P1 |
| F08 | **No connected visual editorial inspection of the finished edit was found.** | The main judge request is created before render using source frames. After render, pipeline measurement/reconciliation checks media properties; no subsequent rendered-video editorial judge/repair loop appears in the inspected path. Existing diagnostics/proposal agents are useful infrastructure, not proof of this loop. | P1 |
| F09 | **Episode selection remains disconnected.** | `select_episode_plan` still has no production call in the scoped source/script search. The main path selects one winner. Existing ranking/diversity mismatch and source-to-output mapping issues from the prior audit remain implementation targets. | P1 |
| F10 | **“Understands content” lacks a released holdout result.** | Existing rubrics and acceptance tools do not supply a current blind outcome on unseen Sorani episodes. Questions, qualifications, reactions and meaning preservation must be labelled and evaluated, not inferred from model names or fluent explanations. | P1 |

F01–F04 prevent a credible “most robust” claim. F05–F10 prevent a credible “real team editor” or “number one” claim. They should not be averaged away by strengths in unrelated areas.

## Artifact observation

Inspected: `work/ep29-broadcast-master/ep29-VbX8UWwl1c4-s25-25.mp4`.

- SHA-256: `50e5a57619c9c6737caa3ef48f2c0a79e1cc3b80073c795389a0b2ee55e3a604`.
- FFprobe: 1080×1920, 25/1 fps, duration 56.600000 seconds.
- Tool: FFmpeg/FFprobe 8.1.1 full Gyan build, Windows host `HAWAPC01`, Python 3.12.10 for the fault probe. No GPU model benchmark was run.
- Contact sheet command: `ffmpeg -hide_banner -loglevel error -i work/ep29-broadcast-master/ep29-VbX8UWwl1c4-s25-25.mp4 -vf fps=1/5,scale=270:-1,tile=4x3 -frames:v 1 -update 1 -y <temporary-jpeg>`.
- The contact sheet's unused final tile is black padding from the sheet layout; it is **not evidence of a black frame in the video**.
- Visual opinion: close-ups are usable; the caption scale and some wider compositions are below the intended premium mobile presentation. A visible listener shot is not automatically wrong: audio/context must determine whether it is useful or misleading.

## Reproducer for F01

Run with the project interpreter from the repo root. This simulates an unavailable dependency only inside the process; it does not uninstall packages or alter source/tests.

```python
import sys
import json
from pathlib import Path
from dataclasses import asdict
from unittest.mock import patch
from hawedit.measure import probe_caption_ink

media = Path("work/ep29-broadcast-master/ep29-VbX8UWwl1c4-s25-25.mp4")
with patch.dict(sys.modules, {"cv2": None}):
    print(json.dumps(asdict(probe_caption_ink(media, media.with_suffix(".ass")))))
```

Observed literal result:

```json
{"events_count": 45, "ink_energy_detected_share": 1.0, "median_contrast_ratio": 5.0}
```

Required future behavior: structured unavailable/failed measurement, with publication refused when that evidence is required. The measurement must never substitute a plausible success number. Audit adjacent dependency fallbacks too.

## External research and what it contributes

- [Google Research AutoFlip](https://research.google/blog/autoflip-an-open-source-framework-for-intelligent-video-reframing/) describes scene-based reframing and adapting crop behavior to salient content. The architectural lesson is to plan a camera path over a shot rather than chase isolated detections. This is an older primary reference, not a recommendation to replace HawEdit with AutoFlip.
- [Video-MME](https://arxiv.org/abs/2405.21075) and [Video-MME-v2](https://arxiv.org/abs/2604.05015) separate temporal and multimodal reasoning demands. They motivate event-order and cross-scene tests; benchmark scores cannot establish professional editing quality or Sorani understanding.
- [Creator repair-work report](https://www.reddit.com/r/ContentCreators/comments/1uavwy8/i_still_spend_hours_editing_after_using_opus_clip/) and [mid-idea cutting report](https://www.reddit.com/r/YouTubeCreators/comments/1uawdyq/opus_clip_keeps_cutting_clips_in_the_middle_of/) describe fixing boundaries and weak standalone selections. These are anecdotes with promotional replies, not prevalence estimates. The relevant outcome is reduced correction effort and stronger complete passages, not more generated clips.
- The official competitor sources above establish product scope only. This assessment does not adopt vendor accuracy, virality, “every frame” or superiority claims as measured facts.

No internal analytics or user interviews were available for this scan. The current code, controlled fault probe and actual local artifact are the strongest evidence. Serena tools were not exposed; references were mapped with `rg` and source reads, with semantic re-grounding required before implementation. Work stayed sequential in accordance with the user's host-stability instructions.

## Research conclusion

The route to a defensible leading system is **source-grounded visual editorial judgment followed by inspection of the rendered result**, with uncertainty handled honestly. The next [plan](plan.md) specifies that route in executable units, reuses the approved reliability program and keeps music/sound design outside the critical path.
