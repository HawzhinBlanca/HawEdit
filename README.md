# hawedit — Kurdish Video Repurposing System

Central Kurdish / Sorani (`ckb`, Arabic script). Built against `BLUEPRINT.md` v1.1 (frozen).

## What this is today

**This is a fully composed, rigorously tested pipeline, not a production-proven product.** The
runner wires canonical OmniASR, real confidence/disagreement routing to the rzgar Sorani
validator, Qwen retrieval/reranking, survivor-only VideoChat3, multimodal
Gemini judging, TimeLens grounding, automatic sentence selection and face-aware reframing. A
production claim still needs external weights, an authorized cloud route and real
human-labelled Sorani/editorial sets; this repository does not fabricate those results.
Stage 1 is runnable through `--omni-asr`; on Windows the runner automatically uses the WSL2
bridge because Meta's fairseq2 native extension has no Windows wheel. The complete LLM + CTC +
validator path has run on both RTX 3090 Ti GPUs; that execution is not a measured Sorani
benchmark until a labelled Sorani corpus exists.
`--omni-asr-adapter <PEFT bundle>` runs a **fine-tuned** decoder — base plus LoRA — and the
adapter's digest is recorded in `AsrProvenance.adapter`, so an adapted transcript is never
reused by, or mistaken for, a stock one. Only the decoder is adapted: CTC-3B and every word
timing are unchanged, per Kurdish invariant #5. An adapter has no §7 row until its licence is
recorded (`BLOCKED.md` #21).

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
| 0 · Ingest | **partial** | Audio/proxy/cuts/VAD run. A strict injected exclusive-diarization seam now preserves base ingest on model refusal and feeds measured turns to Stage 5; the production Community-1 adapter and bytes remain gated (`BLOCKED.md` #4). |
| 1 · Speech | **runs** | `--omni-asr` runs official OmniASR LLM/CTC in parallel, decodes the CTC hypothesis, routes the bottom confidence quartile and material disagreement to rzgar, and CTC-realigns validator corrections. A source-bound 38.56-minute Sorani run published 5,897 timed words while retaining canonical segments for two explicitly rejected corrections; labelled Sorani accuracy remains external. |
| 2 · Index | **wired** | `--visual` extracts each scene once, embeds all windows, retrieves top 50, reranks all hits and retains 5–10. Media with fewer scenes than the survivor count is **refused**, not silently shortened — measured on the 3-scene fixture, `evidence/unlisted-modules.md`. |
| 3 · Discovery | **wired** | Path A and composed Path B union without promoting non-survivor scenes; `--auto-select` anchors complete contiguous sentences. |
| 4 · Editorial judge | **wired** | Requests carry actual source JPEG bytes. Developer API handles non-confidential work; Vertex uses ADC bearer auth and an attributed ZDR gate. Credentials/billing remain external. |
| 5 · Boundary fusion | **wired** | `--timelens` fuses only relevant media-clock intervals; an enabled validated diarizer additionally supplies only the turns containing the selected anchor edges. |
| 6 · Render | **wired, production speaker adapter pending** | `--face-reframe` tracks a dominant continuous face. The runner also has a strict injected active-speaker seam: only validated focus points matching measured overlapping diarization turns may produce `speaker_face` / `SPEAKER_TRACKED`; explicit ambiguity falls back, while invalid or failed association refuses. No production associator, CLI flag, or accuracy claim exists yet (`BLOCKED.md` #1 and #4). |

"Runs" means: on real media, in a test, in the gate. Nothing here is marked done because it
compiles. `PROGRESS.md` carries the per-task evidence and `BLOCKED.md` carries what needs Hawa.

A successful delivery is one directory named for the clip, containing exactly ASS, MP4, SRT,
EDL and editing JSON. The runner builds all five in a hidden sibling directory and publishes
the directory only after the complete set is non-empty and flushed. If render or sidecar work
fails, no partial delivery becomes public; an existing bundle is write-once and wins unchanged.

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

HawEdit supports Python 3.11 and 3.12. Python 3.13 is refused rather than advertised: the pinned
base dependency graph has no complete 3.13 distribution set, and the official OmniASR stack also
caps at 3.12. Setup validates both the selected base interpreter and an existing `.venv`.

> **Windows.** hawapc01 is a Windows box, so every `.venv/bin/python` below is
> `.venv/Scripts/python.exe` there. `setup.sh` and `verify.sh` detect the layout themselves;
> only the commands quoted in this file are written one way. An ffmpeg on `PATH` with libass,
> HarfBuzz and FriBidi is accepted as-is — `winget install Gyan.FFmpeg` (the *full* build)
> supplies one, and `fetch-ffmpeg.sh` verifies it rather than downloading a Linux binary over it.

Canonical OmniASR needs a one-time WSL2 runtime setup on Windows (the official native loader is
Linux/macOS only):

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-wsl-asr.ps1
# When the default LocalAppData volume is unsuitable:
powershell -ExecutionPolicy Bypass -File scripts/setup-wsl-asr.ps1 -RuntimeRoot D:\HawEdit-runtime\wsl-asr
```

That creates a source-fingerprinted runtime below `%LOCALAPPDATA%\HawEdit\wsl-asr`, using Python
3.12, matched Torch/torchaudio 2.8, official OmniASR 0.2.0, fairseq2 0.6 and Qwen-ASR 0.0.6.
Before importing either model stack it downloads and SHA-256-verifies the exact 43.5 GB
LLM-7B/CTC-3B/tokenizer set; every worker hashes those bytes and the installed official card again
before model construction. Rerunning setup revalidates or repairs missing assets instead of
trusting an old `.ready` marker. It then imports both stacks and probes both CUDA GPUs. The host
runner still owns Stage 0, cuts every VAD-bounded WAV
locally, invokes one WSL worker so both models load once, then validates the returned immutable
transcript. An installed wheel exposes the same operation as `hawedit-asr-setup`, including
`--runtime-root D:\HawEdit-runtime\wsl-asr`. Override the distribution with
`-Distribution Ubuntu`. An explicit runtime-root argument takes precedence over
`HAWEDIT_WSL_RUNTIME`; setup, the Stage 1 worker and the live VEX gate share that same absolute,
non-empty host-path contract. Advanced deployments can also set `HAWEDIT_WSL_PYTHON` and
`HAWEDIT_WSL_SOURCE` explicitly.

The WSL receipt also owns the exact checkpoint source/revision/integrity manifests used by the
validator; it does not resolve trust metadata from mutable weight storage. Reprovisioning stages a
new generation without invalidating a prior valid receipt, and the WSL result crosses through a
random no-follow, single-link, descriptor-bound host file. See
`evidence/wsl-runtime-receipt.md`.

The media extra is not optional here even though `pyproject.toml` marks it optional: without
it the Stage 0 tests *skip*, and a skipped test is the quiet green this project is written
against. That is also why setup ends with the gate rather than with an install.

<details><summary>Doing it by hand</summary>

```bash
python3 -m venv .venv
.venv/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu -e '.[dev,media]'
bash scripts/fetch-ffmpeg.sh     # ~142 MB, lands in .ffmpeg/ (git-ignored)
bash scripts/verify.sh
```

`fetch-ffmpeg.sh` addresses an immutable upstream commit, verifies the Git-LFS SHA-256 before
unpacking, then verifies the RTL stack and refuses a build that cannot shape Arabic script.
`verify.sh` discovers the binary automatically; without it §4.3.6's golden render — the only
real safeguard on Kurdish invariant #4 — skips.

</details>

## Reproducible release

Release from a clean, committed checkout with one command:

```bash
hawedit-release --project-root . --gate-run-id GITHUB_ACTIONS_RUN_ID
```

The run id is explicit: the command queries GitHub and requires the official repository's
`.github/workflows/gate.yml` **push** run on `main` for the exact clean `HEAD`. The run, its single
`gate` job and every mandatory install/gate/real-media/evidence step must be completed and
successful. A feature-branch, pull-request, manual, fork, queued, failed, wrong-SHA or incomplete
run is refused; network/API failure is also a refusal. Set `GITHUB_TOKEN` when unauthenticated API
limits are insufficient. Redirects are rejected before following so that token is never forwarded
to another host. The accepted run and job are written into schema-5 provenance.

Only then does the command derive `SOURCE_DATE_EPOCH` from `HEAD`, create a private temporary
builder from the exact Pip and Setuptools wheels hash-locked in
`requirements/release-build.txt`, export the verified Git object twice with replacement refs
disabled, and build each wheel from its own pristine source directory. It requires identical
filenames and SHA-256 digests, checks the archive for the Kurdish font/licence and model
source/revision manifests, and requires one distribution name/version across the archived
`pyproject.toml`, wheel filename and the wheel's single METADATA record, then atomically publishes a
write-once directory under `dist/`. That directory contains the wheel, `SHA256SUMS`,
`release-provenance.json`, and deterministic SPDX 2.3 JSON. The SBOM binds the exact wheel and
bundled Noto font hashes and records every base/optional dependency declared by the wheel; it
marks unbundled requirements unresolved instead of borrowing versions from the build machine.
Provenance records that distribution identity, the measured Python, build frontend/backend and
build-lock digest.
`SHA256SUMS` covers all three metadata/artifact payloads. A dirty checkout, unpinned or drifting
gate mismatch, builder drift, hash mismatch, non-reproducible build, missing runtime file, corrupt
wheel, or existing release directory is refused.

On the default branch, `.github/workflows/release.yml` consumes only a successful official
`gate` **push** run on `main`, checks out that run's exact SHA, invokes the same fail-closed release
verifier in a read-only job, then requires fresh no-checkout Python 3.11 and 3.12 runners to install
the exact wheel, run `pip check`, resolve installed package data and start all fifteen CLIs. Only
after
both pass does it transfer the four explicit payloads to a fresh runner. Only that isolated job has
OIDC/attestation authority; it refuses any extra, nested,
linked, malformed or digest-mismatched entry, independently requires the wheel to identify the
`hawedit` distribution with the same filename/METADATA version, and binds schema-5 provenance to
that identity and the triggering run
before attesting and uploading the same explicit four-file set. The workflow actions are
full-commit pinned and neither job has repository-content write permission. Verify a downloaded
run artifact rather than trusting its filename. If `main` advances before an older gate is
promoted, the workflow refuses that stale run so GitHub's OIDC/SLSA commit claim cannot name newer
source than the bytes being attested.

Public releases add one deliberate promotion input. A strict `vMAJOR.MINOR.PATCH` tag derived from
the wheel version must already point to the exact accepted main SHA. With no tag, the workflow
keeps the attested Actions artifact and publishes nothing. After all acceptance gates pass, create
the exact tag; if the release workflow already completed, rerun that same immutable event with
`gh run rerun RELEASE_RUN_ID`. A fresh no-checkout job re-verifies the four attestations, creates a
draft, downloads and byte-compares its exact assets, and only then publishes. Repository-level
**immutable releases** are enabled, and the workflow refuses a published result unless GitHub
reports it immutable. Operators must never move, delete, or reuse a production tag. Rollback is a
new patch version, never a rewritten release. See `evidence/versioned-immutable-release.md`.

Before creating that tag, produce the owner handoff from the downloaded four-file Actions artifact:

```bash
hawedit-release-approval prepare \
  --project-root . \
  --release-dir PATH/TO/DOWNLOADED/hawedit-release-SHA \
  --output-dir PATH/TO/release-owner-packet \
  --release-run-id RELEASE_WORKFLOW_RUN_ID
```

The command independently rechecks the clean protected-main SHA, schema-5 provenance, exact bundle
digests, all five hosted release jobs and the strict `gh attestation verify` policy. It emits a
write-once packet whose owner, action, timestamp, rationale and four risk acknowledgements are all
unset. The owner reviews and fills a separate copy, signs its canonical bytes with OpenSSH namespace
`hawedit-release-approval`, and passes that copy, signature and an allowed-signers file to
`hawedit-release-approval verify`. Verification reopens every artifact and packet byte. A valid
approval returns the exact fetch/check/tag/push commands as JSON; a rejection returns no commands.
Neither operation creates a tag, pushes Git, publishes a release, or chooses for the owner.

Verify either the Actions artifact or downloaded GitHub Release assets with the exact signer
policy:

```bash
cd PATH/TO/DOWNLOADED/hawedit-release-SHA
sha256sum --check SHA256SUMS
EXPECTED_SHA=THE_EXACT_40_HEX_SHA_IN_THE_ARTIFACT_NAME
for file in *; do
  gh attestation verify "$file" \
    --repo HawzhinBlanca/HawEdit \
    --signer-workflow HawzhinBlanca/HawEdit/.github/workflows/release.yml \
    --source-ref refs/heads/main \
    --source-digest "$EXPECTED_SHA" \
    --signer-digest "$EXPECTED_SHA" \
    --deny-self-hosted-runners
done
```

This proves repeatable source-to-wheel bytes and defines a keyless publisher-identity check. The
hosted workflow still needs one post-merge protected-`main` run before the Python 3.12 prerequisite,
installed-wheel matrix, attestation path, and versioned immutable publication have live evidence;
a feature branch cannot supply it. The policy and automation exist, but no production tag or
release is created before that acceptance. Separately, OmniASR's
package-managed assets and the project-managed Hugging Face snapshots have application-owned byte
identities and pre-load verification; those runtime proofs are not implied by a green wheel. See
`evidence/release-attestation.md` and `evidence/versioned-immutable-release.md`.

## Models and weights

Check what this machine has:

```bash
.venv/bin/python -m hawedit.models      # §7 component readiness
```

Fetch what it does not:

```bash
# Source checkout; use .model-fetch/Scripts/python.exe on Windows Git Bash.
python -m venv .model-fetch
bash scripts/install-host.sh .model-fetch/bin/python models
PY=.model-fetch/bin/python bash scripts/fetch-models.sh
```

The wheel-installed fetcher is driven by the §7 registry, so it cannot download a model the blueprint
excludes and refuses a NonCommercial licence before any bytes move. Needs
`huggingface.co` reachable, `HF_TOKEN` for the gated Community-1 repo, and ~50 GB free.
Four wheel-packaged `models` locks cover Linux/Windows on Python 3.11/3.12 with one exact wheel
hash per dependency. The dedicated environment above uses the matching lock; the command then
audits every locked transitive before importing `huggingface-hub==0.36.2`. It never installs or
upgrades packages from inside an operator command. The checkout shell file is only a launcher for
the wheel's Python transaction.

For a wheel-only install, install the local wheel without dependencies, ask that wheel for its
target lock, then install/audit the lock explicitly (set `PY=.model-fetch/Scripts/python.exe` on
Windows Git Bash):

```bash
python -m venv .model-fetch
PY=.model-fetch/bin/python
"$PY" -m pip install --no-index --no-deps /path/to/hawedit-0.1.0-py3-none-any.whl
LOCK="$("$PY" -I -m hawedit.environment --show-lock models)"
"$PY" -m pip install --require-hashes --only-binary=:all: -r "$LOCK"
"$PY" -m pip check
"$PY" -I -m hawedit.environment --extra models --lock "$LOCK"
"$PY" -m hawedit.model_fetch             # use --status for readiness only
```
It plans from verified status rather than directory existence, resumes each pinned revision in a
private sibling, exact-verifies it, and atomically publishes under a writer lock. Existing resume
trees are recursively checked for owner, private mode, regular single-link members and
reparse/symlink objects **before** the Hub client can write through them. Fresh staging is created
under an unpredictable name and atomically published as the revision-specific resume tree before
transfer. POSIX uses mode 0700; Windows creates a protected DACL granting only the current user,
SYSTEM and Administrators, and validates every inherited member ACL. A planted link or
`Everyone:F` volume cannot turn a failed download into an external-file write. The stable private
resume name survives Ctrl-C and hard process death without leaking an undiscoverable partial tree.
An empty, partial
or corrupt final directory is preserved and refused—move/quarantine it explicitly before retrying.
Any target failure makes the command exit nonzero after the full status report. Use only the same
override the runtime reads:

```bash
HAWEDIT_MODELS_DIR=/absolute/model/root "$PY" -m hawedit.model_fetch
```

The two Qwen checkpoint names are resolved in tracked `models/sources.json`; the fetcher never
guesses a repository id. OmniASR is deliberately absent from that file: the pinned official
`omnilingual-asr` package ships the `_v2` model cards and owns their Meta transport URLs, while
HawEdit's packaged `omni_assets.py` owns exact URL/cache-key/size/SHA-256 identities, freezes card
overrides, verifies the effective cards and holds the verified descriptors through both real model
loads. Empty cache paths and altered bytes are refused before any load. Downloading
similarly named Hub repositories into `models/` would provision weights the runtime never reads.
Project-managed Qwen/VideoChat/TimeLens and Qwen-ASR loads hold a shared checkpoint binding from
exact verification through config/recipe parsing and every `from_pretrained` reopen; constructors
cannot cache unverified prompts, pooling rules or score-token ids. A custom model root stores only
checkpoint bytes—trusted source/revision/integrity metadata remains checkout/installed—and final
publication uses native no-replace rename. The Windows producer also keeps a host lease across the
complete WSL validator call because DrvFS does not make Windows and Linux advisory locks
interoperate. See
`evidence/checkpoint-provisioning.md` and `evidence/checkpoint-load-binding.md`.

Weights themselves never enter the repository: `models/*` and `.ffmpeg/` are git-ignored.

On Linux, install `.[asr]` for the official OmniASR + validator runtime. Keep it in a separate
environment from `.[gpu]`: fairseq2n requires Torch 2.8 while the visual checkpoint stack is
verified on Torch 2.13, so resolving both extras together is intentionally unsupported. On
Windows that isolation is automatic through WSL2; run `scripts/setup-wsl-asr.ps1`. Model loading
is lazy, so a missing package or checkpoint is reported without making basic ingest unusable.
Provisioning uses reviewed hashes for 137 runtime requirements plus four build requirements and
the readiness receipt rechecks the exact 140-distribution union. KenLM and Sox remain named source
builds: source archives are hashed, but compiler, system headers and produced native bytes are not
yet attested. `security/wsl-asr-vex.json` is a 30-day policy bound to those lock digests, the full
receipt and the three OmniASR assets. It does not call the runtime vulnerability-free: five Torch
families remain affected and CVE-2026-24747 is affected-but-mitigated. The policy parser ships in
the wheel. Protected-main run `31874928483` executed the live, hash-locked
`pip-audit==2.10.1` boundary on the dual-GPU WSL runner and uploaded its accepted evidence for
exact source `ef40ff7c`; the 30-day policy still expires on 2026-09-08 and must be renewed rather
than treated as a permanent clean bill of health.
The full canonical pair and rzgar routing have run on hawapc01, including through the real CLI.
The committed media fixture is synthetic Kurmanji, so this is execution evidence—not Sorani
accuracy evidence. See `evidence/m1-4-stage1-validator.md` and
`evidence/current-main-acceptance-2026-08-15.md`.

## GPU (§3 Stages 2, 3 Path B, 5)

Stage 0 runs on CPU by design (§6), so the ordinary setup remains CPU-only. The measured visual
host is narrower and fail-closed: Windows x86-64, CPython 3.11, two 24 GiB RTX 3090 Ti cards and
CUDA 13.0. Create a dedicated environment and install the exact 46-wheel graph rather than asking
pip to resolve a live CUDA stack:

```bash
PY311=/absolute/path/to/cpython-3.11/python.exe
"$PY311" -m venv .gpu
bash scripts/install-host.sh .gpu/Scripts/python.exe gpu
```

The installer uses `requirements/host-gpu-windows-py311.txt` with `--require-hashes` and
`--only-binary`, audits the exact inventory, runs `pip check`, imports the pinned Torch,
Torchvision and Torchaudio builds, and performs bfloat16 work on both cards. An installed wheel
contains the same authenticated lock; resolve it with `python -I -m hawedit.environment
--show-lock gpu`, install it in hash mode, then run `python -I -m hawedit.gpu_runtime`.

This qualifies dependency and hardware identity, not the application quality ceiling:
VideoChat3-4B still reads at most eight frames on one card while the frozen blueprint describes a
64-frame unit. See `evidence/gpu-dependency-lock.md`, `evidence/gpu-stack.md`, and
`BLOCKED.md` #17.

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
.venv/bin/python -m hawedit.smoke --video PATH_TO_A_VIDEO_OF_THE_SAMPLE  # ~$0.003
```

It runs §3 Stage 3 Path A over a built-in Sorani sample and §3 Stage 4 on the top candidate,
then prints the Kurdish title it got back. It checks what offline tests cannot: that
`gemini-2.5-pro` is enabled on your key's project, that the structured-output schema survives a
real response, and that the model actually answers in Kurdish.

`--video` is required, and no matching video ships in this repository. The built-in sample spans
13 seconds; the 4.162-second Kurdish fixture is a different recording and cannot supply honest
pixels for later candidate spans. Until a matching recording exists (`BLOCKED.md` #19), the live
check is not runnable as shipped. Missing or nonexistent video now returns exit 2 before the
confirmation prompt and before either billed Path A call.

**Before the first client job**, §3 Stage 3 requires a decision, not a setting: full-transcript
discovery sends 100% of every transcript to Google, and for COMMS and KAAE material paid-tier
Vertex with zero-data-retention is *mandatory, not advisory*. `--vertex-project` routes Path A
and Stage 4 through Vertex REST with ADC bearer credentials. Confidential uploads are still
refused unless ZDR is explicitly confirmed and attributed; code cannot verify a customer's
contractual retention configuration by itself.

Stage 4 samples up to 20 JPEG keyframes from the exact candidate span and sends those same image
parts to `countTokens` and `generateContent`. Textual SV6D remains supporting evidence; it no
longer masquerades as source pixels.

`hawedit-vertex-acceptance` is the confidential-route acceptance coordinator. Its preparation
phase performs no cloud request: it binds one authorised video, normalized transcript, candidate
slice, retained ZDR-policy digest, approved project/location, ADC identity, billing account and
owner token/cost ceilings, then emits an unsigned approval template. Execution requires the exact
OpenSSH-signed approval, revalidates all private bytes, refreshes ADC, mechanically checks the ADC
project plus live Cloud Billing and Vertex API state, removes its private extracted pixels, and
retains a durable no-replay receipt before the one non-retried paid generation attempt. The public
result contains hashes and numeric operational facts, never access tokens, billing-account names,
full transcript text, raw frame bytes, generated title/description/hashtags or retained policy
text. This code does not prove a customer's contractual ZDR assertion: a responsible human still
has to sign it, and no live Vertex acceptance has been run in this repository.

`hawedit-owner-decisions` prepares the six remaining owner choices (#9, #13, #14, #15, #18 and
#21) without silently choosing for Hawa. It authenticates the frozen blueprint, each exact blocker
section and the reviewed evidence behind each recommendation, then publishes deterministic pages,
a machine-readable manifest and a self-contained JSON template whose owner, timestamp, rationale
and selected option remain unset. Publication is write-once; changed or linked authority files are
refused.

## Benchmarks

`bench.py` remains the §8.1 ASR harness: normalized/spacing-free CER, named entities,
code-switching, alignment, RTF, VRAM and per-dialect coverage. A production run now requires a
content-bound acceptance manifest plus a human approval signed with OpenSSH's detached-signature
format. The guard re-hashes each audio item before and after every model measurement, and the
benchmark report records the manifest, approval, signature and allowed-signers SHA-256 identities.
Synthetic, interim, changed, linked, duplicate, path-escaping or declared training audio is refused.
`hawedit-editorial-bench` validates and scores a blind human regression manifest, requiring at
least 20 items, at least five per dialect, two named reviewers per item, exact candidate/span
equality and source media on disk. The separate `hawedit.editorial_acceptance` coordinator prepares
the larger §8.2 study: it deterministically selects 200–500 candidates, conceals incumbent/shadow
identity, freezes a dialect-balanced training/holdout split before labelling, and emits unsigned
review/adjudication templates. Preparation and evaluation require probeable video whose measured
duration matches the inventory; evaluation reopens the exact inventory and recomputes sampling,
blinding, split and media identities. Detached OpenSSH evidence must come from a coordinator, two
distinct reviewers and a separate adjudicator using four distinct signing keys. Training and
holdout labels/reports are published separately. Preparing a packet is not human acceptance.

```bash
python -m hawedit.corpus_acceptance prepare sorani-corpus.json \
  --audio-root /secure/audio --output-dir /secure/asr-acceptance \
  --dataset-owner "<owner>" --authorized-by "<signer identity>" \
  --licence "<licence>" --consent-basis "<recorded consent basis>" \
  --permitted-use "HawEdit internal model evaluation and acceptance" \
  --redistribution-forbidden --exclude-hashes /secure/training-audio.sha256
# Review and fill approval.template.json, then sign it exactly as INSTRUCTIONS.txt specifies.
hawedit-asr-bench sorani-corpus.json --audio-root /secure/audio \
  --acceptance-manifest /secure/asr-acceptance/corpus-acceptance.json \
  --approval /secure/approval.json --signature /secure/approval.json.sig \
  --allowed-signers /secure/allowed_signers --host hawapc01 \
  --accelerator "2x RTX 3090 Ti" --output asr-report.json
hawedit-editorial-bench editorial.json --media-root /secure/media --output report.json
python -m hawedit.editorial_acceptance prepare editorial-inventory.json \
  --media-root /secure/media --output-dir /secure/editorial-study --sample-size 200
# Complete and sign the generated coordinator/reviewer/adjudication documents as INSTRUCTIONS.txt
# specifies, then run `python -m hawedit.editorial_acceptance evaluate --help` for the exact inputs.
python -m hawedit.diarization_acceptance prepare diarization-reference.json \
  --media-root /secure/multispeaker-media --output-dir /secure/diarization-study
# Run pinned Community-1 and the non-routable 3.1 control after accepting both gated repositories;
# fill and sign the generated documents exactly as INSTRUCTIONS.txt specifies, then run
# `python -m hawedit.diarization_acceptance evaluate --help` for the bound evaluation inputs.
hawedit-owner-decisions prepare --project-root . \
  --output-dir /secure/hawedit-owner-decisions
# Read all six pages; filling the template is an owner decision, not automated acceptance.
hawedit-vertex-acceptance prepare --source-manifest /secure/vertex-source.json \
  --private-root /secure/vertex-client-inputs --output-dir /secure/vertex-approval
# Fill/sign the generated approval exactly as INSTRUCTIONS.txt specifies. `run --help` lists the
# bound execution inputs; it reserves one paid attempt and therefore is never run by setup or CI.
```

The private signing key, allowed-signers trust file, client audio, signed approval and training
hash inventory stay outside Git. The preparation command emits an unsigned template; it is not
approval and cannot make the blocked benchmark complete by itself.

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
Remote actions in the gate workflow are pinned to full commits; moving major-version tags are
rejected by the test suite (`evidence/ci-actions.md`).

The gate is deliberately hard to fool, because it is the only thing that decides DONE:

- **The interpreter is part of the evidence.** Only the path-identical Python inside this
  checkout's `.venv` is accepted; an arbitrary `PY` executable is refused before it runs. An
  isolated preflight binds the editable distribution to this checkout and checks the supported
  Python/project versions plus exact active requirements. A printed token is diagnostic, never an
  authentication mechanism (`evidence/environment-identity.md`).
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

CI runs the same script on a clean runner (`.github/workflows/gate.yml`), fetches the FFmpeg
archive **at a pinned commit and verifies its SHA-256 before unzipping it** (D-121 — this line once
said "pinned" while the URL was a branch path), and fails if the §4.3 golden render or §3 Stage 0
tests *skip* rather than run. `gate` is a strict required status check on protected `main` and
is therefore a required status check on `main`;
force-pushes and deletions are disabled (`BLOCKED.md` #7 records the live setting).

## Module map

| Module | Blueprint | What it enforces |
|---|---|---|
| `registry.py` | §7 | The model allowlist, checked against §7 by parsing the blueprint. NC licences hard-rejected. |
| `normalize.py` | §4.1 | Sorani normalization: KLPT for four collisions, a dictionary-backed rule for conjunctive `و`. Failure mode #1 in §0. |
| `transcripts.py` | §4.1, §5 | The raw/norm artifact pair, exact source-media SHA-256 binding, and Kurdish invariants #1 and #3. |
| `alignment.py` | §4.2, §8.1 | Alignment accuracy. Kurdish invariant #5. |
| `metrics.py` | §8.1 | Normalized CER, spacing-free CER, named-entity error, code-switch error. |
| `corpus.py` | §8.1, §4.4 | The labelled set and its coverage grid — 3 dialects × 7 conditions. |
| `corpus_acceptance.py` | §8.1 | Canonical corpus/audio/reference hashes, rights and exclusion binding, detached human approval verification, and per-measurement byte guards for real AC-7 evidence. |
| `asr.py` | §8.1, §3 Stage 1 | Official LLM+CTC/Viterbi producer, decoded CTC disagreement, rzgar correction routing, RTF, VRAM and failure rate. Hardware is required. |
| `asr_worker.py` | §3 Stage 1, §6 | Strict create-once Windows→WSL2 worker protocol for the official Linux runtime. |
| `wsl_setup.py` | §3 Stage 1, §6 | Wheel-safe, source-fingerprinted WSL2 runtime provisioning and CUDA probe. |
| `wsl_asr_locks.py` | §3 Stage 1, §6 | Hash-locked PyPI inputs and exact installed name/version identity for the isolated Linux/Python 3.12 ASR generation; KenLM/Sox remain explicitly disclosed native source builds, not binary reproducibility proof. |
| `wsl_audit_locks.py` | §6, §7 | Complete wheel hashes and installed identity for the isolated pip-audit 2.10.1 scanner used by the WSL ASR security gate. |
| `wsl_vex_gate.py` | §6, §7 | Live, source-bound WSL receipt and asset verification, hash-locked OSV scan, VEX evaluation, and write-once evidence publication. |
| `omni_assets.py` | §3 Stage 1, §7 | Exact OmniASR model/tokenizer/card identities, atomic verified provisioning, frozen card sources and pre-load byte enforcement. |
| `bench.py` | §8.1 | The benchmark run, the comparable report, and the canonical-model decision rule. |
| `editorial_bench.py` | §8.2 | A real-media, two-reviewer, dialect-balanced editorial regression manifest and judge-promotion report. |
| `editorial_acceptance.py` | §8.2 | Deterministic 200–500-item blinded A/B preparation, predeclared dialect-balanced holdout, independent signed review/adjudication import, content revalidation, and separate training/holdout evidence. |
| `diarization.py` | §8.1, §3 Stages 0 and 5 | Production-exclusive DER, benchmark-only overlap-aware DER for the 3.1 control, boundary reconciliation, and anchor-edge-to-turn selection without nearest-turn invention. |
| `diarization_acceptance.py` | §8.1, §3 Stages 0 and 6 | Content-bound real multi-speaker references and media, exact Community-1/control receipts, signed rights/access/crop approval, raw DER/boundary/association/crop metrics, explicit fallbacks, attribution, and atomic write-once reports. |
| `vertex_acceptance.py` | §3 Stages 3 and 4 | Transport-free confidential packet preparation, exact private-content and signed ZDR/spend binding, live ADC/billing/API preflight, one counted non-retried generation reservation, private-frame cleanup, and redacted write-once evidence. |
| `decision_packets.py` | §§3, 4.1, 4.2, 5, 7, 8.2 | Content-bound, deterministic, write-once recommendation packets for blockers #9/#13/#14/#15/#18/#21; every human decision field stays explicitly unset. |
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
| `captions.py` | §4.3 | RTL captions: `shaping=complex`, stack check, ASS-family-to-font coverage binding, our own line breaks. |
| `ffmpeg_setup.py` | §4.3, §7 | Installed-wheel FFmpeg verification and Linux per-user provisioning through the authenticated pinned transaction; Windows/macOS return package-manager remediation. |
| `ingest.py` | §3 Stage 0 | 16 kHz mono audio, 1 fps proxy, shot cuts from the **source**, VAD under the ASR ceiling. |
| `path_a.py` | §3 Stage 3 Path A | The Kurdish judge over the **whole** transcript. Refuses to send a subset, and refuses to split one. |
| `path_b.py` | §3 Stage 3 Path B | `VideoChat3-4B` over scenes. Inputs are packed into ≤256-frame calls; every SV6D label must cite a time **inside the scene it describes**. |
| `video_reader.py` | §3 Stage 3 Path B | `MCG-NJU/VideoChat3-4B` and the SV6D prompt. The model is shown one scene starting at zero, so every time it cites is moved onto the media's clock here — the invariant alone accepts an unshifted one whenever it happens to land in range. |
| `video_grounding.py` | §3 Stage 5 | `MCG-NJU/TimeLens2-4B` grounding a query in one scene. It answers in seconds from the window's start; `VisualEvidenceInterval.from_window` moves that onto the media's clock, because an unshifted span can overlap the anchored sentence and extend the clip on footage from elsewhere. |
| `visual_pipeline.py` | §3 Stages 2–3B | Extract once → Qwen embed → top-50 retrieve → rerank every hit → bounded survivors → VideoChat3 only on those survivors, with exact ID/score provenance. |
| `keyframes.py` | §3 Stage 4 | Real source-timestamped JPEG extraction for the multimodal judge, capped at 20 images and 5 MiB per bounded read. |
| `reframe.py` | §3 Stage 6 | Dominant-face continuity plus strict speaker-labelled focus evidence reconciled to exclusive diarization turns; the production active-speaker associator remains external. |
| `discovery.py` | §3 Stage 3 | The dual-path union. Nothing is dropped, per-path attribution survives, overlap does not chain. |
| `pipeline.py` | §3 | The runner. Joins every stage that can run and names every one that cannot. |
| `events.py` | §3 | What a run says about itself *before* it returns: one stage-transition event per start and per end, to a sink that defaults to discarding. A skip carries the same reason the report will carry, so the timeline cannot go green over a stage that refused. Owns the JSONL ledger format both ways — `JsonlEventSink` writes it, `read_events` reads it back — so reading a run's timeline needs no durable-execution engine imported. |
| `durable.py` | — | The `hawedit-durable` CLI entry point. Parses and validates argv — including `-h`/`--help` — before importing anything that needs the `agentic` extra, so `--help` is a pure no-op regardless of whether `dbos` is installed. |
| `durable_workflow.py` | Phase 1 | The coarse DBOS workflow around `_build_and_run`: one `@DBOS.step()`. All four of Phase 1's acceptance properties verified against the installed `dbos` source rather than assumed — crash-recovered on the next `DBOS.launch()` (a real killed subprocess), deduplicated by workflow ID, cancellation observed to fail the awaiter rather than interrupt the running call, and the JSONL event ledger readable mid-run for reconnect. Also writes `report.json`, the on-disk mirror of the step's return value `agent.py` reads. |
| `agent.py` | Phase 2 | The read-only creative-director agent: `inspect_run`, `explain_run_state`, `compare_candidates`, `run_timeline`, `run_quality_checks`, one Pydantic AI tool each, reading only `report.json`/`events.jsonl`. `run_quality_checks` (D-A18) itemizes the same four gates `Clip.assert_renderable()` checks — boundary invariant reused from `boundary.py`, QC, editorial, output — rather than stopping at the first failure; a test proves `all_passed` never disagrees with `assert_renderable()` itself. Loads the generated `AppManifest` into the system prompt, with a test asserting the manifest's tool list equals the agent's real one. `work_dir` is bound at construction via `Deps`, never a model-suppliable tool argument — proven read-only by an AST scan of the module's own source, not a docstring claim. Model-agnostic: chooses no provider, no default model. |
| `proposals.py` | Phase 3 | The `hawedit-revise` CLI plus Phase 3's two mutating capabilities: propose a boundary or caption revision, validate each against the real render-gate check (`assert_boundary_invariant`/`assert_captions_within_clip` — Kurdish invariants #2/#4), commit only after an attributed, explicit "yes" and a stated `reason_code` on a real terminal, then render a real second deliverable set (MP4/ASS/SRT/EDL) from `PipelineRun.selected_sentences` — the original render and delivery untouched. `revisions/<id>.json` records carry `"kind"` so each render function refuses the other's record. Every commit outcome, including a decline or refusal, is recorded to `decisions.jsonl` via `learning.py`; `replay_decision_deltas` re-checks every approved one against today's real validator. No `pydantic_ai` import at module level, so `--help` and every function here need none of it. |
| `editor_agent.py` | Phase 3 | The agent wrapper around `proposals.py`: registers `propose_boundary_revision` and `propose_caption_revision` (caption style typed `Literal["line", "word_highlight"]`, a closed enum, never a free string). Neither `commit_boundary_revision` nor `commit_caption_revision` appears anywhere in this module's source, checked by an AST scan — the model can check whether a revision would be legal and nothing else. |
| `policy.py` | Phase 0 | The Policy Gate as a declaration: every tool any agent may register, with its approval class, plus the architecture record's never-expose list. `tests/test_policy.py` discovers every `build_*_agent` in the package and fails the build on an undeclared tool — so a capability cannot ship without someone deciding who must approve it. Blocked-capability names are refused even when declared. |
| `learning.py` | Phase 4 | The decision-delta ledger: `DecisionDelta` (`ReasonCode` + `DecisionOutcome`, validated so a human-reached decision must carry both and a refused one must carry neither), an append-only JSONL sink/reader (`events.py`'s own shape, a separate file since `RunEvent`'s schema cannot carry this). `proposals.py` is the only writer today. |
| `promotion.py` | Phase 4 | The shadow-verdict ledger (per run, `shadow_verdicts.jsonl`) and the judge promotion/rollback gate — the missing second half of `judge.py`'s already-built, never-wired `ShadowVerdict`/`decide_judge`. `promote_judge` turns a winning `JudgeDecision` into a recorded version only after a named approver and an explicit "yes"; `rollback_judge` restores the immediately preceding one. The first system-wide (cross-run) state in this branch — `.hawedit/judge_promotions.jsonl`, the same installation-level precedent `.dbos/` already set. Read-only integration: `gemini.py` does not consult `current_judge()` yet, named as a scope boundary rather than left implicit. |
| `scale.py` | Phase 5 | "Scale only when triggered": the architecture record's five DBOS→Temporal conditions, quoted verbatim and checked against the record's own text so the two cannot silently drift apart. `evaluate_scale_triggers` refuses a missing answer for any condition — none of the five are measurable from this codebase's own state, so nothing here assumes one is "no". `describe_migration_path()` is prose, not a `.md` file, specifically so `tests/test_scale.py` can bind every module and function it names to the real source and catch the day either goes stale. |
| `developer_report.py` | Phase 3 | `export_developer_report`'s data model: `build_developer_report` composes and validates, never writing; `write_developer_report` is the only write and is not a tool any agent registers. Sanitized against Kurdish-script content in every free-text field (`captions.py`'s own `KURDISH_REQUIRED_GLYPHS`, reused) — a defect report is prose about the application, not a place for verbatim transcript text. |
| `diagnostics_agent.py` | Phase 3 | The agent wrapper around `developer_report.py`: registers only `export_developer_report_tool`. `write_developer_report` does not appear anywhere in this module's source, checked by an AST scan — the model can compose a report and nothing else. |
| `workflow_control.py` | Phase 3 | `start_pipeline` (D-A19), `cancel_run`/`resume_run` (D-A20/D-A21): three propose/commit pairs for a durable pipeline's whole lifecycle. `dbos_run_id_for(work_dir)` is a pure, deterministic DBOS workflow ID so `commit_start_pipeline` and `propose_cancel_run`/`propose_resume_run` always agree without a discovery file. Cancelling marks the workflow `CANCELLED` and fails its awaiter — measured not to stop a step already executing — and resuming re-enqueues a `CANCELLED`/`MAX_RECOVERY_ATTEMPTS_EXCEEDED` workflow, replaying an already-checkpointed step result instead of recomputing it. Every outcome records a `DecisionDelta` (`kind="start_pipeline"`/`"cancel_run"`/`"resume_run"`). The `hawedit-workflow {start,cancel,resume}` CLI. |
| `workflow_agent.py` | Phase 3 | The agent wrapper around `workflow_control.py`: registers `propose_start_pipeline_tool`, `propose_cancel_run_tool`, `propose_resume_run_tool` — never a `commit_*` function, checked by an AST scan. Found and fixed a real Policy Gate false positive along the way: `_FORBIDDEN_NAME_FRAGMENTS`'s bare `"pip"` matched "pipeline" — narrowed to `"pip_"` (`policy.py`) rather than renaming this tool away from the architecture record's own vocabulary. |
| `explorer_agent.py` | Phase 3 | The fourth agent (D-A22/D-A24): `inspect_artifact_tool`, `compare_versions_tool`, `list_candidates_tool`, `preview_candidate_tool`. Split from `agent.py` for a tested reason, not a stylistic one — `build_agent`'s whole toolset is pinned to *zero* parameters by `test_prompt_injection.py`, and all four of these inherently need a caller-supplied identifier or filter. Holds its own weaker, explicitly-stated guarantee instead: every parameter is an integer, a closed enum, or one of three named lookup identifiers. None of the four raises for an identifier that resolves to nothing — they report `found=False`. |
| `render_agent.py` | Phase 3 | The fifth agent (D-A25): `propose_render_tool` only. Split from `editor_agent.py` for the same kind of reason — that module's parameters are pinned to integer-or-closed-enum, and `revision_id` cannot honestly be either. `commit_render`, `render_boundary_revision` and `render_caption_revision` are all absent from this module's source, checked by an AST scan: the agent that is *about* rendering is the one whose inability to render needs a structural proof, not a promise in a prompt. |
| `smoke.py` | §3 Stages 3–4 | The one live check. Two real calls, announced and confirmed before spending. |
| `credentials.py` | — | The key store. Refuses a git-tracked target, an unverified key, and printing either. |
| `http_transport.py` | — | Shared authenticated HTTP boundary: redirects are refused before API-key or bearer headers can reach another origin. |
| `gemini.py` | §3 Stage 4 | `gemini-2.5-pro` behind the judge interface: schema-enforced output, real token counts, and fail-closed confidential routing. |
| `judge.py` | §3 Stage 4 | The judge contract: shadow never routed, 200K tier ceiling, promotion only on evidence. |
| `delivery.py` | §2 | The SRT sidecar (clip timeline) shares §4.3.5's word-aligned RTL breaks with ASS; the CMX 3600 EDL (source timeline) writes SMPTE drop-frame for NTSC 30000/1001 and refuses other unsupported fractional rates. |
| `artifact_bundle.py` | §2 | Private staging and atomic, write-once publication of the exact ASS/MP4/SRT/EDL/JSON delivery directory. |
| `atomic_fs.py` | §2, §7 | Native cross-platform no-replace directory publication shared by delivery bundles and checkpoint provisioning; unsupported POSIX platforms fail closed. |
| `render.py` | §3 Stage 6 | Cut, 9:16 crop, `shaping=complex` burn-in, encode. Refuses an unusable encoder rather than substituting. |
| `environment.py` | — | Binds the canonical `.venv`, editable distribution root, supported Python/project versions and active exact requirements to this checkout before the gate runs. |
| `host_lock_hashes.py` | — | Generated source-bound SHA-256 identities for every supported host dependency lock. |
| `gpu_runtime.py` | §6 | Exact dual-3090-Ti CUDA/Torch identity plus real bfloat16 compute on both cards; refuses version, visibility, topology, capability or memory drift. |
| `gate.py` | — | Positive evidence that the test step ran: the gate reads the report, not the exit code. |
| `release.py` | — | Exact-SHA official main-gate proof, clean-HEAD double-build wheel reproducibility, runtime-data validation and atomic checksummed provenance. |
| `release_approval.py` | — | Independent four-payload, hosted-run and attestation verification; deterministic unset owner packet; detached OpenSSH decision verification; never tags, pushes or publishes. |
| `cli.py` | — | Shared entry-point rules: `use_utf8_streams` pins stdout/stderr to UTF-8; `machine_readable_stdout` reserves stdout for one parseable document; `program_name` makes help name the installed launcher or pasteable `python -m` command. |
| `collisions.py` | §4.1 | The collision table itself, and the incidence measurement over a real lexicon. |
| `corpus_import.py` | §8.1 | Public-corpus import that refuses to invent dialect, condition or duration. |
| `models.py` | §7 | Which §7 components this machine actually has, plus trusted source/revision/byte identities and reader/writer checkpoint binding. |
| `model_fetch.py` | §7 | Installed-wheel checkpoint planning, private resume validation, exact byte verification and atomic no-replace publication. |
| `windows_security.py` | §7 | Native protected-DACL creation and inspection for Windows checkpoint staging. |
| `vex.py` | §6/§7 | Identity-bound WSL-ASR vulnerability disposition gate over pip-audit output and runtime receipts. |
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
with a stated mitigation. Until D-168 the comparison was on the *subjects* only, so a bullet
could state a licence its subject does not have; the licence each notice carries, and its
share-alike claim, are now checked against the whole bullet, and each registry licence against
BLUEPRINT §7's own Licence column. Models come from §7's registry; the font comes from
`registry.SHIPPED_ASSETS`, because a font is not a model and §7's table is not ours to widen.
