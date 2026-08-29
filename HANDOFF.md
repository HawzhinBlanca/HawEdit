# HANDOFF — making genuinely professional Kurdish shorts with this repo

**For the next AI agent.** Read this before `AGENTS.md`, then read `AGENTS.md` — it is still the
single source of truth for gate commands and hard boundaries, and nothing here overrides it.

Written 2026-08-29 at commit `149a47d`, gate green, test floor 3309.

This file exists because the previous agent shipped a clip that passed a 3,300-test suite and was
still, in the owner's words, *"one cut… embarrassing."* Everything below is the difference between
those two facts.

---

## 0. The one rule that produced every real improvement

> **Watch the video. The suite cannot see the picture.**

Six genuine defects were found in this system. **Every one of them was invisible to the test suite
and obvious in the output frames**: a default crop that rendered a wall, a framing floor derived
from one source, punch-ins firing once in 35 seconds, a double-cut 0.77 s wide, the champion
decoder path that had never once executed, and a cost default hiding a shippable clip at rank 8.

The suite was green through all of them. `specs/pro-edit/impact-map.md` wrote it down before any of
it was built — *"no test asserts anything about the visual variety of a render"* — and that is
still the most useful sentence in the feature.

**Section 4 is the inspection kit. Use it on every render. A run you did not look at is a run you
did not verify.**

---

## 1. Anti-hallucination contract

These are not style preferences. Each one is here because it was violated and cost real time.

### 1.1 Never state a number you did not just measure

Report a measurement with the command that produced it and the hardware it ran on, or do not report
it. `AGENTS.md` already says this; the failure mode is subtler than inventing numbers — it is
**carrying a number forward after the thing it measured changed.**

Judgment recorded as judgment is fine. Judgment presented as a measurement is not.

### 1.2 Never generalise from one source

This was got wrong **three times in one session**:

- `TARGET_FACE_HEIGHT_SHARE = 0.22`, derived from one video. The owner's own footage fell below it
  and would have been zoomed and softened. Corrected to `0.15`.
- "Misleading-edit risk has a floor of 0.10", from 15 consecutive verdicts. Later runs produced
  0.20 and 0.40.
- "The champion decoder ships nothing", from 5 of 13 candidates. It ships at rank 8.

**A constant tuned on one video is a guess wearing a number's clothes.** Say which sources it was
measured on, in the comment, next to the value. All three current framing constants do this.

### 1.3 A passing test is not a working feature

`punch_in_schedule` passed `test_the_crop_changes_scale_at_least_once` while producing **one**
scale change in a 35-second clip. The test was true and the feature was useless. When you add an
edit feature, the acceptance is a rendered frame sequence, not an assertion.

### 1.4 "Done" is not yours to declare

`AGENTS.md`: done = `bash scripts/verify.sh` exits 0 **and** the required CI checks are green on
the PR. Rows flip only via `scripts/update-ledger.sh`, never by hand, never from memory.

### 1.5 `--qc-pass` is a claim that a human watched the clip

It writes `qc.human_reviewed: true` into the delivered contract. **Do not pass it because it makes
the run complete.** If no human watched, the honest run omits it and stops before delivery, or you
say plainly in your report that you set it and no human reviewed the output.

### 1.6 When a run contradicts something you wrote, correct the file

`evidence/the-champion-transcribed-and-shipped-nothing.md` was wrong. It was replaced by
`evidence/the-champion-ships-at-rank-eight.md`, which **keeps the wrong claim in full** and explains
the error. Do that. Silently deleting a wrong record destroys the only thing that makes the rest of
the records trustworthy.

### 1.7 Distinguish "not built" from "blocked" from "measured as not worth it"

All three exist here and they are different states:
- **Not built** → build it (`pro-edit` T6).
- **Blocked** → cite the `BLOCKED.md` number and stop (`pro-edit` T7 → #4).
- **Measured as not worth it** → the measurement is in `specs/pro-edit/plan.md`; re-measure on new
  material before reversing it (`pro-edit` T4).

---

## 2. The machine, the material, the state

### 2.1 Environment

| | |
|---|---|
| Host | `HAWAPC01`, Windows 11 Pro |
| GPU | 2 × RTX 3090 Ti, 24564 MiB each, driver 596.36 |
| Python | `.venv/Scripts/python.exe` (Windows layout — never hardcode `bin/`) |
| ffmpeg | 8.1.1-full, `--enable-libass --enable-libharfbuzz --enable-libfribidi --enable-nvenc` |
| ffmpeg path | `C:/Users/Wareen/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin/ffmpeg.exe` |
| ASR runtime | WSL2 (`Ubuntu`). Only the ASR worker is in WSL — **the pipeline itself runs Windows-side** |

### 2.2 Material

`C:/Users/Wareen/Desktop/Test Videos/ZarPodcast/`

| File | What it is |
|---|---|
| `ep29-VbX8UWwl1c4.mp4` | **The owner's own channel** (`UC7jbpjdftJ61wV5cKGr9axg`). 2560×1440, multi-camera. Use this. |
| `ep29-chunk50min.mp4` | 50-minute chunk of the above, re-encoded at `-cq 27`. The working test file. |
| `ep10-0zC2bd03stw.mp4` | Owner's channel, second episode. |
| `01-…`, `02-…`, `03-…`, `04-…` | **A different channel** (`UCyULE_OfQlJAOi4eLKfUzIg`). Downloaded by mistake. `01-MmQ9XPggSig` is that channel's Episode 4, *not* "ep01". |

> **Provenance debt you inherit:** D-257 and several commit messages still call `01-MmQ9XPggSig`
> "ep01" / "ZAR Podcast episode 1". The `evidence/` files were corrected; the ADR text was not.
> **Ask Hawa before editing a committed ADR** — amending is right, silently rewriting is not.

### 2.3 Where the outputs live

```
work/<run>/
  stage0/                        ingest: shot cuts, keyframes, media clock
  transcripts/<media-id>.transcript.raw.json   ← invariant #1, write-once
  transcripts/<media-id>.transcript.norm.json  ← §4.1 KLPT; models read THIS, never raw
  stage4/<candidate>/verdict.json              ← one per billed judge call
  <clip-id>/<clip-id>.{mp4,ass,srt,edl,json}   ← §2 delivery set, all five or none
```

The reference delivered clip is `work/ep29-deep/ep29-champ6-s76-77/`. Compare against it.

---

## 3. The pipeline, stage by stage, with the commands that actually run

`BLUEPRINT.md` is frozen; its § numbers are the spec. Diverging needs an ADR in `DECISIONS.md`.

### Stage 0 — ingest
Media clock, SHA-256, shot-cut detection, keyframes. **It already finds every camera cut in the
source** (271 in the 50-minute chunk, one per 11.1 s) and until recently nothing downstream used
them. When you add a visual feature, check whether Stage 0 already measured what you need.

### Stage 1 — canonical ASR (OmniASR LLM-7B + CTC-3B Viterbi, in WSL)

**The champion adapter is mandatory (D-260).** `--stock-decoder` is a deliberate, recorded
downgrade; the base decoder hallucinates words it does not emit.

```bash
.venv/Scripts/python.exe -m hawedit.pipeline \
  "C:/Users/Wareen/Desktop/Test Videos/ZarPodcast/ep29-chunk50min.mp4" \
  --work-dir work/<run> --media-id <media-id> \
  --omni-asr --omni-asr-runtime wsl --wsl-distro Ubuntu \
  --omni-asr-adapter '//wsl$/Ubuntu/home/ai/cortex_champion_model' \
  --json
```

> ### ⚠ The trap that will cost you an hour if you skip it
> The WSL runtime receipt is keyed to `package_digest()` over **all of `src/hawedit/`**. *Any*
> source edit — a comment, a constant, a docstring — invalidates it and forces re-provisioning via
> `hawedit.wsl_setup`.
>
> **Therefore: freeze the tree, then run ASR.** Commit first. Do not edit source while a
> transcription is in flight, and do not start a gate and then edit underneath it — the gate grades
> a moving tree and refuses, correctly.
>
> Also: **never `pip install` anything into the audited runtime venv.** Installing `py-spy` there
> made provisioning refuse with *"installed OmniASR distribution identity does not match the
> reviewed lock"* — which was the correct behaviour. Debug tooling goes in a throwaway env.

Runtime reference: a 38-minute source measured **1,547 s** on this box
(`evidence/the-champion-adapter-would-have-shipped-the-base-models-words.md`). Scale from that; do
not quote it as if it were your run.

Transcripts are write-once (Kurdish invariant #1). To re-run ASR, use a **new `--media-id`** — that
is why the reference run is `ep29-champ6` and not `ep29`.

### Stage 2 — index
BM25 over normalized text plus scene windows. §4.2 sentence segmentation. Kurdish invariant #3:
**every model input reads `norm`, never `raw`.**

### Stage 3 — discovery
- **Path A** (`--gemini`): Gemini reads the transcript and proposes spans.
- **Path B** (`--visual`): local Qwen embedding/reranker + VideoChat3-4B.

Path A's prompt **states the target duration**, formatted from `clip.MIN_CANDIDATE_SPAN_MS` /
`MAX_CANDIDATE_SPAN_MS` so the prompt and the measurement cannot drift. Before that fix it returned
**1.1-second fragments**; after it, 24 of 24 spans landed in range across two episodes. An
instruction to a model is a request, so compliance is *measured* — see `_span_compliance()`.

Path A is **not reproducible across calls**: the identical transcript returned 13 candidates on one
run and 10 on the next. Never treat a candidate count as a stable fact.

### Stage 4 — editorial judge (`gemini-2.5-pro`, pinned by §4)

Each judged candidate is one billed request, roughly $0.36–0.72 with video.

| Gate | Value | Where |
|---|---|---|
| `MIN_HOOK_SCORE` | 0.75 | `clip.py` |
| `MAX_MISLEADING_EDIT_RISK` | 0.10 | `clip.py`, raised from 0.05 by D-257 |
| `MIN_CANDIDATE_SPAN_MS` | 30 000 | `clip.py` |
| `MAX_CANDIDATE_SPAN_MS` | 90 000 | `clip.py` |
| `DEFAULT_JUDGE_TOP_N` | **5** (CLI); `run_pipeline`'s library default is **1** | `pipeline.py` |

> **`--judge-top-n 5` hid a shippable clip at rank 8.** At 5, the run reported "none cleared the
> thresholds" — exact, and it was a fact about the cost ceiling, not about the material. At 12 the
> winner appeared: 64.1 s, hook 0.75, misleading 0.10, self-contained, fidelity 1.00.
> **Use 12 when you are testing quality. Ask Hawa before changing the default** — it is her cost.

Note the tension the gate exists to arbitrate: **both 0.90-hook candidates failed `self_contained`;
the 0.75 winner passed.** The strongest hooks are the least complete thoughts.

### Stage 5 — boundary fusion
VAD onset / tail extension onto complete sentence boundaries. **Kurdish invariant #2: never render
an incomplete sentence.** The delivered clip shows `in_extended_by: vad_onset`,
`out_extended_by: tail`, `sentence_complete: true`.

### Stage 6 — render (this is where "pro" is won or lost)

Everything in §5 below.

### Delivery — §2
Five files, atomically, or none: `.mp4 .ass .srt .edl .json`. A partial set is a defect
(`evidence/partial-delivery-set.md`).

---

## 4. The inspection kit — how to actually *see* the video

**Run these on every render. This is the section that separates this handoff from a green suite.**

Set `FF` to the ffmpeg path in §2.1 first.

### 4.1 Look at the frames — literally

```bash
mkdir -p /tmp/frames && "$FF" -hide_banner -i CLIP.mp4 -vf fps=1 /tmp/frames/%03d.png
```
Then **open the PNGs with the Read tool.** You can see images. Use that. Look for:
- Is the speaker's face in the frame at all, or did the crop find a wall?
- Is there headroom, or is the head cropped / floating?
- Does the framing ever change, or is it one static rectangle for 60 seconds?
- Do the captions sit over the face? Is the hook card legible against the actual background?
- Is the Kurdish text shaped and right-to-left, or letter-by-letter Latin-ordered?

A contact sheet for one glance:
```bash
"$FF" -hide_banner -i CLIP.mp4 -vf "fps=1,scale=180:-1,tile=8x8" /tmp/sheet.png
```

### 4.2 Count the visual changes

```bash
"$FF" -hide_banner -nostats -i CLIP.mp4 -vf "select='gt(scene,0.3)',showinfo" -f null - 2>&1 | grep -c pts_time
```
The reference clip scores **11** in 64 s. **Zero means you shipped an excerpt, not an edit.**
Print the timestamps too — clustered changes read as a glitch, evenly spread ones read as rhythm.

### 4.3 Loudness — §2 requires −14 LUFS / −1 dBTP

```bash
"$FF" -hide_banner -i CLIP.mp4 -af ebur128=peak=true -f null - 2>&1 | tail -20
```

### 4.4 Dead air

```bash
"$FF" -hide_banner -i CLIP.mp4 -af silencedetect=n=-30dB:d=0.25 -f null - 2>&1 | grep silence_
```
Reference clip: 7 gaps over 250 ms totalling 2.78 s (4.3%); **zero** over 600 ms; longest 580 ms —
a breath, not dead air. That measurement is why `pro-edit` T4 is open rather than built.

### 4.5 Container sanity

```bash
ffprobe -v error -select_streams v:0 \
  -show_entries stream=width,height,r_frame_rate,nb_frames \
  -show_entries format=duration -of json CLIP.mp4
```
Must be 1080×1920.

### 4.6 Read the contract, not just the video

```bash
python -X utf8 -c "import json,sys;sys.stdout.reconfigure(encoding='utf-8');d=json.load(open(r'CLIP.json',encoding='utf-8'));print(json.dumps({k:d[k] for k in ('editorial','output','qc','boundary')},ensure_ascii=False,indent=1))"
```
`-X utf8` and `reconfigure` are required — Windows' default `cp1252` stdout raises
`UnicodeEncodeError` on Kurdish text and will look like a code bug.

### 4.7 Sanity-check the source before blaming the pipeline

`ZAR38` and similar low-grade sources are 640×360 / 48 kbps. **No pipeline recovers from that.**
Check the source resolution and bitrate before concluding the render is soft.

---

## 5. Every technique, at its real grade

Honest status. Do not report any row as better than it is.

| Technique | Status | Implementation | Notes |
|---|---|---|---|
| 9:16 vertical reframe | **built** | `render.vertical_framing`, `crop_filter` | face-tracked is the **default**; `--static-crop` opts out |
| Face-aware headroom | **built** | `TARGET_FACE_HEIGHT_SHARE=0.15`, `FACE_COMPOSITION_LINE=0.38`, `MAX_VERTICAL_ZOOM=1.5` | 0.15 measured across two sources after 0.22 was disproved |
| Punch-ins (scale changes) | **built** | `punch_in_schedule`, `PUNCH_IN_ZOOM=1.25`, `MIN_SHOT_MS=3000` | cuts land on **breaths** (`CUT_PAUSE_MS=120`), not sentence starts |
| Source-cut guard | **built** | `SHOT_CUT_GUARD_MS=1500`, symmetric | prevents a punch-in beside a real camera cut |
| Hook card | **built** | `HOOK_CARD_MS=1800`, `HOOK_CARD_THEME` | the judge's own `title_ckb`, on a 40% plate |
| Karaoke captions, RTL | **built** | `build_ass`, libass/HarfBuzz/FriBidi | Kurdish invariant #4 |
| Emphasis on the carrying word | **built** | `emphasis_index`, `EMPHASIS_SCALE=118` | style change only, **never** a text change |
| Broadcast loudness | **built** | `DELIVERY_LUFS=-14.0`, `DELIVERY_TRUE_PEAK_DB=-1.0` | EBU R128 |
| Five-file delivery set | **built** | `delivery.py` | atomic |
| **Silence tightening** | **not built** | `pro-edit` T4 | measured unnecessary on ep29 (§4.4). Revisit threshold: *a measured clip with gaps over 600 ms.* Couples to three timing systems — `sendcmd` stamps, crop `x` as a function of `t`, absolute ASS stamps. |
| **Multi-moment assembly** | **not built** | `pro-edit` T6 | Hawa approved building it. Counter-argument on record: the source is already multi-camera, so harvesting its own cuts may make synthetic assembly unnecessary. Judge must score the **assembly**, not the source spans. |
| **Speaker-tracked reframe** | **BLOCKED** | `pro-edit` T7 → `BLOCKED.md` #4 | crop currently follows the **largest face**, not the person speaking. On a two-person podcast this is the single biggest remaining gap. |
| **Visual-variety in selection** | **not built** | — | selection ranks on hook score alone, so it is quietly biased toward visually flat footage: judged spans average one source cut per 19.8 s vs the episode's 11.1 s, and the first shipped clip had **zero**. **Hawa's editorial call — do not change the ranking unilaterally.** |
| B-roll / cutaways / graphics | not built | — | not in `BLUEPRINT.md`; would need an ADR |

### The honest verdict on the current best output

From `evidence/what-the-edit-features-changed.md`:

> **This is a good social clip and not a team-made edit.** It has a hook in the first two seconds,
> cut rhythm, three real camera angles, emphasis, correct RTL captions and broadcast loudness. It is
> still one continuous *moment*: no b-roll, no assembly across moments, no silence tightening, and
> the crop follows the largest face rather than the person speaking.

**Closing that gap is your job.** In order of impact: speaker-tracked reframe (#4) > assembly (T6)
> visual-variety selection (Hawa's call).

---

## 6. Defect register — what broke, why, and whether it is fixed

### Fixed (keep them fixed; each has a test *and* a frame)

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | Clip rendered a wall, not the speaker | face tracking was opt-in behind `--face-reframe` | face tracking is the default; `--static-crop` opts out; missing OpenCV degrades **visibly** |
| 2 | Well-composed source got zoomed and softened | `TARGET_FACE_HEIGHT_SHARE=0.22` derived from one video | 0.15, measured on two |
| 3 | One scale change in 35 s | punch-ins cut only on sentence starts; the clip held two sentences | cut on breaths ≥120 ms — where the speaker themselves broke |
| 4 | Angle change, then a crop jump 0.77 s later | nothing consumed Stage 0's shot cuts | `SHOT_CUT_GUARD_MS=1500`, symmetric |
| 5 | Judge wrote a title; render discarded it | never wired | hook card burns `title_ckb` |
| 6 | "No clip worth shipping" | `--judge-top-n 5`; winner sat at rank 8 | use 12 to test; default unchanged pending Hawa |
| 7 | Path A returned 1.1 s fragments | the prompt never stated a duration | prompt states the range, formatted from the constants; compliance measured |
| 8 | Nothing could ever pass Stage 4 | `MAX_MISLEADING_EDIT_RISK=0.05` unreachable | 0.10 (D-257) |
| 9 | Champion adapter had never run since D-181 | **five stacked defects** — see below | all five fixed; adapter id `lora:22b2c9eed5a67425` now appears in the transcript |

**Defect 9 in detail**, because you will meet its shape again:
1. UNC path `\\wsl.localhost\…` fed through `wslpath` → `wsl_native_path()` returns it directly.
2. `peft` absent from the runtime lock → added as `peft==0.19.1`, lock count 137 → 138 (D-261).
3. A misdiagnosis: the first "fix" asked for the tokenizer by name and changed nothing — **the name
   itself was the bug.** fairseq2 parses card names as `name@env`; a trailing `@` means "no
   environment lookup", and `resolve_tokenizer_reference` is a `while True` following
   `tokenizer_ref`. The card resolved to itself and spun **3 h 20 m at 99% of one core.** Solved
   only by dumping the spinning frame's locals and seeing `ref_card is card`.
4. `py-spy` installed into the audited venv contaminated the runtime identity.
5. `base_name = self.llm_card.split("@", 1)[0]` before composing the adapted card name.

> **Lesson worth more than the fix:** a hang is not a slow run. Dump the frame. Three hours were
> spent believing a 31.2 GB checkpoint was loading slowly; it had read 418 MB and stopped.

### Open

| Symptom | Status |
|---|---|
| Selection blind to visual variety | **Hawa's editorial call.** Measured, recorded, not changed. |
| Two concurrent gates corrupt `.gate/last-test-run.xml` (*"junk after document element"*) | Known. **Run one gate at a time, in the foreground.** |
| D-257 + commit messages mislabel `01-MmQ9XPggSig` | Ask Hawa before amending the ADR. |
| `pro-edit` T4, T6, T7 | See §5. |
| `diarization-adapter` T2–T5 buildable now; T6 blocked | See §7. |

### Traps that cost hours and will do it again

- **Heredoc backslash collapsing.** Writing ASS strings through a shell heredoc turned `\\N` into
  `\N` and `\fscx118` into a formfeed. **Write patch scripts with the Write tool**, and build
  backslash literals from `chr(92)` when a shell is unavoidable.
- **`\U` in a non-raw docstring** → *"Got unexpected unicode"*. Use `r"""` for anything with
  backslashes. Cost two parse failures.
- **ASS field indices are off by one** from the naive split: `BorderStyle` is `split(",")[15]`, not
  `[16]`, because index 0 is the `"Style: Name"` prefix.
- **ffmpeg evaluates crop's `w`/`h` once at configuration**, only `x`/`y` per frame. A scale change
  can *never* come from a bigger expression — it needs `sendcmd`. All four crop options carry the
  `T` flag; verify on your build before designing around it.
- **NVENC ignores `-crf`.** Use `-rc vbr -cq N -b:v 0` (D-249). And `-cq 20` on a 3.5 Mbps source
  produced a **2.65 GB** intermediate; `-cq 27` gave 0.98 GB. Right for a deliverable, wrong for a
  working file.
- **MSYS mangles `/mnt/...`** → prefix with `MSYS_NO_PATHCONV=1`.
- **CRLF in a bash script written from Windows** → `set: - : invalid option`.
- **`git commit -q` inside an `&&` chain can fail silently** and the next step never runs while you
  believe it is in flight. Check exit codes.
- **`ps` inside WSL will not show the pipeline.** It runs Windows-side.

---

## 7. The work queue, in order

Follow `research → plan → implement` from `AGENTS.md`. **PLAN stops for a human on the
`Approved-by:` line.** Do not start implementing an unapproved plan.

1. **`pro-edit` T7 — speaker-tracked reframe.** Highest impact. Needs `BLOCKED.md` #4: the pyannote
   gated licence accepted on Hugging Face and an `HF_TOKEN`. **Only Hawa can click that.** Ask
   once, plainly, and move on if the answer has not arrived.
2. **`diarization-adapter` T2–T5.** Buildable *today* without the model: the conversion rules, the
   refusals, and the `--diarize` flag are all provable against a stubbed pyannote `Annotation`. T6
   is the blocked half. This is the largest piece of real work available with no external
   dependency.
3. **`pro-edit` T6 — multi-moment assembly.** Approved by Hawa. Before building it, test the
   cheaper hypothesis: does selecting spans that *contain* the source's own camera cuts produce a
   clip that reads as assembled? Stage 0 already has the cut list. If it does, record that and say
   so — a feature not needed is a better outcome than a feature built.
4. **`pro-edit` T4 — silence tightening.** Only after a measured clip shows gaps over 600 ms.
   Re-measure with §4.4 on new material before reopening it.

Everything else in `specs/` predates this work; read its `tasks.md` before assuming it is stale.

---

## 8. The gate, and what proof means

```bash
bash scripts/verify.sh
```
Runs `ruff check` → `mypy` → `ruff format --check` → `pytest --junitxml=.gate/last-test-run.xml` →
`hawedit.gate` grading that report for freshness and count. `--fast` stops after typecheck and
**cannot print the success line**. The steps are not configurable; `LINT_CMD`, `TEST_CMD`, `PY` and
friends are *refused*, not honoured.

Flip a row only after it exits 0:
```bash
bash scripts/update-ledger.sh <feature> T5 test_the_name_you_wrote
```
It re-runs the gate itself and refuses a citation it cannot find in the report that run wrote.

### Violations, not shortcuts

No `@pytest.mark.skip`, no `xfail`, no `-k` / `--deselect` / `--ignore` to make a red suite look
green. Do not weaken an assertion, mock the thing under test, or edit a golden so it matches buggy
output — §4.3.6's golden render is a **pixel** comparison, and changing the reference is changing
the answer. Do not hand-edit `scripts/test-count.floor`; the gate ratchets it and CI fails a run
that ratcheted.

### What counts as proof of *quality* (the gate cannot supply this)

A quality claim needs **all four**:
1. `bash scripts/verify.sh` green.
2. The rendered `.mp4` inspected with §4 — frames looked at, cuts counted, loudness measured.
3. The numbers written into `evidence/<claim>.md` with the source file, the date, the host, and the
   commands.
4. The honest limitation stated in the same file. Every good record here ends with what is *still*
   not established.

**And then it is still a draft, not an acceptance.** `specs/true-10-10-acceptance/tasks.md` is
explicit: a 10/10 verdict requires owner **and** Kurdish-editor sign-off (F8). You cannot award it.
Nor can I.

---

## 9. What only Hawa can decide — ask once, then work around it

Do not move any of these unilaterally. Each is a number she sets or a term only she knows.

| Decision | Why it is hers |
|---|---|
| pyannote gated licence + `HF_TOKEN` (`BLOCKED.md` #4) | a licence click, unblocks speaker tracking |
| Champion adapter licence (#21) | commercial terms |
| Visual-variety tiebreak vs hook score strictly dominant | editorial taste |
| `--judge-top-n` default (5 hid a rank-8 clip) | her billing |
| Vertex zero-data-retention before client work (#3, governance half) | §3 calls it *"mandatory, not advisory"* — full transcripts leave the network |
| Labelled Sorani corpus (#1) | Mozilla Data Collective terms; or her own footage |
| 64-frame window (#17) | recorded in `BLOCKED.md` |

**Never enter an API key, token, or credential on her behalf** — that is prohibited regardless of
authorisation. Direct her to `hawedit-credentials` / `hawedit-setup` and let her type it. If a
secret appears in a chat transcript, say so and advise rotating it.

---

## 10. The loop, if you are told to keep going

1. Pick the next unchecked row from §7. Research it. Plan it. **Wait for approval.**
2. Test first. Watch the test fail for the reason you expect.
3. Implement the smallest correct change inside the impact map.
4. `bash scripts/verify.sh`. Green → `update-ledger.sh`.
5. **Render a real clip from `ep29-chunk50min.mp4` and run §4 on it.** Every time.
6. Write what changed into `evidence/`, including what did not work.
7. Commit — to `main`, split by unit, message carrying the measurement, gate result as the last
   line. Fetch first: the repo has a remote and concurrent sessions.
8. **Stop when the only remaining work is a decision in §9.** Say so plainly and stop. Looping past
   that point produces noise that looks like progress — which is exactly the failure this file
   exists to prevent.
