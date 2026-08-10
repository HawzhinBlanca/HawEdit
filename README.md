# hawedit — Kurdish Video Repurposing System

Central Kurdish / Sorani (`ckb`, Arabic script). Built against `BLUEPRINT.md` v1.1 (frozen).

## What this is today

**This is a fully composed, rigorously tested pipeline, not a production-proven product.** The
runner wires canonical OmniASR, Qwen retrieval/reranking, survivor-only VideoChat3, multimodal
Gemini judging, TimeLens grounding, automatic sentence selection and face-aware reframing. A
production claim still needs external weights, an authorized cloud route and real
human-labelled Sorani/editorial sets; this repository does not fabricate those results.
Stage 1 is runnable through `--omni-asr`; on Windows the runner automatically uses the WSL2
bridge because Meta's fairseq2 native extension has no Windows wheel. Its model execution is
not a measured Sorani benchmark until the package-managed weights and labels are present.

```bash
.venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work
```

Run bare, it does Stage 0 on real media, exits non-zero, and prints every stage it could not
run with the blocker named. Nothing is skipped quietly.

```bash
.venv/bin/python -m hawedit.credentials                    # store a Gemini key, once
.venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work \
  --transcript t.json --gemini --sentences 0,1 --qc-pass
```

The autonomous local/cloud route is explicit:

```bash
.venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work \
  --omni-asr --visual --gemini --auto-select --timelens --face-reframe --qc-pass
```

For confidential material, replace `--gemini` with `--vertex-project PROJECT`, configure ADC,
and supply `--confidential --zero-data-retention --zdr-confirmed-by NAME`.

| §3 Stage | State | What is missing |
|---|---|---|
| 0 · Ingest | **runs** | Diarization — Community-1 is a gated repo (`BLOCKED.md` #4). |
| 1 · Speech | **wired** | `--omni-asr` runs official OmniASR inference plus CTC-Viterbi timing. Real weights and labelled Sorani validation remain external. |
| 2 · Index | **wired** | `--visual` extracts each scene once, embeds all windows, retrieves top 50, reranks all hits and retains 5–10. Media with fewer scenes than the survivor count is **refused**, not silently shortened — measured on the 3-scene fixture, `evidence/unlisted-modules.md`. |
| 3 · Discovery | **wired** | Path A and composed Path B union without promoting non-survivor scenes; `--auto-select` anchors complete contiguous sentences. |
| 4 · Editorial judge | **wired** | Requests carry actual source JPEG bytes. Developer API handles non-confidential work; Vertex uses ADC bearer auth and an attributed ZDR gate. Credentials/billing remain external. |
| 5 · Boundary fusion | **wired** | `--timelens` runs TimeLens2 per overlapping scene window and fuses only relevant media-clock intervals. |
| 6 · Render | **wired** | `--face-reframe` tracks a dominant continuous face and drives a time-varying vertical crop. It is face-aware, not active-speaker diarization. |

"Runs" means: on real media, in a test, in the gate. Nothing here is marked done because it
compiles. `PROGRESS.md` carries the per-task evidence and `BLOCKED.md` carries what needs Hawa.

| File | What it is |
|---|---|
| `BLUEPRINT.md` | The frozen source of truth. Not edited by implementation work. |
| `PROGRESS.md` | Milestone/task ledger generated from §9, with evidence per task. |
| `DECISIONS.md` | Append-only: every deviation and judgment call, with its measurement. |
| `BLOCKED.md` | What needs Hawa. The only legitimate reason to stop the loop. |

## Setup

One command, from a fresh clone to a green gate:

```bash
cd hawedit
bash scripts/setup.sh
```

It creates the venv, installs the dev and §3 Stage 0 media dependencies (CPU torch — §6 puts
Stage 0 on CPU by design), verifies or fetches an ffmpeg whose libass has HarfBuzz, reports §7
model readiness, and finishes by running the gate. If it exits 0 the checkout is genuinely
ready, and the last thing it prints is the interpreter path for *this* machine.

> **Windows.** hawapc01 is a Windows box, so every `.venv/bin/python` below is
> `.venv/Scripts/python.exe` there. `setup.sh` and `verify.sh` detect the layout themselves;
> only the commands quoted in this file are written one way. An ffmpeg on `PATH` with libass,
> HarfBuzz and FriBidi is accepted as-is — `winget install Gyan.FFmpeg` (the *full* build)
> supplies one, and `fetch-ffmpeg.sh` verifies it rather than downloading a Linux binary over it.

Canonical OmniASR needs a one-time WSL2 runtime setup on Windows (the official native loader is
Linux/macOS only):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-wsl-asr.ps1
```

That creates a source-fingerprinted runtime below `%LOCALAPPDATA%\HawEdit\wsl-asr`, using Python
3.12, and probes both CUDA GPUs. The host runner still owns Stage 0, cuts every VAD-bounded WAV
locally, invokes one WSL worker so both models load once, then validates the returned immutable
transcript. An installed wheel exposes the same operation as `hawedit-asr-setup`. Override the
distribution with `-Distribution Ubuntu`; advanced deployments can set
`HAWEDIT_WSL_RUNTIME`, `HAWEDIT_WSL_PYTHON` and `HAWEDIT_WSL_SOURCE` explicitly.

The media extra is not optional here even though `pyproject.toml` marks it optional: without
it the Stage 0 tests *skip*, and a skipped test is the quiet green this project is written
against. That is also why setup ends with the gate rather than with an install.

<details><summary>Doing it by hand</summary>

```bash
python3 -m venv .venv
.venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -e '.[dev,media]'
bash scripts/fetch-ffmpeg.sh     # ~200 MB, lands in .ffmpeg/ (git-ignored)
bash scripts/verify.sh
```

`fetch-ffmpeg.sh` verifies the RTL stack and refuses a build that cannot shape Arabic script.
`verify.sh` discovers the binary automatically; without it §4.3.6's golden render — the only
real safeguard on Kurdish invariant #4 — skips.

</details>

## Models and weights

Check what this machine has:

```bash
.venv/bin/python -m hawedit.models      # §7 component readiness
```

Fetch what it does not:

```bash
bash scripts/fetch-models.sh             # everything §7 needs, into models/
bash scripts/fetch-models.sh --status    # same as the readiness report
```

The fetcher is driven by the §7 registry, so it cannot download a model the blueprint
excludes and refuses a NonCommercial licence before any bytes move. Needs
`huggingface.co` reachable, `HF_TOKEN` for the gated Community-1 repo, and ~50 GB free.

The two Qwen checkpoint names are resolved in tracked `models/sources.json`; the fetcher never
guesses a repository id. OmniASR is deliberately absent from that file: the pinned official
`omnilingual-asr` package ships the exact `_v2` model cards and owns their Meta asset URLs and
cache. Downloading similarly named Hub repositories into `models/` would provision weights the
runtime never reads.

Weights themselves never enter the repository: `models/*` and `.ffmpeg/` are git-ignored.

On Linux, install `.[asr]` for the official OmniASR runtime. On Windows, run
`scripts/setup-wsl-asr.ps1`; the `asr` dependency is intentionally platform-marked away from the
host venv because `fairseq2n` cannot install there. Model loading is lazy, so a missing package
or checkpoint is reported without making basic ingest unusable. This checkout has not run the
full canonical pair on a real labelled Sorani set; wiring is not accuracy evidence.

## GPU (§3 Stages 2, 3 Path B, 5)

Stage 0 runs on CPU by design (§6), so `setup.sh` installs the CPU build of torch. For the
model stages, install the CUDA build **first** — naming the local version, because the CPU wheel
already satisfies a bare `torch==2.13.0` and pip will report success while changing nothing:

```bash
pip install --index-url https://download.pytorch.org/whl/cu130 --extra-index-url https://pypi.org/simple "torch==2.13.0+cu130" "torchvision==0.28.0+cu130"
```

Then the extra:

```bash
pip install -e '.[dev,media,gpu]'
```

Verified on hawapc01: both RTX 3090 Ti doing bfloat16 work, and `Qwen3-VL-Embedding-2B`
returning 2048-d vectors for Kurdish text at 3.98 GiB. See `evidence/gpu-stack.md` — it also
records two traps that decide how Stage 2 must be written (D-048).

## Gemini access (§3 Stage 4)

```bash
.venv/bin/python -m hawedit.credentials          # panel: paste a key, it verifies, it stores
.venv/bin/python -m hawedit.credentials --check  # status only; exits non-zero if unusable
```

Input is hidden and never echoed. The key is verified against Google before anything is
written — a revoked key looks exactly like a working one, so a regex would not help. It lands
in an owner-only user config file (`%APPDATA%/hawedit/credentials.env` on Windows,
`$XDG_CONFIG_HOME/hawedit/credentials.env` on Linux). Explicit alternate paths are still
refused unless Git ignores them.

Get a key at <https://aistudio.google.com/apikey>. There is deliberately no `--key` flag:
command-line arguments are visible in `ps` to everyone on the machine.

Once a key is stored, verify the real path end to end — this is the only thing in the project
that spends money, and it says how much before it does:

```bash
.venv/bin/python -m hawedit.smoke --video PATH_TO_A_VIDEO_OF_THE_SAMPLE   # two real calls, ~$0.003
```

It runs §3 Stage 3 Path A over a built-in Sorani sample and §3 Stage 4 on the top candidate,
then prints the Kurdish title it got back. It checks what offline tests cannot: that
`gemini-2.5-pro` is enabled on your key's project, that the structured-output schema survives a
real response, and that the model actually answers in Kurdish.

**`--video` is required and no matching video ships with this repository.** §3 Stage 4 judges
real source pixels — text-only visual judging is refused — so the check needs a video of the
built-in sample, which spans **0..13,000 ms**. The only Kurdish video here,
`tests/fixtures/kurdish-speech-3cuts.mp4`, is **4.162 s** and does not match it: measured,
keyframes for `5000..13000 ms` fail outright, and `0..13000 ms` yields only **6** frames — real
ones covering the first 3.6 s, since D-153 stamps them from the sampling rate — for a candidate
13 s long. Until such a recording exists the
live check is not runnable as shipped — `BLOCKED.md` #20. Without `--video` it now refuses at
**exit 2 before spending anything**; it used to make both Path A calls first (D-152).

**Before the first client job**, §3 Stage 3 requires a decision, not a setting: full-transcript
discovery sends 100% of every transcript to Google, and for COMMS and KAAE material paid-tier
Vertex with zero-data-retention is *mandatory, not advisory*. `--vertex-project` routes Path A
and Stage 4 through Vertex REST with ADC bearer credentials. Confidential uploads are still
refused unless ZDR is explicitly confirmed and attributed; code cannot verify a customer's
contractual retention configuration by itself.

Stage 4 samples up to 20 JPEG keyframes from the exact candidate span and sends those same image
parts to `countTokens` and `generateContent`. Textual SV6D remains supporting evidence; it no
longer masquerades as source pixels.

## Benchmarks

`bench.py` remains the §8.1 ASR harness: normalized/spacing-free CER, named entities,
code-switching, alignment, RTF, VRAM and per-dialect coverage. `hawedit-editorial-bench`
validates and scores a blind human regression manifest, requiring at least 20 items, at least
five per dialect, two named reviewers per item, exact candidate/span equality and source media
on disk.

```bash
hawedit-asr-bench sorani-corpus.json --audio-root /secure/audio \
  --host hawapc01 --accelerator "RTX 3090 Ti" --output asr-report.json
hawedit-editorial-bench editorial.json --media-root /secure/media --output report.json
```

No production benchmark number ships in this repository. The required client/archive Sorani
audio and 200–500 human-reviewed editorial candidates have not been supplied, so claiming a CER,
hook-quality win or cultural-fit score would be fabricated evidence.

## The gate

```bash
bash scripts/verify.sh          # lint + typecheck + format + tests — this decides DONE
bash scripts/verify.sh --fast   # lint + typecheck only, for editor feedback
bash scripts/build-wheel.sh     # the wheel, reproducibly, and its SHA-256
```

`build-wheel.sh` takes `SOURCE_DATE_EPOCH` from the commit's own author date, so the same commit
produces the same bytes on any machine on any day. Two builds of one tree used to differ (D-120),
which is why `AUDIT_REPORT.md` quoted a size and no digest; now the digest is printed and a test
holds both halves — two builds identical, every ZIP entry stamped with the commit rather than the
clock.

A task is DONE when this exits 0 **and** its evidence is recorded in `PROGRESS.md`. Nothing
is marked done by judgment.

The gate is deliberately hard to fool, because it is the only thing that decides DONE:

- **Its steps are not configurable.** Setting `TEST_CMD`, `LINT_CMD` or either of the others
  is refused outright (exit 5) before anything runs. A blacklist of ways to run nothing can
  never be complete — `TEST_CMD="echo skipped"` walked past the old one — so the rule is
  inverted. Use `--fast` for a partial check; it cannot print the success line.
- **The exit code is not the evidence.** The report is. The gate deletes it, runs pytest
  under `--junitxml`, and then requires a fresh report with zero failures and at least
  `scripts/test-count.floor` tests **passed**. Passed, not collected: the two differ by
  exactly the skips, and a skip creeping into the suite is the case the floor exists to
  catch. That floor ratchets up on its own and never down, so a suite that shrinks has to
  shrink in a diff someone can see.
- **A nested invocation refuses its own test step** — it would otherwise recurse, and once
  did (D-005).

CI runs the same script on a clean runner (`.github/workflows/gate.yml`), fetches the
ffmpeg archive **at a pinned commit and verifies its SHA-256 before unzipping it** (D-121 — this
line said "pinned" for a while when the URL was a branch path), and fails if the §4.3 golden render
or the §3 Stage 0 tests *skip* rather than run. **That job is a required status check on `main`**
(`BLOCKED.md` #7, resolved 2026-08-08), with `strict: true`, so a branch must also be up to date
with `main` before it can merge. Measured against the live API:
`required_status_checks.contexts == ["gate"]`.

**Corrected 2026-08-10 (D-143):** the paragraph above ended "Making that job a required status
check is a repository setting, and is not done" for two days after #7 was resolved — understating
the project's own bar, in the one document a reader meets first.

## Module map

| Module | Blueprint | What it enforces |
|---|---|---|
| `registry.py` | §7 | The model allowlist, checked against §7 by parsing the blueprint. NC licences hard-rejected. |
| `normalize.py` | §4.1 | Sorani normalization: KLPT for four collisions, a dictionary-backed rule for conjunctive `و`. Failure mode #1 in §0. |
| `transcripts.py` | §4.1, §5 | The raw/norm artifact pair. Kurdish invariants #1 and #3. |
| `alignment.py` | §4.2, §8.1 | Alignment accuracy. Kurdish invariant #5. |
| `metrics.py` | §8.1 | Normalized CER, spacing-free CER, named-entity error, code-switch error. |
| `corpus.py` | §8.1, §4.4 | The labelled set and its coverage grid — 3 dialects × 7 conditions. |
| `asr.py` | §8.1, §3 Stage 1 | Official LLM+CTC/Viterbi producer, RTF, VRAM and failure rate. Hardware is required. |
| `asr_worker.py` | §3 Stage 1, §6 | Strict create-once Windows→WSL2 worker protocol for the official Linux runtime. |
| `wsl_setup.py` | §3 Stage 1, §6 | Wheel-safe, source-fingerprinted WSL2 runtime provisioning and CUDA probe. |
| `bench.py` | §8.1 | The benchmark run, the comparable report, and the canonical-model decision rule. |
| `editorial_bench.py` | §8.2 | A real-media, two-reviewer, dialect-balanced editorial regression manifest and judge-promotion report. |
| `diarization.py` | §8.1, §3 Stage 0 | DER and boundary reconciliation against word alignment. |
| `forced_alignment.py` | §4.2, §7 | Viterbi CTC forced alignment — in-house, no library. |
| `sentences.py` | §4.2, §5 | Sentence segmentation on punctuation **plus** pauses; §5 anchors. |
| `escalation.py` | §3 Stage 1 | Validator routing: log-prob quartile + model disagreement. |
| `index.py` | §2 | BM25 + character 3-grams over normalized Sorani. |
| `visual_index.py` | §3 Stage 2 | The visual half: scenes segmented to ~1 fps × 64 frames, cosine retrieval, and the top-50 → rerank → keep-5–10 contract. |
| `video_input.py` | §3 Stages 2, 3B, 5 | Putting a scene window in front of a Qwen3-VL model *at the right time*. Without `video_metadata` the processor stamps a 4.16 s window as 0.1 s long, silently. |
| `qwen_visual.py` | §3 Stage 2 | `Qwen3-VL-Embedding-2B` behind the embedding contract. Pooling read from the checkpoint, §7 role checked before the weights load, and no silent CPU fallback. |
| `boundary.py` | §3 Stage 5 | Boundary fusion. Kurdish invariant #2, at construction and at the render gate. |
| `timelens.py` | §3 Stage 5, §7 | TimeLens2's intervals as evidence, never as cuts — and only the ones that overlap the anchored sentence may move a boundary. |
| `clip.py` | §5 | The clip contract, validated. Rejection is a first-class type. |
| `captions.py` | §4.3 | RTL captions: `shaping=complex`, stack check, font coverage, our own line breaks. |
| `ingest.py` | §3 Stage 0 | 16 kHz mono audio, 1 fps proxy, shot cuts from the **source**, VAD under the ASR ceiling. |
| `path_a.py` | §3 Stage 3 Path A | The Kurdish judge over the **whole** transcript. Refuses to send a subset, and refuses to split one. |
| `path_b.py` | §3 Stage 3 Path B | `VideoChat3-4B` over scenes. Inputs are packed into ≤256-frame calls; every SV6D label must cite a time **inside the scene it describes**. |
| `video_reader.py` | §3 Stage 3 Path B | `MCG-NJU/VideoChat3-4B` and the SV6D prompt. The model is shown one scene starting at zero, so every time it cites is moved onto the media's clock here — the invariant alone accepts an unshifted one whenever it happens to land in range. |
| `video_grounding.py` | §3 Stage 5 | `MCG-NJU/TimeLens2-4B` grounding a query in one scene. It answers in seconds from the window's start; `VisualEvidenceInterval.from_window` moves that onto the media's clock, because an unshifted span can overlap the anchored sentence and extend the clip on footage from elsewhere. |
| `visual_pipeline.py` | §3 Stages 2–3B | Extract once → Qwen embed → top-50 retrieve → rerank every hit → bounded survivors → VideoChat3 only on those survivors, with exact ID/score provenance. |
| `keyframes.py` | §3 Stage 4 | Real source-timestamped JPEG extraction for the multimodal judge, capped at 20. |
| `reframe.py` | §3 Stage 6 | Dominant-face continuity tracking that drives the render crop over time. |
| `discovery.py` | §3 Stage 3 | The dual-path union. Nothing is dropped, per-path attribution survives, overlap does not chain. |
| `pipeline.py` | §3 | The runner. Joins every stage that can run and names every one that cannot. |
| `smoke.py` | §3 Stages 3–4 | The one live check. Two real calls, announced and confirmed before spending. |
| `credentials.py` | — | The key store. Refuses a git-tracked target, an unverified key, and printing either. |
| `gemini.py` | §3 Stage 4 | `gemini-2.5-pro` behind the judge interface: schema-enforced output, real token counts, and fail-closed confidential routing. |
| `judge.py` | §3 Stage 4 | The judge contract: shadow never routed, 200K tier ceiling, promotion only on evidence. |
| `delivery.py` | §2 | The SRT sidecar (clip timeline) and the CMX 3600 EDL (source timeline). Refuses NTSC rather than writing timecode that drifts. Shares §4.3.5's line breaks with the ASS — an SRT cue on one line hands the break points to the player. |
| `render.py` | §3 Stage 6 | Cut, 9:16 crop, `shaping=complex` burn-in, encode. Refuses an unusable encoder rather than substituting. |
| `gate.py` | — | Positive evidence that the test step ran: the gate reads the report, not the exit code. |
| `cli.py` | — | What every entry point does before it writes. `use_utf8_streams` pins stdout and stderr to UTF-8 — the locale's codec is cp1252 on §6's machine and the output is Sorani. `machine_readable_stdout` holds stdout for one JSON document and sends everything a library prints to stderr. `program_name` derives the name `--help` shows from how the process was started, because a console script and `python -m` are different commands. |
| `collisions.py` | §4.1 | The collision table itself, and the incidence measurement over a real lexicon. |
| `corpus_import.py` | §8.1 | Public-corpus import that refuses to invent dialect, condition or duration. |
| `models.py` | §7 | Which §7 components this machine actually has, and the registry-driven fetcher. |
| `repurposing.py` | §8.2 | Per-path Recall@K, temporal IoU, misleading-edit rate, cost per source hour. |

## Two conventions worth knowing before reading the code

**Unmeasured is `None`, never `0.0`.** An item with no annotated entities has no
named-entity error; a corpus of 30-second clips has no long-audio failure rate. Returning
zero would render in a report as a perfect score. §1: "Fail visible, not silent."

**A number carries its provenance or it is not a number.** Throughput records the machine it
was measured on and refuses cross-hardware comparison (§3 Stage 1). Accuracy records the
adapter class that produced it, so a run driven by a test double cannot be read as a run on
real weights. Reports carry the corpus coverage they ran on, so a headline CER from an
incomplete set never looks unqualified.

## Attribution (licence obligations, §7 and D-002)

- `pyannote/speaker-diarization-community-1` — CC-BY-4.0, attribution required.
- KLPT — Sina Ahmadi, CC-BY-SA-4.0, attribution required; share-alike attaches if the rule
  tables are ever adapted.
- ASS + libass/HarfBuzz/FriBidi — LGPL/GPL, attribution required.
- Noto Naskh Arabic (The Noto Project Authors) — OFL-1.1. The licence must accompany the
  font: `assets/fonts/OFL.txt` ships beside it.

These must appear in shipped product documentation. `registry.attribution_notices()` generates
the list, and `tests/test_claims.py` asserts this section matches it **in both directions** —
this list had already drifted from its generator in both, which is what §10 calls a known risk
with a stated mitigation. Models come from §7's registry; the font comes from
`registry.SHIPPED_ASSETS`, because a font is not a model and §7's table is not ours to widen.
