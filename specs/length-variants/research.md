# Research — Length Variants 15/30/60 (§5 durations) (Task T2.11)

## 1. Problem Statement
BLUEPRINT §5 specifies:
```json
"output": {
  "title_ckb": "...",
  "description_ckb": "...",
  "crop_target": "speaker_face",
  "caption_style": "word_highlight",
  "durations": [15, 30, 60]
}
```
In `pipeline.py`, however, `output.durations` currently carries only a 1-element tuple matching the single rendered clip duration (e.g. `durations=(57,)`).
Social media distribution requires different lengths for different platforms and viewer contexts:
- **15s**: Instagram Stories, YouTube Shorts quick hook, TikTok rapid-scroll.
- **30s**: Standard TikTok / Instagram Reels pacing.
- **60s**: In-depth narrative / complete contextual argument.

Task T2.11 requires:
> "Length variants 15/30/60 (§5 `durations`). Sentence-complete sub-spans inside the winner, each re-judged (billed) and re-reconciled; one delivery set per variant."

## 2. Invariants & Requirements
1. **Sentence-Complete Sub-Spans (Invariant #2 & #5)**:
   - Sub-spans must never cut mid-sentence. Every variant must start at `sentence[i].start_ms` and end at `sentence[j].end_ms`.
   - Every included sentence must have `complete == True`.
2. **Hook Anchoring**:
   - For short-form social reels, the hook sentence (sentence 0) must be preserved in the short variants (15s and 30s) so the clip retains its critical 0–3s viewer retention trigger.
3. **Target Tolerances**:
   - Spans are matched against target durations `(15, 30, 60)` seconds.
   - Because sentences are natural human speech segments of varying lengths, exact second matching is impossible without cutting words. We select the sentence boundary that minimizes $| \text{duration} - \text{target} |$ within reasonable bounds (e.g. 10–22s for 15s; 22–40s for 30s; 45–70s for 60s).
   - If the source winner is shorter than a target (e.g., winner is 35s, so no 60s variant is possible), only the achievable variants are emitted.
4. **Independent Delivery Sets & Reconciliation**:
   - Each variant produces an independent, self-contained deliverable bundle:
     `<work_dir>/delivery/<clip_id>-{variant}/` containing `.mp4`, `.ass`, `.srt`, `.edl`, `.json`, `.measured.json`, and `.cover.png`.
   - Each variant is reconciled with Level C `reconcile_delivery`.
   - The primary clip's `Output.durations` records the actual durations of all emitted variants.

## 3. Real Code Surface Mapping
- `src/hawedit/sentences.py`: `Sentence`, `assert_deliverable_order`.
- `src/hawedit/clip.py`: `Output.durations: tuple[int, ...]`.
- `src/hawedit/delivery.py`: `publish_delivery_bundle`, `reconcile_delivery`.
- `src/hawedit/render.py`: `render_clip`.
- `src/hawedit/variants.py` (New module): `LengthVariant`, `plan_length_variants`.
