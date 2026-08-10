# M0.15's numbers were reproducible in principle and not on this machine

M0.15 is DONE on a measurement: *"24,894 real entries; 0.21% of distinct forms would have failed
to match"*, `evidence/collision-incidence.md`, **Reproduce:**
`.venv/bin/python scripts/measure_collisions.py`. Its own script says the numbers *"are only
worth having if they are reproducible"*.

They were not reproducible here. The one step that produces them failed twice, for two unrelated
reasons, and neither was covered by a test.

## Failure 1 — a venv layout instead of the installed package

```python
KLPT_DIC = ROOT / ".venv/lib/python3.11/site-packages/klpt/data/ckb-Arab.dic"
```

That path exists on POSIX. On Windows the venv is `.venv/Lib/site-packages/…` — capital `L`, no
version segment — so:

```
FileNotFoundError: [Errno 2] No such file or directory:
'C:\Users\Wareen\Desktop\HawEdit\.venv\lib\python3.11\site-packages\klpt\data\ckb-Arab.dic'
real exit=1
```

The file is present, at `.venv/Lib/site-packages/klpt/data/ckb-Arab.dic` (946,155 bytes). Nothing
was missing; the path was assembled rather than asked for. `tests/test_waw.py:45` already does it
the right way — `Path(klpt.__file__).parent / "data" / "ckb-Arab.dic"` — so the correct idiom was
in the repository the whole time and this script was the one place that guessed.

## Failure 2 — the finding did not survive stdout

With the path fixed, the script still exited 1:

```
24894 items, 0.84% altered by normalization; 24051 distinct raw forms -> 24000 normalized …

forms that normalization merges (each pair is an index miss avoided):
UnicodeEncodeError: 'charmap' codec can't encode characters in position 2-7
real exit=1
```

The summary line went out and the **finding itself** — the Kurdish word pairs that collide — died
on cp1252. This is the worse of the two: exit 1 *with the headline already printed*, which reads
like success to anything that checks only the first line. `cli.use_utf8_streams` exists for
exactly this and its docstring calls itself *"the first statement of every `main()`"*; all six
argument parsers call it and this script never did.

## The numbers themselves are correct

With both fixed, `exit=0`, and every figure in `evidence/collision-incidence.md` reproduces
exactly four days on:

```
24894 items, 0.84% altered by normalization; 24051 distinct raw forms -> 24000 normalized
(0.21% would have failed to match); arabic_kaf=1, arabic_yeh=0, eastern_arabic_numerals=0,
farsi_numerals=0, he_plus_zwnj=0, heh_doachashmee=204
```

| Evidence file | Re-measured 2026-08-10 |
|---|---|
| 24,894 entries | 24894 |
| 0.84% altered (209 / 24,894) | 0.84% |
| 24,051 distinct raw forms | 24051 |
| 24,000 after normalization | 24000 |
| **0.21%** would have failed to match | **0.21%** |
| `heh_doachashmee` 204 items | 204 |

All six word pairs the evidence file quotes come back, in the same forms:
`ئاهەنگ|ئاھەنگ`, `بەرهەم|بەرھەم`, `جیهان|جیھان`, `بەهار|بەھار`, `دهۆک|دھۆک`, `سەرهەنگ|سەرھەنگ`.

So the row's claim was **true**, and unverifiable by the command that documents it. The fix is to
the reproduce path, not to the number.

## The binding

Three tests in `tests/test_collisions.py` run the script as a **subprocess** — not an import,
because both defects are only reachable that way — and require exit 0, then compare the evidence
file against what the run emitted. The figures are **parsed from the evidence file**, not written
into the test, so a KLPT update or a `normalize_sorani` change fails naming both numbers instead
of leaving the document describing a run nobody can repeat.

The control is that `0.21%` and `0.84%` both appear in that document: a check that only asked
*"is this percentage mentioned"* would pass with the two swapped, so the collision rate is
asserted **in its own table row** and the altered-items rate asserted absent from it. A second
control requires the quoted merges themselves, because the percentages could match while the
merges changed entirely.

Cost: 1.0 s per run of the script, three runs.

## Mutation audit — 7/7

```
baseline green: True
CAUGHT    the defect restored: KLPT_DIC is assembled from a POSIX venv layout again
           red (3): test_every_merge_the_evidence_quotes_is_still_produced,
                    test_the_evidence_file_still_states_what_the_script_measures,
                    test_the_reproduce_command_for_m0_15_actually_runs
CAUGHT    the defect restored: the script stops pinning stdout to UTF-8
           red (3): (the same three)
CAUGHT    the evidence file's entry count drifts from the corpus
           red (1): test_the_evidence_file_still_states_what_the_script_measures
CAUGHT    the evidence file's collision rate drifts from the measurement
           red (1): test_the_evidence_file_still_states_what_the_script_measures
CAUGHT    the altered-items rate stands in for the collision rate
           red (1): test_the_evidence_file_still_states_what_the_script_measures
CAUGHT    the evidence quotes a merge the script does not produce
           red (1): test_every_merge_the_evidence_quotes_is_still_produced
CAUGHT    the script stops printing any merged group
           red (2): test_every_merge_the_evidence_quotes_is_still_produced,
                    test_the_reproduce_command_for_m0_15_actually_runs
7/7
restored and green: True
```

Both restored defects are **platform-specific by nature** — the POSIX venv layout exists on
Linux, and cp1252 stdout is a Windows default — so this 7/7 is measured on hawapc01 (Windows).
The *fix* is not platform-specific: asking the installed package and pinning UTF-8 are right on
both, and CI runs the same three tests. What a Linux runner cannot reproduce is the failure, and
that is precisely why it went unnoticed.

### Two corrections to the sweep itself

**It reported 7/7 once before this, and two of those catches were not trustworthy.** The first
run flagged mutations 1 and 2 `[lint dirty]`: removing the `klpt.__file__` line orphaned
`import klpt`, and removing the `use_utf8_streams()` call orphaned its import — F401 both times,
the contamination of D-148 and D-150. Redone removing the import alongside its use, both are
still CAUGHT and the red lists are unchanged, so the original result held; but it was not
*measured* to hold until the mutations were clean.

**And the lint check itself was over-broad.** It ran `ruff check` over
`scripts/measure_collisions.py`, which `verify.sh` does not lint: `LINT_CMD` is
`ruff check src tests` and mypy's `files = ["src", "tests"]`. **`scripts/` is outside the gate's
lint and typecheck entirely** — so a lint error there can never redden the suite, and flagging it
marks honest catches as contaminated. Narrowed to `src tests`, which is what can actually redden
the gate-as-subprocess tests.

That scope gap is worth stating plainly rather than fixing here: the fix in this commit lives in
a file the gate neither lints nor typechecks, and the only thing standing behind it is the
subprocess test added alongside it. Widening `LINT_CMD` to `scripts` is a separate change that
would have to survive every other script in that directory first.

**And a third pass, because mutation 1 was not restoring the defect it named.** `ROOT` went away
with the fix — nothing else in the script used it — so replacing only the `KLPT_DIC` line left
`ROOT` undefined and the script died on `NameError` at import rather than `FileNotFoundError` at
the read. The test caught it either way, and would have: it requires exit 0. But the label claimed
one thing and the run measured another, which is the same defect as reporting a number without its
provenance. Reinstating `ROOT = Path(__file__).resolve().parents[1]` alongside the old path makes
it the original failure and nothing else; still 7/7, same red lists. Eighth bad mutation of mine
in this loop after D-137, D-141, D-144, D-147, D-149, D-155 and D-156 — and the second caught only
by reading the committed diff rather than the sweep's own output.
