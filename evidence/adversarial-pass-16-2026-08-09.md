# Adversarial pass #16 - the end-to-end runner

Run 2026-08-09 against upstream `7269dd0`; semantically integrated into the readiness branch as
D-159 because D-129 was already assigned there.

The pass targeted seven original M2.7 mechanisms. Exit-code refusal in both directions and the
visual window plan's dependence on Stage 0 cuts were already mutation-sensitive. Four mechanisms
were correct but under-proved.

## The complete branch had never run

`PipelineRun.complete` drives the CLI exit code and has eleven conjuncts. Before this pass, even the
largest end-to-end fixture was incomplete: it had no candidates and reported visual/discovery
skips. Replacing `not self.skipped()`, `bool(self.visual_windows)`, or `bool(self.candidates)` with
`True` therefore left every test green.

The new module fixture uses the real runner and media path with injected discovery, visual and judge
seams. Ingest, transcript normalization, indexing, visual planning, discovery, boundary fusion,
editorial projection, render and delivery all produce evidence. The control requires
`complete is True` and no skips; three tests then remove one requirement at a time and require
`complete is False`.

## Stage 5 cut provenance

On this fixture, natural silence extends to the end of the file and wins over every shot-cut
candidate. Asserting the final boundary label therefore cannot prove cut wiring. The new test
records the `BoundaryInputs` passed through the real runner and requires their `shot_cuts_ms` to
equal the cuts in the same run's Stage 0 `IngestResult`.

## Stale count corrected

The original ledger said a bare run named four blocked stages. The current pipeline names eight:
transcript, index, visual index, discovery, editorial, boundary, render and delivery. The count grew
as later stages were composed and is no longer stated as four.

No production code changed. The seven targeted mechanisms now have discriminating controls.
