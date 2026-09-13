# Reality check — are we at 10/10? (2026-09-13)

HEAD aa6b43d (11 commits since the 2026-09-09 director audit at 7f499f5). Measured on HawaPC01,
ffmpeg 8.1.1, `hawedit.measure` schema 1. Working tree: `src/hawedit/web.py` modified, uncommitted.

## Answer

**No. Director score stays 3/10.** The 11 commits added 5,879 lines and 85 tests and moved the
production path approximately nowhere. Two things got worse: the studio now ships six hand-cut
reels with music beds and sound effects as if they were pipeline output, and the only artifacts
the pipeline ever produced were deleted from `work/`.

## D1–D9 at HEAD aa6b43d

| ID | Claim | 09-09 | 09-13 | Evidence |
|----|-------|-------|-------|----------|
| D1 | Every reel from an EditPlan artifact; no hand-cut scripts | red | **red** | `VisualEditPlan` is written *after* `bundle.publish()` inside `suppress(Exception)` (`pipeline.py:3379-3383`); nothing reads it; not in `ArtifactBundle.suffixes()`; no gate refuses an mp4 without one. 8 mp4s under `work/`, 0 plan files. `scripts/render_pro_reel_master.py` still tracked with `span_words[44]…[172]`. Today's reel came from `scratch/render_perfect_reel.py` with hand-typed trim and crop offsets. |
| D2 | No synthetic imagery; no asset without provenance | red | **red, worse** | `work/assets/`: threat-letter jpg, `music_tension_bed.wav`, `sfx/{chamber_click,clock_tick,sub_bass_drop,whoosh}.wav`. All three studio flagship reels mix them (up to 11 audio inputs). No provenance file. No gate. `--music-bed` is a first-class pipeline flag (`render.py:1453-1511`). |
| D3 | Critic signs every join; no dangling-conjunction joins | red | **red** | `render_critic.inspect_rendered_sequence` has zero callers in `pipeline.py`/`web.py`/`cli.py`; it checks bytes, SHA, brightness and audio presence, and takes editorial defects as `injected_observations` from the caller. It never reads join words. Dangling-conjunction check sets `anchors=None` (`pipeline.py:1415`); it does not refuse. |
| D4 | Word-level filler/restart excision, hidden under punch-ins | red | **partial** | `excise_fillers=False` by default (`pipeline.py:1750`), on only under `--preset viral`. List grew 8→26 tokens (`silence.py:39-68`); stale 8-token copy remains in `condenser.py`. No restart/repetition detection. Excision cuts are *offered* to the punch-in scheduler, not guaranteed a framing change. Today's reel: 16% silence, six gaps of 274–893 ms. |
| D5 | Active-speaker face ≥98% of speaking frames | red | **red** | `measure.py` reports any-face share over fixed samples; delivery threshold is 0.90 (`delivery.py:507-521`). Today's reel measured 96.1% (123/128 samples). `sanity_gate.check_face_presence` has no src caller. |
| D6 | Discovery reproducible, K=5 voting | red | **red** | No K, vote or agreement code in `path_a.py`/`discovery.py`/`pipeline.py`. `compute_repeat_k_agreement` called only from a test. |
| D7 | Ranker fitted on ≥200 human-rated clips | red | **red** | `judge.py:809-817` weights 0.40/0.30/0.20/0.10 unchanged, docstring still says "calibrated". No editorial dataset, no fit report. |
| D8 | H7 blind panel, CI lower bound >50% | red | **red** | `comparison_kit.py` tooling exists. Zero studies. Zero numbers in `evidence/`. Zero evidence files of any kind since 09-09. |
| D9 | −14 LUFS, no added music | red | **half** | Pipeline target is −14.0 with 0.5 dB tolerance (`render.py:143`, `delivery.py:442`). Shipped reels are not from the pipeline: today's reel is hand-normalised to −14.5 and measures −13.9, with music and 4 SFX. |

Score: 0 green, 2 partial, 7 red. Same as 09-09 with D4 and D9 half-moved.

## What the 11 commits actually did

| Commit | Claim | Reality |
|--------|-------|---------|
| 180424a | "autonomous viral highlight discovery" | `web.py:834-836`: `is_ep29 = "ep29" in stem or "threat" in stem`; if true, return a typed list of six mp4 paths with literal virality scores 98.0, 95.0, 92.5, 99.0. No scoring code. Any other file gets URLs to mp4s that do not exist. |
| 4256649 | "ultra-tight viral reel as premier candidate" | 15-line insert of a hardcoded path and the literal 99.5. |
| f355c4a | "publish VisualEditPlan, multi-span assembly" | Plan written post-publish and swallowed on failure. `assemble_spans` is live behind `--assemble`, off by default. |
| 52f49a3 | "media-grounded critique, complete thoughts" | Critic has no production caller. |
| 7a9c1d0, aa6b43d | filler excision, RTL fix | Excision off by default. The RTL change edits karaoke tags; today's reel captions still show reversed word pairs: "مەسعود کاک", "برێمەر پۆڵ", "دەکەین دروست". |
| uncommitted web.py | studio | Six hand-cut reels shown on page load with `currentJobId = "job-ep29-showcase"` before any job runs; a "−20.5 LUFS" audit pill hardcoded as passing. |

`web.py` does not import the pipeline. `JobManager._run_job_stages` (`web.py:938-1000`) sleeps 40 ms seven times and serves files off disk. Every studio claim is a claim about a mock.

## Today's flagship, measured

`work/clean-pro-viral/ep29-clean-viral-reel.mp4`, sha256 a8e31d24…, 25.56 s, 1080×1920, 25 fps.

| Metric | Value | Bar |
|--------|-------|-----|
| Producer | `scratch/render_perfect_reel.py`, hand-typed trims and crops | pipeline (D1) |
| Audio inputs | speech + music bed at 0.18 + bass drop + 2 whooshes + climax boom | speech only (D9) |
| Integrated loudness | −13.9 LUFS, TP −1.4 | −14 ±0.5 |
| Silence share | 16.0%, 4,081 ms in 6 gaps up to 893 ms | tight (D4) |
| Face detected share | 96.1% (measure.py, 200 ms interval) | ≥98% (D5) |
| Caption contrast | 41.5:1 median | ≥4.5:1 ✓ |
| Caption word order | reversed in two-word chunks | correct |
| Edit plan / provenance / measured.json beside mp4 | none | required |

## What was lost

`work/transcripts/` (the 38-min Sorani ASR, 2,804 s of GPU time), `work/stage0`–`stage5`, the seven
live Gemini verdicts from 2026-08-30, and the s25-25 contract, the only clip the pipeline ever
delivered, are gone from `work/`. `work/events.jsonl` is empty. In their place: 30+ `cut_*.jpg`
frame grabs from a human hunting for a cut point by eye.

## Gate

`bash scripts/verify.sh` at aa6b43d with `src/hawedit/web.py` uncommitted, HawaPC01, 2026-09-13:
**exit 1.** `2 failed, 3709 passed, 1 skipped, 3 errors in 802 s`. Lint, mypy and format passed.

- FAILED `test_build.py::test_the_wheel_contains_every_file_the_audit_report_says_it_does`
- FAILED `test_vex.py::test_checked_in_policy_binds_current_lock_and_assets_and_closes_report`
- ERROR `test_build.py` ×3 (byte-identical builds, commit timestamp, hash-locked builder)

All five trace to the same root: the uncommitted `web.py`. The release builder refuses a dirty
tree and the VEX policy binds the package digest of the committed source. The gate has been red
on every audit since 09-02 for a dirty tree. The `1 skipped` contradicts the zero-skip floor
(T1.11) and needs its own look.

## What truly remains for 10/10

Nothing on this list is a feature. Each item ends with the proof that makes it true.

1. **Stop shipping hand-cut reels as system output.** Move every `work/*/` reel and every
   `scratch/render_*.py` to `demos/hand-cut/` with a README saying a person made them. Remove the
   six hardcoded entries from `web.py`; the studio shows only what a job produced. Proof: `grep -c
   "/media/ep29" src/hawedit/web.py` is 0.
2. **Make the studio call the pipeline.** `JobManager` invokes `run_pipeline`; the stage list
   comes from `StageSkipped` events, not `time.sleep`. Proof: a studio job on a fresh file writes
   a bundle with `measured.json`.
3. **Make the plan the contract, not the receipt.** `VisualEditPlan` is built before render,
   render consumes only the plan, it is in `ArtifactBundle.suffixes()`, publish fails without it.
   Proof: test that deletes the plan and asserts no mp4 is published.
4. **Provenance gate.** Every non-source input (image, audio, font) needs a sidecar with origin
   and licence or the render refuses. Delete `work/assets/music_tension_bed.wav` and `sfx/`.
   Remove `--music-bed` or require a provenance file for it. Proof: render with an orphan asset
   exits non-zero.
5. **Wire the critic and make it read.** Call `inspect_rendered_sequence` from `run_pipeline`
   before publish. Give it the join words: it must reject a span ending in
   `DANGLING_CONJUNCTIONS_CKB` or starting mid-clause, and an LLM pass on the composed script
   answers "does it stand alone, is any join misleading". Failure re-plans, never publishes.
   Proof: the 09-09 "because" join is rejected by a test built from that transcript.
6. **Excision on by default, with restarts.** `excise_fillers=True` in every profile. Add
   repeated-phrase and false-start detection on forced alignment (n-gram repeat within 2 s,
   truncated word followed by its full form). Every excision cut must coincide with a punch-in
   change. Proof: silence share <5% and blind listeners cannot locate the cuts.
7. **Active-speaker face on speaking frames.** Join diarization turns with face tracks; measure
   face share over frames where someone speaks; raise the delivery threshold to 0.98. Proof:
   `measured.json` carries `speaking_face_share`.
8. **Reproducible discovery.** K=5 Path A calls, span voting, cached by transcript hash; judge
   every candidate, dedupe by span. Proof: two runs on the same file agree on ≥90% of spans.
9. **Fit, don't assert.** Commission the editorial gold set (20 episodes cut by a professional
   Kurdish editor with reasons; 200 clip pairs rated by 20 viewers). Fit the ranker; report
   held-out AUC; delete the 0.40/0.30/0.20/0.10 line. Only Hawa can commission this.
10. **Run H7 blind.** Publish the win-rate and its confidence interval. Until the lower bound
    passes 50%, the word "better" does not appear in any doc, commit or dashboard.
11. **Unblock #3 and #4, register the runner, rerun ASR.** Without a live judge and diarization
    no run exits 0; without the runner no level-E proof exists; without the transcript nothing
    above can be tested on real material.
12. **Fix the visible bug.** Two-word caption chunks are emitted in reversed order in today's
    reel. Whatever produced it must not be used again; the pipeline path needs a golden that
    asserts source word order.

## Rule going forward

A commit whose message says "autonomous", "director", "critic", "masterpiece" or "10/10" must
name the evidence file that proves it, and that file must contain a number from a run. None of
the 11 commits since 09-09 produced an evidence file.
