# Research: Silence Tightening Wired End-to-End (Task T3.3, ADR D-266)

## 1. Problem Statement & Context
Pro Kurdish social reels require punchy, high-retention pacing without dead air. Longform source audio (such as podcast discussions and interview pauses) frequently contains unvoiced gaps (400–1200 ms) between utterances.
While `src/hawedit/silence.py` contains basic mathematical helper functions (`tighten_silence`, `tighten_sentences`, `tighten_clip`) to shift `Word` timestamps, it was never connected to the actual media render or the pipeline:
1. `pipeline.py` did not invoke `tighten_clip` or pass silence tightening parameters.
2. `render_clip` in `src/hawedit/render.py` cut a single continuous interval `-ss clip_in -t duration_ms -i source`. It did not trim or splice media streams.
3. Subtitles (`build_ass`), camera focus points (`focus_points`), punch-ins (`punch_ins`), and source shot cuts were not re-timed against the tightened timeline.
4. `reconcile_delivery` in `src/hawedit/delivery.py` includes Clause 4:
   ```python
   expected_silence_removed = clip.output.silence_removed_ms if clip.output else 0
   measured_audio_dur = measurement.audio.duration_ms
   measured_removed = span_ms - measured_audio_dur
   if abs(expected_silence_removed - measured_removed) > tolerance_ms:
       raise DeliveryRefused(...)
   ```
   Without actual media trimming, any non-zero `silence_removed_ms` immediately triggers `DeliveryRefused("silence_math_mismatch")`.

## 2. Technical Architecture & Constraints
### A. Threshold Policy & Intent
Per `specs/pro-grade-program/tasks.md` Task T3.3 and `HANDOFF.md`:
- "Threshold is a parameter with no default until Hawa sets it from a measured A/B."
- Default must remain **0 / disabled** unless explicitly passed via `--silence-threshold-ms` or configured in a content-type profile.
- When enabled (e.g. `--silence-threshold-ms 500`), pauses between words exceeding `threshold_ms` are tightened to `target_gap_ms` (default 150 ms, natural breath pacing).

### B. Media Retained Intervals
Given words in the selected clip span `[clip_in_ms, clip_out_ms]`:
For any consecutive pair of words $W_i, W_{i+1}$ where $W_{i+1}.\text{start\_ms} - W_i.\text{end\_ms} > \text{threshold\_ms}$:
- Keep $W_i.\text{end\_ms} + \text{target\_gap\_ms}$.
- Excise $[W_i.\text{end\_ms} + \text{target\_gap\_ms}, W_{i+1}.\text{start\_ms}]$.
- Retain all active speech intervals.
The sum of excised durations is $\Delta_{\text{total}} = \text{silence\_removed\_ms}$.
The resulting media duration is $\text{effective\_duration\_ms} = (\text{clip\_out\_ms} - \text{clip\_in\_ms}) - \Delta_{\text{total}}$.

### C. FFmpeg Media Splicing Architecture
In `render_clip`, we decode `-ss {clip.in_ms/1000} -t {duration_ms/1000} -i {source}`.
When silence tightening is active ($\Delta_{\text{total}} > 0$ and retained intervals count $N > 1$):
We construct filter complex segments:
For interval $k$ with bounds $[s_k, e_k]$ (relative to clip in-point):
`[0:v]trim=start=s_k:end=e_k,setpts=PTS-STARTPTS[v_k];`
`[0:a]atrim=start=s_k:end=e_k,asetpts=PTS-STARTPTS[a_k];`
Concatenate all $N$ pairs:
`[v_0][a_0]...[v_{N-1}][a_{N-1}]concat=n=N:v=1:a=1[v_stitched][a_stitched]`
Then `[v_stitched]` feeds into `crop_filter` and `subtitle_filter`, and `[a_stitched]` feeds into `audio_filter` (speech chain + loudnorm).
If $N == 1$ (no pauses exceeded threshold), the standard single-stream pipeline runs with zero concatenation overhead.

### D. Timeline Synchronization
When media is spliced, all downstream events must be re-timed to the concatenated timeline:
1. **Captions**: `tighten_sentences` adjusts `Sentence` and `Word` start/end times. `build_ass` is called with the tightened sentences, so caption events match the tightened speech exactly.
2. **Punch-in Cuts**: Any punch-in at source time $T$ shifts to $T' = T - \text{cumulative\_removed}(T)$.
3. **Face Focus Points**: Continuous face tracking keyframes $(t, x)$ shift to $t' = t - \text{cumulative\_removed}(t)$.
4. **Shot Cuts**: Source shot cuts within the clip span shift similarly so punch-in collision avoidance matches the new video timeline.
5. **Encoded Span Verification**: `assert_encoded_span` in `render_clip` checks against `effective_duration_ms = duration_ms - silence_removed_ms`.
6. **Delivery Reconciliation**: Clause 1 (`duration`), Clause 4 (`silence_math_mismatch`), Clause 5 (`missing_punch_in_cut`), Clause 6 (`caption ink`) all reconcile with 0 tolerance errors.

## 3. Serena Symbol Mapping
- `hawedit.silence`:
  - `tighten_silence(words, threshold_ms, target_gap_ms)` -> `tuple[tuple[Word, ...], int]`
  - `tighten_sentences(sentences, threshold_ms, target_gap_ms)` -> `tuple[tuple[Sentence, ...], int]`
  - `tighten_clip(clip, threshold_ms, target_gap_ms)` -> `tuple[Clip, int]`
- New helpers in `hawedit.silence`:
  - `plan_silence_tightening(...)` -> `SilencePlan`
  - `remap_timestamp(t_ms, plan)` -> `int`
  - `silence_trim_filter(...)` -> FFmpeg filtergraph snippet
- `hawedit.render.render_clip`:
  - Accepts `silence_plan: SilencePlan | None = None`
  - Re-times `focus_points` and `punch_ins`
  - Applies `silence_trim_filter`
  - Validates `effective_duration_ms` in `assert_encoded_span`
- `hawedit.pipeline.run_pipeline`:
  - Accepts `silence_threshold_ms: int | None = None`, `silence_target_gap_ms: int | None = None`
  - When active, plans tightening, tightens clip and sentences before `build_ass`, re-times cuts and punch-ins, passes plan to `render_clip`.
