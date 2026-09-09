# Director audit — is HawEdit a creative director? (2026-09-09)

Scope: the editorial intelligence only. Not the harness, not robustness. The bar set by the
owner: the system must act as a director that produces professional edit plans and real
professional shorts, highlights and cutdowns, with only highlight speech, no filler, a true
linked story, cut better than a human editor, no manual editing and no added sound.

Evidence: repo at HEAD 7f499f5; the two reels rendered today (`work/ep29-highlights-master`,
`work/ep29-un-sergio-master`); the source transcript
`work/transcripts/ep29-VbX8UWwl1c4.transcript.norm.json`; the seven live Gemini verdicts in
`work/stage4/`; frames, scene cuts and loudness measured this morning with ffmpeg 8.1.1 on
HawaPC01. Method: the product-design audit skill (flow → captures → numbered steps → findings
→ limits), adapted to a video pipeline where the "screens" are the delivered frames.

## Verdict

**Director score: 3 / 10.** Against the same bar: OpusClip 6, Descript 6, Vizard 5, a good
human editor 9. HawEdit is behind all three on editorial intelligence and ahead of all three
on Sorani captions and cut-point craft.

The system today ships one contiguous take with excellent in and out points. Everything that
would make it a director exists as code, is tested, is counted in the test floor, and is
connected to nothing. Today's two "master reels" were cut by a person typing sentence indices
into a script and then graded "passed" by the same script.

## The flow, step by step

| # | Step | Health | Evidence |
|---|------|--------|----------|
| 1 | Discovery reads the whole transcript and proposes moments (Path A, Gemini) | Amber | Real editor-grade prompt (`path_a.py:88-115`). Not reproducible at temperature 0: a second call returns a different candidate set (`evidence/the-fragments-were-the-prompts-fault.md:103`). Winner sat at rank 8 while only 5 were judged (`evidence/the-champion-ships-at-rank-eight.md`). |
| 2 | Judge scores each candidate with an editorial rubric | Amber | Rubric is good: hook anchors in Sorani, ends_on_a_beat, pessimistic misleading-edit risk (`gemini.py:255-281`). Weights 0.40/0.30/0.20/0.10 asserted, never fitted (`judge.py:809`). Live result: narrative_role "aside" on 5 of 7 verdicts. No critique pass. |
| 3 | Span growth pads the moment outward to reach 30 s | Red | `_grown_sentence_run` (`pipeline.py:1197`) adds sentences until a duration target. That is the opposite of highlight-only. |
| 4 | Story construction: link non-contiguous moments into one story | Red | `story.py`, `assembly.py`, `episode.py`, `edit_plan.py`, `condenser.py` have zero callers in `src/`. `run_pipeline` asserts contiguity (`pipeline.py:1374`), so a cutdown is unrepresentable in the shipping path. Nothing produces a `StoryRelation`. |
| 5 | Tightening: remove filler, restarts, repeats, dead air | Red | No word is ever removed. Dead-air trim exists (`silence.py`), is off in every profile, dropped 0 ms in the delivered clip. The 8-word filler list only penalises a score inside dead code. Today's reels still contain یەعنی and ئابزانم. |
| 6 | Boundary: pick the exact in and out frame | Green | Sentence anchor, VAD lead-in 120 ms, tail 200 ms, shot-cut guard 400 ms, outward-only invariant (`boundary.py:360-481`). This is craft. |
| 7 | Reframe and visual grammar | Amber | Active-speaker tracking, measured headroom constants, punch-ins only on pauses (`render.py:548-662`). But no shot awareness, no cut to the listener, no reaction shot. In today's reels the crop delivers 12 s of table and rug with no face while the guest speaks (sergio reel 12–24 s and 40–45 s; highlights reel 24 s and 42–46 s). |
| 8 | Captions | Green | RTL karaoke, 2–3 word chunks, safe margin, readable. One ASR fragment ("سە") shipped as a caption cue. |
| 9 | Self-verification of the delivered reel | Red | `quality_audit_report.json` is prose written by the render script. It claims "100% live video, zero dead frames, face centered" over frames with no face, and "zero mid-sentence clipping" over a chapter that opens mid-clause. The pipeline's own `measure.py` was not used. |
| 10 | Proof against a human editor | Red | H7 never run. `pairwise_preference` has been called once, with empty input. No retention, watch-time or preference number exists. |

## Findings from today's reels

**F1. The flagship reels are hand-cut.** `work/render_complete_highlights_master.py:65-71`
selects `sentences[67]`, `sentences[31]`, `sentences[71]`. Chapter titles are typed by hand.
`work/render_sergio_un_master.py` is the same pattern. Neither is under git or in the package.
The system did not make these edits; a person did, using the system's renderer.

**F2. A fabricated "archival" photograph in a true story about a real bombing.** The sergio
reel cuts at 23.5 s to `work/assets/un_baghdad_archival.jpg`, labelled in the script and in
the QA report as "authentic archival news photo". The frame shows an AI-generated composition:
a ruin with a painted sign reading "CANAL HOTEL - UNITED NATIONS HQ", stylised blue-helmet
figures, an ambulance with garbled lettering. The 2003 Canal Hotel bombing killed 22 people
including Sérgio Vieira de Mello. Presenting a synthetic image as archival in that story is a
journalistic fabrication and would end a media organisation's credibility. This must never
reach a viewer.

**F3. The edit creates a false causal link.** Highlights chapter 2 ends on the word چونکە
("because", 493.4 s in the source) and hard-cuts to chapter 3, "those in Kurdistan will not go
back, they are terrified". The source continues "because later I met another person, a
diplomat…". The reel makes the guest say people were upset *because* Kurds will not return.
The condenser's own `DANGLING_CONJUNCTIONS` list names چونکە as forbidden at a span end. The
judge rubric names misleading_edit_risk as "the number a media organisation is judged on".
Both rules exist; neither ran.

**F4. Mid-clause entry.** Chapter 2 opens at 477.41 s on "an hour, two hours after…". The
source at 475.4 s is "من ڕۆشتم ئەو" ("I went there"). The verb is gone. The QA report says
"zero mid-sentence clipping".

**F5. Faceless seconds while a person speaks.** Measured from the delivered frames: about a
quarter of both reels shows the studio table and rug with the guest's voice over it. The QA
report says "face centered, upper-third eye placement".

**F6. Music was added.** The sergio reel carries a "sidechain-ducked tension music bed". The
owner's bar is no added sound. Loudness is −20.7 and −21.0 LUFS integrated; social platforms
normalise to about −14, so both reels play quiet on a phone. Normalisation is not "sound
addition" and should be on.

**F7. Story link is weak even where it is not false.** Chapter 1 (a family's death-threat
letter, source 1183 s) and chapter 2 (the UN bombing, source 477 s) are two different
anecdotes. Only chapter 3 pays off chapter 1. A director would cut 1→3 and hold 2 for its own
reel, which is exactly what the sergio reel already is.

## Where the real intelligence is

- The Path A prompt: "return the span that holds the complete point, the setup that makes it
  land and the payoff that follows, not the single strongest sentence". An editor wrote that.
- The judge rubric with Sorani calibration anchors and the pessimistic misleading-edit frame.
- Boundary fusion and punch-in scheduling, with constants measured on real footage and
  corrected once when ep29 disproved ep10 (D-258).

## Where it is theatre

- `condenser.py` "virality score" to two decimals from "sentence 0 is the hook, last sentence
  is the climax". Dead code.
- `tournament_score` weights over numbers the LLM invented about itself.
- Every `quality_audit_report.json` on disk: a script grading its own output "passed".
- Two of five billed judge calls scored identical footage (dedupe by candidate, not span).

## What 10/10 means

Ten out of ten is not "many features". It is: a blind panel of Kurdish viewers cannot tell the
system's cutdown from a senior editor's, and prefers it at least as often, on sources it has
never seen, with zero fabrications and zero misleading joins, reproducibly. Each line below is
a measured claim with a named proof.

| ID | Claim | Proof | Today |
|----|-------|-------|-------|
| D1 | Every delivered reel is produced by `run_pipeline` from an `EditPlan` artifact. No hand scripts. | plan.json next to every mp4; gate refuses an mp4 without one | 0 of 2 today |
| D2 | No synthetic imagery, no external asset without a provenance record | provenance file per asset; gate refuses otherwise | 1 fabricated image shipped |
| D3 | No join across a dangling conjunction, no mid-clause entry; the story critic signs every join | critic verdict per join, in the plan | 2 violations in 3 joins |
| D4 | Filler, restarts and repeats removed at word level; cuts hidden under punch-ins | words_removed list in plan; blind listeners cannot locate cuts | 0 words removed |
| D5 | Face of the active speaker present ≥ 98 % of speaking frames, measured by `measure.py` | measured.json | about 75 % |
| D6 | Discovery is reproducible: K=5 runs, vote, ≥ 90 % span agreement | evidence per run | not reproducible |
| D7 | Ranker weights fitted on a labelled editorial set of ≥ 200 human-rated clips, not asserted | fit report with held-out AUC | asserted |
| D8 | Blind pairwise win-rate vs a professional Kurdish editor, 95 % CI lower bound > 50 % | H7 report | never run |
| D9 | Reels play at platform loudness (−14 LUFS ± 1) with no added music | ebur128 in measured.json | −21 LUFS, music added |

## The path

### Stage 1 — Stop lying to yourself (week 1)
- Delete or quarantine `work/render_*_master.py` and `work/plan_highlights_assembly.py`.
  Anything hand-cut is a demo and is labelled a demo. D1.
- Kill prose QA. The sanity gate calls `measure.py` for face presence per second, loudness,
  cut list, and refuses on numbers. It never writes a "details" sentence it did not measure.
- Ban synthetic and unprovenanced assets in the gate. Remove `un_baghdad_archival.jpg`. D2.
- Remove the music bed. Turn loudness normalisation to −14 LUFS on. D9.

### Stage 2 — Wire the director that already exists (weeks 2–4)
- Make `EditPlan` the pipeline's output contract: an ordered list of spans, each with source
  in/out, role (hook, setup, turn, payoff, close), the sentence text, the join reason, and
  the words removed. Render consumes only plans.
- Replace the contiguity assertion with the assembly path (`assembly.py`) behind the plan.
- Route discovery → story map → plan → critic → render. `story.py` gets a producer: the LLM
  writes `StoryRelation`s (question→answer, setup→payoff, correction) from the full transcript.
- Add the critic pass: given only the composed script text, the model must answer "does this
  stand alone, is any join misleading, would a Kurdish journalist sign it". A failed join is
  re-planned, never rendered. D3.

### Stage 3 — Tighten like an editor (weeks 4–8)
- Word-level excision on forced alignment: fillers (grow the list from the corpus, not 8
  words), false starts, repeated phrases, breaths over 600 ms. Every excision lands on a
  punch-in change so the jump is invisible. Rule: never remove a word the critic marks as
  meaning-bearing. D4.
- Highlight-only: kill the 30 s padding. A moment is as long as its setup and payoff. Length
  targets are satisfied by adding another linked moment, not by padding.

### Stage 4 — See the room (weeks 6–10)
- Shot classifier per source cut: single, two-shot, wide, host. Crop policy per shot type.
- Cut to the listener on speaker change and on reactions; hold the speaker otherwise.
- Gate: active-speaker face present ≥ 98 % of speaking frames, measured. D5.

### Stage 5 — Make discovery trustworthy (weeks 8–12)
- K=5 discovery with span voting; cache by transcript hash. D6.
- Judge every candidate, not top 5. Dedupe by span, not by candidate.
- Retire the asserted weights once D7's data exists.

### Stage 6 — Learn from humans, then prove it (months 3–9)
- Commission the editorial gold set: 20 episodes, a professional Kurdish editor's cutdowns
  with their reasons, plus 200 clip ratings from 20 viewers. This is blocker #1's editorial
  twin and only Hawa can commission it.
- Fit the ranker on it; report held-out AUC. D7.
- Run H7 blind. Publish the win-rate with the CI. Claim nothing before. D8.
- Feed real channel analytics (watch-time, completion) back as labels for the next fit.

### What not to do
- No new "score" that was not fitted on labelled data.
- No image, music or sound that was not in the source.
- No hand-cut reel presented as system output.
- No feature work until D1–D3 are green; they are the honesty layer for the director.

## Evidence limits
- I read Sorani captions and transcript words directly; a native editor should confirm the
  F3 and F4 readings.
- Face presence was judged from one frame every 3 s and spot frames, not a per-frame count.
  `measure.py` should produce the exact number.
- The full pipeline still cannot exit 0 on this machine (blockers #3 and #4), so the only
  system-made edit is the 2026-08-30 clip; the rest of the output on disk is hand-directed.
- OpusClip, Vizard and Descript scores are from published reviews and their own docs, not a
  side-by-side run on Sorani material. H7 is how that becomes a measurement.
