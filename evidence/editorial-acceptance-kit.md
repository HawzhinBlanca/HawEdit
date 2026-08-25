# Blinded editorial acceptance kit — 2026-08-17

## Scope and honesty boundary

`src/hawedit/editorial_acceptance.py` prepares and verifies the 200–500-item §8.2 human
study. It does not provide the missing real Kurdish labels, tune a threshold, promote a judge, or
turn generated templates into acceptance evidence. `PROGRESS.md` M7.2 therefore remains BLOCKED.

## What is bound

- The exact strict inventory bytes, authorizer, media-use assertion, pinned incumbent/shadow
  verdicts, source identities and the source-hour economics denominator.
- A content-derived, near-equal dialect sample; per-dialect holdout; concealed A/B order; and opaque
  review identities. Evaluation reopens the inventory and recomputes the complete manifest.
- Stable single-link media bytes before and after ffprobe, a real video stream, and an exact measured
  duration. Different paths with identical bytes and conflicting media aliases/durations are refused.
- Coordinator approval, two complete independent reviewer records and exact disagreement
  adjudication under one captured allowed-signers file. Four distinct identities, four distinct
  OpenSSH key fingerprints, and approval/review/adjudication chronology are required.
- Write-once atomic packet/result directories. Training and holdout labels and metrics are separate;
  adjudication reasons and both signed reviewer positions survive in the final coordinator report.

## Automated measurement

The focused suite uses the repository's decodable 4,162 ms Kurdish video fixture rather than fake
media bytes and generates real Ed25519 keys and OpenSSH detached signatures during the run.

```text
tests/test_editorial_acceptance.py: 26 passed
editorial + judge + metrics + claims + CLI + VEX adjacency: 310 passed
Ruff check/format: clean
mypy --strict --no-incremental: clean
```

Adversarial cases include schema coercion, links, non-video bytes, false duration/source-hour
claims, media and inventory mutation, sample/split drift, signature tampering, identity and key
reuse, chronology inversion, incomplete reviews, inexact adjudication, allowed-signers resnapshot,
competing publication and output overwrite.

## Remaining human evidence

There is no completed 200–500-item label set in the repository. A coordinator must supply authorised
real candidate media and inventory, two independent Kurdish reviewers must label the frozen packet,
a separate adjudicator must resolve disagreements, and a Kurdish editor must approve the eventual
locked-holdout result. Until then this is a ready-to-fill acceptance instrument, not AC-8 success.
