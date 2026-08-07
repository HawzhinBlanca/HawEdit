# hawedit2 — Kurdish Video Repurposing System

Central Kurdish / Sorani (`ckb`, Arabic script). Built against `BLUEPRINT.md` v1.1 (frozen).

## What this is today

**There is no end-to-end product yet.** You cannot point this at a video and get clips back.
What exists is most of §3 except the middle — ingest, the transcript artifacts and their
invariants, alignment, segmentation, the text index, boundary fusion, captions, and a render
path that produces a real vertical clip with Kurdish captions burned in — plus the whole §8
measurement apparatus, each piece tested and gated. Every §3 stage has code, and one
command runs them:

```bash
.venv/bin/python -m hawedit2.pipeline VIDEO.mp4 --work-dir work
```

It exits non-zero and prints every stage it could not run, with the blocker named. What is
missing is the three hosted or GPU-bound *models* at the middle — Path A's Kurdish judge, Path
B's `VideoChat3-4B`, and Stage 4's judge call — which is exactly the part that needs
credentials and hardware this machine does not have. Supply a transcript and a verdict in
their place and the runner goes all the way to a rendered vertical clip with burned-in Kurdish
captions:

```bash
.venv/bin/python -m hawedit2.pipeline VIDEO.mp4 --work-dir work \
  --transcript t.json --sentences 0,1 --qc-pass
```

| §3 Stage | State | What is missing |
|---|---|---|
| 0 · Ingest | **runs** | Diarization — Community-1 is a gated repo (`BLOCKED.md` #4). |
| 1 · Speech | contracts only | The ASR models themselves (`BLOCKED.md` #2). Alignment and segmentation are done and tested. |
| 2 · Index | text only | The visual index (Qwen3-VL embeddings) needs weights and a GPU. |
| 3 · Discovery | merge only | Both *producers* — Path A needs Gemini (`BLOCKED.md` #3), Path B needs `VideoChat3-4B` weights (`BLOCKED.md` #2). The union that joins them is built. |
| 4 · Editorial judge | contract only | The call itself — Gemini credentials and the §3 ZDR governance decision (`BLOCKED.md` #3). |
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

```bash
cd hawedit2
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

§3 Stage 0 needs the media stack — PySceneDetect and Silero VAD, and torch because Silero's
interface takes tensors. It is a separate extra because torch is ~2 GB and nothing outside
Stage 0 touches it; without it the Stage 0 tests skip and you lose real-media coverage of
ingest, so install it before trusting a green gate:

```bash
.venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -e '.[dev,media]'
```

## Rendering captions (§4.3)

The golden-render test needs an ffmpeg whose libass has HarfBuzz. Fetch one once per
checkout — the script verifies the RTL stack and refuses a build that cannot shape Arabic:

```bash
bash scripts/fetch-ffmpeg.sh     # ~200 MB, lands in .ffmpeg/ (git-ignored)
```

`verify.sh` discovers it automatically. Without it the golden test skips and you lose
§4.3.6's only real safeguard, so run it.

## Models and weights

Check what this machine has:

```bash
.venv/bin/python -m hawedit2.models      # §7 component readiness
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
`Qwen3-VL-Reranker-2B` — are named in §7 as *checkpoints*, not repository ids. The script
refuses to guess a repo for them; supply one in `models/sources.json`:

```json
{ "omniASR_LLM_7B_v2": "<org>/<repo>" }
```

`models/` and `.ffmpeg/` are git-ignored — weights never enter the repository.

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

CI runs the same script on a clean runner (`.github/workflows/hawedit2.yml`), fetches the
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
| `boundary.py` | §3 Stage 5 | Boundary fusion. Kurdish invariant #2, at construction and at the render gate. |
| `clip.py` | §5 | The clip contract, validated. Rejection is a first-class type. |
| `captions.py` | §4.3 | RTL captions: `shaping=complex`, stack check, font coverage, our own line breaks. |
| `ingest.py` | §3 Stage 0 | 16 kHz mono audio, 1 fps proxy, shot cuts from the **source**, VAD under the ASR ceiling. |
| `discovery.py` | §3 Stage 3 | The dual-path union. Nothing is dropped, per-path attribution survives, overlap does not chain. |
| `pipeline.py` | §3 | The runner. Joins every stage that can run and names every one that cannot. |
| `judge.py` | §3 Stage 4 | The judge contract: shadow never routed, 200K tier ceiling, promotion only on evidence. |
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
- KLPT (Sina Ahmadi) — CC-BY-SA-4.0, attribution required; share-alike attaches if the rule
  tables are ever adapted.
- Noto Naskh Arabic (The Noto Project Authors) — OFL-1.1. The licence must accompany the
  font: `assets/fonts/OFL.txt` ships beside it.

These must appear in shipped product documentation. `registry.attribution_notices()`
generates the list.
