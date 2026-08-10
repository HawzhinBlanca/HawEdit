# Two ledger rows had five columns

> Measured 2026-08-10 on hawapc01 against `7d3d1f2`.

## How it surfaced

Scanning for DONE rows never touched by an adversarial pass, my scan reported **M0.1** as
unaudited. M0.1's own cell contains `**Audited 2026-08-10 (D-156)**`. The scan was reading the
evidence column as `cells[3]` after `line.split("|")` — and M0.1's evidence has a pipe in it.

```
M0.1   …`--check`'s exit through `| tail` reported…
M2.7   …`discovery` and `editorial` are typed `StageSkipped | None` and success…
```

In GFM a `|` inside a table cell splits it **even inside backticks**; there is no code-span
exemption. So both rows render with a fifth column, and read as five cells to any parser.

```
50 milestone rows
naive split('|')        shifted rows: 2  [('M0.1', 5), ('M2.7', 5)]
```

Both are mine: the `| tail` quote comes from D-144, the `StageSkipped | None` from D-111.

## Escaping alone is not the fix

```
after escaping to `\|`
  naive split('|')             shifted rows: 2  [('M0.1', 5), ('M2.7', 5)]
  escape-aware (?<!\\)\|       shifted rows: 0  []
```

`\|` fixes the renderer. It does not fix `split("|")`, which splits on that pipe just the same.
Both halves are needed: the ledger escapes, and `row_cells()` splits on `(?<!\\)\|` so the parser
agrees with Markdown. `test_every_blocked_row_points_at_a_live_blocked_entry` and `_status()` both
index by column and both go through it now — neither was broken today only because both escaped
pipes sit in the evidence cell, which is last.

## The latent hole

A BLOCKED row with a stray pipe ahead of its `BLOCKED.md #N` would have its citation searched in
the wrong half of its own cell: no citation found, or one found and another missed. That is
D-144's *"a blocker could resolve invisibly"* arriving through a different door. The audit reaches
it directly — injecting a pipe into a BLOCKED row's evidence reddens both that guard and the new
column check.

## Proof

```
baseline green: True

RED  the defect restored: an unescaped pipe goes back into M0.1's evidence
RED  the defect restored: an unescaped pipe goes back into M2.7's evidence
RED  a BLOCKED row gains a stray pipe ahead of its citation
RED  row_cells stops respecting the escape
RED  a stray pipe lands in a DONE row the escape-control never mentions
RED  the ledger stops quoting anything that needs an escape

6/6
restored and green: True
```

The fifth is the one that isolates the column guard: neither the escape-control nor the BLOCKED
check names that row, so only the column count can see it.

## The first pass was 5/6, and the survivor was mine

I neutered the column guard *alone*, with the ledger intact — and a guard for malformed rows
measures nothing when no row is malformed. Second time this session I have mutated a test in
isolation and learned only that it is redundant today; D-149 was the first, and the lesson is the
same: a test's discriminating power only shows against a defect.

## The control

A `PROGRESS.md` with no pipes left anywhere would pass the column guard by having nothing to
escape. So a second test requires both quoted forms to still be present, escaped — deleting the
quote instead of escaping it reddens.

Gate: `VERIFY OK — hawedit gate green`, 1509 tests (floor 1507 → 1509).
