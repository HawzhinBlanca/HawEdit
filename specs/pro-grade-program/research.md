# Research — pro-grade program (deep audit, 2026-09-02)

> Measured 2026-09-02 on `HAWAPC01` (Windows 11 Pro, 2× RTX 3090 Ti), working tree at
> `d79501e` plus 18 uncommitted files. ffmpeg 8.1.1-full (libass, HarfBuzz, FriBidi, NVENC,
> libvmaf). Source under audit: `work/ep29-VbX8UWwl1c4-s25-25/` cut from
> `ep29-VbX8UWwl1c4.mp4` (2560×1440, VP9, 25 fps, 3.39 Mbps, 84 min), the owner's own channel.
> Code cites are to the working tree at that state. Everything in §3 was produced by the
> commands in §3; nothing else in this file is a measurement.

## 1. Verdict, honestly

**Grade today: a good single-moment social clip, not a team-made edit, and not a system that
can prove its own output.** `evidence/what-the-edit-features-changed.md` (2026-08-29) said the
same and it still holds. The delivered clip is competent: hook in the first two seconds, ten
scene changes in 56.6 s, correct RTL karaoke, −14.2 LUFS, five-file atomic delivery, transcript
from the champion adapter. Three things stop it being 10/10:

1. **It cannot follow the person speaking.** The crop follows the largest Haar face at 2 fps.
   `SpeakerSubjectTracker` is a Protocol with no implementation anywhere in `src/`
   (`reframe.py:112-125`). On a two-person podcast this is the single largest visible gap.
2. **It ships one clip per run, chosen on one number.** Winner = `max(hook_score)` among
   passers (`pipeline.py:2053`). No dedup, no diversity, no topic structure, no calibration,
   no multi-clip plan. A team produces 5–15 clips per episode and they differ from each other.
3. **Its contract can say things the pixels do not.** `captions_burned_in=True` is unconditional
   (`render.py:874`), `RenderResult.width/height` are constants (`render.py:866-867`),
   `FACE_TRACKED` is stamped from one focus point (`pipeline.py:2301-2311`), `human_reviewed`
   comes from a CLI flag (`pipeline.py:3115`), `silence_removed_ms` promises an edit no code
   performs (`clip.py:495`, `silence.py` has no caller in `src/`). A 3,326-test gate is green
   through all of it because the suite asserts intent, not outcome.

Two ledger rows were flipped since `HANDOFF.md` was written for features that do not work
(§6.2). That is the exact failure `HANDOFF.md` §1.3 named — *"a passing test is not a working
feature"* — repeated after the warning.

## 2. What was inspected

| Source | How |
|---|---|
| `BLUEPRINT.md` §2, §3, §5, §6, §8, §9 | read |
| `HANDOFF.md`, `AUDIT_REPORT.md`, `BLOCKED.md` open items, `specs/*/tasks.md` open rows | read |
| Vault canon: Owner Canon, Honesty Law, No Fancy Features, Kurdish Invariants, Champion Supremacy, Calibrated Numbers, Working With Hawzhin | read |
| `render.py`, `reframe.py`, `captions.py`, `silence.py`, `assembly.py`, `keyframes.py`, `ingest.py`, `delivery.py` | full read (subagent), cites below |
| `pipeline.py`, `clip.py`, `judge.py`, `boundary.py`, `path_a.py`, `path_b.py`, `discovery.py`, `sentences.py`, `repurposing.py`, `gemini.py`, `visual_pipeline.py`, `timelens.py`, `video_grounding.py` | full read (subagent), cites below |
| `tests/`, `scripts/verify.sh`, `gate.py`, `tests/golden/`, acceptance modules | full read (subagent), §7 |
| The delivered clip | ffprobe, scdet, ebur128, silencedetect, 57 frames at 1 fps, contact sheet, contract JSON, ASS, EDL |
| `bash scripts/verify.sh --fast` on the uncommitted tree | lint + mypy clean, 190 files; tests did not run |
| `gh api …/actions/runners` | **0 runners registered** |

## 3. The delivered clip, measured

`work/ep29-VbX8UWwl1c4-s25-25/ep29-VbX8UWwl1c4-s25-25.mp4`, 21,106,780 bytes, written
2026-08-30 21:08.

| Property | Value | Command |
|---|---|---|
| container | h264 1080×1920, 25 fps, 1,415 frames, 56.600 s, 2.79 Mbps | `ffprobe -show_entries stream=…` |
| scene changes (`scene>0.3`) | **10** at 0.56, 11.04, 17.08, 20.84, 26.00, 34.24, 39.68, 44.64, 47.68, 55.64 s | `-vf select='gt(scene,0.3)',showinfo` |
| loudness | **−14.2 LUFS**, LRA **2.2 LU** | `-af ebur128=peak=true` |
| silences ≥ 250 ms | **18**, total ≈ 6.7 s (**11.9 %** of the clip), longest 0.545 s, none ≥ 600 ms | `-af silencedetect=n=-30dB:d=0.25` |
| contract | hook 0.90, misleading 0.10, self-contained, fidelity 1.00, cultural 1.00, `narrative_role: aside`, `sv6d: null`, `speaker: null`, `boundary.confidence: null`, `durations: [57]`, `silence_removed_ms: 0`, `crop_target: face_tracked`, `qc.human_reviewed: true`, `asr.mean_logprob: −7.158`, `validated_by: rzgar/…` | contract JSON |
| EDL | one V event + one A event, 00:05:11:07 → 00:06:07:21 | `.edl` |
| ASS | `Kurdish` style Noto Naskh Arabic 108 px, MarginV 360, `\kf` karaoke, `\fscx118` emphasis; `Hook` style 0–1.8 s | `.ass` |

### 3.1 What the frames show (57 frames at 1 fps; `ep29-s25-25-contact-sheet-2026-09-02.jpg` beside this file)

- **0–1 s: the opening frame is the wrong person.** The hook card sits over a wide two-shot in
  which the crop shows the host drinking from a cup; the guest who speaks the whole clip is cut
  off at the right edge. The first frame a viewer sees is not the speaker.
- **1–16 s, 27–57 s: good.** Close-up of the guest, headroom correct, face on the composition
  line, captions clear of the face, punch-ins visible as scale steps.
- **17–25 s: eight seconds of a tiny subject.** The source cuts to a wide angle; the vertical
  crop keeps the whole table, rug and window and the face is roughly 6–8 % of frame height. A
  human editor would zoom hard, switch layout, or avoid the span. `MAX_VERTICAL_ZOOM=1.5`
  (`render.py:292`) cannot reach it.
- **Cut rhythm reads as rhythm**, not glitches: gaps of 4–10 s, none clustered.
- **Captions are legible** against this background. Nothing measures that; a darker source
  would not be caught.
- **Dead air is 11.9 %.** Every gap is under the 600 ms tightening threshold, so tightening
  would have removed nothing; a fast-paced social edit trims 300–500 ms pauses to ~200 ms.
  That is a taste decision, and it is Hawa's (§9).
- **LRA 2.2 LU** is very compressed. Single-pass `loudnorm` in dynamic mode
  (`render.py:147-150`) is a gain rider; two-pass linear mode is the broadcast method.
- **`mean_logprob: −7.158`** is not plausible as a per-token mean log-probability (perplexity
  ≈ 1,300); either the unit is not what the field name says or the value is a sum. Unverified;
  a task, not a finding.

## 4. Layer-by-layer reality

### 4.1 Picture — `render.py`, `reframe.py`

| Concern | Reality | Cite |
|---|---|---|
| Face detector | OpenCV **Haar** frontal + profile + mirrored profile, `minSize=40`, sampled at **2 fps** by seeking the full-res source | `reframe.py:230,249,262-267,214,256` |
| Face choice with two faces | largest area ÷ (1 + distance from previous). No speech signal | `reframe.py:192-198` |
| No face at a sample | nothing appended; interpolation pans across the gap (documented "rug on screen") | `reframe.py:269-279,210-211` |
| Zero faces in clip | `()` → `STATIC_CENTRE`, no operator warning | `pipeline.py:2213,2301-2311` |
| Speaker tracking | Protocol only; CLI never passes `speaker_tracker=`; `SPEAKER_TRACKED` unreachable | `reframe.py:112-125`, `pipeline.py:2214-2286` |
| Camera path | dead zone `crop_w/10`, settle 600 ms, linear 400 ms pan to the median; instant step at Stage 0 cuts; pans > `0.6·crop_w` **silently discarded** (uncommitted) | `reframe.py:306-408,387-389`, `pipeline.py:1449-1454` |
| Punch-ins | word gaps ≥ 120 ms, ≥ 3 s apart, ≥ 1.5 s from source cuts, alternating 1.0/1.25, **hard `w/h` step via `sendcmd`**. No easing, no push-in, no transition | `render.py:327-391,555-576` |
| Composition under punch-ins | vertical placement drops from the 0.38 line to **dead centre** whenever punch-ins exist | `render.py:431` vs `:565` |
| Constants | `TARGET_FACE_HEIGHT_SHARE=0.15` (3 sources), `FACE_COMPOSITION_LINE=0.38`, `MAX_VERTICAL_ZOOM=1.5`, `PUNCH_IN_ZOOM=1.25` (taste), `MIN_SHOT_MS=3000` and `CUT_PAUSE_MS=120` (one clip), `SHOT_CUT_GUARD_MS=1500` (one clip), `MIN_FACE_AREA=2000` (D-258) | `render.py:267-324`, `reframe.py:37-42` |
| Encode | `h264_nvenc -rc vbr -cq 20 -b:v 0` or `libx264 -crf 20`; `-threads 1`; no preset, profile, `-bf`, AQ, keyint, or colour tags; bicubic `scale=1080:1920`; a 1080p source upscales 1.78× at 1.0 zoom and 3.3× at a punch-in | `render.py:119-137,793-839` |
| Result labels | `width/height` constants; `captions_burned_in=True` unconditional | `render.py:866-874` |

### 4.2 Captions — `captions.py`

- Karaoke `\kf` from CTC word timings, gaps tiled (`:794-818`). Popup chunking by **character
  count**, 3 words / 22 chars (`:114-119,628,677`) — not shaped glyph width.
- One font file, Regular; `bold=True` makes libass synthesise bold (`:224`).
- Fixed `margin_v=360`, `margin_l/r=80` (`:229-231`); no face-relative placement; no contrast
  measurement.
- Emphasis = longest word at 118 % (`:782-816`). Style-only, never text.
- Golden pixel test exists and is real (`tests/test_captions.py:536-549` vs
  `tests/golden/kurdish-caption.png`) but covers **`REPORT_THEME` on black only**. `VIRAL_THEME`,
  karaoke, the hook card and captions over video — everything a client sees — have no pixel test.

### 4.3 Sound — `render.py`, `ingest.py`

- Single-pass `loudnorm=I=-14:TP=-1:LRA=11` without `measured_*`/`linear=true` = dynamic gain
  rider (`render.py:147-150`). `-ac 2` upmixes mono.
- No `afftdn`, `deesser`, EQ, compand, ducking, or music anywhere in `src/` (grep).
- Ingest audio is correct for ASR: 16 kHz mono, `loudnorm I=-23`, Silero VAD, PySceneDetect
  `ContentDetector(27)` on the source (`ingest.py:80,397-542`).

### 4.4 Silence tightening — `silence.py`

Pure arithmetic on `Word` timestamps; writes `silence_removed_ms` (`silence.py:34-163`).
**No caller in `src/`**, no CLI flag, no media cut, no ASS regeneration. Applied as written it
would drift captions off untouched audio. Ledger `pro-edit` T4 is `[ ]` — honest. The commit
title "Implement silence tightening" (`d79501e`) is not.

### 4.5 Assembly — `assembly.py`

Concatenates sentence-group **text and timestamps** onto one timeline and sends the text to the
judge with `tokens = words*2` and no frames (`assembly.py:77-207,678`). **No caller in `src/`**,
no render, no concat, no crossfade. `GeminiJudge` refuses a frameless Stage 4 request
(`gemini.py:~415`), so it cannot run against the real judge. `tests/test_assembly.py` uses
`MockEditorialJudge`. Ledger `pro-edit` T6 is **`[x]`**.

### 4.6 Discovery — `path_a.py`, `path_b.py`, `discovery.py`, `visual_pipeline.py`

- **Path A**: whole normalised transcript + word table (≤ 4,000 words), asks for 30–90 s
  stand-alone moments, temperature 0, schema-enforced (`path_a.py:68-118`). `reason_ckb` is
  **discarded** (`:302`). No cap, no dedup of overlapping spans (`discovery.py:32`). Text only.
  Not reproducible across calls (13 vs 10 candidates, `evidence/the-champion-ships-at-rank-eight.md`).
- **Path B is not independent discovery.** Its retrieval query is `--visual-query` or **the
  transcript slice of Path A's rank-1 candidate** (`pipeline.py:1351-1376,1849`); the
  whole-transcript fallback is refused. `SceneReading.score` is the reranker logit
  (`video_reader.py:334`); VideoChat3's SV6D text never affects ranking. §3's *"neither path
  filters the other"* is not what runs: Path B finds scenes that resemble Path A's best moment.
  At the measured 8-frame ceiling (`BLOCKED.md` #17) a window is 4 s.
- Fusion is rank-based (IoU ≥ 0.5 pairing, `discovery.py:788-878`), never score arithmetic.

### 4.7 Judge and selection — `judge.py`, `gemini.py`, `pipeline.py`, `clip.py`

- Verdict fields: `hook_score, self_contained, payoff_at_ms, meaning_fidelity,
  misleading_edit_risk, cultural_landing, narrative_role, title_ckb, description_ckb,
  hashtags_ckb` (`gemini.py:205`). Prompt: candidate slice, Path A score, SV6D lines, ≤ 20 JPEGs
  ≤ 768 px, one-line field definitions, **no rubric anchors, no few-shot, no audience or format**
  (`gemini.py:233-266`).
- Gates: hook ≥ 0.75, misleading ≤ 0.10, `self_contained` (`clip.py:246-247`).
  `meaning_fidelity` and `cultural_landing` are collected and **never gated** on the single-clip
  path. `MAX_MISLEADING_EDIT_RISK=0.10` was set to the model's observed floor (`clip.py:238-245`)
  — a threshold fitted to the judge's output, not to an editorial standard.
- No calibration across calls, no pairwise comparison, no repeat-K, no content-type mode, no
  hook taxonomy, no retention prior. `payoff_at_ms` is range-checked and never used.
- Selection: `_judgeable_plans` grows seeds to ≥ `min_clip_ms` on sentence boundaries, judges
  the first N, **winner = max hook_score** (`pipeline.py:1224,2053`). Two seeds can grow into
  the same run and both get billed. One clip per run (`:2318`). `Clip.speaker` always `None`.
- Cost is estimated from a back-solved `$2/M` (`judge.py:104-107`) and **not recorded in the run
  report**.

### 4.8 Boundary — `sentences.py`, `boundary.py`

- Split on `. ! ? ؟ ۔ …` or a ≥ 500 ms gap (`sentences.py:119-169`); the 500 ms is a
  placeholder (D-014); a 105 s "sentence" is on record (`BLOCKED.md` #14).
- Fusion is outward-only and correct (`boundary.py:352-455`); `confidence` never set.
- If the widened span pulls in an unselected word the run **refuses** (`pipeline.py:2181-2199`),
  so shot-cut and turn extension rarely apply in continuous speech.

## 5. Claims-without-measurement register (how a green run can lie)

| # | Claim in the artifact or report | Where it comes from | Truth source that should back it |
|---|---|---|---|
| 1 | `captions_burned_in: true` | constant | ink energy in the caption band of the delivered frames |
| 2 | `RenderResult.width/height` | constants | `ffprobe` of the delivered file |
| 3 | `crop_target: face_tracked` | ≥ 1 focus point | a face inside the delivered frame in ≥ N % of sampled frames |
| 4 | `qc.human_reviewed: true` | `--qc-pass` | a review record naming reviewer, time and the mp4 sha256 |
| 5 | `silence_removed_ms` | default 0 / arithmetic | delivered audio duration vs source span |
| 6 | `discovery_path: verbal` on a `--sentences` run | stamped | the stage that actually ran |
| 7 | `editorial.sv6d` | back-filled from Path B when the judge returned none (`pipeline.py:2031-2032`) | the judge's own output only |
| 8 | punch-in count / positions | the plan | `scdet` timestamps on the delivered file ± 1 frame |
| 9 | `−14 LUFS / −1 dBTP` | the filter string | `ebur128` on the delivered file |
| 10 | `pro-edit` T6 `[x]` | mock judge, no caller | a real render of an assembled reel judged with frames |
| 11 | `pro-edit` T7 `[x]` | a test that the label is *not* claimed | a speaker-tracked render measured against labelled turns |
| 12 | `JudgeRequest.tokens` in `judge_assembly` | `words*2` | `countTokens` |
| 13 | run cost | not recorded | billed calls × counted tokens, labelled *estimate* |
| 14 | `mean_logprob: −7.158` | worker output | unit check against CTC posteriors |

## 6. Process findings

### 6.1 The uncommitted tree

18 files, +284/−121, lint and mypy clean, **tests not run**. Two untracked specs:
`specs/audit-remediation/` (all four rows `[x]` by hand — no `ledger.log`, no
`update-ledger.sh` provenance) and `specs/smart-reframe-cuts/` whose `plan.md` reads
`Approved-by: pending` while its Tasks 1–3 are already implemented in `reframe.py` and
`pipeline.py`. `AGENTS.md` step 2 says PLAN stops for approval before code. Also untracked:
`.agents/rules/canonical-source-video.md`, a policy file written by another agent, and
`GEMINI.md` modified — at least two agents have written to one checkout since `d79501e`
(`BLOCKED.md` #12 was this exact situation).

**The full gate on this tree is red** (run 2026-09-02 12:31 by the Stop hook, 490.96 s):
3,335 tests, 3,330 passed, 0 skipped, **2 failed, 3 errored**. Four `tests/test_build.py`
cases refuse because `release._source_identity` runs
`git status --porcelain --untracked-files=all` and refuses **any** uncommitted path, tracked or
untracked (`release.py:501-506`); it prints only the first eight, which is why the message
names `GEMINI.md`, `security/wsl-asr-vex.json` and `src/hawedit/*.py`. **This audit's own
untracked `specs/pro-grade-program/` is one of those paths**, as are the other agents'
`specs/smart-reframe-cuts/`, `specs/audit-remediation/` and `.agents/rules/`. Those four tests
cannot pass until every file in the tree is committed or removed — this audit is committed as
its own unit for that reason; the rest is T0.1. The fifth,
`tests/test_vex.py::test_checked_in_policy_binds_current_lock_and_assets_and_closes_report`,
is independent of this audit (it hashes `src/hawedit` only) and
fails because `security/wsl-asr-vex.json` carries `source_sha256 = 256726…` while
`package_digest(src/hawedit)` of the working tree is `8a11f4…` — the uncommitted source edits
moved the digest and the VEX was rebound to some other intermediate state. Proof that HEAD is
clean: in a detached worktree of `d79501e`, `tests/test_vex.py` passed 25/25 (`test_build.py`
cannot run there — the worktree has no `.venv`). The floor was not ratcheted (`3326`). The
count went 3,326 → 3,335 from the three uncommitted tests plus parametrisation, not from this
audit. Resolving it is **T0.1** and needs Hawa's decision on the smart-reframe plan; nothing in
this program can be flipped on a red gate. Three other worktrees exist on other branches
(`HawEdit-codex-readiness`, `HawEdit-harden`, `D:/HawEdit-worktrees/active-speaker`), which
confirms concurrent sessions and makes T0.4 more than hygiene.

### 6.2 Two ledger rows flipped for features that do not work

- **T6 assembly**: flipped 2026-08-29 (`752b0b5`) on `MockEditorialJudge`; zero callers, no
  render path, refused by the real judge. `evidence/what-the-edit-features-changed.md`
  (same day) still says *"no assembly across moments"* — the record and the ledger disagree.
- **T7 speaker-tracked reframe**: flipped 2026-08-29 (`9152e59`) on
  `test_an_unavailable_diarizer_never_claims_speaker_tracking`, which asserts the artifact does
  **not** say `speaker_face`. The row text allowed that, and the feature it names does not exist.

Both are correctable without deleting anything: an ADR that says what the row proved and what it
did not, and a re-opened row with the real proof attached (tasks T0.2).

### 6.3 CI

`gh api …/actions/runners` → **0**. The `wsl-asr-security` job targets
`[self-hosted, Windows, X64, hawedit-gpu]` and has been queued since the 2026-08-25 merge (vault:
*Projects/HawEdit.md*). Nothing that needs the source video or a GPU can be a required check
until Hawa registers that runner. Latest `gate` runs: `d9b07d4` success (2026-08-25), `aaa5971`
cancelled.

## 7. Proof surface — what the suite proves and where it can be fooled

3,326 tests pass (floor). About 200 need a real ffmpeg, about 10 compare decoded pixels, about
3 measure audio. The rest test structure, refusals, schema, prose claims and mocked adapters.
The suite is unusually honest about what it does not prove; the gaps it admits are exactly
where a bad video ships green.

### 7.1 Real media in the suite

- One fixture: `tests/fixtures/kurdish-speech-3cuts.mp4` — 4.1 s, 640×360, three coloured
  shots, **no face** (`tests/test_ingest.py:4,63,69`).
- One golden: `tests/golden/kurdish-caption.png`, full-frame exact RGB24 equality through
  ffmpeg (`captions.py:1088-1124`) with a `shaping=simple`-must-differ control
  (`test_captions.py:613`). It is **one 28-character line in `REPORT_THEME` on black**. Its
  sha256 is pinned nowhere; regenerating it from a broken libass leaves only the control.
- Face-in-crop: **no test.** `test_reframe.py` replaces `cv2` in `sys.modules` (`:127-138`);
  `test_real_render_accepts_a_time_varying_face_track` (`test_render.py:816`) feeds hand-made
  focus points and asserts the label and a file size > 1,000 bytes.
- Loudness: ebur128 on a **synthetic sine**, ±1.5 LU (`test_render.py:1293-1359`), never on
  speech or a delivered file.
- Silence tightening: pure functions on synthetic `Word` tuples (`test_silence.py:70-197`).
- Burned-in check: "> 1,000 bytes differ" (`test_render.py:606`) — a caption 4 px tall or
  off-screen passes.

### 7.2 Silent-skip surface

200 tests vanish without ffmpeg, 9 without `[media]`, 3 without the fixture, 14 without bash,
`importorskip("torch")` in `test_qwen_visual.py:271`. The floor counts **passed** (good,
`gate.py:237`) and CI greps "skipped" — but only in `test_ingest.py` output
(`gate.yml:150-155`). One `skipif` plus one trivial test elsewhere is invisible.

### 7.3 Mocks

Gemini/Vertex via injected transport with hand-written JSON (`test_gemini.py:93-116`); the
docstring's "one opt-in live script" does not exist in `scripts/`. OmniASR: `subprocess.run`
monkeypatched; pipeline transcripts are hand-typed with
`AsrProvenance(canonical="omniASR_LLM_7B_v2")` — the **string** is what gets checked
(`test_pipeline.py:97-115`). pyannote: `_MeasuredDiarizer` returns two hard-coded segments
(`test_pipeline.py:138`). Qwen/VideoChat/TimeLens loaders stubbed. No cassette recording anywhere.

### 7.4 The gate

`verify.sh` and `gate.py` are sound about *counting*: refuses overrides, empty or stale reports,
`passed < floor`, and CI refuses a ratcheted floor. They measure **nothing about test quality**:
no coverage threshold, no mutation score; `assert True` and the golden render weigh the same.
1,131 `pytest.raises` sites; 23 files assert on prose in the living docs.

### 7.5 Acceptance and evidence machinery

`editorial_acceptance.py`, `corpus_acceptance.py`, `diarization_acceptance.py`,
`vertex_acceptance.py` bind manifests to media sha256, need two reviewer ids plus a coordinator,
and verify OpenSSH signatures — **against an `allowed_signers` file passed on the command line**
(`editorial_acceptance.py:1018-1060,1764`). No trust root is pinned in the repo; a self-minted
key and a self-written signers file produce "verified". `decision_packets.py` hashes six named
evidence files into a packet — bytes to packet, not evidence to commit. `evidence/` holds 222
files; about 8 name a commit SHA; the only machine link is a size check on
`evidence/m2-4-rendered-clip.mp4` (`test_render.py:665`).

### 7.6 Human review and provenance

`Clip.assert_renderable()` refuses without `qc.human_reviewed` (`clip.py:733`) and `--qc-pass`
sets it from any shell (`pipeline.py:2848,3115`); only the *agent tool surface* withholds the
flag (`workflow_control.py:10-12`). No reviewer, time, or mp4 digest. The contract records the
judge model **name** and ASR provenance strings, and omits: prompt hash, response id, judge
thresholds, VAD and scene thresholds, crop constants, git SHA, `revisions.json` digest.
Temperature is 0 and model revisions are pinned; **no re-render reproducibility test exists**
for MP4.

### 7.7 Ten ways to ship a bad video green (from the test audit, kept as the threat model)

1. `--qc-pass` from any shell. 2. Hand-typed transcript carrying the canonical model's name.
3. Any `JudgeVerdict` with `judge="gemini-2.5-pro"`. 4. Any focus points → `FACE_TRACKED`.
5. Wrong silence cut points — arithmetic only. 6. A `skipif` on an awkward media test plus one
trivial test. 7. Regenerate the golden PNG. 8. Self-signed acceptance packet. 9. Loudness never
measured on speech. 10. Captions drawn 4 px tall still "burned in".

## 8. Gap list against a professional team and the top tools

Ordered by what a viewer notices first. **B** = build, **D** = owner decision, **ADR** = diverges
from or extends `BLUEPRINT.md` §3 Stage 6 and needs a `DECISIONS.md` entry.

| Gap | Today | Pro team / Opus Clip / CapCut / Premiere | Kind |
|---|---|---|---|
| Follow the speaker | largest Haar face | active-speaker (lip motion + diarization) | B, blocked #4 |
| Wide shots in 9:16 | tiny subject for 8 s | hard zoom, blurred-fill layout, or avoid | B |
| Opening frame | wrong person drinking | speaker's face + hook, always | B |
| Camera motion | hard scale steps | eased push-ins, motivated cuts | B, D (taste) |
| Two-person exchanges | never crosses to the second face | split-screen / cut-to-listener | B, needs #4 |
| Face detection | Haar, 2 fps | DNN + tracking every frame | B, ADR (new model) |
| Captions | fixed band, char-count breaks, one theme pixel-tested | face-aware placement, contrast-checked, shaped-width breaks, per-speaker colour | B |
| Sound | single-pass loudnorm, nothing else | two-pass linear, denoise, de-ess, EQ, music bed + ducking | B, D (music licence) |
| Dead air | measured, never cut | tightened to taste | B (wire T4), D (threshold) |
| Encode | `-cq 20`, no preset/profile/tags, bicubic upscale | platform profile, lanczos + light sharpen, VMAF-checked | B |
| Clips per episode | 1 | 5–15, diverse, ranked, non-overlapping | B, D (N, cost cap) |
| Selection signal | `hook_score` alone | hook type, payoff, loop, fidelity, visual variety, speaker change | B, D (variety) |
| Judge reliability | uncalibrated, non-reproducible candidate set | calibrated against labels, stable | B, needs H2 |
| Path B | query = Path A's rank-1 | independent visual discovery | B, D (#18, #17) |
| Sentence rule | 500 ms placeholder | measured on real audio | B, needs #1 or ep29 labels |
| Cold open / assembly | text-only, unwired | rendered, re-judged with frames | B (rewrite T6) |
| Lower-third, logo, end card, progress bar | none | standard | B, ADR, D (brand kit) |
| Length variants 15/30/60 (§5) | one length | per platform | B, D (cost) |
| Cover frame / title variants | one title | chosen frame, 3 titles | B, D (cost) |
| Proof of output | intent labels | independent measurement reconciled against the file | B — **first** |
| Proof of "better than humans" | none | blind pairwise preference with CI | D (commission editor + raters), B (kit) |

## 9. Decisions only Hawa can make (ask once, then work around)

Unchanged from `HANDOFF.md` §9: pyannote licence + `HF_TOKEN` (#4), champion licence (#21),
visual-variety tiebreak, `--judge-top-n` default, Vertex ZDR (#3), labelled corpus (#1), 64-frame
window (#17), #13/#14/#15/#18. **New from this audit:** register the self-hosted GPU runner;
clips per episode and the per-episode judge cost cap; the silence-tightening threshold; the
content-type of each source; brand kit (names, logo, fonts) and music licence; whether to
commission one human editor's cuts of ep29 for the blind comparison; single-writer rule for the
checkout.

## 10. What this audit did not do

The full gate ran once, by the Stop hook, and is red for the reasons in §6.1; this audit did
not make it green and does not claim to. It did not re-render anything. It did not measure any model's accuracy — no labelled Sorani data exists
(`BLOCKED.md` #1), so every editorial number above is the judge's own output, recorded as
judgment. It did not read `DECISIONS.md` or `PROGRESS.md` whole.
