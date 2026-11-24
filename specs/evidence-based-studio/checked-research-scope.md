# Checked Research Script Relocation

Approved-by: Wareen - inherited approved studio implementation and explicit local-only
checkpoint authorization; no harness, spending, publication or release authorization.

## Research

The exact clean-commit gate at 1dbc2b1a661f6d3f608a9dc931d54fec3c85b48d reports
4,261 passed, two failed, zero errors/skips, 1200.99s. One failure is current VEX binding
(#24). The other is test_the_gate_reads_every_python_file_in_the_repository: 19 committed
research/probe scripts under specs are outside the canonical src/tests/scripts scope.
Do not weaken that assertion, rename executable code into unchecked artifacts, hide it
with ignore rules, or change the protected gate. Move actual code under scripts.

Actual Serena before-map contains 20 definition/reference records: each existing main
and LostAcknowledgementHandler with its override. The sole callers found are each
script's own __main__ entry point (the handler is also used by its own HTTP diagnostic).
They are engineering research tools, not production, CLI package or web workflow callers.
The map/log and terminal gate are in the private external directory
C:/Users/Wareen/AppData/Local/HawEditEvidence/studio-commit-1dbc2b1a661f6d3f608a9dc931d54fec3c85b48d.
Historical failed probes/maps and outputs remain preserved, never reclassified as passes.

## Impact And Plan

Move all 19 scripts to scripts/studio_research, preserving the two-level repository-root
resolution. Fix sibling-output paths to their original specs evidence location. Historical
commands at the old path are provenance for the earlier commit, not current entry points.
Make relocated scripts pass existing lint, strict typing and formatting without suppressions
or runtime/model policy changes. Keep dynamic cached Serena import support, exact source
guards, refusal assertions and immutable output behavior. Add named relocation/compile/
output-location regressions and a fresh actual final definition/reference map. No new
dependency, BLUEPRINT divergence or ADR is needed for relocating checked engineering tools.

The first checked import pass exposed duplicate mypy module identities for two research
tools' tests.* imports versus the repository's flat test-module inventory. A trial explicit
tests package exposed 23 errors in existing flat imports and was removed before commitment.
Keep the existing test topology: these two tools resolve the actual repository tests path
and import the same statically checked flat helpers inside main. Do not hide imports behind
Any, suppress errors or rewrite unrelated tests. Preserve both failed check logs as evidence.

After review, prepare a normal local follow-up commit, then run the unchanged exact full
gate with fresh external source/runtime manifests. Capture all failures honestly. Do not
flip the ledger or call this done without canonical green and required same-SHA CI.

## EARS

WHEN research tools are committed, THE repository SHALL place their executable Python
under the existing checked scripts scope (test_studio_research_tools_are_in_checked_scope).

WHEN the research scripts are compiled, THE tools SHALL remain syntactically valid without
running paid services or historical diagnostics (test_studio_research_tools_compile).

WHEN a relocated tool resolves its historical evidence output, THE tool SHALL retain the
original specs/evidence-based-studio destination rather than create evidence beside code
(test_studio_research_outputs_keep_original_evidence_location).

## Ledger

- [ ] RS1: Checked relocation and output locations; three named regressions above, exact
  canonical gate and applicable same-SHA CI required before acceptance.

## Local Engineering Observations

New test-first run: 25 failures and one pass, 4.55s. Initial focused run after filesystem
relocation still failed the scope test because the Git index retained the original paths:
53 passed, one failed, 37.94s. After staging the real relocation, all 54 focused cases
passed, 42.80s. The final fast check passes lint and strict types for 295 files, not the
canonical gate. A fresh actual final Serena map contains 21 definition/reference records,
including the new mapper. External evidence filenames: research-scope-red.log/.xml,
research-scope-focused.log/.xml, research-scope-focused-final.log/.xml,
research-scope-fast-initial/second/third/fourth/fifth.log,
research-script-before-map.json and research-script-final-map.json with their Serena logs.

Measurements are native engineering tests on the recorded HAWAPC01 Windows/CPython 3.12.10
host, pytest 9.1.1, ruff 0.9.6 and mypy 1.15.0. They are not pipeline speed, labelled-media
quality, accessibility, human workflow, clean runner or release acceptance measurements.
Keep RS1 unchecked pending exact full gate and applicable CI. No protection surface changed.
