# 27 GB of weights, and nothing recorded which revision produced them

> Measured 2026-08-09 on hawapc01 against `cb5194e`, live against huggingface.co.

> Current implementation amendment (D-121): the shell transaction described below was replaced
> by the wheel-installed `hawedit.model_fetch` transaction. Historical measurements and mutation
> results remain the evidence for why commit pins were introduced; current transaction evidence is
> in `evidence/checkpoint-provisioning.md`.

`fetch-models.sh` called `snapshot_download(repo_id=source, local_dir=dest)` — no `revision=`.
That resolves whatever the branch head points at on the day it runs, so two machines can hold
different weights under one §7 name and nothing reports it.

This is the project's own rule one level down. *"A number carries the hardware and adapter that
produced it"* — and the adapter's **weights** were unidentified.

## The measurement that made it a finding rather than a worry

Every §7 repository resolves to a head, live:

```
Qwen/Qwen3-VL-Embedding-2B             9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda  2026-04-16
Qwen/Qwen3-VL-Reranker-2B              4bd860ac4f15ad1897a214615cccc700f8f71818  2026-04-16
MCG-NJU/VideoChat3-4B                  37fa901ec5913f84bc31108ebc1e60ad1903634c  2026-07-22
MCG-NJU/TimeLens2-4B                   ddbb6cb944f13ce21e59e85da23c5f356107260e  2026-07-21
rzgar/qwen3-asr-sorani-kurdish-ckb-v1  d71490a623113b4b069ac07cfc85b409389dde4c  2026-06-12
```

And nothing in this checkout knew any of them:

```
IS THE REVISION RECORDED ANYWHERE ON DISK?
  MCG-NJU__TimeLens2-4B                   markers=NONE
  MCG-NJU__VideoChat3-4B                  markers=NONE
  Qwen3-VL-Embedding-2B                   markers=NONE
  Qwen3-VL-Reranker-2B                    markers=NONE
  rzgar__qwen3-asr-sorani-kurdish-ckb-v1  markers=NONE

tracked files mentioning a revision: NONE
```

`snapshot_download(local_dir=…)` writes a plain directory and keeps no commit marker, so the
provenance of the weights behind `evidence/m5-2-embedder.md`, `m5-2-reranker.md`,
`m5-4-path-b.md` and `m6-3-grounding.md` was unrecoverable from the machine that produced them.

## Whether the pins are a guess — they are not

The hard rule forbids guessing a repo id, a licence or a threshold, and the same spirit covers a
revision. So each pin was **verified against the weights already here**, by comparing the git
blob id of the local `config.json` with the Hub's blob id for that path:

```
does the local config.json match the Hub head's blob?
  Qwen3-VL-Embedding-2B        local=e426469143f8 hub=e426469143f8 MATCH
  Qwen3-VL-Reranker-2B         local=5a1243ac0690 hub=5a1243ac0690 MATCH
  MCG-NJU/VideoChat3-4B        local=5744392f49e2 hub=5744392f49e2 MATCH
  MCG-NJU/TimeLens2-4B         local=fef3dc4fca35 hub=fef3dc4fca35 MATCH
```

All four match. So `models/revisions.json` does not merely name a plausible commit — it names
**the revision that produced every visual measurement in `evidence/`**, which is what makes those
numbers reproducible rather than merely recorded.

**Corrected 2026-08-09 (D-075): `pyannote/speaker-diarization-community-1` is pinned too.**
This file first omitted it, arguing that pinning a repository nobody here has downloaded would
record a number rather than a fact. That was wrong, and a parallel branch pinning it is what
prompted the re-check. Gating on this repo covers file **downloads**, not metadata — measured
from this machine with no `HF_TOKEN`:

```
model_info()        -> sha=3533c8cf8e369892e6b79ff1bf80f7b0286a54ee
list_repo_files()   -> 10 files ['.gitattributes', 'README.md', 'config.yaml', …]
hf_hub_download()   -> GatedRepoError: 401 Client Error
```

So the revision was always a verifiable fact here, and pinning it means that the day
`BLOCKED.md` #4 is resolved the download lands on a known commit rather than a head. The test
now asserts **no** repository is unpinned, which is strictly stronger than the exemption it
replaced. `BLOCKED.md` #4 itself is unchanged and still accurate: downloads 401.

## The fix, shaped like the one already there

D-022 established the pattern: `source_for` refuses rather than guessing a repo id.
`revision_for` refuses rather than resolving a branch head, with the same message shape and the
command to resolve it honestly. The fetcher refuses that repository and continues with the rest,
exactly as it does for an unconfigured source.

Revision pinning is also the checksum: the Hub resolves a commit to exact file hashes, so a
pinned download either yields those bytes or fails.

## The tests execute the transaction, they do not grep it

The compatibility harness imports and executes the real `hawedit.model_fetch.fetch_checkpoint`
transaction against a stubbed `huggingface_hub`, asserting the call is

```python
{"repo_id": "Qwen/repo", "revision": "bbbb…bbbb", "local_dir": "…/dest"}
```

An assertion about the *text* of a command is not an assertion about what it does — the mistake
D-067 recorded, one layer up, and the reason a grep-based test was rejected here. The control is
the unpinned case: no download call at all, and exit 1.

## Mutation audit, against a baseline verified green first

```
baseline: GREEN
CAUGHT   an unpinned repo falls back to the branch head instead of refusing
CAUGHT   the fetcher drops revision= and downloads the head (the original defect)
CAUGHT   the fetcher downloads anyway when the repo is not pinned
CAUGHT   a pin is loosened from a commit sha to a branch name
CAUGHT   a repository the fetcher downloads loses its pin entirely
CAUGHT   comment keys are treated as repositories

6/6
```

The original mutation run included the checkout script. D-121 now separately pins the shell file
as a transaction-free launcher and tests the installed console entry point and optional dependency.

## What this does not fix

**`fetch-ffmpeg.sh` still downloads a mutable archive with no checksum** —
`media.githubusercontent.com/.../ffmpeg_bins/main/v8.0/linux.zip`, a branch path, unzipped and
executed. The path segment is versioned but the ref is not, so the bytes can change under it.
Untouched here on purpose: it is a different supply chain with a different verification story
(a published digest to compare against, which that repository does not appear to publish), and
folding it into this change would have made neither testable. Named as an open gap in
`AUDIT_REPORT.md`.

**The weights already on disk were not re-downloaded.** They are verified to match the pinned
revision by `config.json` blob id, not by re-fetching 27 GB. A full byte-level verification of
every safetensors shard is possible and was not done.

## The pin file shipped to nobody, and the local gate could not tell

The first push of this change was **red on the runner**:

```
FAILED tests/test_models.py::test_every_repository_the_fetcher_would_download_is_pinned
  AssertionError: no pinned revisions found under /home/runner/work/HawEdit/HawEdit/models
```

`models/*` is git-ignored — with a `!models/sources.json` exception and a comment explaining
exactly this trap — so `git add -A` skipped `models/revisions.json` **in silence**. The file
existed on hawapc01, the local gate passed against it, and the commit shipped the code that
requires it without the file itself. `git diff --cached --stat` showed nine files and not that
one; I read the number, not the list.

The `.gitignore` now carries a second exception, and the class of defect is closed by a test
rather than a third comment: `test_every_data_file_the_wheel_ships_is_tracked_by_git` reads
`[tool.setuptools.data-files]` out of `pyproject.toml` and asserts every path it declares is in
`git ls-files`. Verified red before the fix — it named `models/revisions.json` — and green after.
Anything added to the wheel is covered without anyone extending a list.

This is D-067's shape a third time: the local gate and the runner were checking different
programs, and only the runner could see it.

Gate: `VERIFY OK — 1092 passed, 0 skipped`.
