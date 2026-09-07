# Road to #1 — robustness and smooth working

Date: 2026-09-08. Based on the audit in `research.md` (2026-09-02), the master task sheet, and a
fresh repo audit on 2026-09-08 (HEAD 0c6970d, floor 3627, gate red on 7 untracked paths).
Competitors: OpusClip, Vizard, Descript.

"#1" is not a feeling. It is the eight lines below, each with a test or an evidence file.
Nothing on this sheet is done until its proof exists.

## What #1 means (the only definition that counts)

| ID | Claim | Proof required | Today |
|----|-------|----------------|-------|
| R1 | 99 of 100 varied sources exit 0 with no human touch | `evidence/soak-*.md`, 100-source corpus, per-run exit code | 0 runs have ever exited 0 (#3, #4) |
| R2 | No hang: every subprocess has a timeout, 0 hangs in soak | grep: 0 subprocess calls without `timeout=`; soak log | 41 call sites, 22 timeouts; `ingest._run` has none |
| R3 | Resume: a run killed at any stage resumes from that stage with byte-identical output | `test_pipeline_resume_*` kills after each stage; sha256 match | no checkpoint/resume on `run_pipeline` |
| R4 | Every delivered clip ships with an independent measurement record that passed reconciliation | `--qc-record` mandatory in `--profile production` | done (T1.1–T1.3), but 56% face rate and 3.26:1 contrast pass through |
| R5 | CI green on every commit, on a registered GPU runner, with the real-media tier running | `gate.yml` green with `HAWEDIT_MEDIA_ROOT` set | 0 runners since 2026-08-25; media tier silently excluded |
| S1 | Drop a file, get ranked clips, zero flags | web UI smoke test | 55 flags + tkinter key box |
| S2 | p95 wall time per source minute, tracked per commit | `evidence/perf-*.md` on HawaPC01 / RTX 3090 Ti | one 38-min run: 2,804 s |
| S3 | A human panel prefers hawedit's Sorani clips over OpusClip's on the same source | H7 run, blinded | H7 never run |

## Phase 0 — Make it run (week 1)

Nothing else matters until one run exits 0.

- **0.1 Blocker #3 (judge billing).** Two options, pick one, write the ADR.
  a) Enable Gemini billing (cheapest: ~$0.20 for T1.12).
  b) Add a local judge fallback on VideoChat3-4B (already on disk, 8.8 GB) so a run can complete
     without a paid API. This diverges from BLUEPRINT §5 and needs a D-number. Recommended: do both,
     local is the fallback, not the default.
- **0.2 Blocker #4 (pyannote).** Accept the gate on HF, fetch `speaker-diarization-community-1`,
  record the licence in DECISIONS.md. Without it `PipelineRun.complete` is false forever
  (`pipeline.py:456`).
- **0.3 Clean the tree.** Sign `specs/story-condensation/plan.md` or stash the 7 untracked paths.
  `test_build.py` refuses uncommitted paths (`release.py:501`). The gate has been red for this
  since the 2026-09-02 audit.
- **0.4 Register the GPU runner** (T0.3). `gate.yml:39` targets `hawedit-gpu`; 0 registered.
  Every level-E proof in the program is unreachable until this exists.
- **Exit:** ep29 exits 0 end to end; `gate.yml` green on HawaPC01. Evidence file with SHA.

## Phase 1 — Make it unkillable (weeks 2–4)

- **1.1 Timeouts everywhere.** `ingest.py:126` `_run`, `measure.py:300/395/456/867`. Rule:
  `timeout = 60 + 4 × source_seconds`. Add a test that greps `src/` for `subprocess.run(` /
  `Popen(` without `timeout=` and fails on any hit. Fixes R2.
- **1.2 Stage checkpoints and resume.** Each stage already writes artifacts into `work/`. Add a
  `stage.done` marker with input SHAs; on restart skip stages whose markers match. Reuse
  `durable.py` if it fits, else a 40-line marker file. Test: kill after each of 7 stages, resume,
  sha256 of the final MP4 identical to an uninterrupted run. Fixes R3.
- **1.3 Real logging.** `logging.getLogger` per module, JSONL handler feeding the existing
  `events.py` sink, rotating file in `work/`. `print` stays only in `main()`. 0 `getLogger` today.
- **1.4 Turn the media tier on.** `conftest.py:31` ignores `tests/media/` whenever
  `HAWEDIT_MEDIA_ROOT` is unset. Set it in `gate.yml`, and make the unset case fail loudly on
  the self-hosted runner instead of collecting nothing. T1.4 is DONE on paper and off in practice.
- **1.5 Split `run_pipeline`.** 1,530 lines (`pipeline.py:1632–3160`) → one function per stage
  with a typed input/output. Behaviour-preserving, proven by the bit-identical re-render test.
  Do this before 1.2, resume is much easier on stage functions.
- **1.6 Soak corpus.** 30 sources: 3 lengths (2 / 20 / 60 min), 2 speakers vs 1, phone vs
  studio audio, portrait vs landscape, one corrupt file, one silent file. Nightly on the runner.
  Any non-zero exit is a P0. Grows to 100 for R1.
- **Exit:** R2, R3, R5 proven. Soak 30/30.

## Phase 2 — See and hear properly (weeks 4–8)

- **2.1 Replace Haar cascades.** OpenCV's YuNet (Apache-2.0, ships in the installed OpenCV) as the
  face detector. Target ≥95% detection on the ep29 dialogue reel (56% today,
  `evidence/measured-baseline-ep29-s25-25.md`). ADR for the model row in §7.
- **2.2 Active speaker.** Diarization turns + face tracks → who is talking → reframe follows
  them. This is the two-shot podcast case the audit named first. Test on ep29 two-speaker section.
- **2.3 Caption contrast.** Median 3.26:1 measured; floor is 4.5:1. Make the sanity gate refuse
  below floor in production profile, then fix the box/outline in `caption_layout.py`.
- **2.4 Multi-clip per run by default.** The episode plan exists; make it the default output:
  8–15 candidate clips, ranked, each with its own measurement record.
- **Exit:** face rate ≥95%, contrast ≥4.5:1, 10 clips per episode, all measured.

## Phase 3 — Choose well (weeks 6–10)

- **3.1 Retire the hand-tuned scores.** `condenser.py:198` additive heuristics and the hardcoded
  `virality_score=85.0` (`:279`) go. Scoring comes from the judge (Gemini or local fallback) with
  a 50-clip labelled calibration set from blocker #1. No number is shown that was not measured.
- **3.2 Run H7.** Blinded panel of 5 Sorani speakers, same 3 episodes through hawedit and
  OpusClip (their auto captions will be wrong for Sorani; that is the point). Publish the
  preference rate as `evidence/h7-*.md`. This is the only proof of "better than a team".
- **3.3 Never ship a virality score.** OpusClip's users report low-score clips beating high-score
  ones. Rank clips; do not print a fake probability.
- **Exit:** S3 measured once. Calibration set committed.

## Phase 4 — Product surface (weeks 8–14)

- **4.1 Local web UI.** One FastAPI process, one HTML page: drop a file, watch stages, get a
  ranked clip grid, edit caption text, export. The CLI stays the engine; the UI calls
  `run_pipeline` through a job queue that survives restarts (resume from 1.2).
- **4.2 Zero flags.** `--profile production` is the default in the UI. Every flag a user must
  know is a bug.
- **4.3 Time-to-first-clip.** Measured and tracked in `evidence/perf-*.md`. Target on HawaPC01:
  under 1× real time for the first clip of a 20-minute source.
- **Exit:** S1, S2 proven. A stranger uses it without reading the README.

## Phase 5 — Own the niche (ongoing)

- Sorani first, then Kurmanji, Arabic, Farsi, Urdu: the RTL, under-served languages none of the
  three competitors caption correctly. Every language gets its own golden render and measured
  ASR number from a labelled set.
- Trust as the product: every clip leaves with its measurement record, provenance, and a
  reproducible render. No competitor offers this. Say so on the scorecard, with the files.
- Public scorecard: R1–S3 with current numbers, hardware, and commit, regenerated by the gate.

## What not to do

- No new features before R1–R5 are green. The audit and this sheet agree.
- No virality percentages, no "AI-picked" claims without the calibration set.
- No new ML dependency without a licence row; NonCommercial is a reject (insightface's model
  zoo falls here, which is why 2.1 says YuNet).
- No more code ahead of a signed `Approved-by:` line. It has happened twice.

## Scorecard vs the top 3 (2026-09-08)

| | HawEdit | OpusClip | Vizard | Descript |
|---|---|---|---|---|
| Sorani ASR + RTL karaoke captions | yes, measured | no | no | no |
| Independent output verification | yes | no | no | no |
| Reproducible render | yes, bit-identical | no | no | no |
| Exits 0 on a fresh install | no | yes | yes | yes |
| Speaker tracking | Haar, 56% | production | production | production |
| Clips per run | 1 | 10–15 ranked | 10+ | user-chosen |
| UI | CLI, 55 flags | browser | browser | desktop |
| CI green | no, 0 runners | — | — | — |

Sources for the competitor column: techsy.io, forkoff.xyz, ngram.com, bigvu.tv, eesel.ai, opus.pro
(fetched 2026-09-08). The HawEdit column is from this repo at 0c6970d.
