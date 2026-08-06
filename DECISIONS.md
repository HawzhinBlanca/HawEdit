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

---

## D-007 · Lint: RUF001/2/3 (ambiguous unicode) disabled project-wide

**Date:** 2026-08-06 · **Blueprint ref:** §4.1 · **Type:** infrastructure

These rules flag characters *confusable with ASCII*. The collisions this project actually
cares about are Arabic-script-internal — Arabic `ي` vs Farsi `ی`, `ه`+ZWNJ vs `ە` — which
look nothing like ASCII and which the rules never fire on. So they provide no §4.1
protection whatsoever.

What they do fire on is every `§` and en dash quoted verbatim from `BLUEPRINT.md`, and every
Kurdish string in the test fixtures — which must contain the confusable characters, since
that is the thing under test. Disabling them loses no coverage. The real protection is
`tests/test_normalize.py`, which asserts every §4.1 collision resolves.

---

## D-008 · Definitions §8.1 names but does not specify

**Date:** 2026-08-06 · **Blueprint ref:** §8.1 · **Type:** judgment call

§8.1 lists "named-entity error" and "code-switch error" without defining them. Chosen
definitions, and why:

**Named-entity error = fraction of annotated entities absent from the normalized
hypothesis.** Matching is exact after §4.1 normalization, so a keyboard difference is not
scored as a lost name, but a near-miss is: a name 90% right is still the wrong name in a
burned-in caption, and §8.2 identifies misleading output as the error class that matters
most to a media organisation. Strictness here is deliberate.

**Code-switch error = mean CER over annotated switched spans, each located by best
substring alignment.** Spans are annotated in isolation but occur embedded in surrounding
Kurdish, so the metric aligns each span against any substring of the hypothesis (free
prefix/suffix). A whole-utterance CER would dilute a destroyed switch into invisibility —
which is the exact reason §8.1 breaks it out as its own metric.

**Unmeasured returns `None`, never 0.0.** An item with no annotated entities has no
named-entity error. A 0.0 would render in a report as a perfect score. §1: "Fail visible,
not silent."

**CER is not clipped at 1.0.** Standard definition; a model hallucinating past the end of
the reference should be able to score above it, and clipping would hide exactly that.

All four are testable choices, not conventions to remember: see `tests/test_metrics.py`.

---

## D-009 · "Several hours" is enforced as a 3.0-hour floor

**Date:** 2026-08-06 · **Blueprint ref:** §8.1 · **Type:** judgment call

§8.1 asks for "several hours" of labelled audio without a number. `MINIMUM_HOURS = 3.0` —
the smallest quantity "several" honestly describes — is enforced as a **floor, not a
target**: a corpus below it fails `assert_section_8_1_coverage()` with the shortfall named.

Why enforce anything at all: the coverage grid alone is gameable. Three dialects × seven
conditions can be "fully covered" by 21 thirty-second clips, which satisfies every cell and
measures nothing. The hours check and the grid check together are what make coverage mean
something.

It is one constant, and the right way to change it is evidence from a real run — not a
convenient number.

---

## D-010 · What "material gain" and "acceptable throughput" mean in §8.1's decision rule

**Date:** 2026-08-06 · **Blueprint ref:** §8.1, §4.4 · **Type:** judgment call

§8.1: "LLM-7B stays canonical unless another model shows a material accuracy gain on *your*
audio at acceptable throughput." Neither "material" nor "acceptable" is given a number.

**Material = ≥10% relative reduction in normalized CER** (`MATERIAL_GAIN_RATIO`). Relative,
not absolute: an absolute threshold means something different at CER 0.30 than at 0.06.
Ten percent sits clear of run-to-run noise while still admitting a real improvement. It is a
floor for *considering* a switch, never sufficient on its own.

**Acceptable throughput has no default — the caller must state `max_rtf`.** It is a capacity
decision about a specific box and workload, and §3 Stage 1 explicitly warns against deriving
it from Meta's A100 figures. A default here would be a fabricated number wearing the
authority of a constant. The check uses **worst-case** RTF, not mean: a batch pipeline is
sized by its slow items.

**A fourth clause the sentence does not contain, from §4.4: no dialect may regress.** A
challenger that wins on average while losing Mukriyan has not won, it has averaged. This is
the entire reason per-dialect numbers exist, and enforcing it in the rule is what stops the
aggregate from quietly becoming the decision.

**A fifth, from ordinary caution: the incumbent must be in the run.** `decide_canonical`
raises if it is absent rather than promoting whichever model happens to be present — that is
precisely how a pinned choice disappears without anyone deciding to unpin it.

Aggregates are **micro-averaged** (total edits over total reference characters). A macro
average lets a five-character item weigh as much as a five-hundred-character one, which on a
corpus mixing news and podcast material reports a different number than anyone means by
"CER".

Failed items are counted as failures and excluded from accuracy. Dropping them silently
would reward a model for choking on the audio it finds hardest.
