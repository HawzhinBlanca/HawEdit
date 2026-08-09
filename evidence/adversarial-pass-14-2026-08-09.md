# Adversarial pass #14 — model provisioning, and a correction that stopped halfway

> Run 2026-08-09 on hawapc01 against `b5662a0`.
> Target: **M1.6**, DONE — never attacked. It decides which weights get downloaded and executed.

## The code held

```
CAUGHT  every component prints OK whatever its verdict
CAUGHT  every verdict is inverted
CAUGHT  a measured size of zero prints as unmeasured again
CAUGHT  the summary claims everything is available
CAUGHT  the summary counts something other than what it lists
CAUGHT  an unpinned repository resolves to a branch head instead of refusing
CAUGHT  a checkpoint whose loader is missing reports available

7/7
```

D-100's readiness-report fix, `revision_for`'s refusal and D-099's loader check are all still held.

## Two of the cell's claims were false

```
"pins all five downloaded repositories"
  revisions.json pins                      6
  registry entries with a download source  6
  unpinned among them                      0

pyannote "deliberately unpinned … a test asserts it is the only one"
  pyannote pinned                          True            (D-075)
  tests/test_models.py asserts             unpinned == []  no exemptions

"Still unpinned: fetch-ffmpeg.sh downloads a mutable main/ archive and executes it with
 no SHA-256 check"
  URL carries a 40-hex commit ref          True            (D-121)
  a 64-hex digest is recorded              True
  compared before the unzip                True
```

Every one of those was made false by a commit in this repository — D-075 pinned pyannote, D-121
pinned and checksummed the archive — and **D-120 corrected the same two sentences in
`AUDIT_REPORT.md` without looking in the ledger.** A correction landing in one document and not the
other is the failure this project keeps catching; this is the second time on this pair of facts, and
both times it was mine.

## So the fix is not the sentence

Two claims tests, keyed on the files the claims are about:

* a document saying *"all N download… repositories"* must say the number `revisions.json` pins —
  only the count, because a count is a fact and a phrase is not;
* no document may describe a *"mutable `main/` archive"* while the URL line in `fetch-ffmpeg.sh`
  carries a commit — and it fails the other way too, so if the URL regresses to a branch, silence
  becomes the failure.

`DECISIONS.md` is exempt: it is append-only and its old entries are supposed to record what was true
then. Forcing them current would be a check whose cheapest fix is editing history.

**Verified before correcting anything** — both tests fail on the tree that motivated them:

```
AssertionError: models/revisions.json pins 6 repositories, and these say otherwise:
  ["PROGRESS.md: 'all five downloadable repositories'"]

AssertionError: the archive is fetched at a pinned commit and ['PROGRESS.md'] still describe
  a mutable `main/` archive. D-121 closed that; the document did not follow.
```

A claims test that passes on the tree that motivated it measures nothing.

## The first claims test was wrong, and the correction is what showed it

The ffmpeg half started as *"no live document may say `mutable `main/` archive` while the URL carries
a commit"* — and it failed on the correction that retired the claim, because this project's
convention is to **quote** a wrong sentence while correcting it (D-069, D-076, D-105, and the cell
this pass just corrected). A grep cannot tell a document making a claim from one retiring it.

Rewritten to bind fact to fact: the 40-hex commit in `fetch-ffmpeg.sh` must appear in a live
document, so a reader can check the pin without opening the script and a pin that moves has to be
republished. If the archive is ever unpinned there is no commit to publish and it fails the other
way. 3/3 on its own audit — the wrong count restored CAUGHT, the published commit removed CAUGHT,
the script unpinned CAUGHT.

Gate: `VERIFY OK — 1298 passed, 0 skipped`.
