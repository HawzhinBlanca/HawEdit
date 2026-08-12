---
name: research
description: Phase 1 of the CODYSTEM loop for hawedit. Map every relevant file, symbol, and data flow for a feature using Serena (read-only). Writes a compacted specs/<feature>/research.md. Use BEFORE any planning or coding. No code is written.
---

# Research (no code)

**Goal:** a small, high-signal map of the real code touched by `<feature>`, so the plan is
grounded in what `src/hawedit/` actually does rather than in what it sounds like it does.

## Procedure

Research only. Do not write or edit code. Using Serena (`find_symbol`,
`find_referencing_symbols`, `get_symbols_overview`), map every file, symbol, and data flow
relevant to `<feature>`. Use a subagent for broad searches and keep only its summary.

Four documents are part of the terrain here, and all four are large — grep them, never read
them whole:

- `BLUEPRINT.md` — the frozen spec. Find the § this feature implements and quote the sentence
  it turns on. If no § covers it, say so; that is a divergence and it needs an ADR.
- `BLOCKED.md` — numbered blockers. If the feature depends on one, name the number now, not
  after the plan is written.
- `DECISIONS.md` — `## D-NNN` ADRs. Search before proposing anything; the question is often
  already settled, and re-deciding it silently is how a repo contradicts itself.
- `evidence/` — measurement records. Prefer a number with a file behind it to a number in prose.

Write a compacted `specs/<feature>/research.md` (≤ ~60 lines) covering:

- relevant files / symbols (real ones, found with Serena — never invented)
- current behavior, including which stage of the §3 pipeline this sits in
- integration points, and every caller you will have to keep working
- risks: what skips silently today, what is guarded by `skipif`, what has no test at all
- the § / D-NNN / BLOCKED # this work answers to

Stop when done.

## Done when
- `specs/<feature>/research.md` exists, ≤ ~60 lines, listing files/symbols/data-flows and risks
  grounded in real symbols.
- Every claim about existing behavior points at a symbol, a §, or a D-number.
- No code or tests were created or edited.

→ Next: `plan`.
