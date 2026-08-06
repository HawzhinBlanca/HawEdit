# DECISIONS — append-only

Every deviation from `BLUEPRINT.md`, and every judgment call the blueprint left open, with
reason and measurement. Append only; never rewrite an entry.

---

## D-001 · Implementation language and layout — Python under `hawedit2/`

**Date:** 2026-08-06 · **Blueprint ref:** §2, §7 · **Type:** judgment call, not a deviation

The blueprint's entire stack is Python (KLPT, pyannote.audio 4.x, `omnilingual_asr`,
PySceneDetect, Silero, fontTools) plus ffmpeg. The host repo (`Codystem`) is a TypeScript
harness; its gate (`scripts/verify.sh`) lints `src/**/*.ts` only and its
`surface-manifest.sha256` covers root `scripts/` and `.github/`. `hawedit2/` is therefore
self-contained with its own gate so neither project's CI can silently pass the other's code.

**Measurement:** `bash hawedit2/scripts/verify.sh` runs ruff + mypy + pytest over
`hawedit2/` only; root `bash scripts/verify.sh` is unaffected (verified green after this
change).

---

## D-002 · Dependency licence audit — all permissive, no NC

**Date:** 2026-08-06 · **Blueprint ref:** §7, gate "no new dependency without a licence check"

| Dependency | Version | Licence | Verdict |
|---|---|---|---|
| `klpt` | 0.1.7 | **CC BY-SA 4.0** | ACCEPT (not NC) — obligations below |
| `chunspell` (klpt dep) | 2.0.4 | LGPL-2.1+/MPL (hunspell binding) | ACCEPT — dynamic-linked binding, not modified |
| `pytest` | dev | MIT | ACCEPT |
| `ruff` | dev | MIT | ACCEPT |
| `mypy` | dev | MIT | ACCEPT |

Licence read from the published wheel metadata, not from a README:
`klpt-0.1.7-py3-none-any.whl` → `METADATA` → `License: CC BY-SA 4.0`.

**KLPT obligations.** CC BY-SA 4.0 is not NonCommercial, so it clears the hard-reject gate.
It does carry two obligations, which go in the same shipped-attribution bucket as pyannote
Community-1 (CC-BY-4.0, §7):

1. **Attribution** — Sina Ahmadi / KLPT must be credited in shipped product docs.
2. **Share-alike on adapted material** — we consume KLPT unmodified as a library. If we
   ever vendor or modify its rule tables, ShareAlike attaches to that adaptation. Flagged
   so it is a decision, not an accident.

---

## D-003 · KLPT `normalize` covers 4 of the 5 §4.1 collisions — measured

**Date:** 2026-08-06 · **Blueprint ref:** §4.1 · **Type:** measured gap in a blueprint-mandated tool

Ran `klpt.preprocess.Preprocess("Sorani", "Arabic", numeral="Latin")` against each collision
listed in §4.1:

| §4.1 collision | Input | `normalize()` output | Covered |
|---|---|---|---|
| `ه` + ZWNJ vs `ە` | `ئه‌مه‌ زۆر باشه‌` | `ئەمە زۆر باشە` | YES |
| Arabic `ي`/`ك` → Farsi | `كوردي` | `کوردی` | YES |
| Farsi numerals | `ساڵی ۲۰۲۵` | `ساڵی 2025` | YES |
| Eastern Arabic numerals | `ساڵی ٢٠٢٥` | `ساڵی 2025` | YES |
| Conjunctive `و` separation | `من وتو` | `من وتو` (unchanged) | **NO** |

`normalize()` already unifies numerals, so `unify_numerals()` is not called separately.
`standardize()` performs orthographic standardization, *not* normalization — it left every
collision above untouched and must not be substituted for `normalize()`.

**Deviation:** §4.1 attributes conjunctive-`و` separation to AsoSoft ("AsoSoft applies a
separation algorithm"), and KLPT does not implement it. Correct separation needs a lexicon
(`وتو` is ambiguous without one). Rather than guess, this is left unimplemented and
**asserted as a known gap in the test suite**, so the day it is implemented the test tells us.
Deferred to M1, tracked in `PROGRESS.md`.

**Consequence today:** the index will treat a joined `و` and a separated `و` as distinct.
Character 3-grams (§2) absorb part of this; the residual is unmeasured until M0 has audio.

---

## D-004 · `--fast` gate mode

**Date:** 2026-08-06 · **Blueprint ref:** none · **Type:** infrastructure

`hawedit2/scripts/verify.sh --fast` runs lint + typecheck only, for use as an editor/hook
feedback loop. The full gate — the one that decides DONE — always runs tests. `--fast` can
never print the full-gate success line.

---

## D-005 · Two real defects found in the gate by its own tests

**Date:** 2026-08-06 · **Blueprint ref:** none (infrastructure) · **Type:** defect + fix

Writing M0.1's tests before trusting the gate paid for itself immediately.

**Defect 1 — the anti-cheat could not see an empty command.** The gate read its steps as
`${LINT_CMD:-default}`. The `:-` form substitutes the default when the variable is unset
**or empty**, so `LINT_CMD=` — an operator explicitly asking to run nothing — silently
became the real linter. The no-op refusal never fired because by the time it ran, the value
was no longer empty. Fixed by switching every step to `${VAR-default}` (no colon), which
substitutes only when unset. `LINT_CMD=` now reaches `_noop_check` and is refused.

**Defect 2 — the gate could fork-bomb itself.** `tests/test_gate.py` invokes the gate to
assert its refusal behaviour. Any invocation that reached the test step ran
`pytest` → `test_gate.py` → gate → `pytest` → … Observed live: 235 processes before the
run was killed. Defect 1 was the trigger (the empty-`LINT_CMD` case fell through to a full
run), but the recursion was latent and would have returned with any future test that shells
out to the gate.

Fixed with a depth guard: the gate exports `HAWEDIT2_GATE_DEPTH`, and a nested invocation
refuses to run the **test step** (exit 4) while still permitting lint/typecheck, so
`--fast` remains usable from inside a test. Asserted by
`test_nested_full_gate_refuses_instead_of_recursing` and
`test_nested_fast_run_is_still_allowed`.

**Measurement:** `bash hawedit2/scripts/verify.sh` → 9 passed, `VERIFY OK`, no recursion.

---

## D-006 · Normalization: numeral target, and measured whitespace behaviour

**Date:** 2026-08-06 · **Blueprint ref:** §4.1, §8.1 · **Type:** judgment call + measurement

**Numeral target = Latin.** §4.1 lists Farsi (`۰۱۲`), Eastern Arabic (`٠١٢`) and Western
(`012`) as all occurring in real Kurdish text, and requires unification, but does not name
the target. Latin is chosen because it is what timestamps, IDs and the §5 JSON contract
already use, so a normalized transcript carries exactly one numeral convention rather than
two. Reversible: it is a constant in `normalize.py`.

**Whitespace — measured, and not what I first assumed.** The test written for M0.3 asserted
that KLPT collapses internal whitespace. It does not, and the test failed:

| Input | Output |
|---|---|
| `"   "` | `""` |
| `"  ئەمە  "` | `"ئەمە"` |
| `"ئەمە    زۆر"` | `"ئەمە    زۆر"` (4 spaces preserved) |

So `normalize()` strips the ends and leaves internal runs alone. The assertion was corrected
to the measured behaviour rather than the assumed one, and pinned — this is exactly the kind
of detail a library update changes quietly.

**Consequence:** normalized CER alone would charge a model for spacing it cannot reliably
produce in a morphologically rich, clitic-heavy script. That is why §8.1 asks for a
spacing-free CER *alongside* it, and both are implemented in M0.5.
