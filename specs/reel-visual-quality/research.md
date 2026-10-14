# Research — Reel Visual Quality (ep29 demo defects, 2026-10-14)

Evidence: four frame grabs per reel from `scripts/run_tier3_demonstration.py` and
`scripts/run_bremer_story_demonstration.py`, rendered on HAWAPC01 (2× RTX 3090 Ti), ffmpeg
8.1.1-full_build (Gyan winget), source `ep29-chunk50min.mp4` 2560x1440 @25.

## 0. The demo scripts are not the pipeline, and they are not fake-free

The 2026-10-14 report said the scripts ran with "zero fakes or fallbacks". That was wrong. Both scripts
build the `Clip` by hand and skip every gate that the real `run_pipeline` runs:

| Location (both scripts) | What it does |
|---|---|
| `Editorial(hook_score=0.94, meaning_fidelity=1.0, cultural_landing=0.96, judge="gemini-2.5-pro")` | Hardcoded editorial verdict. No judge was called. |
| `AsrProvenance(canonical="omniASR_LLM_7B_v2", mean_logprob=-0.12)` | Hardcoded ASR provenance. ASR was not run; a pre-existing transcript was loaded. |
| `Qc(auto_pass=True)` | QC forced to pass. |
| `conf=item.get("conf", 0.95)` | Invented confidence when missing. |
| `headline_kurdish or "فەلسەفەی مینیمالیزم لە ژیاندا"` | Fallback hook text. |
| `source_path` → falls back to `work/stage0/proxy.mp4` | Silent source fallback. |
| `Encoder.X264` | Not NVENC (§6). |
| `SanityGate.run_full_audit(strict_fail_stop=False)` | Gate cannot stop the run. |

The real pipeline (`pipeline.py` ~2490–2525) runs `measure_clip`, `reconcile_delivery(min_face_share=…)`
and `render_critic.inspect_rendered_sequence`. The demo scripts run none of them.

`GeminiStoryEvaluator.evaluate_story` (`condenser.py:258-277`) silently fills in defaults when the
model omits fields: `virality_score` 85.0, placeholder Kurdish headline and summary,
`importance_score` 0.5, `keep` True. In `_condense_story_with_evaluator` (`condenser.py:571`), a
sentence the model did not score falls back to `_calculate_sentence_importance`. Both runs
printed exactly `78.5/100`. I could not tell from the log whether Gemini returned that number or it
came from a default path. **Unverified.**

## 1. Wide shot shows table, chair legs and carpet (bremer_frame_hook_banner.jpg)

Root cause: `reframe.median_face_box` (`reframe.py:875`) returns **one** `(center_y, face_height)`
for the whole clip. This is deliberate: the docstring says "one placement for the whole clip".
`render.crop_filter` → `vertical_framing` sizes one crop from that box. ep29 cuts between close-up
and wide cameras. Close-up samples dominate the median, so the wide shot gets the close-up crop
size (no tightening) and the subject ends up in the top third, above empty furniture.

Constraint already measured (D-258, `render.py:650-669`): `TARGET_FACE_HEIGHT_SHARE=0.15`,
`MAX_VERTICAL_ZOOM=1.5`. A 1440p 9:16 crop is 810x1440. That is already a 1.33x upscale to 1080 wide,
and a 1.5x zoom takes it to 2.0x. For a wide shot, zoom alone cannot reach close-up framing without
visible softness. So the honest options for wide shots are:
(a) per-shot zoom up to the 1.5x cap (better, still loose);
(b) a per-shot `Reframe.BLURRED_FILL` layout (sharp 16:9 over blurred 9:16), which already exists
    as `render.blurred_fill_filter`. Switching layout per shot needs segment-wise render + concat,
    because one ffmpeg graph cannot swap layouts by `sendcmd`;
(c) story selection that prefers spans without wide shots.

The `smart-reframe-cuts` work (ledger T1–T6) fixed horizontal tracking across cuts. It did not
touch vertical size per shot.

## 2. The gate passed it anyway

`sanity_gate.check_face_presence` (`sanity_gate.py:218-314`) passes a shot if a Haar cascade finds
**any** face of at least 50x50 px in at least one of three samples. Face share, headroom and empty
lower frame are never measured, so the wide-shot frame passes. `check_narrative_integrity` rounds
duration (`round(24.79) = 25`), so a 23.49 s effective reel passed a 25 s floor. The gate also
reported MaxChars 12 while the script requested 18. Not investigated.

## 3. Captions sit on the table and in the platform UI zone

The demo passed `margin_v=280`, which renders at `\pos(…,1640)` of 1920 (`CaptionStyle` default is
140, `captions.py:218`). That is in the band where Reels/TikTok/Shorts draw the caption, handle and
music ticker, and here it lands on the cup and glass. The exact platform safe zones are **not
measured here**. Commonly published guidance keeps the bottom ~20–25% and right ~10% clear, but
that needs checking against current platform specs before it becomes a constant.

## 4. Hook banner looks like a debug bar

`HookBanner` style is `BorderStyle=3` (opaque box), 54 pt, yellow on black (`captions.py` style
line, ASS `Style: HookBanner,...,3,16,0,8,60,60,120`). ASS has no rounded boxes. A modern badge
needs either `\p` vector drawing in ASS or a PNG overlay. The PNG route needs asset provenance
(`assert_asset_provenance`).

## 5. Not verified this session
- Transcript provenance: `ep29-chunk50min.transcript.norm.json` was loaded, not produced. I did not
  confirm which ASR produced it.
- Whether `run_pipeline` on these two spans would have failed `reconcile_delivery` /
  `render_critic`. That is the first thing to measure.
