# Prompt for the Gemini agent — close every gap in the 2026-09-13 reality check

Copy everything below the line into the agent. Do not soften it.

---

You are working in `C:\Users\Wareen\Desktop\HawEdit`, a Python 3.11 Sorani (ckb) video
repurposing system. Read `AGENTS.md` first and obey it: Research → Plan (stop for
`Approved-by:`) → Implement one task at a time → `bash scripts/verify.sh` after every task → flip
the ledger only with `scripts/update-ledger.sh`. Never skip, xfail or weaken a test, never edit a
golden or fixture to match output, never hand-edit `scripts/test-count.floor`, never touch
`.gate/`, never run `git push --force`, `git reset --hard` or `--no-verify`. Commit to `main`,
one unit per commit, long messages carrying the measurement, the gate result as the last line.

## The situation you are inheriting

Two audits exist. Read both before writing a line of code:

- `specs/pro-grade-program/director-audit-2026-09-09.md`
- `specs/pro-grade-program/reality-check-2026-09-13.md`

The second one is the verdict on the eleven commits that tried to fix the first. Summary: the
creative-director score is 3/10 and did not move. The commits added 5,879 lines and 85 tests and
changed the production path approximately nowhere. Specifically:

- `src/hawedit/web.py` does not import the pipeline. Its job runner sleeps 40 ms seven times and
  serves six hand-cut mp4s from disk. "Autonomous discovery" is `if "ep29" in filename`.
- `VisualEditPlan` is written after `bundle.publish()` inside `suppress(Exception)`. Nothing
  reads it. No gate refuses an mp4 without one.
- `render_critic.inspect_rendered_sequence` has zero callers in `pipeline.py`, `cli.py` or
  `web.py`, and never reads join words.
- `excise_fillers` defaults to `False`. There is no restart or repetition detection.
- A music bed and four sound effects in `work/assets/` are mixed into every flagship reel. The
  owner's bar is: no added sound, no synthetic imagery, ever.
- Judge weights `0.40/0.30/0.20/0.10` are asserted, docstring says "calibrated", nothing fitted.
- No blind human comparison has ever run. Zero evidence files were written since 09-09.
- The gate is red: `2 failed, 3709 passed, 1 skipped, 3 errors`, all from a dirty tree, plus one
  skip that the zero-skip floor should have refused.
- `work/transcripts/`, the stage folders, the seven live Gemini verdicts and the only clip the
  pipeline ever delivered were deleted.

Commit messages in that period said "autonomous", "director", "critic", "masterpiece" and
"10/10". None of them was true. You are being asked because the previous agent wrote claims
instead of proofs. Do not repeat that. A claim without a number from a run is a lie in this repo.

## The bar

10/10 means: on a source the system has never seen, with no human touch, it produces a
professional short (highlight or cutdown) with only highlight speech, no filler, a true linked
story, clean cut points, the active speaker in frame, correct Sorani captions, and a blind panel
of Kurdish viewers cannot tell it from a senior editor's cut and prefers it at least as often.
Zero fabrications. Zero misleading joins. Reproducibly. No editing UI, no added music or sound
effects, no synthetic imagery. The app is the director; the output is the video.

## The work, in order. Do not reorder. Do not start item N+1 until item N's proof exists.

### Phase A — honesty layer (nothing else counts until this is green)

A1. **Quarantine every hand-cut artifact.** Move `work/*/` reels, `work/*.ass`,
`scratch/render_*.py`, `scripts/render_pro_reel_master.py` and `work/assets/` into
`demos/hand-cut/` with a README stating a person made them. Delete
`work/assets/music_tension_bed.wav` and `work/assets/sfx/`.
Proof: `git ls-files | grep -c "render_.*reel"` is 0; `grep -rc "/media/ep29" src/` is 0.

A2. **Studio calls the pipeline.** `JobManager` invokes `run_pipeline` on the uploaded file;
stage progress comes from `StageSkipped`/stage events, not `time.sleep`; the clip list is what
the run delivered, nothing pre-seeded. Delete `DEFAULT_CLIPS`, `job-ep29-showcase`, and every
hardcoded audit pill.
Proof: `tests/test_web.py::test_studio_job_runs_pipeline_and_lists_only_delivered_bundles`
runs a job on `tests/fixtures/kurdish-speech-3cuts.mp4` and asserts the served mp4's sha256
equals the bundle's `measured.json` sha256. A second test asserts the clip list is empty before
any job.

A3. **Plan is the contract, not the receipt.** Build `VisualEditPlan` before render. `render_clip`
takes only the plan. `edit_plan.json` joins `ArtifactBundle.suffixes()` and the atomic publish
set. Publish fails without it.
Proof: `test_publish_refuses_bundle_without_edit_plan` deletes the plan in staging and asserts no
mp4 exists after publish. `test_render_is_a_pure_function_of_the_plan` renders the same plan
twice and asserts byte-identical mp4 (the bit-identical machinery already exists, reuse it).

A4. **Provenance gate.** Every input that is not the source video (image, audio, font, overlay)
requires `<asset>.provenance.json` with origin URL or path, licence, sha256, and
`synthetic: false`. The render refuses otherwise. Remove `--music-bed` or make it require the
same file; the production profile forbids it outright.
Proof: `test_render_refuses_orphan_asset` and `test_production_profile_rejects_music_bed`.

A5. **Gate green on a clean tree, zero skips.** Find the one skipped test, make it run or make the
gate refuse a skip count above zero (`hawedit.gate` already grades the JUnit report; extend it).
Commit `web.py`. Register the GPU runner (`gate.yml` targets `hawedit-gpu`; 0 registered since
2026-08-25) and set `HAWEDIT_MEDIA_ROOT` in CI so `tests/media/` is collected.
Proof: `bash scripts/verify.sh` prints its success line; CI green on the self-hosted runner
with the real-media tier collected (count > 0 in the JUnit report).

A6. **Restore the lost run.** Re-run Stage 1 ASR on ep29 (`tests/media/provenance.json` names
it) and keep the transcript under the checkpoint scheme from commit 9ca0205 so it cannot be
lost again.
Proof: `evidence/asr-rerun-ep29-2026-09-*.md` with wall time, hardware, sha256 of the transcript.

### Phase B — the director, wired and refusing

B1. **Critic on the path, reading words.** Call `inspect_rendered_sequence` from `run_pipeline`
before publish. Feed it the plan's join words. It must refuse a span ending in
`DANGLING_CONJUNCTIONS_CKB`, a span starting mid-clause (first sentence incomplete), and any join
the LLM critique marks misleading. Add the LLM pass: given only the composed script, answer
"stands alone? / any join implies something the source does not say? / would a Kurdish
journalist sign it?" with a structured verdict. A refusal re-plans; it never publishes.
Proof: `test_critic_rejects_the_09_09_because_join` built from the ep29 transcript words around
493.4 s (چونکە → cut → کوردستان) asserts refusal. `test_critic_rejects_mid_clause_entry` for the
478.4 s entry. Both use real transcript words, not fixtures you invent.

B2. **Excision on, with restarts, under punch-ins.** `excise_fillers=True` in every profile. Add
false-start detection (truncated token followed within 1.5 s by a token it prefixes) and
repeated-phrase detection (identical n-gram, n≥2, within 3 s). Every excision cut must coincide
with a framing change; the scheduler guarantees it, not offers it.
Proof: silence share < 5% on the ep29 real-media tier (measured by `hawedit.measure`);
`test_every_excision_cut_has_a_framing_change`; and a listening test: 10 Kurdish listeners,
given the clip and asked to mark every cut they hear, find < 20% of the real cuts.
Record that in `evidence/`.

B3. **Highlight-only.** Remove the 30 s padding in `_grown_sentence_run`. A moment is as long as
its setup and payoff. Length targets are met by adding a linked moment via `assemble_spans`, never
by padding. Make `--assemble` the default in production.
Proof: `test_no_span_is_grown_past_its_payoff`; ep29 delivered clip has no sentence outside the
judge's setup/payoff window.

B4. **Story map has a producer.** `story.build_story_map` currently takes relations nobody
produces. Add the LLM producer over the full transcript: setup→payoff, question→answer,
correction, callback. The plan's ordering comes from the map, not from index.
Proof: `test_story_map_orders_payoff_after_setup` on ep29; the plan JSON carries
`relation_ids` for every join.

B5. **Speaking-frame face share.** Join diarization turns to face tracks. Measure face share only
over frames where someone speaks. Threshold 0.98 in `delivery.reconcile_delivery`.
Proof: `measured.json` carries `speaking_face_share`; ep29 real-media clip ≥ 0.98; a test with
a synthetic faceless second asserts refusal.

B6. **Reproducible discovery.** K=5 Path A calls, span voting (IoU ≥ 0.6), cached by transcript
sha256. Judge every surviving candidate, not the top 5. Dedupe by span, not by candidate.
Proof: `evidence/discovery-stability-ep29-*.md` with two independent runs agreeing on ≥ 90% of
spans; the billing line count in the evidence equals K × candidates, nothing hidden.

B7. **Captions in source order.** Today's flagship shows two-word chunks reversed
("مەسعود کاک" for "کاک مەسعود"). Add a golden that asserts every caption chunk's words appear
in the same order as the forced-alignment words.
Proof: `test_caption_chunks_preserve_source_word_order` over the whole ep29 transcript.

### Phase C — proof against humans (you cannot fake this; if it is not run, you are not done)

C1. **Editorial gold set.** Write the brief and the rating forms (`comparison_kit.py` has the
tooling). Ask Hawa to commission: 20 episodes cut by a professional Kurdish editor with written
reasons per cut, and 200 clip pairs rated by 20 Kurdish viewers. Do not proceed to C2 on a
dataset you generated yourself.
Proof: `assets/editorial-gold/manifest.json` with rater ids, dates, and sha256 of every file.

C2. **Fit, don't assert.** Fit the ranker on C1. Report held-out AUC and calibration curve.
Delete the `0.40/0.30/0.20/0.10` line and the word "calibrated" from `judge.py` unless the
fit report is cited beside it.
Proof: `evidence/ranker-fit-*.md` with AUC ≥ 0.80 on a held-out split the fit never saw.

C3. **H7, blind.** Five unseen episodes. The system cuts five clips per episode with no human
touch. The professional editor cuts five. Twenty viewers rate blind pairs. Report the win-rate
with a 95% Wilson interval.
Proof: `evidence/h7-blind-panel-*.md`. "Better than an editor" may be written anywhere in this
repo only when the interval's lower bound exceeds 50%. Until then the phrase is banned.

### Phase D — unkillable on a stranger's file

D1. **Soak.** 100 sources the system has never seen: 2 / 20 / 60 min; 1 and 2 speakers; phone
and studio audio; portrait and landscape; one corrupt; one silent. Nightly on the runner.
Proof: `evidence/soak-*.md`, 99 of 100 exit 0 with a plan, a critic verdict and a
`measured.json` each; every failure is a named `StageSkipped` with a blocker number.

D2. **Resume.** Kill after every stage; resume; byte-identical final mp4.
Proof: `test_pipeline_resume_is_byte_identical_after_kill_at_every_stage` (7 kills).

D3. **Timeouts.** No `subprocess.run`/`Popen` without `timeout=`.
Proof: `test_no_subprocess_call_lacks_a_timeout` greps `src/` and fails on any hit.

## The toughest proofs, stated once so there is no argument later

You are done with a phase only when all of these are true and I can verify each in under five
minutes without talking to you:

1. `bash scripts/verify.sh` prints the success line on a clean tree, skip count 0, and the same
   run is green on the self-hosted runner with `tests/media/` collected.
2. `python -m hawedit.pipeline <a file I choose, that you have never seen> --profile production`
   exits 0 on this machine and leaves a bundle with `edit_plan.json`, `critic.json`,
   `measured.json`, and an mp4 whose sha256 the measured file names.
3. `python -m hawedit.measure` on that mp4 reports: integrated −14.0 ± 0.5 LUFS, true peak
   ≤ −1.0, silence share < 5%, `speaking_face_share` ≥ 0.98, caption contrast ≥ 4.5, and the
   audio stream contains nothing that is not in the source (assert with a spectral diff against
   the source span, tolerance you document).
4. I can delete `edit_plan.json` from staging and no mp4 appears. I can drop an unprovenanced
   jpg into the inputs and the render exits non-zero.
5. I can build a plan that joins across چونکە and the critic refuses it, with the refusal text
   in `critic.json`.
6. I can run discovery twice on the same file and diff the spans: ≥ 90% agreement.
7. Every number in every evidence file names the commit SHA, the hardware, the tool versions,
   and the wall time. A number without those is deleted, not fixed.
8. Every commit message that claims a capability names the evidence file. `git log --grep` for
   "autonomous|director|critic|masterpiece|10/10" returns only commits whose bodies cite a file
   under `evidence/` that exists and contains a number from a run.
9. The H7 report exists with an interval, whatever it says. If the lower bound is below 50%, the
   report says so and the dashboard says so.
10. Nothing in `work/` is presented in the studio unless a job in `events.jsonl` produced it.

## What you may not do

- Do not write a test that asserts a docstring. Do not write a test whose name claims more than
  its body checks (`test_plan_write_failure_cannot_follow_publication` was one; find and fix it).
- Do not add a score that was not fitted. Do not print a virality percentage.
- Do not mark anything done. Only `scripts/update-ledger.sh` does that, only after the gate is
  green and every cited test is in that run's report.
- Do not produce a reel by hand and call it output. If you need a demo, put it in
  `demos/hand-cut/` and say so.
- Do not delete anything under `work/` that a run produced. If space is the problem, say so in
  `BLOCKED.md` and wait.
- Do not touch `BLOCKED.md` #3 (Gemini billing) or #4 (pyannote) by working around them. Both
  are owner actions; ask Hawa in chat, cite the number, and build everything that does not depend
  on them first.

## How to report

After each task, one message:

```
Task <id> — <name>
Gate: <exit code> · <passed>/<failed>/<skipped> · <seconds>
Proof: <evidence file or test name>, <the number>, <hardware>, <SHA>
Not proven: <anything the proof does not cover, in one line>
```

If a proof cannot be produced, say "not proven" and why. That sentence is worth more than any
green checkmark you could type.
