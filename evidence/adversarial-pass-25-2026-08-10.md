# Adversarial pass 25 - extracted visual pixels have a bounded lifetime

Date: 2026-08-10
Baseline: `eef02e96f90650518deafceb403a13e654d580a4`

## Finding

Stage 2, Path B, and TimeLens extracted source-video frames into unique private directories, but a
successful call deliberately retained those JPEGs and every failure cleanup ignored filesystem
errors. A normal composed visual run therefore left all sampled source pixels on disk indefinitely.
The Qwen one-window helper and TimeLens had the same successful-retention behavior. A permission or
scanner failure during cleanup was invisible, so the structured report could not tell an operator
that confidential source pixels remained.

## Fix and proof

`WindowFrames` now records the identity of the private directory created by its extraction call and
owns an idempotent cleanup operation. Cleanup refuses a missing, replaced, linked, reparse, or
unexpectedly nested owner instead of recursively deleting by pathname. It deletes only direct files
from the identity-bound directory. A cleanup failure during another exception is attached as a note
without replacing the primary failure; a cleanup failure after success is a domain refusal.

The composed visual frame cache is released after VideoChat3 has materialized every reading. The
standalone Qwen embedder and TimeLens release their frames in `finally` blocks. TimeLens copies a
cleanup privacy note onto its normalized `GroundingError`, preserving it for structured pipeline
reporting.

Discriminating regressions prove that:

- an extracted owner is erased exactly once and repeated cleanup is inert;
- a renamed or replaced owner is refused while both the original pixels and replacement remain
  untouched;
- permission failure preserves the primary model error and records the retained-pixel warning;
- a full composed retrieval/rerank/VideoChat3 run removes every cached source-frame directory;
- standalone Qwen embedding and TimeLens grounding remove their source pixels after model use; and
- frame-directory creation failures are normalized as `VideoInputError` before inference.

This is a lifetime and ownership guarantee for HawEdit-created frame directories. It does not claim
to defeat a hostile process running with the same account and mutating an open directory between
individual filesystem operations.
