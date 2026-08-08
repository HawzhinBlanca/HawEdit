# Adversarial pass over ten DONE rows: what survived and what did not

> Measured 2026-08-09 on hawapc01 against `81caa3e`. Ten agents, one per row, each in its own
> git worktree, each instructed to try to prove its row **false**.

118 distinct claims extracted from ten DONE rows. **All ten baselines verified green before any
mutation** — an audit against a red baseline measures nothing, and that has happened here twice
before. Aggregate: **19 claims falsified, 26 guards revertible with no test noticing, 59 places
prose disagreed with code, 2 untestable.**

Agent reports are not findings. Everything acted on below was re-measured by hand first; the rest
is listed as reported-and-unverified so nothing is lost and nothing is overstated.

## The tooling was verified before the agents ran

A git worktree has no `.venv`, and the editable install points at the *main* `src` — so a
mutation in a worktree might not be what pytest imports. Checked first:

```
PYTHONPATH=$PWD/src <main venv python> -c "import hawedit.boundary as b; print(b.__file__)"
  -> C:\...\wt_probe\src\hawedit\boundary.py          (the worktree, not main)

TAIL_MS 200 -> 999 in the probe worktree:
  worktree: 3 FAILED    main tree: 37 passed
```

Isolation holds in both directions.

## Verified by hand, and fixed

### The Kurdish-script gate could be satisfied and then invalidated — §3 Stage 4

`_kurdish_field` checked `_is_kurdish` on the **raw** string and returned
`normalize_sorani(stripped)`. §4.1 normalization can delete the characters that satisfied the
check:

```
probe             '٠١٢'        (Arabic-Indic digits — inside the block _is_kurdish tests)
_is_kurdish(raw)  True
_kurdish_field    '012'        <- returned, past the guard
_is_kurdish(out)  False
```

A title, description or hashtag of Arabic-Indic digits passed a guard whose entire purpose is to
refuse text with no Kurdish script, and shipped as Western digits into `JudgeVerdict` — which §5
and the delivery set consume as finished work.

**Fixed at the root** — one shared function, four call sites. The check now runs on the
normalized text. That is strictly stronger than checking first, because normalization never
*adds* Kurdish script, so anything the late check accepts the early one would also have accepted.

```
'٠١٢'    -> REFUSED: title_ckb '٠١٢' contains no Kurdish script once §4.1-normalized to '012'.
'یک ٠١'  -> 'یک 01'          (control: Kurdish + digits still accepted, digits still unified)
'ئه‌مه‌ باشه‌' -> 'ئەمە باشە'   (control: normalization still applied)
```

Mutation audit, baseline verified green first:

```
baseline: GREEN
CAUGHT   the check runs before normalization again (the original defect)
CAUGHT   the gate is removed entirely
CAUGHT   the refusal stops naming the normalized form
CAUGHT   normalization is dropped from the accepted path

4/4
```

## Verified by hand, recorded, not fixed — §4.1's fifth collision does not exist as claimed

M0.3 is marked DONE with *"All five §4.1 collisions are now handled: four by KLPT (D-003), the
fifth — conjunctive `و` — by M1.7"*. Read straight out of the frozen blueprint,
`BLUEPRINT.md:228-232`:

| # | Collision |
|---|---|
| 1 | `ه` + ZWNJ vs `ە` |
| 2 | Farsi vs Arabic `ی` / `ک` |
| 3 | Numerals (Farsi, Eastern Arabic, Western — **one** row) |
| 4 | Conjunctive `و` |
| 5 | **Diacritics `ř` / `ł` — "Normalize in Latin-script material."** |

Conjunctive `و` is row **four**, not five. The row reaches "four by KLPT" only by counting the
single Numerals row twice. Row five is unimplemented and, until now, undocumented:

```
'řoj baş'   -> 'řoj baş'   changed=False
'łe gułan'  -> 'łe gułan'  changed=False
grep -rlniE "ř|ł" --include=*.py src/ tests/   ->  (no files)
```

So §4.1 coverage is **4 of 5**, not 5 of 5, and `tests/test_normalize.py`'s
`SECTION_4_1_COLLISIONS` holds four entries while its docstring claims *"Every collision in the
§4.1 table gets a case"*.

**Not fixed, because the fix requires a decision I must not invent.** "Normalize in Latin-script
material" does not say what `ř` and `ł` normalize *to*. In Kurdish Latin orthography they mark a
trilled r and a velarized l — distinct phonemes — so folding them to `r`/`l` destroys
information, and folding them anywhere else is a guess. Two questions belong to Hawa: what the
target form is, and whether Latin-script Kurdish is in scope at all for a pipeline whose §7 ASR
emits `ckb_Arab`. Recorded in D-076 and as a BLOCKED entry; M0.3 demoted to PARTIAL naming the
shortfall.

Note the existing guard did not catch this and could not: `test_claims.py`'s
`test_the_ledger_tracks_whether_all_five_collisions_are_handled` defines "all five handled" as
"conjunctive `و` separates", so it encodes the same miscount it was written to prevent.

## Reported and verified, not yet acted on

| Row | Finding | Severity |
|---|---|---|
| M7.1 | `path_unique_wins` returns `0` for every path when the gold set has no winners, while `recall_at_k` returns `None`. Zero-when-unmeasured is what the project's own "unmeasured is None, never 0.0" rule forbids; zero-when-measured is a real answer. The code conflates them. | real, hard-rule tension |
| M7.1 | `iou_match` is never validated — a caller passing `1.5` or `-1` gets silent nonsense rather than a refusal | real |
| M2.2, M6.2 | both cite a sweep as **"exhaustive"** over the soft inputs; it varies 5 of 7 `BoundaryInputs` fields, omitting `media_duration_ms` and `natural_silence_ms` — the latter being the signal D-070 wired *this week*, so the sweep has never covered it | overstated word, real gap |
| M0.3 | `evidence/waw-separation.md` records `waw_initial_words: 491`; re-measured 504 with duplicates / 492 distinct, and 491 contradicts the file's own arithmetic (24,894 − 491 ≠ 24,390). Six of the other seven numbers reproduce exactly. Its "Reproduce" command also cites `.venv/bin/python`, which does not exist on this host. | wrong number in evidence |
| M3.4 | `evidence/m3-4-shipped-clip-invariant.md` says the runner shipped a clip **138 ms** shorter than recorded; re-measured under restored pre-fix behaviour the shortfall is **120 ms** (4300 recorded, 4180 on disk). 138 is a different quantity — the overshoot past media duration. | wrong number in evidence |
| M0.4, M2.2, M2.6, M3.6 | per-row test counts are stale in the understating direction: 17→34, 31→37, 20→22, 40→43, 25→26. Each was true when written; nothing guards them, and `test_every_test_count_in_the_audit_is_dated` deliberately covers `AUDIT_REPORT.md` only | doc drift, a class |
| M1.1 | the skip-transition comment claims two conditions do work; one is dead code — `state` and `state - 2` share parity, so the blank test is unreachable. Property run under the mutation gave a byte-identical checksum (`18ebebb50771ca8b`, 3000 cases, 0 violations) | comment falsified, not behaviour |
| M3.5 | two prose claims wrong: invariant #4 was absent only when a clip's in-point exceeds its own duration (otherwise captions drew late and truncated), and the cited fixture cuts at **500 ms**, not 300 | overstated |

**26 guards were revertible with no test noticing.** That is the single largest result of this
pass and it is not yet triaged; five are in `forced_alignment.py` alone, and several in
`boundary.py`/`clip.py` are caught only by tests in *other* files than the two the M2.2 row cites
as its evidence.

## What this pass says about the DONE rule

The project's rule is code + test + gate green + evidence. Ten rows that all satisfy it produced
19 false claims — none of them a broken behaviour except the Stage 4 gate, and almost all of them
prose that was true when written and was never re-measured. The gate cannot catch that, because
the gate tests code and these are claims *about* code. `tests/test_claims.py` exists for exactly
this and covers five properties; per-row test counts, evidence-file numbers and the word
"exhaustive" are not among them.

Gate after the Stage 4 fix: `VERIFY OK — 1096 passed, 0 skipped`.
