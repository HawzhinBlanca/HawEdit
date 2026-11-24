# Task sheet for the Gemini agent — make HawEdit the #1 Kurdish clipper (2026-11-18)

Copy everything below the line into the agent. Do not soften it.

---

You are working on HawEdit, a Python 3.11+ Sorani (ckb) video repurposing system. The repository
is `C:\Users\Wareen\.gemini\antigravity\scratch\HawEdit` (GitHub `HawzhinBlanca/HawEdit`).

## 0. Rules before anything else

1. **Read `AGENTS.md` and obey it.** Research → Plan (`specs/<feature>/plan.md` + `impact-map.md`,
   then STOP until the owner fills the `Approved-by:` line) → Implement one task at a time,
   test-first → `bash scripts/verify.sh` → flip the ledger only with
   `bash scripts/update-ledger.sh <feature> <T1,T2,...> <test_a,test_b,...>`.
2. **Never:** skip, xfail, delete or weaken a test; use `-k`/`--deselect`/`--ignore` to hide red;
   edit a golden or fixture to match output; hand-edit `scripts/test-count.floor` or
   `scripts/coverage.floor`; write into `.gate/`; edit `.env*`, `secrets/**`, `.venv/**`,
   `models/**` (except `sources.json`, `revisions.json`); run `rm -rf`, `git push --force`,
   `git reset --hard`, `--no-verify`, `curl … | sh`. Never print or commit a credential.
3. **Single writer.** Another agent owns branch `fix/kurdish-rtl-captions` and its pull request
   (HawzhinBlanca/HawEdit#25). Do not commit, push or rebase that branch. Work in your own
   worktree:
   `git worktree add ../HawEdit-gemini -b gemini/number-one fix/kurdish-rtl-captions`
   and rebase onto `main` once #25 is merged.
4. **A number carries where it came from.** Every measurement you report names the machine, the
   library versions, the input file and the commit. Judgment written as judgment is fine;
   judgment written as a measurement is a lie in this repo. Earlier agents wrote "autonomous",
   "director", "10/10" and "masterpiece" in commit messages with nothing behind them. Do not.
5. **Anything that needs the owner (Hawa) is marked `[HAWA]` below.** Do not code around it. Write
   the exact question, add or cite a `BLOCKED.md` number, and move to the next task that does not
   depend on it.
6. **New dependency, model, API or architectural change → an ADR** (`## D-NNN` in `DECISIONS.md`;
   next free number is **D-336**), with its licence audited. NonCommercial is a hard reject.
7. **Environment facts** (HawaPC01, Windows 11): interpreter `.venv/Scripts/python.exe`; set
   `PYTHONIOENCODING=utf-8` for Kurdish output; the full gate takes about 46 minutes and runs
   6,560 tests; do not pass a long `--basetemp` to pipeline tests (it breaks Stage 0 ingest on
   Windows); `update-ledger.sh` accepts several rows in one call, and each call re-runs the gate;
   if the gate ratchets the floors, commit them as `chore(gate)` before pushing (CI fails a run
   that ratchets them). Serena MCP may not connect; then map callers with grep and say so in
   `impact-map.md`.

## 1. Where the product stands (verified 2026-11-17/18 on this tree)

The engineering harness is strong; the product has not shipped a real reel. Evidence:

| # | Fact | Where |
|---|---|---|
| 1 | The studio cannot generate: `POST /api/repurpose` validates the upload, then answers 503 `studio_runner_unavailable`. | `src/hawedit/web.py:591, 814` |
| 2 | No real Kurdish reel exists in the repo; the only delivered clips are 2.24 s synthetic fixtures. The real episodes and reels that used to live on the Desktop are gone. | `evidence/`, owner's disk |
| 3 | The last real-media attempt (2026-10-14, 38-min ZAR episode) produced nothing: a readiness receipt gate refused the run. | `evidence/zar-real-retest-preflight-20261014.md` |
| 4 | Speech recognition took **13,288 s (3.7 h)** for a 38.6-min episode (158 drafts, 76 validator passes; a gate ran at the same time, so an upper bound). | vault `HawEdit ZAR ASR final result 2026-10-08` |
| 5 | The ASR is good: fused OmniASR 7B v12 = 23.29 WER / 5.50 CER on FLEURS ckb (beam 5), 25.19 WER on 473 unseen own rows. Not measured on podcast conversation. | `specs/v12-fused-model/research.md` |
| 6 | Discovery's word-timing table stops at 4,000 words; a one-hour episode has ~9,000. | `src/hawedit/path_a.py:120` `_timing_table(limit=4000)` |
| 7 | The judge never hears audio, sees only the clip's own words (not what was cut away), gets no speaker labels, at most 20 frames at 768 px. | `gemini.py:245-247`, `keyframes.py` |
| 8 | Ranking weights are asserted, never fitted. | `judge.py:799-816` |
| 9 | The judge is pinned to `gemini-2.5-pro`. Research (unverified): Google routes 2.5 Pro/Flash away on 2026-12-01. **Check the vendor page first.** | `src/hawedit/gemini.py:1` |
| 10 | Reframing follows the dominant face (Haar, optional YuNet); there is no active-speaker associator. Haar found a face in only 56 % of samples on real episode ep29. `models/face_detection_yunet.onnx` is not in the checkout. | `reframe.py:303-333` |
| 11 | Captions now lay Sorani out right-to-left (D-334), and the delivery face check ignores caption text (D-335). Still wrong: the `\kf` karaoke fill sweeps each word from its left edge (libass #406); Latin words fall back to a larger bold font. | `DECISIONS.md` D-334, D-335 |
| 12 | No speech-to-text other than OmniASR is wired; ElevenLabs Scribe is not referenced anywhere. | grep of `src/`, `scripts/` |
| 13 | No `LICENSE` file; the repo is public. | repo root |
| 14 | Open human blockers: #1 labelled Sorani audio set, #3 Gemini credentials, #4 pyannote gated-model acceptance, #21 champion adapter licence row, #25 editorial gold set + blind panel + GPU runner. | `BLOCKED.md` |

**Why it stalled:** each disappointing reel was answered with another gate, ledger or signed
packet. October was almost entirely Linux sandboxing and signed admission for the ASR worker on
a single-user desktop tool, and every status line ended "no new ZAR reel". **Rule for this whole
sheet: a week counts only if it ends with reels a Kurdish viewer watched.** Do not add a gate,
ledger or signed packet until reels ship weekly.

## 2. The bar ("true #1")

On a real source the system has never seen, with no human touch:

| Measure | Market today | HawEdit target |
|---|---|---|
| Sorani captions read correctly (order, punctuation, mixed script) | OpusClip refuses RTL | 100 % of lines, proven by rendered frames |
| Caption words correct on the published reel | best public ASR ~32 % WER | ≥ 97 % after correction and one-tap fixes |
| Upload to first previews | minutes (non-Kurdish tools) | ≤ 15 min per source hour on HawaPC01 |
| Clips usable without edits | 62 % (OpusClip, English, one secondhand test) | ≥ 80 % on the owner's channel |
| Active speaker in frame | weak on two-person shots | ≥ 98 % of frames, 100 % of first frames |
| Knows what Kurdish viewers watch | nobody | ranking refitted weekly on the channel's own retention |

No added music, sound effects or synthetic imagery, ever. No fabricated or misleading joins.

## 3. The tasks, in order

Each task becomes its own `specs/<feature>/` folder with research, plan, EARS spec, impact map
and ledger. Do not start a phase before the previous phase's "done when" has evidence in
`evidence/`. Inside a phase, independent tasks may run in any order.

### Phase A — Real reels from one command (first; nothing else counts until this works)

- **A1 Real footage — on disk since 2026-11-18.** `D:\HawEdit-media\` holds three Zar Podcast
  episodes as 4K VP9 + Opus masters (40 min, 1h08, 1h48), a 5-minute excerpt for quick runs, and
  contact sheets. Read its `README.md` first: checksums, what each episode tests, and the
  human-edited "لەم پۆدکاستەدا:" teaser that opens each episode (a gold reference for selection).
  Never modify `sources/`; write derived files to `excerpts/` and reels to `reels/<run>/`. Set
  `HAWEDIT_MEDIA_ROOT=D:\HawEdit-media` so the real-media test tier stops being silently skipped.
  Stop testing picture quality on the 640×360 fixture. Not yet known: how ingest and frame
  analysis cope with 4K VP9; measure it on the excerpt first.
- **A2 One command, many reels.** `python -m hawedit.pipeline EPISODE.mp4 --work-dir work`
  produces 5–10 vertical reels with the champion ASR running in plain WSL, the judge, QC and
  delivery. Find exactly which gate refused the 2026-10-14 run and why; fix the cause, do not
  delete the gate. Done when: ten reels from one real 1440p episode exist on disk, each with its
  `.measured.json`, and the run's wall time is recorded in `evidence/`.
- **A3 `[HAWA]` Park, not delete, the heavy runtime controls on the default path.** The protected
  producer, Linux namespace sandbox, VEX and signed-packet admission may stay available behind an
  explicit flag, but must not stand between a single-user desktop run and its reels. This
  changes policy: write the ADR, list exactly what is moved behind the flag, and stop for the
  owner's approval.
- **A4 Studio button runs the real pipeline.** Replace the 503 in `web.py` with a queued job that
  calls the same entry point as A2, streams stage events, and serves the delivered reels. Done
  when: dropping a real episode into the studio yields reels with zero flags.
- **A5 Judge model current.** Verify the 2.5-Pro retirement date on Google's model page. If true,
  ADR + move the Stage 4 judge to the current Gemini Pro-tier model before 2026-12-01, and re-run
  the judge tests and one live verdict. `[HAWA]` for the paid key (#3) if the call is billed.
- **A6 `[HAWA]` Licence.** Ask the owner which licence to publish. Add `LICENSE`; check it does
  not conflict with KLPT (CC BY-SA 4.0) or the adapter weights (#21).
- **A7 Usable-rate sheet.** For every reel produced from now on, the owner marks it publishable /
  needs a fix / unusable in `evidence/usable-rate.csv` (episode, reel, verdict, reason). This is
  the scoreboard for every later phase; the number to beat is 62 %.

### Phase B — Speech: fast and right

- **B1 Profile the 3.7 hours.** Run ASR on one real episode with timing per stage (draft,
  validator, re-alignment, model load, I/O). Write `evidence/asr-profile-<date>.md`. No
  optimisation before this exists.
- **B2 Final-pass ASR only on chosen clips.** Run OmniASR v12 + CTC-3B on the selected clips,
  each padded by 3–5 s, instead of the whole episode. Ten 45-s clips are under 8 min of audio
  instead of 60. Done when: per-clip caption text and word timings match a whole-episode run on
  the same spans, and wall time is measured.
- **B3 `[HAWA]` Draft pass with speaker labels.** ADR for a fast whole-episode draft transcript
  with diarization (candidate: ElevenLabs Scribe v3; price and Kurdish quality are research, not
  measured; it sends audio to a third party, so the owner must approve that and supply a key).
  The draft is only for finding moments; published captions always come from B2. Alternative if
  the owner refuses: pyannote community-1 (needs #4) on the local draft.
- **B4 Disagreement as a quality signal.** Where the draft engine and OmniASR differ on a word,
  mark the word amber in the review packet and the studio. Names, numbers and English brand
  words are where both fail.
- **B5 Correction layer.** A per-channel word list (guest names, places, brands); a constrained
  LLM pass that may only choose between the engines' candidates, never invent words; one-tap
  human fixes that feed the word list. Done when: WER of published captions is measured against
  a hand-corrected transcript of at least 20 real clips (`[HAWA]` for the reference text, #1).
- **B6 Validator off the default path until it is measured.** The Qwen validator was 76 extra
  passes in the 3.7-hour run. Measure WER with and without it on the same clips; keep it only if
  it helps, and record the number in the ADR.
- **Phase B done when:** first previews are ready within 15 min per source hour on HawaPC01, and
  published-caption WER on real conversation is measured and in `evidence/`.

### Phase C — Content-aware selection

- **C1 Sentence numbers, not milliseconds.** Discovery returns `sentence 212 to 219`; code maps
  sentences to CTC word times. This removes the 4,000-word timing table (`path_a.py:120`), the
  guessed timestamps, and makes every candidate sentence-complete by construction.
- **C2 The judge sees what an editor sees.** Give it the candidate, 60–90 s either side marked as
  context, speaker labels (from B3), and the candidate's audio. Then "misleading edit risk" is
  answerable. Keep the Sorani rubric anchors; they are good.
- **C3 Episode map.** One Gemini call over the full video and audio returns chapters, host vs
  guest, and typed moments (story, claim, confession, joke, clash) with a reason and what was
  visible. Never cut on its timestamps; snap every range to CTC word times in code.
- **C4 A no-API candidate source.** Topic segmentation over sentence embeddings (the ClipsAI
  `texttiler.py` method, MIT). Merge candidates from C3, the transcript judge and C4.
- **C5 Pairwise ranking replaces asserted weights.** Over the top dozen candidates, ask "which of
  these two would a Kurdish viewer keep watching", 2–3 rounds. Retire `0.40/0.30/0.20/0.10` in
  `judge.py:799-816`. Never ship a "virality score" (research ceiling for engagement prediction is
  about 0.71 rank correlation, in-domain).
- **C6 Clip structure.** Hook, the context that makes it land, payoff, clean ending on a pause.
  `assembly.py` already supports moving a strong line to the front as a cold open; use it only
  when the meaning is unchanged.
- **C7 Close the loop.** Weekly, pull retention for posted reels and refit the ranking. Until
  about 50 reels are posted, the owner's A7 verdicts are the labels.
- **Phase C done when:** the owner keeps at least 8 of 10 reels from an unseen episode without
  edits, recorded in A7's sheet.

### Phase D — Picture: edit like a multi-camera editor

- **D1 YuNet replaces Haar** in the tracker and in the delivery probe (`measure.py`). Apache-2.0;
  ADR with the model's §7 row and checksum in `models/sources.json`. Keep D-335's 5 % height floor
  unless real footage says otherwise. Measure detection rate on real episodes against the 56 %
  Haar figure.
- **D2 Voice-to-face binding.** Speaker turns (B3) × the existing shot cuts × face tracks, with
  LR-ASD (MIT, ~0.84 M parameters, CPU-capable; research) deciding which face is talking. This
  replaces "largest face" and the unbuilt associator seam in `reframe.py`.
- **D3 Crop rules** (from the owner's design, 2026-11-17):

  | Situation | Rule |
  |---|---|
  | Close-up of the speaker | One fixed crop for the whole shot, eyes in the upper third, no panning |
  | Close-up of a listener while someone else talks | Keep only if under ~2 s (a reaction); otherwise cut to the speaker |
  | Wide or two-person shot | Punch in on the active speaker; fast back-and-forth may stack speaker over listener |
  | First frame | Always the person speaking the hook line |
  | Speaker change inside a wide shot | Hard cut between two fixed crops, no slide |

- **D4 Single-pass render.** Send crop change points to ffmpeg (`sendcmd` pattern from OpenShorts
  `reframe_v2.py`, MIT) instead of a Python frame loop. Measure render time before and after.
- **D5 Captions that read on a phone.** Two or three words per group, about twice today's size,
  heavy outline, lower-middle safe zone, moved off faces and table objects
  (`caption_layout.py` already protects regions; add tables). New goldens need the owner's
  approval `[HAWA]`, as D-334's did.
- **D6 Karaoke fill direction.** Fix the `\kf` sweep so the highlight moves right-to-left inside
  each Sorani word (libass #406); likely per-word events or a clip-based highlight. Prove it with
  a frame sequence, not a unit test of the ASS text alone.
- **D7 Latin fallback font.** Latin words inside a Sorani line must not switch to a larger bold
  font. Prove with a rendered frame.
- **D8 Sound.** Keep two-pass loudness; add ~30 ms fades at every cut.
- **D9 `[HAWA]` A real-face fixture.** A short clip with consented real faces, so a test can
  publish a `face_tracked` render through the real cascade. Today no test can (D-335).
- **Phase D done when:** on three real episodes the speaker is in frame on every first frame and
  ≥ 98 % of sampled frames (measured by the delivery probe and spot-checked by the owner), and no
  reel shows a wide shot left wide.

### Phase E — Automatic review of the finished reel

- **E1 Contact sheet per reel.** First frame, the frames either side of every cut, one enlarged
  caption crop, a 4×N sheet. Saved next to the reel.
- **E2 One review agent, about six typed tools** (`get_transcript`, `propose_edl`,
  `validate_edl`, `render_preview`, `view_frames`, `commit`). A fixed checklist: right person on
  frame one, face fully inside the crop, captions readable and off objects, caption text matches
  the transcript, ending on a pause. A failure returns a specific change (move crop, swap opening
  shot, shift captions); at most three rounds, then to the owner with the reason. Wire or delete
  the unwired `render_critic.py`; do not leave a third critic beside it.
- **E3 Hard rules in code, not prompts:** never cut inside a word, 30–200 ms padding, duration
  bounds. Check them in `validate_edl`.

### Phase F — The proof that makes "#1" checkable

- **F1 `[HAWA]` Hands-on test of mazdek** ("Kurdish Video Clip Maker", the one rival claiming the
  niche) on the same episode. Record what it produced.
- **F2 `[HAWA]` Blind panel (#25).** 20 reels rated blind by Kurdish viewers: HawEdit vs a human
  editor's cut vs mazdek, same episodes.
- **F3 Publish the numbers** no clipper publishes: usable-clip rate (A7) and caption WER (B5),
  with their method.

## 4. Do not

- Add another gate, ledger, signed packet or audit layer before Phase A is done.
- Chase B-roll, auto-posting or a virality score.
- Adopt a second rendering stack (Remotion, Electron editors) for captions; libass shapes Sorani
  correctly now.
- Copy AGPL code (Clips Kitty); read it for ideas only. Reject NonCommercial weights (MMS
  aligner, MMS-1b, InsightFace zoo, DiariZen, Sortformer v1, Vekol Sorani models).
- Report a task done because the code exists. Done = `verify.sh` green, the ledger flipped by
  `update-ledger.sh`, CI green on the pull request, and — for anything a viewer sees — a real reel
  the owner has looked at.

## 5. How to report

At the end of each task: what changed (files, commit), the gate result line, the measurement with
its provenance, what was not verified, and the next task. If you are blocked on `[HAWA]`, say the
exact question in one sentence.
