# hawedit — Kurdish Video Repurposing System

Central Kurdish / Sorani (`ckb`, Arabic script). Built against `BLUEPRINT.md` v1.1 (frozen).

## What this is today

**One thing stands between this and a runnable product: §3 Stage 1.** The ASR models need
weights and a GPU this machine cannot reach, so nothing here can turn audio into a transcript
yet. Give it a transcript and a Gemini key, and the rest of §3 runs — discovery, judging,
boundary fusion and a rendered vertical clip with burned-in Kurdish captions.

```bash
.venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work
```

Run bare, it does Stage 0 on real media, exits non-zero, and prints every stage it could not
run with the blocker named. Nothing is skipped quietly.

```bash
.venv/bin/python -m hawedit.credentials                    # store a Gemini key, once
.venv/bin/python -m hawedit.pipeline VIDEO.mp4 --work-dir work \
  --transcript t.json --sentences 0,1 --qc-pass
```

| §3 Stage | State | What is missing |
|---|---|---|
| 0 · Ingest | **runs** | Diarization — Community-1 is a gated repo (`BLOCKED.md` #4). |
| 1 · Speech | contracts only | The ASR models themselves (`BLOCKED.md` #2). Alignment and segmentation are done and tested. |
| 2 · Index | text only | The visual index (Qwen3-VL embeddings) needs weights and a GPU. |
| 3 · Discovery | **Path A built, needs a key** | Path B — `VideoChat3-4B` weights and a GPU (`BLOCKED.md` #2). The union runs one-sided, which §3 says is correct rather than degraded. |
| 4 · Editorial judge | **built, needs a key** | Nothing — run `python -m hawedit.credentials`. The §3 ZDR answer is still required for confidential material. |
| 5 · Boundary fusion | **runs** | TimeLens2 refinement (M6). |
| 6 · Render | **runs** | Speaker-tracked reframing — the crop is static centre (`BLOCKED.md` #4). NVENC needs hawapc01. |

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

Four checkpoints — `omniASR_LLM_7B_v2`, `omniASR_CTC_3B_v2`, `Qwen3-VL-Embedding-2B`,
`Qwen3-VL-Reranker-2B` — are named in §7 as *checkpoints*, not repository ids, and the script
refuses to guess. All four are now resolved in `models/sources.json`, which is **tracked** — it
is configuration, not weights, and re-deriving it per machine is the guessing D-022 forbids. The
two Qwen rows are verified name matches; the two omniASR rows are a recorded decision, because
§7's `_v2` suffix appears on no published Meta checkpoint (`BLOCKED.md` #10, D-046).

Weights themselves never enter the repository: `models/*` and `.ffmpeg/` are git-ignored.

**The two omniASR checkpoints cannot be loaded on Windows** — they are raw fairseq2 `.pt` files
and `fairseq2n` publishes no Windows wheel, so §3 Stage 1 needs WSL2, a container, or a Linux
host. That is `BLOCKED.md` #11, and it is the one thing between this and a runnable product.

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
in `.env` at 0600, and the panel refuses to write anywhere git does not ignore.

Get a key at <https://aistudio.google.com/apikey>. There is deliberately no `--key` flag:
command-line arguments are visible in `ps` to everyone on the machine.

Once a key is stored, verify the real path end to end — this is the only thing in the project
that spends money, and it says how much before it does:

```bash
.venv/bin/python -m hawedit.smoke     # two real calls, ~$0.003
```

It runs §3 Stage 3 Path A over a built-in Sorani sample and §3 Stage 4 on the top candidate,
then prints the Kurdish title it got back. It checks what offline tests cannot: that
`gemini-2.5-pro` is enabled on your key's project, that the structured-output schema survives a
real response, and that the model actually answers in Kurdish.

**Before the first client job**, §3 Stage 3 requires a decision, not a setting: full-transcript
discovery sends 100% of every transcript to Google, and for COMMS and KAAE material paid-tier
Vertex with zero-data-retention is *mandatory, not advisory*. `gemini.Governance` refuses to
upload material marked confidential until that is configured and attributed.

## The gate

```bash
bash scripts/verify.sh          # lint + typecheck + format + tests — this decides DONE
bash scripts/verify.sh --fast   # lint + typecheck only, for editor feedback
```

A task is DONE when this exits 0 **and** its evidence is recorded in `PROGRESS.md`. Nothing
is marked done by judgment.

The gate is deliberately hard to fool, because it is the only thing that decides DONE:

- **Its steps are not configurable.** Setting `TEST_CMD`, `LINT_CMD` or either of the others
  is refused outright (exit 5) before anything runs. A blacklist of ways to run nothing can
  never be complete — `TEST_CMD="echo skipped"` walked past the old one — so the rule is
  inverted. Use `--fast` for a partial check; it cannot print the success line.
- **The exit code is not the evidence.** The report is. The gate deletes it, runs pytest
  under `--junitxml`, and then requires a fresh report with zero failures and at least
  `scripts/test-count.floor` tests collected. That floor ratchets up on its own and never
  down, so a suite that shrinks has to shrink in a diff someone can see.
- **A nested invocation refuses its own test step** — it would otherwise recurse, and once
  did (D-005).

CI runs the same script on a clean runner (`.github/workflows/gate.yml`), fetches the
pinned ffmpeg, and fails if the §4.3 golden render or the §3 Stage 0 tests *skip* rather than
run. Making that job a required status check is a repository setting, and is not done.

## Module map

| Module | Blueprint | What it enforces |
|---|---|---|
| `registry.py` | §7 | The model allowlist, checked against §7 by parsing the blueprint. NC licences hard-rejected. |
| `normalize.py` | §4.1 | Sorani normalization: KLPT for four collisions, a dictionary-backed rule for conjunctive `و`. Failure mode #1 in §0. |
| `transcripts.py` | §4.1, §5 | The raw/norm artifact pair. Kurdish invariants #1 and #3. |
| `alignment.py` | §4.2, §8.1 | Alignment accuracy. Kurdish invariant #5. |
| `metrics.py` | §8.1 | Normalized CER, spacing-free CER, named-entity error, code-switch error. |
| `corpus.py` | §8.1, §4.4 | The labelled set and its coverage grid — 3 dialects × 7 conditions. |
| `asr.py` | §8.1, §3 Stage 1 | Adapter boundary, RTF, VRAM, long-audio failure rate. Hardware is required. |
| `bench.py` | §8.1 | The benchmark run, the comparable report, and the canonical-model decision rule. |
| `diarization.py` | §8.1, §3 Stage 0 | DER and boundary reconciliation against word alignment. |
| `forced_alignment.py` | §4.2, §7 | Viterbi CTC forced alignment — in-house, no library. |
| `sentences.py` | §4.2, §5 | Sentence segmentation on punctuation **plus** pauses; §5 anchors. |
| `escalation.py` | §3 Stage 1 | Validator routing: log-prob quartile + model disagreement. |
| `index.py` | §2 | BM25 + character 3-grams over normalized Sorani. |
| `visual_index.py` | §3 Stage 2 | The visual half: scenes segmented to ~1 fps × 64 frames, cosine retrieval, and the top-50 → rerank → keep-5–10 contract. |
| `video_input.py` | §3 Stages 2, 3B, 5 | Putting a scene window in front of a Qwen3-VL model *at the right time*. Without `video_metadata` the processor stamps a 4.16 s window as 0.1 s long, silently. |
| `boundary.py` | §3 Stage 5 | Boundary fusion. Kurdish invariant #2, at construction and at the render gate. |
| `timelens.py` | §3 Stage 5, §7 | TimeLens2's intervals as evidence, never as cuts — and only the ones that overlap the anchored sentence may move a boundary. |
| `clip.py` | §5 | The clip contract, validated. Rejection is a first-class type. |
| `captions.py` | §4.3 | RTL captions: `shaping=complex`, stack check, font coverage, our own line breaks. |
| `ingest.py` | §3 Stage 0 | 16 kHz mono audio, 1 fps proxy, shot cuts from the **source**, VAD under the ASR ceiling. |
| `path_a.py` | §3 Stage 3 Path A | The Kurdish judge over the **whole** transcript. Refuses to send a subset, and refuses to split one. |
| `path_b.py` | §3 Stage 3 Path B | `VideoChat3-4B` over scenes. Frame budget refused before the call; every SV6D label must cite a time **inside the scene it describes**. |
| `discovery.py` | §3 Stage 3 | The dual-path union. Nothing is dropped, per-path attribution survives, overlap does not chain. |
| `pipeline.py` | §3 | The runner. Joins every stage that can run and names every one that cannot. |
| `smoke.py` | §3 Stages 3–4 | The one live check. Two real calls, announced and confirmed before spending. |
| `credentials.py` | — | The key store. Refuses a git-tracked target, an unverified key, and printing either. |
| `gemini.py` | §3 Stage 4 | `gemini-2.5-pro` behind the judge interface: schema-enforced output, real token counts, §3's ZDR gate. |
| `judge.py` | §3 Stage 4 | The judge contract: shadow never routed, 200K tier ceiling, promotion only on evidence. |
| `delivery.py` | §2 | The SRT sidecar (clip timeline) and the CMX 3600 EDL (source timeline). Refuses NTSC rather than writing timecode that drifts. |
| `render.py` | §3 Stage 6 | Cut, 9:16 crop, `shaping=complex` burn-in, encode. Refuses an unusable encoder rather than substituting. |
| `gate.py` | — | Positive evidence that the test step ran: the gate reads the report, not the exit code. |
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
