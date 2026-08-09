# A Kurmanji split imported as `ckb` whenever it declined to name its language

> Measured 2026-08-09 on hawapc01 against `2847efb`, against a green 1,148 baseline.

M0.14's row says the importer "refuses to invent dialect, condition or duration", and the module
docstring adds a fourth: "**Locale is checked.** Kurmanji (`kmr`) and Farsi (`fa`) are one directory
away in any Common Voice download, and importing either would silently poison every `ckb` number."

The check was `if row_locale and row_locale != locale:`. The leading truthiness clause skipped it
entirely for any row whose locale was absent or blank — and the provenance name is built from the
**parameter**, never from the data:

```python
name=f"Mozilla Common Voice {locale} ({tsv_path.name})"
```

So the manifest asserted the language on the file's behalf, in exactly the case where the file had
declined to state it.

## Measured, on Kurmanji rows

Before:

```
  A locale present, value kmr    REFUSED: row for clip 'common_voice_kmr_001.mp3' has lo…
  B locale column ABSENT         ACCEPTED 2 Kurmanji items
       provenance : 'Mozilla Common Voice ckb (validated.tsv)'
       item[0]    : 'Ev pir bas e'
  C locale cell BLANK            ACCEPTED 2 Kurmanji items
```

`'Ev pir bas e'` is Kurmanji, stored as `reference_ckb` under a provenance that says `ckb`. This is
the labelled-corpus poisoning the docstring names, reached without touching the locale value at all
— only by omitting it.

After:

```
  A kmr, locale present      REFUSED
  B kmr, column ABSENT       REFUSED
  C kmr, cell BLANK          REFUSED
  D ckb, honest (CONTROL)    ACCEPTED 2 items | 'ڕۆژنامەوانی کوردی'
```

## The fix

Dropped `row_locale and`. One clause, in the one place every row already passes through — there is
no per-caller variant of this, and `import_common_voice` is the module's only entry point.

No threshold was chosen. An unreadable locale is not "no objection"; it is the file failing to
confirm the language the importer is about to assert on its behalf. That is the same rule the module
already applies to duration, which is *required* rather than defaulted for the same reason.

## Mutation audit, against a baseline verified green first

```
baseline FAILED=0
CAUGHT   the truthiness bypass is restored (the defect)
CAUGHT   the locale check never fires
CAUGHT   honest ckb rows are refused (over-strict)

3/3
```

The third is the control doing the work. Refusing every row passes both refusal tests and imports
nothing, ever — and no refusal test can see that. Fourth consecutive iteration where the over-strict
direction was catchable only by a control (D-088, D-087, D-102, now this).

## Scope, stated plainly

M0.16 is BLOCKED and there is no corpus on this machine to import, so **nothing shipped wrong output
to a client from this defect yet**. What it did ship was a false guarantee: the docstring's fourth
promise and M0.14's row both claimed a check that a missing column walked around. The blast radius is
every §8.1 number that would later rest on the first file anybody does import — which is why this
was picked over the remaining pass-#4 findings.

Found by the fourth adversarial pass; the premise was re-verified here rather than taken from the
agent's report.

Gate: `VERIFY OK — 1151 passed, 0 skipped`.
