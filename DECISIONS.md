# DECISIONS — append-only

Every deviation from `BLUEPRINT.md`, and every judgment call the blueprint left open, with
reason and measurement. Append only; never rewrite an entry.

---

## D-001 · Implementation language and layout — Python under `hawedit/`

**Date:** 2026-08-06 · **Blueprint ref:** §2, §7 · **Type:** judgment call, not a deviation

The blueprint's entire stack is Python (KLPT, pyannote.audio 4.x, `omnilingual_asr`,
PySceneDetect, Silero, fontTools) plus ffmpeg. The host repo (`Codystem`) is a TypeScript
harness; its gate (`scripts/verify.sh`) lints `src/**/*.ts` only and its
`surface-manifest.sha256` covers root `scripts/` and `.github/`. `hawedit/` is therefore
self-contained with its own gate so neither project's CI can silently pass the other's code.

**Measurement:** `bash hawedit/scripts/verify.sh` runs ruff + mypy + pytest over
`hawedit/` only; root `bash scripts/verify.sh` is unaffected (verified green after this
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

`hawedit/scripts/verify.sh --fast` runs lint + typecheck only, for use as an editor/hook
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

Fixed with a depth guard: the gate exports `HAWEDIT_GATE_DEPTH`, and a nested invocation
refuses to run the **test step** (exit 4) while still permitting lint/typecheck, so
`--fast` remains usable from inside a test. Asserted by
`test_nested_full_gate_refuses_instead_of_recursing` and
`test_nested_fast_run_is_still_allowed`.

**Measurement:** `bash hawedit/scripts/verify.sh` → 9 passed, `VERIFY OK`, no recursion.

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

---

## D-011 · The diarization control lives outside the §7 registry

**Date:** 2026-08-06 · **Blueprint ref:** §7, §3 Stage 0, §8.1 · **Type:** blueprint inconsistency, resolved without deviating

§7's registry table lists **only** `pyannote/speaker-diarization-community-1`. But two other
places require its predecessor:

- §3 Stage 0: "Keep `speaker-diarization-3.1` (MIT) as a benchmark control."
- §8.1: "Also run here: pyannote Community-1 vs 3.1 on Kurdish multi-speaker material."

So the blueprint requires running a model its own registry table does not list. Adding 3.1 to
`REGISTRY` would break the gate rule "nothing in the model registry that isn't in §7" — and
that rule is enforced mechanically, by parsing §7, so the conflict is a test failure and not
a matter of opinion.

**Resolution:** a separate `BENCHMARK_CONTROLS` mapping. §7's table stays authoritative for
what ships; the control is available for measurement only. `resolve()` does not find it, and
`routable` is `False`, so no pipeline stage can select it even by accident. Asserted in
`tests/test_registry.py`.

This is not a request to amend the blueprint — §3 Stage 0's instruction is unambiguous and
the distinction between "ships" and "is benchmarked against" is real. Flagged because a
future reader comparing §7's table to the code would otherwise find an apparent extra model.

---

## D-012 · Interim corpus authorised — public Sorani data, with hard limits

**Date:** 2026-08-06 · **Blueprint ref:** §8.1, §1 · **Type:** authorised deviation

Hawa authorised using a public Sorani corpus as an interim set while the real labelled
material is assembled. §8.1 wants measurement on *your* audio, so the deviation is bounded
in code rather than by intention:

1. Imported items carry **no dialect and no condition**. Common Voice has neither, and
   inventing them would fabricate exactly the evidence §4.4 exists to protect.
2. Unlabelled hours **fill no coverage cell and count toward no minimum**.
   `assert_section_8_1_coverage()` still fails on an interim corpus.
3. `Corpus.provenance.interim` propagates into the benchmark report's JSON, and
   `bench.decide_canonical` **refuses to switch the canonical model on interim data** no
   matter how large the measured gain. It will name a challenger worth testing properly;
   it will not move the pin. §1: "No model changes without measurement."
4. Durations are required from the source, never defaulted — a default would fabricate both
   the real-time factor and the hours figure.

What the interim set buys: proof the harness runs end to end on real Kurdish, and a place to
measure §4.1 collision incidence (D-013). What it does not buy: any threshold, any model
decision, or the closure of M0.

---

## D-013 · Measured: §4.1's table is missing a collision (U+06BE vs U+0647)

**Date:** 2026-08-06 · **Blueprint ref:** §4.1, §0 · **Type:** measured gap in the blueprint

Ran the §4.1 collision detectors over KLPT's bundled Sorani lexicon — 24,894 entries, 24,051
distinct forms. Full evidence: `evidence/collision-incidence.md`.

**0.84%** of entries are altered by normalization; **0.21%** of distinct forms merge with
another form, i.e. would have been two index entries that never match.

Every one of those merges came from a pair §4.1's table does not list: **`ھ` U+06BE ARABIC
LETTER HEH DOACHASHMEE against `ه` U+0647 ARABIC LETTER HEH** — 204 affected entries, in
ordinary high-frequency words (`دهۆک`/`دھۆک` Duhok, `جیهان`/`جیھان` world, `بەهار`/`بەھار`
spring). KLPT resolves it, so §4.1's mandate covers it in practice; the *table* does not
mention it, so nobody working from the blueprint would think to test for it.

The rule is **contextual**: KLPT rewrites `ھ`→`ه` inside a word and leaves an isolated `ھ`
untouched. Pinned by a test, because a library update changing it would silently shift every
index key without failing anything.

**Action taken:** `heh_doachashmee` added to the measured collision set. **Not** a blueprint
amendment — §4.1's normalization mandate already covers it via KLPT. Recorded so §4.1's table
can be corrected at the next revision.

**Honest limit on the number.** A curated dictionary is close to already-normalized, so
0.21% is a **floor**, not an estimate for real text. `ه`+ZWNJ and Arabic-keyboard `ي`/`ك`
scored zero here precisely because a lexicon does not contain typing artefacts — which is
where §4.1's other collisions actually live. The measurement worth acting on is the same
script over real transcripts, and that is blocked on M0.12.

---

## D-014 · Sentence-pause threshold and the completeness rule

**Date:** 2026-08-06 · **Blueprint ref:** §4.2, §5, §3 Stage 5 · **Type:** judgment call

§4.2 requires segmenting on "Kurdish punctuation *plus* VAD pauses" and names no pause
threshold. `DEFAULT_PAUSE_MS = 500` — a conversational sentence break rather than a breath.
It is a **parameter, not a constant to trust**: the right value comes from real Kurdish
conversational audio, which is M0.12. Both `segment_sentences` and its VAD input take it
explicitly so tuning is a call-site change.

**Why the pause path is not optional.** §4.2 warns that ASR punctuation for low-resource
languages is unreliable. If it is absent entirely — the realistic case for Kurdish
conversation — a punctuation-only segmenter returns one enormous sentence, §5's anchors
collapse onto the whole segment, and "a clip never starts or ends mid-sentence" stops meaning
anything while every test still passes. `test_punctuation_alone_would_have_returned_one_sentence`
exists to keep that failure visible.

**Completeness.** A sentence is complete when closed by punctuation or by a pause — the
speaker finished it. A trailing run of words that merely ran out of segment is a fragment
(`complete=False`). §5's contract: `sentence_complete == false ⇒ reject, never render`.

**`anchors_for` returns `None` rather than a best guess** when a selection contains no
complete sentence. §3 Stage 5: "If no sentence boundary exists within tolerance, extend to
the next one or reject the candidate." A plausible-looking anchor derived from a fragment is
exactly how a clip that starts mid-sentence reaches a client — the caller must decide to
extend or reject, and cannot do that if the anchor function hides the problem.

---

## D-015 · "Materially disagree" in §3 Stage 1's escalation rule

**Date:** 2026-08-06 · **Blueprint ref:** §3 Stage 1 · **Type:** judgment call

§3 Stage 1 routes to the validator "any segment where LLM-7B and CTC-3B disagree materially"
without defining materially. `DEFAULT_DISAGREEMENT_CER = 0.15` — normalized CER between the
two hypotheses. Measured after §4.1 normalization, so the two models typing the same Kurdish
with different keyboards is agreement, not a reason to spend the validator's 4 GiB.

A tunable awaiting real audio: the right value is whatever separates "the models heard
different words" from "the models spelled the same words differently", and that boundary is
empirical. Configurable per call.

**The quartile is relative, not a threshold.** Log-probability scales vary with audio and
model, so an absolute cutoff escalates everything on one recording and nothing on the next.
`len(scores) // 4` segments; with fewer than four there is no bottom quarter and confidence
escalates nothing, though disagreement still applies.

**The prohibition is enforced structurally.** §3 Stage 1: "Never escalate on duration or
word-count heuristics." `duration_s` is carried on `SegmentScore` for reporting and read by
no code path, and two tests assert that batches differing only in duration — or only in word
count — produce identical decisions. Length is the cheap proxy for difficulty and it is
wrong: 38 seconds of clean studio speech needs no validator; three seconds of overlapping
Slemani conversation does.

---

## D-016 · §2 index: field weighting and tokenization choices

**Date:** 2026-08-06 · **Blueprint ref:** §2, §4.1 · **Type:** judgment call

§2 mandates "BM25 + character 3-grams over the normalized transcript" without saying how the
two combine. Choices:

**Two separately scored BM25 fields, combined as `word + 0.5 × ngram`.** Both contributions
survive onto every `SearchHit`, so the balance is visible and tunable rather than baked into
one opaque number. 0.5 is set so an exact word match outranks pure morphological overlap
(`test_word_matches_still_outrank_mere_ngram_overlap`) while a clitic-attached variant is
still retrievable at all. A tunable awaiting §8.2's real candidates.

**N-grams are per word, with boundary padding** (`\x02word\x03`) rather than over the whole
string. Cross-word grams would match on accidental letter runs spanning a space; padding
means `کتێب` standing alone and `کتێب` heading `کتێبەکەم` share their interior grams but
differ at the trailing boundary — which is exactly the gradient that keeps exact matches
ahead of relatives.

**k1 = 1.2, b = 0.75** — Okapi's standard defaults, exposed as parameters. §8.2 tunes
retrieval against real candidates; convention is a starting point, not evidence.

**Queries are normalized too.** An index that normalizes its documents but not its queries
has §4.1's bug with extra steps. Asserted by
`test_encoding_differences_do_not_prevent_a_match`.

**Why this is not optional.** With word-level BM25 alone, querying the stem `کتێب` against a
document containing only `کتێبەکەم` scores **exactly zero** — measured, not asserted, in
`test_the_failure_section_2_describes`. §2's warning that "word-level matching misses
variants a human reads as identical" is the literal behaviour of the field without n-grams.

---

## D-017 · §5 contract: what the type enforces, and what it deliberately does not

**Date:** 2026-08-06 · **Blueprint ref:** §5, §3 Stage 3, §3 Stage 5, §4 · **Type:** judgment call

§5 gives a JSON shape. A shape in a document gets violated the first time two stages disagree
about a field and nothing notices until a client sees the output, so these rules are enforced
at construction:

- **`in_ms`/`out_ms` must equal the boundary's final points.** A span contradicting its own
  boundary block is a lie the renderer acts on.
- **The judge must be `routable`.** §4 marks `gemini-3.1-pro` "evaluated, not routed";
  recording it as a clip's judge would mean a model the blueprint keeps out of the path
  scored client output.
- **SV6D labels must cite a timestamp** (§3 Stage 3: "Reject output where a claim has no
  timeline evidence"). Accepted forms: `84.6s`, `84600ms`, `1:24`, `00:01:52` — the
  requirement is timeline evidence, not one house format.
- **Rejection is a type**, with `reject_reason` and `discovery_path` both required and a
  blank reason refused. §5: "That set is your only measure of recall", and §8.2 needs recall
  *per path* to justify the dual-path cost.

**Deliberately not enforced: `Boundary` does not self-validate.** `assert_boundary_invariant`
is the render gate §3 Stage 5 asks for, and a type that could not represent a violation would
give that gate nothing to catch. A boundary deserialized from another stage's JSON has to be
checkable on arrival — so `Boundary.from_dict` builds without validating, and the gate is
called explicitly.

**`editorial` and `output` are optional.** Stage 5 produces boundaries before Stage 4 has
scored anything; a clip mid-pipeline is a real state, not an incomplete record.

---

## D-018 · Caption font and the §4.3 dependency, with licences verified

**Date:** 2026-08-06 · **Blueprint ref:** §4.3, §7 · **Type:** dependency + licence check

§4.3.4 names Noto Naskh Arabic or Vazirmatn as safe starts and requires the font be
referenced via `fontsdir` rather than resolved by fontconfig on the render host. So the font
is a shipped asset, not a host assumption.

| Item | Version | Licence | Verified from |
|---|---|---|---|
| Noto Naskh Arabic Regular | 2.012 | **OFL-1.1** | the font's own `name` table, IDs 13/14 |
| `fonttools` | 4.60.2 | MIT | PyPI metadata; CVE-2025-66034 fixed |

OFL-1.1 permits commercial use and embedding; it requires the licence accompany the font, so
`assets/fonts/OFL.txt` ships beside it. The licence was read from the binary's name table
(`nameID 13` → "SIL Open Font License, Version 1.1"), not from a repository README.

**Coverage measured, not assumed.** Running §4.3.4's check against the shipped font:

```
Kurdish set ڕ ڵ ۆ ێ چ ژ پ گ ە  → full coverage
ه U+0647 present · ھ U+06BE present · ە U+06D5 present · ZWNJ U+200C present
```

`KURDISH_REQUIRED_GLYPHS` extends §4.3.4's list with **both heh forms**. `ھ` U+06BE is not in
§4.3's list, but D-013 measured it in 204 real lexicon entries — ordinary words like `دھۆک`.
A font missing it renders boxes in a city name.

---

## D-019 · §4.3: what is enforced, and the one part that is not

**Date:** 2026-08-06 · **Blueprint ref:** §4.3 · **Type:** implementation + honest gap

Five of §4.3's six requirements are enforced in code and tested:

1. `shaping=complex` always emitted, never `auto`.
2. libass + HarfBuzz + FriBidi verified from **both** `-buildconf` and linked libraries.
   Either source satisfies HarfBuzz/FriBidi, because a distro can link them through libass
   without an ffmpeg configure flag naming them — but libass itself must be in the build.
3. `ass`/`subtitles` only; `drawtext` never appears in a generated filter.
4. Font coverage asserted against the real shipped font.
5. `WrapStyle: 2` plus our own `\N` breaks from the word alignment.

**Not done: §4.3.6's golden reference PNG.** Generating it needs a real render on a build
whose libass is verified — this container has no ffmpeg (`BLOCKED.md` #5). The *comparison*
is implemented and tested, and a missing reference **raises** rather than passing: a golden
test that silently succeeds when its reference is absent is decorative, which is the exact
failure mode §4.3.6 exists to prevent.

**A filter-escaping detail worth naming.** An unescaped `:` in a path truncates the
filtergraph argument, and the filter then renders with default options — including
`shaping=auto`. So a path bug reintroduces failure mode #3 silently. `subtitle_filter`
escapes `\ : ' [ ] ,` and there is a test for it.

---

## D-020 · §8.2 metric definitions the blueprint leaves open

**Date:** 2026-08-06 · **Blueprint ref:** §8.2, §3 Stage 3 · **Type:** judgment call

**A retrieved candidate "found" a gold winner at temporal IoU ≥ 0.5** (`DEFAULT_IOU_MATCH`).
The usual temporal-localization convention; §8.2 names IoU as a metric but sets no matching
threshold. Below 0.5 a candidate shares a fragment of the moment without being the moment,
and counting it as a hit would inflate recall for a system that consistently cuts late.

**Per-path recall uses *all* gold winners as its denominator, not the path's own.** This is
the load-bearing choice. Grading each path only against winners it was "expected" to find
lets both paths score 1.0 while each finds half the moments — and §8.2 uses this number to
decide whether Path B earns GPU 0, a segmented 4B model, and the whole of §3's Path B. A test
names the choice explicitly, because the tempting alternative is subtly self-congratulatory.

**`path_unique_wins` answers the collapse question directly.** §8.2: "If Path B never
surfaces a winner Path A missed, collapse it." Zero unique wins is the answer that justifies
removing a path, so every path appears in the result including those scoring zero — an absent
entry reads as "not measured".

**Misleading-edit rate is measured over what ships**, not over all candidates. §8.2: "An
engaging clip that misrepresents the speaker is worse than no clip." A system that generates
a hundred misleading candidates and rejects them all scores zero, which is correct — nothing
misleading reached anyone.

**Ties in pairwise preference count half to each side** rather than being discarded. A tie is
evidence the two systems are close; dropping it inflates whatever margin remains.

**A per-source-hour figure over zero hours raises** rather than returning infinity. Zero
source hours is a corpus bug, not an infinite rate.

---

## D-021 · ffmpeg with a verified RTL stack — obtained, and what it closes

**Date:** 2026-08-06 · **Blueprint ref:** §4.3, §7 · **Type:** blocker resolved + licence check

`BLOCKED.md` #5 recorded that no ffmpeg was available, blocking §4.3.6's golden render. That
is now resolved, and the route matters for anyone reproducing it: `github.com` is denied by
this environment's proxy, but `raw.githubusercontent.com` and the **Git-LFS media endpoint**
are not. The plain raw URL returns a 134-byte LFS pointer; `media.githubusercontent.com`
serves the real 142 MB archive. `scripts/fetch-ffmpeg.sh` automates it and **refuses a build
lacking libass/HarfBuzz/FriBidi** rather than downloading something that cannot shape Arabic.

**Build:** `n8.0.1-48-g0592be14ff`, `--enable-libass --enable-libharfbuzz --enable-libfribidi`.
`assert_rtl_stack()` — written before any ffmpeg existed here — passes on its real
`-buildconf` output unchanged.

**Licence.** The build is `--enable-gpl --enable-version3`. §7 already lists the caption
stack as LGPL/GPL. ffmpeg is invoked as a **separate executable** via `subprocess`, which is
the standard arrangement and does not place this project's source under the GPL. The binary
is **not committed** (~200 MB, `.ffmpeg/` is git-ignored). Bundling a GPL binary into a
shipped product is a different question from invoking one, and is flagged here rather than
decided: confirm before any distribution that includes the binary.

**Measured finding — `auto` matched `complex` exactly on this build.** Recorded in
`evidence/rtl-shaping.md`. This is *why* §4.3.1 forbids relying on `auto`, not evidence
against it: on a build with HarfBuzz, `auto` resolves to complex and the output looks
perfect, so a developer testing there concludes `auto` is fine and ships code that breaks on
a host whose libass lacks HarfBuzz. The explicit setting is the difference between
correctness that happens to hold and correctness that is stated.

**The negative control is load-bearing.** `test_simple_shaping_fails_the_golden_test` renders
with `shaping=simple` and requires the comparison to fail. Without it, the golden test could
pass while measuring nothing, and `shaping=complex` would be cargo cult rather than a
requirement.

**Pixels, not bytes.** The comparison decodes both images to RGB24 through ffmpeg. A PNG
encoder change between versions would otherwise fail a render that looks identical — and a
golden test that cries wolf gets disabled, which is exactly how the regression §4.3.6 warns
about eventually ships.

---

## D-022 · Model provisioning: registry-driven, and sources are never guessed

**Date:** 2026-08-06 · **Blueprint ref:** §7, §3 Stage 0, §6 · **Type:** infrastructure + honest gap

**The fetcher reads §7.** `scripts/fetch-models.sh` enumerates what to download from
`registry.REGISTRY`, not from a list in the script. It therefore cannot fetch a model the
blueprint excludes, cannot silently skip one it requires, and calls
`assert_commercially_usable` before a single byte moves — NonCommercial is refused at
download time, not merely at use time.

**Provisioning is classified per component**, because it is not uniform and pretending
otherwise misleads an operator. Of §7's fifteen entries: 3 arrive with a pip package,
1 is our own code, 2 are cloud APIs needing credentials rather than disk, 1 is a system
library, and **8 are multi-gigabyte checkpoints**. Only the last group can be "missing" in a
way that stops a stage. Silero VAD in particular **ships its ONNX model inside the wheel** —
treating it as a download would send someone hunting for something already present.

**Four sources §7 fixes; four it does not — and those are refused, not guessed.** §7 names
`pyannote/speaker-diarization-community-1`, `rzgar/qwen3-asr-sorani-kurdish-ckb-v1`,
`MCG-NJU/VideoChat3-4B` and `MCG-NJU/TimeLens2-4B` in unambiguous `org/name` form, and those
are used directly. `omniASR_LLM_7B_v2`, `omniASR_CTC_3B_v2`, `Qwen3-VL-Embedding-2B` and
`Qwen3-VL-Reranker-2B` are **checkpoint names, not repository ids**. A plausible-looking
guess (`facebook/omnilingual-asr`, `Qwen/Qwen3-VL-Embedding-2B`) would be a fabrication that
fails as a 404 on hawapc01 with nothing in the code to explain it. They require an explicit
entry in `models/sources.json`, and the script prints exactly what to add.

**Capacity is checked before the download, not during.** The §7 checkpoints total roughly
50 GB. This container has ~22 GB free, so it could not hold them even if Hugging Face were
reachable — worth knowing before an hour is spent finding out.

**Gated repos are handled explicitly.** §3 Stage 0 flags Community-1 as gated and asks that
acceptance be built into deployment automation. Without `HF_TOKEN` the script skips it with
the reason and continues, rather than failing the whole run.

**Still blocked here:** `huggingface.co` is denied by this environment's proxy
(`BLOCKED.md` #6), so no checkpoint could be downloaded. The provisioning path is built and
exercised end to end — enumeration, licence refusal, capacity check, gated-repo skip, and a
real `snapshot_download` attempt that fails on the network exactly as it should.
## D-023 · Shot detection runs on the source, not the 1 fps proxy — measured

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 0, §3 Stage 5 · **Type:** implementation choice

§3 Stage 0 produces a `fps=1` proxy and lists PySceneDetect in the same stage, which reads as
an invitation to detect on the proxy — it is smaller, and that is what a proxy is for. §3
Stage 5 then matches a candidate boundary against a shot cut within a **400 ms** window.
One frame per second cannot express 400 ms, so the two requirements are incompatible.

Measured on `tests/fixtures/kurdish-speech-3cuts.mp4` (three 1.4 s segments concatenated, so
the cuts are at 1400 ms and 2800 ms by construction):

| Detected on | Cuts found | Error vs ground truth |
|---|---|---|
| source | `(1400, 2800)` | **0 ms, both** |
| 1 fps proxy | `()` | both cuts **missed entirely** |

Worse than predicted. The expectation was quantisation to whole seconds — a ±500 ms error,
already past Stage 5's tolerance. What actually happens on a 1.4 s cadence is that
ContentDetector's frame-to-frame comparison has too few frames to fire at all, so the proxy
yields no cuts rather than coarse ones. Stage 5 would then never match a shot cut, and the
whole soft-signal term would silently contribute nothing.

**Decision:** `detect_shots` takes the source. The proxy stays for keyframe and visual work
(Stage 2), which is what §3 Stage 0's 1 fps is sized for. The cost is decoding the full-rate
video once; on the §6 hardware that is CPU-parallel across files and not on the GPU path.

**Guard:** `tests/test_ingest.py::test_detecting_on_the_proxy_is_coarser_than_stage_5s_tolerance`
runs both and fails if the proxy ever becomes as good as the source — which would mean this
decision needs revisiting rather than silently costing decode time for nothing.

---

## D-024 · §3 Stage 0's media stack — licences audited, and why it is a separate extra

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 0, §7 · **Type:** new dependencies

Both models are named in §7 (PySceneDetect for shot detection, Silero VAD for speech), so
this adds no model the blueprint does not permit. Licences, read from the installed
distributions rather than from memory:

| Package | Version | Licence | Source of the reading |
|---|---|---|---|
| `scenedetect` | 0.6.5 | BSD-3-Clause | `dist-info/LICENSE` (the PyPI classifier says MIT and is wrong — the licence text is authoritative) |
| `silero-vad` | 5.1.2 | MIT | classifier; weights ship inside the wheel, no separate download |
| `onnxruntime` | 1.20.1 | MIT | metadata |
| `torch` | 2.13.0 | BSD-3-Clause | `dist-info/licenses/LICENSE` |
| `numpy` | 2.2.1 | BSD-3-Clause | classifier |

**NonCommercial: none.** A naive scan of installed metadata flags numpy, which is a false
positive worth recording so nobody "fixes" it later: the word *noncommercially* appears in
the GPL-with-runtime-exception text of `libquadmath`, vendored into the manylinux wheel. It
is not numpy's licence and it is not a NonCommercial term. Note separately that redistributing
that wheel inside a binary product carries an LGPL obligation — irrelevant today, relevant the
day anything here is shipped as a bundle.

**Deviation:** these are an optional extra (`.[media]`), not core dependencies. torch is ~2 GB
and nothing outside Stage 0 imports it; making it mandatory would put a multi-gigabyte
download in front of the §4.1/§4.2/§4.3/§8.1 work, all of which is pure Python. CI installs
CPU wheels (`--extra-index-url .../whl/cpu`), which §6 justifies independently: Stage 0 is
CPU by design.

**The cost, stated plainly:** an optional extra means the Stage 0 tests *skip* when it is
absent, and a skipped test is the same quiet green this audit was about. So CI installs the
extra and then fails if `tests/test_ingest.py` reports any skip at all.

---

## D-025 · The 2026-08-07 audit — what it found and what changed

**Date:** 2026-08-07 · **Type:** external review, ten findings

An external audit reported ten release-blocking findings. Seven reproduced exactly as
described and were fixed with regression tests (`tests/test_audit_regressions.py`,
`tests/test_gate.py`, `tests/test_gate_evidence.py`, `tests/test_claims.py`). Recorded here
because the pattern matters more than the individual bugs.

**Findings, and the reproduction:**

| # | Finding | Reproduced | Fix |
|---|---|---|---|
| 1 | README overstates: no runnable product | yes | README opens with what does not exist; `tests/test_claims.py` pins it |
| 2 | A challenger failing a whole dialect scored as if the dialect were absent | yes | missing dialects are regressions by name; incomplete coverage blocks promotion |
| 3 | Render/QC gate bypassable by absence | yes | `assert_renderable` refuses `None`; `from_dict` demands real JSON booleans |
| 4 | RTL check certified a build with `--disable-libass` | yes | flag parsing replaces substring search |
| 5 | Gate not authoritative: CRLF, `echo` bypass, CI never ran it | yes, all three | `.gitattributes`; steps not configurable; junit-report evidence + ratchet; `hawedit.yml` |
| 6 | Corpus serialization dropped `reference_words` | yes | serialized and restored |
| 7 | Karaoke drifted by every pause; golden test compared bytes | yes | `\kf` spans tile the line; comparison decodes to pixels |
| 8 | Registry membership mistaken for role | yes | `resolve_role`; PySceneDetect can no longer be an ASR model |
| 9 | `media_id` reached the filesystem unchecked | yes | path validation + `O_CREAT\|O_EXCL` |
| 10 | Premature DONE claims | yes | `PARTIAL` status introduced; M0.3, M0.10, M1.3 corrected |

**The common cause, worth naming:** eight of the ten were a check that accepted the *shape*
of an answer without checking its *content*. Substring instead of flag (#4). Truthiness
instead of boolean (#3). Membership instead of role (#8). Absence instead of refusal (#3).
Exit code instead of report (#5). Metric instead of measurement (#10). Each looked like a
check and was one, but of the wrong thing — and a wrong check is worse than none, because it
reads as coverage.

**What the audit says about the gate:** every one of these passed the gate. The gate was
green through all ten. That is the finding behind finding #5, and it is why the fix there is
structural — evidence rather than exit codes, CI rather than one laptop — rather than another
rule to remember.

**Not fixed here:** making the CI job a *required* status check on the protected branch. That
is a repository setting only Hawa can change, and until it is set, a red `hawedit` job does
not block anything. Added to `BLOCKED.md`.

---
## D-026 · §4.1's fifth collision closed — conjunctive `و`, as a refusal not a prediction

**Date:** 2026-08-07 · **Blueprint ref:** §4.1 · **Type:** closes the gap recorded in D-003

D-003 measured that KLPT's `normalize()` covers four of §4.1's five collisions and left the
fifth — the conjunction `و` typed onto the preceding word — unimplemented, because §4.1 only
says "AsoSoft applies a separation algorithm" and correct separation needs a lexicon. That
reasoning was right and is now satisfied: KLPT ships a Sorani hunspell dictionary, and its
`check_spelling` is morphology-aware, so the evidence exists in a dependency already present
for §4.1 anyway. No new dependency, no new model, nothing added to §7.

**The rule:**

    split `و` + R  →  `و` R    only if   R is a valid Sorani word   AND   `و`+R is not.

Stated as a refusal rather than a prediction. Both conditions are load-bearing: without the
first, every `و`-initial token gets split; without the second, `وتار` ("article") becomes
"and tar" — a word nobody said, written into `transcript.norm.json`, which every index,
embedding and model input reads under Kurdish invariant #3.

**The bias is deliberate and one-directional: under-split, never mis-split.** A joined `و`
left alone costs recall in the §2 index, and §2's character 3-grams absorb part of that. A
real word torn in half costs correctness, and nothing absorbs it. Where the evidence is
ambiguous the rule declines — including on D-003's own example, `وتو`, where neither reading
has lexicon support.

**Measured over all 24,894 dictionary entries** (`evidence/waw-separation.md`):

| | |
|---|---|
| dictionary words damaged | **0** |
| joined forms recovered | 24,124 of 24,390 — **98.91%** |
| `و`-initial words that can never be split | 19 (`وتار`, `وشە`, `ویست`, …) |

The safety claim is checked exhaustively over the whole dictionary, not by example, in
`tests/test_waw.py::test_no_dictionary_word_is_ever_split`. That property had to hold before
this could be turned on at all.

**The 1.09% shortfall has a single named cause,** and it is not this rule: all 266 forms
contain a bare medial `ه` (U+0647) or `ھ` (U+06BE), which KLPT's spell checker rejects from
its own dictionary. That is D-013's finding — §4.1's collision table lists `ه`+ZWNJ → `ە` and
says nothing about bare medial `ه` or U+06BE — arrived at from the opposite direction. Two
instruments agreeing on the same gap is worth more than either alone.

**Ordering:** separation runs *after* KLPT's encoding fixes inside `normalize_sorani`. A
dictionary lookup on unnormalized text fails for exactly the reason §4.1 exists, so separation
would silently never fire on the text that most needs it. Asserted in
`test_normalization_runs_the_encoding_fixes_before_the_lexicon_lookup`.

**What this does not establish:** anything about running Kurdish speech. The dictionary is a
word list. Real incidence, and the recall the §2 index actually gains, need the labelled
corpus (`BLOCKED.md` #1, #6).

**Consequence for the ledger:** M0.3 moves PARTIAL → DONE, the first of audit #10's two
corrected rows to be genuinely closed rather than merely re-labelled. M0.10 stays PARTIAL —
it needs weights and audio, not code.

---
## D-027 · §3 Stage 6 render — what it does, and what it refuses to call itself

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 6, §4.3, §6 · **Type:** implementation choice

§3 Stage 6 is one sentence — "Reframing, captions, encode" — and each of the three has a
failure mode that produces a perfectly playable file.

**Reframing.** §3 Stage 6 tracks the active speaker from diarization plus face detection.
Neither is available (`BLOCKED.md` #4), so what is implemented is a static centre crop. The
choice recorded here is that it is **named** rather than implied: `Reframe.STATIC_CENTRE`
travels on every `RenderResult`, and `Reframe.SPEAKER_TRACKED` exists as a value this module
cannot currently produce. A centre crop that called itself reframing would look correct in
every artifact and be wrong on every two-shot, and no consumer could tell the difference.
`crop_filter(focus_x=...)` is the seam the tracking path plugs into, and it is tested before
it exists so that landing tracking is a caller change rather than a rewrite.

**Captions.** Burn-in goes through `captions.subtitle_filter`, which hard-codes
`shaping=complex` and an explicit `fontsdir` (§4.3.1, §4.3.4). Verified on decoded pixels
rather than on the absence of an error: the shipped render is compared against the same frames
with no subtitle filter (they must differ — otherwise libass drew nothing) and against a
`shaping=simple` render (they must differ — otherwise shaping is not reaching libass).

**Encode, and a measurement worth recording.** `encoder_available` originally read
`ffmpeg -encoders`, which is a list of what was *compiled in*. Measured on the pinned static
build: it lists `h264_nvenc` and **cannot encode a single frame with it**, because NVENC is
loaded at runtime and there is no NVIDIA driver. Worse, that failing run **exits 0** when the
output is `-f null`, so neither the listing nor the exit code answers the question. The probe
now encodes one 64×64 frame to a real file and checks bytes came out.

This is §4.3.2's lesson — "a build accepting the option may still lack the backing library" —
holding for encoders as well as for shapers, and it is the same shape as audit finding #4:
reading the shape of an answer instead of its content. The blueprint stated the principle
about libass; it generalises, and the generalisation was worth a test.

`render_clip` refuses an unusable encoder rather than substituting one. §6 puts NVENC on
hawapc01; getting x264 instead would make any throughput figure quietly a measurement of the
wrong encoder.

**The gate runs first.** `Clip.assert_renderable()` is called before ffmpeg is even located,
so Kurdish invariant #2 and §2's QC-before-output rule are enforced at the last point before a
client could see the file, not only at the contract boundary. A refused clip leaves no
artifact behind, which is asserted rather than assumed.

**Consequence for the ledger:** M2.4 DONE (`evidence/m2-4-rendered-clip.md`), M3.3 PARTIAL —
the encode runs, the reframe is not the one §3 specifies.

---

## D-028 · A resolved blocker is not a blocker — caught by test, not by reading

**Date:** 2026-08-07 · **Type:** process defect found by the audit's own remediation

`BLOCKED.md` #5 (an ffmpeg with libass + HarfBuzz) was resolved on 2026-08-06 and recorded as
such. M2.4 stayed marked `BLOCKED` behind it for two days, and the work — which was the entire
M2 vertical slice deliverable — sat available and looked impossible.

This is audit finding #10's shape pointing the other way. #10 was work that was incomplete and
looked done; this is work that was ready and looked blocked. Both are the same defect: a status
that stopped tracking reality. The first costs trust, the second costs time, and neither is
visible by reading the file, because both look perfectly consistent.

`tests/test_claims.py::test_every_blocked_row_points_at_a_live_blocked_entry` now fails when a
row marked BLOCKED cites only blockers whose `BLOCKED.md` heading says RESOLVED. Entries keep
their headings after resolution — the record of what was in the way is worth more than a tidy
file — so "resolved" is a property of the heading rather than of its absence, and the test
reads it that way.

**The general rule this session keeps arriving at:** every claim in a state file that a test
can check should be checked by one. Prose does not drift because anyone is careless; it drifts
because nothing fails when it does.

---
## D-029 · §3 Stage 3 merge — what "union, never intersect" costs to get right

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 3, §8.2 · **Type:** implementation choice

§3 calls Stage 3 "the most important structural decision in the system" and states the rule in
four words. The four words are easy; the implementations that satisfy them on small examples
and destroy candidates on real input are not. Four decisions, each against a plausible
alternative.

**Overlap is measured against the anchor, never against a growing group.** Grouping by
transitive closure — V1 overlaps X, X overlaps V2, therefore all three are one moment —
produces a merged candidate spanning more time than anything either path proposed. Measured
on the fixture in `test_overlap_does_not_chain_across_a_shared_neighbour`: V1 (0–4000) and X
(1000–5000) match at IoU 0.60, X and V2 (2000–6000) at 0.60, V1 and V2 at 0.33. Union-find
returns one candidate 0–6000; this returns two, neither longer than 4 s. That bug looks correct
in every small test, which is why the fixture asserts all three IoUs before asserting the
result.

**A merged candidate keeps the anchor's span, not the union of the spans that agreed.** §3
Stage 5 owns boundary fusion. Widening here would decide something Stage 3 has no evidence for
and would quietly break §8.2's IoU matching against gold — a candidate stretched to cover both
paths' guesses matches neither gold span.

**A path never dedupes itself.** Two overlapping candidates from Path A are two moments the
Kurdish judge chose to emit. Collapsing them is this module overruling a path on its own
output. Only cross-path grouping happens here, which also means the "no chaining" guarantee is
structural rather than a special case: a visual candidate is claimed by at most one verbal
candidate, in rank order.

**No cross-path score is invented.** Path A's score is an editorial judgment from the Kurdish
judge; Path B's is retrieval similarity. There is no defensible arithmetic between them, and
producing one would be exactly the mistake §3 Stage 1 warns about with published RTF figures —
a number that looks comparable and is not. `verbal_score` and `visual_score` stay separate and
are `None` when that path never saw the candidate. A fused ranking is a §8.2 tuning question
against the labelled set (`BLOCKED.md` #1), not something to guess.

**The grouping threshold defaults to §8.2's own `DEFAULT_IOU_MATCH` (0.5).** Not for
convenience: grouping at one threshold while §8.2 scores at another would measure a system
other than the one the merge produced. It is a parameter so §8.2 can tune both together.

**Why build this with neither producer available.** Path A needs Gemini credentials and the §3
governance decision (`BLOCKED.md` #3); Path B needs `VideoChat3-4B` weights and a GPU
(`BLOCKED.md` #2). But the merge is where the structural decision actually lives, and it is
testable in full without either — the four rules above are properties of the union, not of the
models. Landing either producer is now a matter of emitting `Candidate`s.

**What this does not establish:** anything about candidate quality, recall, or whether the dual
path earns its cost. Those are §8.2 questions and they need the labelled set. What is
established is that the merge cannot be the thing that loses a candidate.

---
## D-030 · §3 Stage 4 lists two judge outputs §5's frozen contract has no cell for

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 4, §5 · **Type:** discrepancy inside the
frozen blueprint — recorded, not resolved. **Needs Hawa.**

§3 Stage 4 states the judge's outputs:

> hook strength · self-containment · **payoff location** · meaning fidelity ·
> misleading-edit risk · cultural landing · Kurdish title, description, **hashtags**

§5's JSON contract carries `hook_score`, `self_contained`, `meaning_fidelity`,
`misleading_edit_risk`, `cultural_landing`, `narrative_role`, `judge`, `sv6d` in `editorial`,
and `title_ckb`, `description_ckb` in `output`. There is no cell for **payoff location** and
none for **hashtags**. `narrative_role` is the nearest thing to the first and is not it — it
records *that* a clip is a payoff, not *where* the payoff lands.

**Not resolved here, because §5 is frozen and adding fields to it would be redesigning the
architecture.** What is done instead:

* `JudgeVerdict` carries the full §3 Stage 4 list, including `payoff_at_ms` and
  `hashtags_ckb`. Nothing the judge produces is discarded at the point of production.
* `to_editorial()` and `to_output()` project onto §5's blocks, and the projection is lossy in
  exactly those two fields. The loss happens in one named place with a docstring on it and a
  test asserting which fields do not survive, instead of being a field nobody noticed was
  missing.

**`payoff_at_ms` is validated even though it does not ship:** it must fall inside the clip. A
payoff outside the cut is not a payoff, it is evidence the judge scored a different span than
the one being rendered — and that is worth catching whether or not the value travels.

**The question for Hawa:** does §5 gain two fields, or is §3 Stage 4's list aspirational? Both
are defensible; only one of them is what the client artifact should contain. Until it is
answered, the payoff location and hashtags exist in the pipeline and stop at §5's boundary.

---

## D-031 · §3 Stage 4's four warnings, made enforceable

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 4 · **Type:** implementation choice

Stage 4 is entirely a hosted model, so the buildable part is the contract — which is also where
§3 puts most of its warnings.

**"Evaluated, not routed", enforced at three points.** `route()` refuses `gemini-3.1-pro`;
`JudgeVerdict.to_editorial()` refuses it again; §5's `Editorial` refuses it a third time. Three
rather than one because a verdict can arrive at §5 as deserialized JSON that never passed
through the other two. What is *not* refused is constructing a shadow verdict at all — the
first draft did that, and it was wrong: the shadow is *evaluated*, so refusing to build its
verdict would make "switch only when 3.1 Pro beats 2.5 Pro" unenforceable for want of a 3.1 Pro
result to compare. Routability is a question about shipping, not about existing.

**"Empirical beats newer", as three refusals.** `decide_judge` will not promote on an empty
regression set (promotion on nothing is precisely the reasoning §3 exists to prevent), will not
promote on a tie (a tie is not beating), and will not promote on fewer than 20 items (a
one-item margin is noise). The 20 is a judgment, not a blueprint figure, and it is a parameter
so §8.2 can raise it against real data.

**The signature takes no date.** §3: the October 2026 deprecation applies to Vertex AI rather
than the Developer API, and this is "a managed migration with a shadow test, not a deadline". A
`decide_judge(..., deprecation_date=...)` would encode the reading §3 explicitly rejects, so a
test asserts no parameter of `decide_judge` is date-shaped.

**The 200K ceiling is arithmetic.** §3's with-video figure is ~360K tokens per source hour
against "keep each request under 200K tokens to stay on the lower Pro price tier" — so the most
expensive mode is also the one that cannot be a single request. §3 already prescribes the fix
(20 × 60 s segments); `assert_within_tier` makes skipping it loud. A request whose token count
is `None` is refused too: "unmeasured is None", and None is not "small enough".

**"Don't pay the judge twice."** `JudgeRequest.for_survivor` carries Path A's score forward and
refuses `PATH_A_DISCOVERY` for a candidate that already has one. That mistake produces a larger
bill and a correct-looking result, which is exactly why nothing else would catch it.

**One addition §3 does not ask for, added anyway.** The Kurdish title, description and hashtags
are refused if they contain no Arabic-script characters. It is the quietest way this system can
fail a Kurdish client: every type downstream accepts a `str`, so a judge answering in English
produces a clip that renders, uploads and reads as finished work in the wrong language. The
check is deliberately weak — "plausibly Kurdish", not "good Kurdish" — because the failure it
exists to catch is total. The fields are also §4.1-normalized on the way in, since an
unnormalized title makes the clip unfindable by its own name in the §2 index.

**Cost figures are back-solved from §3's own table** (20K tokens ≈ $0.04, 360K ≈ $0.72) rather
than from a published price list, so this project's cost claims and the blueprint's cannot
drift apart. It is an estimate and is named as one — the authority on the bill is the bill.

---
## D-032 · The runner reports what it could not do, and that is most of its value

**Date:** 2026-08-07 · **Blueprint ref:** §3, §1 · **Type:** implementation choice

Until now every stage worked and nothing joined them, so "does this system work" was a
question you answered by reading a test suite. `python -m hawedit.pipeline VIDEO.mp4` is the
thing you point at a video.

Three of §3's stages need models this machine does not have. A runner that quietly skipped them
would print a clip path and exit 0, and you would have to already know that no model discovered
that clip to understand what you were looking at. So:

* every stage yields a result **or** a `StageSkipped` naming its blocker — never an empty
  result, the same rule that keeps `IngestResult.diarization` at `None` rather than `[]`;
* `PipelineRun.complete` is false whenever anything was skipped, **even on a run that rendered
  a clip**;
* the CLI exits non-zero on an incomplete run, because that is what a shell script checks.

**Two stand-ins, and the second one was a discovery.** Supplying a transcript for Stage 1 was
the plan. Supplying a *verdict* for Stage 4 was not: the first runner built a clip, called
`render_clip`, and got a refusal — `Clip.assert_renderable` rejects a clip with no editorial
block, because an unjudged clip has no meaning fidelity and no misleading-edit risk and §8.2
calls the second the metric that matters for a media organisation. That is audit finding #3's
fix reaching all the way out to the runner, and it was tempting to route around it. The right
answer was the symmetric one: Stage 4 gets a stand-in exactly as Stage 1 does, and without one
the runner builds a clip and stops. A test asserts the stop.

**The joins are the point, not the stage list.** §3 Stage 5 fuses against the shot cuts Stage 0
detected on *that* video, and §4.2 segments against the VAD pauses from the same run — not
against fixtures. A pipeline whose stages each work on their own test data is a test suite with
a `main()`; the value here is that Stage 0's real output is Stage 5's real input.

**The runner adds no invariants and weakens none.** Every Kurdish invariant is enforced by the
module that owns it: the transcript goes through `TranscriptStore` so #1 governs it, the index
reads the normalized artifact so #3 holds, `fuse_boundary` constructs #2, and the render gate
runs before ffmpeg is located. A second run over the same work directory reads the existing raw
transcript rather than overwriting it — invariant #1 has no exception for "the same pipeline,
again".

---
## D-033 · §5 gains two optional fields — BLOCKED #8 answered

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 4, §5 · **Type:** contract decision,
delegated by Hawa ("u choose best for me")

D-030 recorded that §3 Stage 4 lists *payoff location* and *hashtags* among the judge's
outputs while §5's contract has no cell for either, and refused to pick a reading. Hawa
delegated the choice. **§5 gains both.**

**Why that way round.** Hashtags are not decoration on a video-repurposing product — a Kurdish
title and description with no hashtags is an incomplete social post, and the whole system
exists to produce social posts. Payoff location is operationally useful in a way
`narrative_role` is not: `narrative_role` records *that* a clip is a payoff, while an editor
choosing a thumbnail or trimming a variant needs to know *where* the payoff lands.
"Aspirational" would have meant §3 listing an output nothing consumes, which is the less
plausible reading of a section that is otherwise precise.

**Where each lands.** `payoff_at_ms` in `editorial`, because it is a judgment. `hashtags_ckb`
in `output`, beside the title and description it ships with. Splitting them by kind rather
than putting both in one block keeps §5's two blocks meaning what they meant.

**Both are optional, and that is the load-bearing part.** A required field would make every §5
document written before today unreadable — a migration rather than an addition. §5 is a
contract other stages deserialize, so an addition that breaks readers is not an addition. A
test loads a pre-change `editorial` and `output` payload and asserts they still parse, with
`payoff_at_ms` as `None` (unmeasured, not "at zero") and `hashtags_ckb` as `()` (genuinely
none, because a post with no hashtags is a real deliverable).

**What I did not do:** edit `BLUEPRINT.md`. It is frozen and implementation work does not
touch it. §5's document still shows the old cells, so **the blueprint needs Hawa's amendment
to make this official** — until then the code is ahead of the spec, deliberately and in one
recorded place rather than silently.

---

## D-034 · Credentials: three refusals, not a config file

**Date:** 2026-08-07 · **Type:** implementation choice

A key is the one piece of configuration that is actively dangerous to get slightly wrong, so
`credentials.py` is built around refusals rather than convenience.

**It refuses to write a key anywhere git tracks.** Before writing it asks `git check-ignore`
and stops if the answer is no. `AGENTS.md`'s "never commit secrets" is a rule someone has to
remember; this is the same rule as a check. A key in a commit outlives its own revocation —
rotating it does not remove it from history, and anyone who cloned in between still has it.

**It refuses to store a key it has not verified.** A revoked key and a working key are the
same string shape, so a format check buys nothing. Google answers a bad key with a clear 400
and listing models bills nothing, so validation is a live call. A key that does not work is
worse than no key: it turns a clear "not configured" into a failure inside the first client job.

**It never prints the key.** Not on success, not in an exception, not in the status line — the
panel shows the last four characters and nothing else. Two tests assert that the API's own
error messages do not contain the key, because an error carrying a credential is how secrets
reach log aggregators.

**No `--key` flag.** Command-line arguments are visible in `ps` to every user on the machine.
Input goes through `getpass`, so it is never echoed and never enters shell history. Reading is
layered — environment first, then `.env` — so CI and a laptop differ without either being a
special case.

---

## D-035 · The real Gemini judge, and what it does not trust

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 4, §3 Stage 3's governance box ·
**Type:** implementation

`generativelanguage.googleapis.com` is reachable from this environment — measured, not assumed
— so §3 Stage 4's judge is now implemented rather than only contracted. `judge.py` stays the
contract; `gemini.py` is one implementation of it, and nothing above it knows the provider.

**Structured output, not prompt-and-parse.** The request carries `responseSchema` and asks for
`application/json`. "Reply in JSON please" plus a parser is how a stage acquires a 1% failure
rate that only appears in production. A response that does not match is `JudgeUnusable`, never
a partially-filled verdict.

**Token counts come from `countTokens`.** §3's 200K tier ceiling is about money, and
`assert_within_tier` refuses a request of unknown size. Google counts for free, so estimating
here could only be wrong about the bill. The count happens *before* the billed call, so an
over-ceiling request costs nothing.

**`temperature=0.0`.** §8.2 compares judges against a regression set. A judge that disagrees
with itself makes that comparison measure sampling noise rather than model quality.

**The model is the least trusted source in the system, not the most.** Every check in
`JudgeVerdict` applies to its output exactly as to a hand-written verdict: Kurdish script on
the title, description and every hashtag; the payoff inside the clip; scores in range. The
English-title test is the important one — every type downstream accepts a `str`, so a judge
answering in English produces a clip that renders, uploads and reads as finished work in the
wrong language.

**Retries are bounded and only transient.** 429 and 5xx retry with backoff; a 400 does not,
because retrying a malformed request bills three times for one mistake.

**§3's governance box is a value, not a paragraph.** `Governance(confidential=..., 
zero_data_retention=..., confirmed_by=...)` refuses to upload material marked confidential
without ZDR configured *and* someone recorded as having confirmed it — §3 asks for a
confirmation, and an unattributed one is not one. `BLOCKED.md` #3's second half is still open:
having a key does not answer whether ZDR is configured for COMMS and KAAE material.

---
## D-036 · Path A sends everything, and refuses to split

**Date:** 2026-08-07 · **Blueprint ref:** §3 Stage 3 · **Type:** implementation

`discovery.py` built the union and had no producers. Path A is the first, and it exists now
for a measured reason: `generativelanguage.googleapis.com` is reachable from this environment
while `huggingface.co` is still 403 at the gateway — so the half of Stage 3 that needs a hosted
model is the half that can be finished, and the half that needs weights is not.

**"Not a filtered subset" is the whole design, and implementing it means refusing things.**
Every temptation in this module is to send less: sample the transcript, drop the quiet stretches,
skip whatever the §2 index scored low. Each would be invisible in the output — the candidates
that came back would still look reasonable — and each reintroduces exactly the failure §3 spends
a paragraph on. So the prompt carries the transcript entire, and a test asserts that specific
fragments from the start, middle and end all reach the judge.

**A too-long transcript is refused, not split.** §3's own figures put the one-request ceiling at
roughly ten source hours (20K tokens/hour against a 200K tier ceiling). Splitting would be this
module deciding which parts of a ten-hour transcript the Kurdish judge gets to read — the
decision §3 forbids — so it raises with the arithmetic instead. If splitting is ever right, it
is a blueprint decision, not an implementation convenience.

**Word timings go with the text.** Without them a language model has no way to answer in
milliseconds and will guess. The timing table truncates only at a size that would itself blow
the budget, and the truncation is stated in the prompt rather than silent.

**Every returned span is checked against the transcript's own range.** A model asked for
millisecond boundaries will occasionally invent one past the end of the media, and such a
candidate would reach Stage 5 as a boundary to fuse rather than as a mistake to reject.

**Ranks are dense and ordered by score, ties broken on start time.** §8.2 counts Recall@K by
rank; a gap or a duplicate makes every K mean something slightly different, and a re-run that
reshuffles makes a reviewed candidate list untrustworthy.

**Composition, not inheritance.** Path A is not a `judge()` implementation — it returns
candidates, not a verdict — but it shares §7 routing, credentials, retry and governance with
the Stage 4 judge. Duplicating those is how two code paths end up with two different governance
checks, and the governance check is the one with legal consequences.

**The union now runs one-sided, and that is correct rather than degraded.** Path B has no
producer. §3: "Union, never intersect. Candidates from either path proceed." A verbal-only run
is precisely the case the dual path exists to protect.

---

## D-037 · Stage 2's visual index: four §3 sentences turned into arithmetic

**Decision.** `visual_index.py` implements §3 Stage 2's visual half as checks rather than as
comments, and refuses in four places where the convenient behaviour would be silent.

**1 · `fps` lives on the window, and may not fall below 1.0.** §3 gives the reference settings
as "~1 fps with a maximum of 64 frames". Those are one setting. A 180 s scene sampled at
0.35 fps is 63 frames — under the ceiling — and the embedding that comes back has the right
dimension and the right norm while describing a third of the footage the published retrieval
numbers were measured on. Measured, not reasoned: `math.ceil(180_000 * 0.35 / 1000) == 63`.
So the rate is refused rather than the count silently traded away, which forces the caller to
do what §3 says in the same sentence — "segment before embedding".

**2 · Long scenes split evenly, not into full windows plus a remainder.** 65 s would otherwise
become 64 s + 1 s, and that 1 s window embeds a single frame as a whole scene, then competes
for retrieval slots on equal terms with windows built from sixty-four. Even split: two 32.5 s
windows.

**3 · A zero vector is refused, not scored 0.0.** Cosine similarity against a vector with no
direction is undefined. Returning 0.0 would be this system's oldest mistake — "unmeasured is
`None`, never 0.0" — in numeric form, and would make the scene invisible to every query
without reporting anything. A NaN component is refused for the same reason from the other
direction: NaN compares `False` against everything, so the scene sinks below all others
permanently and silently.

**4 · Below the survivor floor the retrieval refuses instead of shortening.** §3 fixes the
count at 5–10. A three-scene video cannot satisfy it. The alternative considered was returning
whatever exists; rejected because §8.2 counts Recall@K on this list, and three results in a
column that says five is a number that does not mean what the column says. `rerank_and_keep`
raises and names both figures.

**What the reranker may and may not do.** It may reorder and it may score. It may not add a
window that was not retrieved, return one twice, drop below the survivor count, or restate the
`retrieval_similarity` it was handed — that field is the evidence that lets §8.2 ask whether
reranking changed anything, and a reranker supplying its own has erased the comparison while
producing output of exactly the right type and length. Every one of those four is checked.

**Not decided here.** Whether reranking earns its cost, and where in 5–10 the survivor count
should sit. Both are §8.2 questions against the labelled set (M7.2, blocked on annotators).

**Status.** `Qwen3-VL-Embedding-2B` and `Qwen3-VL-Reranker-2B` are `BLOCKED.md` #2 and #6. The
window plan needs neither and runs in `pipeline.py` on real media —
`evidence/m5-1-scene-windows.md`. The splitting path itself is exercised by tests only; there
is no long Kurdish episode here to run it against.

---

## D-038 · TimeLens2's interval must be about the clip it extends

**The defect.** §3 Stage 5 writes the out-point as `latest of { …, timelens_interval_end }`,
and `boundary.py` received that as a bare integer. "Latest" then reads as `max()` over the
intervals the model returned for the episode, which is what a careful implementer would write.
Measured:

```
anchored sentence : 10000..14000 ms  (4.0 s)
naive max(end)    : final_out = 305000 ms -> clip is 295.0 s
relevance-first   : final_out = 16000 ms  -> clip is 6.0 s
invariant #2 satisfied by the naive answer: True
```

A four-second Kurdish sentence becomes a five-minute clip, and **Kurdish invariant #2 passes**
— `final_out >= anchor_out` is satisfied handsomely. The invariant constrains the *direction*
a soft signal may move a boundary. Nothing constrained *relevance*. This is the same class the
last two reviews kept finding: a check that accepts the shape of an answer without its content.

**Decision 1 — eligibility is overlap with the anchored sentence.** §3 says TimeLens2 "returns
intervals containing relevant visual evidence", so an interval sharing no footage with the
anchored idea is evidence about a different moment and may not set this clip's out-point.
Touching at a single instant is not overlap. Considered and rejected: taking `max()` and
trusting the caller to pass only this candidate's intervals — that is the assumption the bare
integer already encoded, unstated and unchecked.

**Decision 2 — the check lives at the fusion site, not only in the selector.** `timelens.py`
provides `interval_end_for_fusion`, and `BoundaryInputs` now carries
`timelens_interval_start_ms` so that `fuse_boundary` can verify the overlap itself. Putting it
only in the selector would leave `BoundaryInputs` accepting the same bare integer, and the next
caller building inputs by hand reintroduces the five-minute clip with every test still green.
That is not hypothetical: it is exactly what round 2 of the independent review found four times
over — a fix applied at one call site and not at its sibling.

**Decision 3 — an overlapping interval ending before the anchor supplies `None`.** It is about
this moment but cannot extend outward, and returning it would record
`out_extended_by="timelens_interval_end"` for a boundary TimeLens2 did not move.

**Not decided here.** No magnitude cap. An interval overlapping by one millisecond and ending
far later is still eligible. §3 caps shot cuts at 400 ms and is silent on TimeLens2; inventing
a threshold would be redesigning a frozen section. Whether one is needed is a §8.2 tuning
question against the labelled set (M7.2).

**Cost.** Four existing tests in `tests/test_boundary.py` passed the bare end and now supply
the interval. They were asserting an interface we now know was insufficient, so they were
updated rather than relaxed, and the refusals they no longer cover are covered by
`tests/test_timelens.py`.

**Status.** `MCG-NJU/TimeLens2-4B` is `BLOCKED.md` #2 and #6. No interval in this repository
came from the model. `evidence/m6-1-timelens-relevance.md`.

---

## D-039 · SV6D: a timestamp is not evidence unless it points at the scene

**The defect.** §3 Stage 3 says "Every label must cite a timestamp. Reject output where a claim
has no timeline evidence." `Sv6d` enforced the first sentence with a regex search, and could
enforce only that, because the type does not know which scene it belongs to. Measured:

```
scene shown to the model : 300000 .. 312000 ms
label                    : 'speaker gestures at 9999s'
cited                    : (9999000,) ms  = 2.7775 hours
Sv6d presence check      : PASSED (constructed)
```

Two and three-quarter hours cited about a twelve-second scene. The two sentences read together
ask for something the presence check cannot express: a timestamp pointing where the model was
never shown is a well-formed string, not evidence.

**Decision 1 — the range check is a function beside the type, not a check inside it.** It needs
the window as an argument, and `Sv6d` travels through §5 documents that carry no window. Same
split as `assert_boundary_invariant` beside `Boundary`, and for the same reason: the type stays
able to represent what arrived so the gate has something to catch.

**Decision 2 — *some* cited time must land in the window, not every number.** "slow push-in
over 3s, starting 5:04" cites 3 000 ms and 304 000 ms; only the second is a point on the
timeline. Requiring all would reject honest labels, and requiring none is what let `9999s`
through. A label citing only a duration anchors nothing and is refused.

**Decision 3 — a two-part clock is minutes and seconds.** `1:24` in a note about a video is a
minute and 24 seconds. Reading it as an hour and 24 minutes would put every such citation
outside every window and turn this check into a blanket rejection.

**Decision 4 — the frame budget is refused before the call, not after.** §3: "Segmentation is
mandatory: the authors report ~17.7 GB at 256 frames and ~26.7 GB at 512." 256 is the ceiling
on a single call, because VRAM responds to a call rather than to a total. Past it the failure
is an out-of-memory kill mid-batch, not a wrong answer, so there is nothing to inspect
afterwards — a test asserts the model was never invoked.

**What Path B does not do.** Rank against Path A, dedupe across paths, or widen a span: a
candidate spans exactly the window it was read from. `discovery.py` owns the union and §3
Stage 5 owns boundaries. Path B never reports `DiscoveryPath.BOTH` — that is the merge's
conclusion about a moment two paths found independently.

**The runner.** `run_pipeline(..., read_scenes=…)` makes §3's union two-sided over the windows
Stage 2 planned on that video. Absent, it stays one-sided, which §3 calls correct rather than
degraded.

**Status.** `MCG-NJU/VideoChat3-4B` is `BLOCKED.md` #2 and #6. No reading here came from the
model, and the prompt is unwritten — a prompt is only testable against the model it is written
for. `evidence/m5-3-path-b.md`.

---

## D-040 · §8.3's "every shipped clip" means the file, not the plan

**The defect.** §8.3's third render-regression bullet asks for the boundary invariant "on every
shipped clip". `render_clip` asserted it on the `Clip` object, ran ffmpeg, and returned
`duration_ms` — the requested duration, echoed back. The artifact was never opened. Measured:

```
requested duration : 8000 ms
file on disk       : 4180 ms
source is          : 4162 ms
encode exit        : 0
```

ffmpeg cuts what exists and exits 0. The shipped clip ends 3.8 s before its own `final_out` —
mid-sentence, which Kurdish invariant #2 exists to prevent — and every check on the numbers
passed, because no check compared the numbers to the file.

**And the upstream cause it found.** The first thing the new check caught was this project's
own end-to-end fixture. §3 Stage 5's out set always includes `anchor_out + 200 ms tail`, and on
a short source that alone runs past the end:

```
media                        : 4162 ms
anchor_out                   : 4100 ms
final_out, duration unknown  : 4300 ms  -> 138 ms past the file
final_out, duration supplied : 4162 ms
invariant #2 holds either way: True True
```

`run_pipeline` had been shipping a clip 138 ms shorter than the boundary it recorded, on every
run, with a green suite. `fuse_boundary` already clamped `final_in` at 0 with the note "a clip
cannot start before the media does"; there was no upper clamp because nothing told it where the
media stopped.

**Decision 1 — `BoundaryInputs.media_duration_ms`, optional.** Supplied, the out-point is
clamped to the end of the media. Absent, §3's formula applies unclamped — honest rather than
safe, since a caller who has not said how long the media is has told fusion nothing, and
`render_clip` is the net. The pipeline passes the duration Stage 0 already probed.

**Decision 2 — an anchor past the end is refused, not clamped.** Clamping the *tail* is safe
for invariant #2 because the anchor still fits inside the media; clamping an anchor that does
not fit would produce `final_out < anchor_out`, the invariant violated by its own fix. An
anchored sentence ending after the file does is a broken transcript.

**Decision 3 — the clamp does not touch `out_extended_by`.** It changes the number, not which
signal reached for it, and §8.2 still asks which one won.

**Decision 4 — two checks, before and after.** The pre-flight (`clip.out_ms` against the probed
source) is deterministic and names both numbers. The post-encode measurement is the general net
for causes the pre-flight cannot see. Tolerance is one frame taken from the file's own rate,
not assumed: correct cuts of the real fixture came back exact except one at `+40 ms`, exactly
one frame at 25 fps. Only the short side is a defect; a frame of container rounding is not.

**Decision 5 — `RenderResult` carries both durations.** `requested_duration_ms` and
`measured_duration_ms`, with `duration_ms` kept as a property returning the measured one,
because the file is the answer. The run report emits both, so drift is visible rather than
inferred.

**Cost.** Two extra ffprobe launches per render, against an encode. Not measurable.

**Already honest.** `evidence/m2-4-rendered-clip.mp4` measures 2240 ms against a 2200 ms
request — one frame of rounding, well inside the source. That artifact was never truncated.

---

## D-041 · Captions belong to the clip's timeline, and the burn checks it

**The defect, and it was shipping.** `build_ass` wrote source-absolute timestamps.
`render_clip` burns them into a stream ffmpeg has already cut with `-ss clip.in_ms`, where t=0
is the start of the clip. Measured on a 1.6 s clip taken from source 2000 ms, sentence spoken
at source 2000–3600 ms:

```
ASS Dialogue line: Dialogue: 0,0:00:02.00,0:00:03.60,Kurdish,,0,0,0,,ڕۆژنامەوانی …
bytes differing between captioned and uncaptioned render: 0
captions drawn: False
```

Zero bytes differ. The caption was scheduled past the end of the clip, libass drew nothing,
ffmpeg exited 0, and the result is a valid, playable, caption-free MP4. Kurdish invariant #4 —
the entire §4.3 surface, the thing §0 calls failure mode #3 — absent from every clip not
starting near zero, with no error anywhere. `render.py`'s docstring names this failure mode
verbatim ("an ASS file libass parses but finds nothing to draw in") and nothing checked it.

**Why the pixel test passed.** `tests/test_render.py` compares captioned against uncaptioned
decoded frames, which is the right test. Its fixture cuts at 300 ms with words at 0–1600, so
the timelines overlap by 1.3 s and something is always drawn. The test measured the right thing
on the one input where the defect is invisible — the same shape as the golden render needing
`shaping=simple` as a failing control before it measured anything.

**Decision 1 — `build_ass` takes the clip window.** `clip_in_ms` shifts each `Dialogue` stamp;
`clip_duration_ms`, when given, bounds it. The `\kf` karaoke spans are durations and were
always correct. A sentence starting before the clip or ending after it is refused rather than
clamped: it is speech this clip does not contain, and a clamped caption would assert a timing
the alignment never produced.

**Decision 2 — the check runs again at the burn.** `assert_captions_within_clip` parses the ASS
`render_clip` is about to use and refuses one with no `Dialogue` line, or none intersecting
`[0, duration]`. Fixing only the writer is not fixing the class — D-038's lesson, and round 2
of the independent review found four instances of exactly that. This catches a hand-written
file, a file from an older run, and the next caller who forgets.

**Decision 3 — partial overlap passes.** Something is on screen, so it is not the silent case.
A stricter rule would reject legitimate captions that begin just before a clip's in-point.

**Decision 4 — `clip_in_ms` defaults to 0.** Seventeen call sites, all of them about clips at
zero, and a required argument would have churned them without making anything safer, because
the *writer* is not where this is caught now. The burn is.

**Not re-rendered.** `evidence/m2-4-rendered-clip.mp4` came from the 300 ms fixture: its
captions are on screen but end 300 ms late. It demonstrates the RTL stack, not client output,
and `evidence/m3-5-caption-timeline.md` records that so nobody later reads its timing as
correct.

---

## D-042 · §2's delivery set was two files short

**The gap.** §2's diagram ends with `MP4 · SRT/ASS · editing JSON · EDL`. MP4, ASS and the §5
JSON existed. **SRT and EDL had never been built**, so two of the four things §2 says this
system delivers did not exist and nothing in the run report mentioned them.

**Decision 1 — one offset rule for both subtitle formats.** An SRT ships beside the MP4, so its
timeline is the clip's. `build_srt` takes the same `clip_in_ms` as `build_ass` and refuses the
same out-of-window sentence, because M3.5 established what happens when a subtitle file is
written on the source's timeline: a valid, playable file that delivers nothing.

**Decision 2 — the EDL is the opposite, deliberately.** Its *source* timecodes are the
source's — where the clip was cut from — and only its *record* timecodes start at zero. An EDL
in clip time conforms the top of the episode and is perfectly well-formed. The two formats sit
in one module so the distinction is written down where both are.

**Decision 3 — a non-integer frame rate is refused, not rounded.** 29.97 and 59.94 need SMPTE
drop-frame timecode. Non-drop at 29.97 drifts about 3.6 s per hour against the footage and the
EDL looks correct for the whole conform, so `ms_to_timecode` raises and names the drift.
Drop-frame is unimplemented; saying so beats approximating it. This required `render.frame_rate`
to report ffprobe's exact ratio (`30000/1001`) rather than a rounded one — a rate rounded on
the way in cannot be refused on the way out.

**Decision 4 — an NTSC source loses the EDL, not the clip.** Delivery is its own field on
`PipelineRun`: a correct MP4 plus a named `StageSkipped` for delivery, and `complete` goes
false. Failing the whole render over a sidecar would be worse; writing a drifting one would be
worse still.

**Decision 5 — empty is refused everywhere it is possible.** An SRT with no cues, an EDL event
shorter than one frame, a video-only EDL: each is a valid file that delivers nothing, which is
the failure class this project keeps finding.

**Decision 6 — the SRT separator is a comma.** A period is WebVTT. A player expecting SRT
rejects or mis-parses the cue and the subtitles do not appear — silent, like the rest.

**Status.** Both files are written by `run_pipeline` on real media —
`evidence/m3-6-delivery-set.md`. The fixture's clip is the whole file, so source and record
timecodes coincide there; the unit test at 84 600 ms is what demonstrates the distinction.

---

## D-043 · §10's attribution mitigation had already drifted, in both directions

**The defect.** §10 lists "Attribution obligations — Community-1 (CC-BY-4.0) requires an
attribution notice in shipped product docs" as a known risk with a stated mitigation. The
mitigation was a hand-written list in the README under a sentence claiming
`registry.attribution_notices()` generated it. It did not, and the two disagreed **both ways**:

- the function emitted **ASS + libass/HarfBuzz/FriBidi (LGPL/GPL)**, which the README omitted;
- the README listed **Noto Naskh Arabic (OFL-1.1)**, which the function omitted.

A licence obligation documented by hand beside a generator that does not generate it is the
same class as everything else this session found: the shape of a mitigation without its
content. The libass notice was missing from the only place §10 says it must appear.

**Decision — `SHIPPED_ASSETS`, separate from `REGISTRY`.** The font is a real shipped artifact
with a real obligation and is **not** a model. Adding it to `REGISTRY` to make the notice
appear would have put something in §7's table that §7 does not contain, and `test_registry.py`
parses §7 out of `BLUEPRINT.md` and asserts set equality both ways precisely so that cannot
happen. §10's obligation is about shipped product docs, which is a wider set than §7's models,
so it gets its own table. `attribution_notices()` now returns both.

**Decision — the README section is asserted against the generator in both directions.** A
notice absent from the docs is an unmet obligation; a bullet nobody generates is one that
outlives its obligation and misstates what the product contains. `tests/test_claims.py` fails
on either.

**Also fixed.** The README pointed CI at `.github/workflows/hawedit.yml`; the file is
`gate.yml`. A test now asserts every workflow path the README names exists on disk.

**Not decided here.** Whether OFL-1.1's obligation is discharged by shipping `OFL.txt` beside
the `.ttf` — it is what the licence asks for and the file is asserted present, but this is a
licence question and I am not counsel.

---

## D-044 · The environment changed: this checkout now runs on hawapc01, and the code did not

**What happened.** Every prior entry was written from a cloud container: no GPU, no ffmpeg, a
proxy that denied `huggingface.co`. This checkout is on **hawapc01** — the machine §6 names and
§8.1 requires the ASR benchmark to run on. Measured, not assumed: hostname `HAWAPC01`, two
NVIDIA RTX 3090 Ti at 24564 MiB each (§6's "2×24 GiB"), `ffmpeg 8.1.1-full` on `PATH` built
`--enable-libass --enable-libharfbuzz --enable-libfribidi --enable-nvenc`, and
`huggingface.co`, `commonvoice.mozilla.org`, `www.openslr.org` and `zenodo.org` all answering
200 where `BLOCKED.md` #6 recorded a proxy denial.

It is also **Windows**, and nothing in this project had ever run there. `bash scripts/setup.sh`
— the one command the README promises takes a clone to a green gate — stopped at its first
line. Six defects, none of them cosmetic, each fixed at the one place all callers route
through rather than at the call site that happened to fail first:

**1 — `ffprobe` was resolved as `with_name("ffprobe")`.** `shutil.which` returns `ffmpeg.EXE`
here, whose sibling is `ffprobe.EXE`; the bare name does not exist. Four call sites had the
same line, so Stage 0 ingest, the frame-rate probe, the pipeline's dimension probe and a test
helper all failed identically. `captions.ffprobe_for` keeps the binary's own suffix, and
`ingest.probe_stream` now gives every probe in the system one resolver and one argv.

**2 — the ffmpeg filtergraph paths were under-escaped, on every platform.** ffmpeg unescapes a
filter option **twice** — once splitting the filtergraph, once parsing the filter's arguments —
so `\:` survives the first pass and is consumed by the second. The escaping was one backslash.
This was invisible on Linux because a POSIX path contains none of the characters being escaped,
so the substitutions never fired; a Windows path carries `C:` and `\` at once and the burn-in
died. Measured against the real binary: `C\:\Users\…` and `C\:/Users/…` both fail, `C\:/Users/…`
renders. Separators are normalised to `/`, which ffmpeg accepts everywhere. **The dangerous
direction is not the one that failed:** a path in the last filter position truncates the
argument in silence and libass falls back to `shaping=auto`, which is exactly §4.3's failure —
correct-looking output, wrong Arabic shaping, invisible until a client sees it.

**3 — `os.O_NOFOLLOW` does not exist on Windows,** and it is the syscall protecting the one
file in this project that holds a secret. `getattr(os, "O_NOFOLLOW", 0)` alone would have made
the flag evaporate on the box that will hold the real key while the code still read as
protected. The guarantee is reconstructed in two halves — refuse a link before the open, then
prove with `fstat`/`lstat` that the handle is the file that was checked — because the pre-check
alone is a TOCTOU window, which is the original symlink bug back again, just narrower.

**4 — `chmod(0o600)` is decoration on Windows.** Measured: the file lands at `0o666` and
inherits the directory's ACL. `restrict_to_owner` now does `chmod` on POSIX and an `icacls`
`/inheritance:r` + owner-only grant on Windows, and **refuses** rather than warning if that
fails. The tests assert the property in the terms each platform has, read back from the OS
rather than from the code that set it, and the umask test became "make the surroundings as
permissive as the OS allows, then check" — on Windows that is a wide-open parent directory ACL,
which is the real check on `/inheritance:r`.

**5 — `subprocess.run(["bash", …])` on Windows launches WSL.** `CreateProcess` searches
`C:\Windows\system32` *before* `PATH`, and that is where WSL's `bash.exe` lives, so Python and
`shutil.which` disagreed about which interpreter `"bash"` meant. Every `test_gate.py` assertion
is `returncode == 3` or `== 5`; WSL exited 127 for a path it could not see, and **the ten tests
whose entire job is proving the gate cannot be neutered were themselves neutered, by the
harness.** They resolve the interpreter through `shutil.which` and pass `as_posix()` now.

**6 — `python3` is a Microsoft Store stub here, and `python` is another tool's virtualenv.**
The stub is on `PATH`, prints "Python was not found", installs nothing and exits non-zero; the
venv is a real 3.11 that cannot build a venv (`ensurepip` exits 1). `setup.sh` now picks an
interpreter by asking each candidate whether it is a base 3.11+, not by trusting a name — and
`PY_BIN`, when set, is the only candidate, so a deliberate choice is never silently replaced.

**Decision — `fetch-ffmpeg.sh` verifies before it fetches.** §4.3.2's requirement is a
*verified* build, not a downloaded one. It now checks `HAWEDIT_FFMPEG`, then `.ffmpeg/`, then
`PATH` — the same order and the same libass/HarfBuzz/FriBidi test `captions.find_ffmpeg` uses,
so the script and the library cannot disagree about which binary is in play — and exits 0 if
one already qualifies. On a non-Linux host with nothing qualifying it **refuses with what to
install**, rather than unpacking a Linux binary that would then fail the RTL check and report a
true-sounding error about the wrong thing.

**Decision — the symlink test does not skip.** A `pytest.skip` on Windows would stop that test
running on the one machine that will hold the real key, and it collided with the gate's floor:
the floor is one committed number and the runnable-test count would have differed per platform,
so the suite could not be green on both. What Windows lacks is the privilege to *build* the
attack, not the refusal that stops it — so where `os.symlink` raises, `is_symlink` is answered
directly and the same assertions run. A POSIX runner still drives the real link through the
real syscall, in the same test. 873 collected, 873 passed, **0 skipped**, on both.

**Note on the ratchet.** The first green run here wrote a floor of 873 from `collected` while
the check gated on `passed`, so one skipped test raised the bar the next run was refused for
missing. Both now read the number of tests that actually ran.

**Not decided here.** Whether `BLOCKED.md` #2 and #6 are resolved *as facts about the project*
or only about this machine — recorded separately in `BLOCKED.md`, because a blocker that lifts
when you change desks is a different claim from one that is gone.

---

## D-045 · The encoder probe asked the wrong question, and answered it confidently

**The defect.** `render.encoder_available` exists because `ffmpeg -encoders` lists what was
*compiled in*, which is a different question from what this machine can encode. Its answer came
from encoding one real frame and checking bytes came out — the right method. The frame was
**64×64**, and NVENC refuses anything below roughly 145×49: *"Frame Dimension less than the
minimum supported value"*, with ffmpeg exiting **0** and writing nothing.

So on hawapc01 — 3090 Ti present, `--enable-nvenc` in the build — the probe reported
`h264_nvenc` unavailable. §6 puts NVENC on hawapc01 and `render_clip` refuses an unavailable
encoder rather than silently substituting x264 (deliberately, and correctly). The two rules
compose into: **asking for NVENC on the one machine the blueprint says to use it on would
raise.** The function written because a listing cannot be trusted was itself the untrustworthy
answer, and nothing downstream could tell the difference — a wrong "no" looks exactly like a
correct "no".

Measured on this box, same binary, same encoder: 64×64 → 0 bytes, 128×128 → 0 bytes, 145×49 →
1032 bytes, 1080×1920 → 1300 bytes.

**Decision — the probe encodes at Stage 6's own output size.** `ENCODER_PROBE_SIZE` is
`(VERTICAL_WIDTH, VERTICAL_HEIGHT)`. The question `render_clip` needs answered is "can this
encoder encode what Stage 6 will hand it", so the probe hands it that. A smaller frame is
cheaper and can fail for reasons that say nothing about availability, which is the whole bug.

**Decision — `NVENC_MIN_FRAME = (145, 49)` is recorded as a constant with a test.** The value
is NVIDIA's, not ours; recording it gives the probe geometry something to be checked against.
The test is arithmetic — no ffmpeg, no GPU — so it holds on a CI runner that could never
observe the failure.

**Decision — the two GPU-shaped tests assert the property, not the environment.** One asserted
NVENC was *unavailable*; its own message admitted it would "outlive the environment it
documents", and it did, by going red the moment the project reached its own hardware. It now
asserts what `encoder_available` reports equals whether an independently spelled-out real
encode writes bytes — true in both directions, on a GPU box and on a bare runner. The other
skipped itself whenever NVENC worked, i.e. exactly on hawapc01; the refusal is what it is
testing, not the graphics card, so availability is answered directly and the refusal runs
everywhere. Neither skips, which also keeps the gate's floor a single number across platforms.

**Not changed.** M3.3 stays PARTIAL. It had two shortfalls and now has one: the reframe still
needs diarization plus face detection, and Community-1 measures **401** from here.

---

## D-046 · The canonical ASR has a repository now, and no loader on this OS

**Context.** `BLOCKED.md` #10 asked whether §7's `omniASR_LLM_7B_v2` / `omniASR_CTC_3B_v2` mean
Meta's published `facebook/omniASR-LLM-7B` / `facebook/omniASR-CTC-3B`, since no published Meta
checkpoint carries a `_v2` suffix. Hawa answered yes on 2026-08-08.

**Decision 1 — the mapping goes in `models/sources.json`, labelled as a decision.** The two
Qwen entries beside it are verified name matches: exact name, official namespace, the licence §7
records. These two are not, and the file says so in a `_`-prefixed note, because in six months
the difference between "verified" and "decided" is the difference between trusting the row and
re-deriving it. `BLUEPRINT.md` §7 keeps its `_v2` cells — it is frozen, implementation does not
edit it, and this is the second recorded place where the code is deliberately ahead of the spec
(the first is #8 / D-033). `tests/test_registry.py` is unaffected: it asserts §7's *model ids*,
and a repository id is not one of those.

**What the answer exposed.** Not a transcript. The two checkpoints are single raw fairseq2 `.pt`
files — 31.2 GB and 12.3 GB — with a SentencePiece tokenizer, no `config.json`, no safetensors,
and `library: None` on the Hub. `transformers` has nothing to dispatch on. The loader is
`omnilingual-asr`, which requires `fairseq2[arrow] <=0.6.0`, which requires **`fairseq2n`** — a
compiled native extension whose only published wheels are `manylinux_2_28_x86_64` and
`macosx_14_0_arm64`.

**hawapc01 is Windows.** So the model §7 makes canonical is, on the machine §6 names, a 31 GB
file with no way to open it. Measured on PyPI rather than inferred from a failed install.

**Decision 2 — this is recorded as `BLOCKED.md` #11 and not engineered around.** Three shapes
are available (WSL2 on this box, a GPU container, a Linux host) and choosing among them is an
architecture decision about where §3 Stage 1 runs, plus a measurement-provenance question §8.1
cares about: it requires "real-time factor measured on hawapc01", and whether WSL2 on hawapc01
*is* hawapc01 for that purpose is a claim about what a number means. My reading is that it is —
same silicon, same driver, `nvidia-smi` inside WSL reports both cards — but `asr.Hardware`
exists precisely so that this project cannot make such a claim by implication, and picking the
environment quietly would bake it into every RTF figure that follows.

**What was verified while establishing that, so the decision is made against facts:** WSL2
Ubuntu 26.04 is installed and running here; `nvidia-smi` inside it reports **both** RTX 3090 Ti
at 24564 MiB on driver 596.36, so CUDA passthrough is live; 740 GB free on `/`; ffmpeg 8.0.1
present. One gap: Ubuntu 26.04 ships **Python 3.14**, and `omnilingual-asr` caps at 3.12, so
that route needs its own interpreter rather than the distro's.

**Decision 3 — nothing else waits on it.** `rzgar/qwen3-asr-sorani-kurdish-ckb-v1` (§3 Stage 1's
*validator*) and every Stage 2 / 3 / 5 model are ordinary `safetensors` repositories that load
natively on Windows. Those integrations proceed. The scope of #11 is exactly the two models §7
makes canonical — which is the worst place for it to be, and is why it is its own entry rather
than a footnote on #10.

---

## D-047 · The interim corpus was authorised, is reachable, and no longer exists

**What happened.** D-012 authorised a public Sorani corpus — Common Voice `ckb` — as an interim
set, and `BLOCKED.md` #6 recorded that the container's proxy blocked every corpus host. From
hawapc01 every one of those hosts answers 200. M0.16 was re-statused TODO on that basis this
morning, and that was a true measurement of the wrong thing: **reachability of a host is not
availability of a corpus.**

**Measured, in order of preference:**

| Source | Finding |
|---|---|
| `mozilla-foundation/common_voice_17_0` | A stub. *"Effective October 2025, Mozilla Common Voice datasets are now exclusively available through Mozilla Data Collective"* |
| Mozilla Data Collective | Account plus accepted terms |
| OpenSLR | 156 resources parsed, **0 Kurdish** |
| `facebook/omnilingual-asr-corpus` | CC-BY-4.0, ungated, the natural match for §7's own ASR — and **349 configs, no `ckb`**. §7's "ckb_Arab CER 6.0" describes the model, not this release |
| `akam-ot/sorani-tts` | Real Sorani audio + reference text, 5.7K clips, ungated — **no licence** |
| `roshna-omer/common_voice_16_0_*_ckb_*` | CV16 ckb re-uploads — metadata only, no `Audio` feature (766 KB for 5,000 rows), no licence |

**Decision 1 — no account is created and no terms are accepted on Hawa's behalf.** Mozilla Data
Collective is one form away, and that form is a licence agreement. Clicking it is Hawa's, and a
project this careful about attribution obligations does not have an agent agree to terms for it.

**Decision 2 — the unlicensed datasets are refused, not weighed.** `akam-ot/sorani-tts` is real
Sorani audio with reference text and it would work. It carries no licence tag and no licence
file. D-002's rule is no dependency or data without one, and this ships to clients; "probably
fine" is not a licence. It is recorded in `BLOCKED.md` #1 as something Hawa may authorise
explicitly, with the reason it is not recommended, rather than quietly used.

**Decision 3 — M0.16 goes back to BLOCKED, and the mistake is written down.** The row said TODO
for a few hours today on the strength of the hosts answering. Silently correcting it would have
left the ledger right and the reasoning invisible, and the reasoning is the transferable part:
`BLOCKED.md` #6 asked "can we reach it", the useful question was "is it still there", and those
came apart the moment the network opened.

**What this does not change.** The importer (M0.14) is built and tested and refuses to invent
dialect, condition or duration. It has nothing to import — which is a fact about the world in
August 2026, not a gap in the code.

---

## D-048 · §3 Stage 2 cannot go through the loader its own checkpoint declares

**Context.** With hawapc01's GPUs available and the Hub reachable, `Qwen3-VL-Embedding-2B` and
`Qwen3-VL-Reranker-2B` are on disk (4.0 GB each, Apache-2.0) and M5.2 became ordinary work. The
embedder loads on `cuda:0` in bfloat16 in 4.9 s, uses 3.98 GiB, and returns 2048-d L2-normalised
vectors for real Kurdish text. Its recipe was read from the files it shipped with rather than
guessed: `lasttoken` pooling, dimension 2048, then Normalize, prompt `"Represent the user's
input."`, cosine similarity — which `visual_index._cosine` already matches.

**Decision 1 — a scene window is embedded as a *video*, never as a list of frames.** Measured on
four frames of the fixture: a list of PIL images returns `(4, 2048)`, four separate embeddings;
`{"video": frames}` returns `(2048,)`, one embedding for the window. Both are available and both
type-check. The list form is the one that invites a mean afterwards, and §7 excludes CLIP with
the reason *"Frame-averaging loses temporal structure — 0.325 vs 0.75+ NDCG@10"*. Taking the
convenient shape here would reimplement, inside Stage 2, the exact thing §7 rejected — and the
index would look identical.

**Decision 2 — Stage 2 uses the `transformers` processor directly, not `sentence-transformers`.**
This is the awkward one, because `sentence-transformers` is the loader the checkpoint *declares*,
in its own `modules.json` and `config_sentence_transformers.json`. It works. It also emits, on
every video encode:

> `Asked to sample fps frames per second but no video metadata was provided ... Defaulting to fps=24.`

§3 Stage 2's reference setting is **~1 fps**. The frames handed over are one second apart and the
model is told they are 1/24 s apart. There is no channel to correct it: `video_metadata` is
refused — *"Multimodal dict input contains unrecognized modality keys: ['video_metadata']"*.

So the declared loader has no way to express the one setting §3 Stage 2 is specific about.
`visual_index.SceneWindow` already refuses a window that quietly lowers its rate, and says why —
*"the resulting embedding is indistinguishable from an honest one"*. A model misinformed about
the rate is the same defect one layer down, and it would be invisible in every artifact. The
processor route can pass `video_metadata` alongside `pixel_values_videos` / `video_grid_thw`, and
it is what the `scripts/qwen3_vl_embedding.py` inside the checkpoint itself uses.

**Consequence for M5.2:** it is not `SentenceTransformer.encode`. It is the processor route, with
the window's real fps passed through, plus a test asserting the fps reaches the model — because
if it does not, every embedding in the index is honest-looking and about footage sampled at a
rate the model was lied to about.

**Decision 3 — whatever embeds a window records the frames it actually saw.** `SceneWindow`
plans `ceil(4.162 × 1) = 5` frames for the fixture; ffmpeg's `fps=1` filter emits **4**. The
window's count is a plan and ffmpeg's output is the fact, which is M3.4's lesson in a new place —
there `RenderResult.duration_ms` was the request echoed back and the file was never opened.

**Decision 4 — the CUDA build is a `gpu` extra with an installation note, not a pin change.**
`pip install torch==2.13.0 --index-url .../cu130` reports success and changes nothing: the
installed CPU wheel *is* 2.13.0, so the requirement is already satisfied. A green install, and
`cuda.is_available()` still False. `torch==2.13.0+cu130` is required, and PEP 440 makes
`pyproject.toml`'s `==2.13.0` match any local version, so nothing had to be loosened. `cu130` is
also the only channel carrying 2.13.0 for cp311/Windows, so keeping the pin and getting CUDA are
one choice rather than a trade. Licences audited: all Apache-2.0, BSD-3-Clause or MIT-CMU.

**Not done here.** The three integrations themselves. Weights, GPU, loader stack and the correct
route are established and recorded; M5.2, M5.4 and M6.3 remain unstarted, which is what the
ledger says.

---

## D-049 · A warning is not a measurement, and the timestamps were worse than the warning

**What D-048 got wrong.** It recorded that `sentence-transformers` warns *"no video metadata was
provided ... Defaulting to `fps=24`"* and concluded that §3 Stage 2 must use the `transformers`
processor. The conclusion holds. The **reason** was a warning string, and this project does not
build architecture on those. Measured properly, the situation is worse and more specific.

A Qwen3-VL processor writes timestamp tokens into the prompt — `<0.5 seconds>` — which is how
each temporal group is placed in time. For the fixture's 4162 ms window at 1 fps:

| Input | Timestamps |
|---|---|
| no metadata | **(0.0, 0.1)** |
| `fps` in the content dict | (0.0, 0.1) — accepted and ignored |
| `video_metadata` in the content dict | (0.0, 0.1) — accepted and ignored |
| `video_metadata=` **top-level** to `apply_chat_template` | **(0.5, 2.5)** |

A 4.162-second window presented as 0.1 seconds. Not a warning about precision — a forty-fold
compression of the timeline, and `sentence-transformers` cannot express the fix at all
(`unrecognized modality keys: ['video_metadata']`).

**Decision 1 — one module builds this, for all three models.** `video_input.py`.
`Qwen3-VL-Embedding-2B`, `MCG-NJU/VideoChat3-4B` and `MCG-NJU/TimeLens2-4B` all take video this
way, so three adapters would otherwise each have to remember a top-level argument whose absence
is invisible. The metadata is derived from the window and from the frames that exist, never
passed by hand.

**Decision 2 — the check reads the decoded prompt, not the arguments.** Every other layer
accepts the wrong answer: the ignored keys return no error, and the tokenised ids are
byte-identical either way (same shape, same `video_grid_thw`, `(a == b).all()` true). The
timestamps in the prompt are the only place the mistake is visible, so that is the artifact
`assert_timestamps_span_window` reads — the same rule as M3.4, where the fix was to open the
written file instead of trusting the request.

**Decision 3 — the threshold is "the stamps reach half the window", and it is set against the
failure.** Not against a notion of precision. One temporal group is one timestamp and Qwen3-VL
pairs frames, so the last stamp sits near the middle of the final group and never equals the
duration — an exact check would be wrong. The broken default reaches 2.4% of the window; half is
comfortably clear of tail rounding in both directions.

**Decision 4 — a window that arrives as one frame is refused, and the remedy is named.** Found
by measuring `plan_scene_windows` on the real fixture: its three 1400 ms scenes each plan 2
frames at 1 fps and yield **1**, because ffmpeg's `fps` filter samples at interval *centres* —
0.5 s exists, 1.5 s is past the end. A one-frame video block has no temporal structure, which is
§7's stated reason for excluding CLIP reached from the other side, and its embedding is
indistinguishable from an honest window's. `SceneWindow` permits any rate at or above the
reference and enforces the 64-frame ceiling against it, so the answer for a short scene is a
higher rate; the error says so. The first tolerance written here — "one frame short" — is exactly
the systematic `ceil` overshoot and therefore also permitted 1-of-2. That is the defect: a
tolerance calibrated on the common case, silently covering the pathological one.

**Decision 5 — the plan is recorded as a plan.** `SceneWindow.frame_count` is `ceil(duration ×
fps)` and runs one high whenever the duration is not a whole number of frames (4162 ms: plan 5,
actual 4). `WindowFrames.count` is what exists on disk and is what reaches
`total_num_frames`; reporting the plan would place the last frame at a time no frame was taken.

**Measured, and stated with its limit.** The defect moves one window 0.009609 in cosine distance,
against 0.186–0.224 between the fixture's three distinct scenes — about 5%, which on *this*
footage would not reorder retrieval. Three unrelated shots is close to the easiest case there
is. The product's input is a single-speaker Kurdish podcast where consecutive windows differ by
far less, so the ratio there is unmeasured, and `BLOCKED.md` #1 is why. The claim recorded is
that the defect is real and its significance on representative material is not yet known — not
that it is small.

**Not done here.** M5.2 itself. This is the input layer the adapter will use, with the two ways
of getting it wrong now caught rather than commented.

---

## D-050 · Stage 2's embedder, and a 0.045 that is recorded rather than rounded off

**What was built.** `qwen_visual.QwenVisualEmbedder` produces `visual_index.VisualEmbedding`
from real frames on hawapc01's `cuda:0` in bfloat16, and `embed_text` produces the query vector
`rerank_and_keep` takes. Measured: three windows over the fixture, 2048-d, |v| = 1.0000, index
built in 10.4 s at 7.94 GiB peak, and a Kurdish query retrieves against it with dense 1-based
ranks. `evidence/m5-2-embedder.md`.

**Decision 1 — the pooling is read from the checkpoint and the recipe is enforced, not assumed
to persist.** `1_Pooling/config.json` declares `lasttoken` and 2048. A checkpoint that switched
to `mean` would load, run, and return 2048 finite non-zero floats passing every check
`VisualEmbedding` makes, so `assert_supported` refuses the mismatch. Reading a recipe and then
ignoring it is the same as not reading it, which is why the refusal has its own test.

**Decision 2 — §7's role check runs before the weights load.** `resolve_role` at construction,
so `PySceneDetect` cannot be handed in as the embedder and a non-§7 model never reaches disk.
Audit finding #8's rule, applied at the earliest point it can be.

**Decision 3 — no silent CPU fallback.** `cuda:0` asked for on a machine reporting no CUDA is a
refusal. §6 puts Stage 2 on a GPU, and a 2B VLM on CPU is not a degraded mode — it is a
different throughput regime, and every number measured afterwards would be about that instead.
Same rule as `asr.Hardware` refusing cross-hardware comparison and `render_clip` refusing an
absent encoder rather than substituting x264. Its test answers `torch.cuda.is_available`
directly rather than branching on what the box has, because deciding by hardware would delete
the check on the only machine where it matters.

**Decision 4 — Kurdish invariant #3 is enforced inside `embed_text`, not asked of the caller.**
`normalize_sorani` runs on the query at the boundary, exactly as `index.index_tokens` does for
§2. Both halves of retrieval must pass through the same §4.1 normalisation or they compare two
different alphabets, and the failure is not an error — it is a slightly wrong score.

**The open discrepancy, stated as open.** The checkpoint names `sentence-transformers` as its
loader and on identical text the two routes differ by cosine **0.955300**. Chased, not rounded:
four prompt placements were measured (system turn 0.955300, prefixed 0.942398, prefixed with
space 0.948999, no prompt 0.955300) and none closes it. Two findings came out of that. The chat
template contains `default_system_message = 'Represent the user\'s input.'`, so it injects the
declared prompt itself — which is why *system turn* and *no prompt* give the identical vector,
and means supplying it here is redundant rather than load-bearing. And the residual 0.045 is
**not** the pooling mode, the normalisation, or the prompt.

It is recorded as unexplained. It does not invalidate the index — `embed_text` and
`embed_frames` share one convention, which is the only property retrieval depends on — but it
*would* matter if it meant this route places text differently relative to video than the trained
convention does, which would cost cross-modal retrieval quality while changing no number's
shape. Settling that needs labelled Kurdish candidates (§8.2, `BLOCKED.md` #1). Recording an
unexplained 0.045 is the honest position; calling the cross-check a validation would not be, and
an earlier draft of this module's docstring did exactly that until the number was measured.

**Not done here.** The reranker. `Qwen3-VL-Reranker-2B` is on disk with a `1_LogitScore` module
of its own, `visual_index.VisualReranker` is an unimplemented Protocol, and until it exists
§3 Stage 2's "top 50 → rerank → keep 5–10" is retrieval only. M5.2 stays PARTIAL.

---

## D-051 · "Same arithmetic on paper" is not a claim about a number until the dtypes are in it

**What was built.** `qwen_visual.QwenVisualReranker` behind `visual_index.VisualReranker`,
closing M5.2's named shortfall. It reorders on real media — scene 0 moved from third to second —
carries every retrieval score through untouched, and reads its instruction, its system turn and
its two score-token ids out of the checkpoint. `evidence/m5-2-reranker.md`.

**Decision 1 — the score is formed the way the model forms it, in float32.** The shipped
`scripts/qwen3_vl_reranker.py` applies a bias-free `Linear` of
`lm_head.weight[yes] - lm_head.weight[no]` to the last hidden state. The first implementation
here differenced the two **logits** instead and a docstring called it "the same arithmetic" —
true on paper, and false as a number:

    shipped formula (W_yes - W_no)·h = -0.263168
    logits difference                = -0.250000     <- bfloat16, on a representable step
    after sigmoid                     0.434585  vs  0.437824

The error is 0.0032. With the formula corrected, the gap between rank 1 and rank 2 on the
fixture is `0.448391 - 0.442759 = 0.0056`. **The shortcut's error was 57% of the margin it was
deciding.** Every §7 checkpoint here declares `bfloat16`, so this is a class of mistake rather
than a line of it: an algebraic identity says nothing about precision, and the two-line
"simplification" was inside the ordering it produced.

Implemented by indexing the two weight rows and casting each before subtracting, cached once —
casting the head first would allocate 151k × 2048 float32 to use two rows.

**Decision 2 — `read_frames` is injected rather than re-extracted.** `VisualHit` carries a
`SceneWindow`, not pixels, so the reranker needs a source. It takes a reader — the same shape as
`pipeline.run_pipeline`'s `read_scenes` for Path B — so the frames a window was *embedded* from
are the frames it is *scored* from. Two independent extractions of "the same" window differ at
the tail (D-049 measured the centred-sampling offset), and the reranker would be judging footage
the index does not hold.

**Decision 3 — one loader for both Stage 2 models.** `load_processor_and_model` carries the
CUDA refusal that §6 requires. Two classes with two copies of that check is one class away from
having only one of them, which is the pattern both independent reviews kept finding.

**Decision 4 — ties break by time then id, matching `VisualIndex.retrieve`.** §8.2 counts
Recall@K on this order and an unstable tie-break makes that number noise. Two different
tie-breaks in one pipeline is the same defect as none.

**Decision 5 — the contract is satisfied, not merely survived.** `rerank_and_keep` refuses a
reranker that invents a window, returns one twice, comes back short, or restates the retrieval
score. The tests drive that real function with five synthetic windows rather than restating its
rules, because the four checks have to hold *at once* and a paraphrase would drift from it.

**Not exercisable here.** §3 Stage 2's keep-5–10 slice. The floor is five survivors, the fixture
has three scenes, and `rerank_and_keep` correctly refuses — the range is covered synthetically
and needs real footage (`BLOCKED.md` #1). D-050's unexplained 0.955 also stands.

---

## D-052 · The sampling rate was 63% of the signal, and one index could hold two of them

**Found by auditing the previous iteration's evidence**, not by a failure. M5.2's index was built
at **4 fps** while §3 Stage 2's reference is **~1 fps**, and that departure was never recorded.
Checking whether it mattered turned up something worse: nothing required a media's windows to
share a rate at all.

Reproduced — `VisualIndex.add` accepted a 1 fps and a 4 fps window together. It checked
`media_id`, duplicate `window_id` and dimension, and said nothing about the rate.

Then measured, because "not comparable" is not a number. The **same** 0–4162 ms span of the
fixture, same model, same weights, only the rate differing:

    1 fps vs 2 fps   cosine distance 0.117419
    1 fps vs 4 fps                   0.057461
    2 fps vs 4 fps                   0.033594

Against three **visually distinct** scenes of that fixture at 0.186–0.224 apart. **The sampling
rate alone is up to 63% of the distance between genuinely different footage.** In a mixed index
a window can outrank a more relevant one for having been read at a different rate, with every
score looking ordinary. And it is not noise: the rate reaches the model explicitly through
`video_metadata` (D-049), so this is the model describing inputs it was told differ.

The relationship is also not monotonic — 1 vs 2 fps is *further* than 1 vs 4 fps — so it is not
a small correction that could be tolerated or compensated.

**Decision 1 — one rate per index, enforced at `add`.** The single funnel, beside the dimension
check it mirrors, with the measurement in the message. `plan_scene_windows` already takes one
`fps` per media, so the honest path was uniform; nothing required it, which is precisely how the
M5.2 evidence index came to be 4 fps with no record.

**Decision 2 — the guard is not "1 fps only".** That would pass the mixing test and break
D-049's remedy: a 1400 ms scene at 1 fps is a single frame with no temporal structure, which
`extract_window_frames` refuses. A uniform index at any rate at or above the reference is legal.
A positive control test builds a whole index at 4 fps and requires acceptance, so the refusal
cannot be satisfied by refusing everything.

**Decision 3 — the rate is a per-media decision with a cost, recorded not absorbed.** The
64-frame ceiling is enforced against whatever rate is chosen, so the longest legal window is
64 s at 1 fps, 32 s at 2, **16 s at 4**. A 4 fps index splits long scenes into four times as
many windows: more embeddings, more reranker calls, and a different number of candidates
competing for §3's 5–10 survivor slots.

**Not decided here — and it is a real open question, not a formality.** Which rate a Kurdish
episode should use. §3 says ~1 fps; D-049 showed 1 fps cannot represent a scene shorter than
about two seconds; and this entry shows the choice is global and materially changes every score.
Three seconds of fixture cannot answer it. It is §8.2's question and it needs `BLOCKED.md` #1 —
recorded here so that whoever has real footage knows it is a decision waiting, rather than
inheriting whichever rate an example happened to use.

---

## D-053 · The evidence held and the tests did not: five fixes were silently revertible

**The adversarial pass on M5.2** did not re-read the row — it broke each guard one at a time,
restoring from git between mutations, and asked whether the gate noticed.

Every claim in the row reproduced exactly: three windows, 10.1 s against a recorded 10.4 s,
ranks `[1, 2, 3]`, the reranker moving scene 0 from third to second, retrieval scores carried
through, 8.17 GiB, unit-norm vectors. Nothing had to be withdrawn.

**Five of seven mutations passed the gate untouched:**

    embed_frames: drop video_metadata — the entire D-049 fix          MISSED
    embed_frames: drop the timestamp assertion                        MISSED
    reranker score: drop video_metadata                               MISSED
    reranker score: add_generation_prompt True -> False               MISSED
    reranker score: replace D-051's float32 formula with a constant   MISSED

Every headline fix of the previous three iterations was silently revertible.

**The cause is one shape, and it is worth naming.** The tests covered every *refusal reachable
without weights* — recipe missing, pooling unsupported, wrong §7 role, no CUDA — and nothing
covered the **wiring**: which arguments actually arrive at the processor. That lives in the one
path the tests could not reach, and the evidence files recorded that it *worked once* rather
than that it *keeps working*. An evidence file measures a moment; only a test measures every
moment after it. This project has caught the same shape three times already at other levels —
M0.10's metric with no benchmark, M3.4's `duration_ms` echoing the request,
`encoder_available` trusting a listing. Here the thing doing the trusting was the test suite.

**Decision 1 — wiring gets stub-level tests, and the stub reproduces measured behaviour.** The
stub processor writes timestamps inside the window when `video_metadata` arrives top-level and
`<0.0 seconds><0.1 seconds>` when it does not — which is exactly what the real processor
produced for the 4162 ms window. A mutation therefore fails for the same reason it would fail
on real weights, rather than for a reason a stub invented. Inventing the stub's behaviour would
have reproduced the original defect one layer out: a check that passes because it agrees with
itself.

**Decision 2 — the score is tested as arithmetic, not as a call.** `lm_head.weight` rows
`[1, 0]` and `[0, 1]` give direction `[-1, 1]`, hidden state `[3, 1]`, so the score must be
`sigmoid(-2) = 0.119203`. Asserting that `_score_direction` was *called* would pass for a
constant; asserting the number does not.

**Decision 3 — no weights, so CI runs it.** `models/` is git-ignored and a runner has no
checkpoint. Wiring tests that needed 4 GB would be wiring tests that never run where it matters.

**Decision 4 — the audit script is not committed.** `scratchpad/mutate.py` rewrites tracked
source and restores with `git checkout`. That is fine to run deliberately and hostile to leave
in a repository, where a dirty tree at the wrong moment loses work.

**What this does not establish.** The mutation set is seven hand-chosen guards, not exhaustive;
a survivor elsewhere would not have shown up. The narrower claim is the one worth having: the
five fixes that three iterations of measurement paid for are now defended by the gate rather
than by a document.

---

## D-054 · A model that loads is not a model that works

**Found while verifying M5.4's premise**, before writing any adapter. `MCG-NJU/VideoChat3-4B`
loads in 4.8 s, reports `VideoChat3ForConditionalGeneration` and 4.86B parameters, and raises
nothing — with `lm_head.weight` **absent from the checkpoint and filled with a fresh random
initialisation**. `lm_head` is the projection from hidden states to token logits, so §3 Stage 3
Path B would have produced SV6D labels that looked exactly like labels.

    missing_keys: {'lm_head.weight'}      lm_head std 0.02000    embed std 0.02014
    tied by identity: False               equal by value: False

**The two standard deviations are 0.0200 and 0.0201.** No statistic separates a random head
from a trained one; `missing_keys` is the only signal, and nothing was reading it.

**Why, established rather than assumed.** All three shards are present and the index holds 734
tensors with no `lm_head` — the checkpoint is complete. `config.json` says
`tie_word_embeddings: False` at the top level and `text_config.tie_word_embeddings: True`
inside; the shapes are identical; transformers 5.14.1 resolves the contradiction from the top
level. The checkpoint declares `transformers_version: 4.57.0.dev0` and its own demo scripts do
a plain `from_pretrained`, so on the version its authors tested the head was tied. A behaviour
change, not an untied head.

**Decision 1 — the guard is `missing_keys`, checked at the loader, not per adapter.**
`models.assert_fully_loaded` refuses a non-empty list and
`qwen_visual.load_processor_and_model` asks for it via `output_loading_info=True`. Every §7
checkpoint this project loads goes through a loader; a per-adapter check is three chances to
forget. This is `encoder_available`'s lesson applied to weights: that function exists because
`ffmpeg -encoders` lists what was compiled in rather than what works, and this exists because
`from_pretrained` returning a model says what was constructed rather than what was loaded.

**Decision 2 — the positive control is not optional.** Both Qwen checkpoints report no missing
keys, so a guard that refused every load would satisfy the refusal test and break Stage 2. One
test refuses the real VideoChat3 case, one accepts a complete checkpoint, one requires *every*
invented weight to be named rather than the first — the fix differs per tensor.

**Decision 3 — the tying is M5.4's, with its own record.** Tying restores the authors' intent,
but overriding a third-party config is a judgment call about someone else's checkpoint and its
consequences belong beside the adapter that depends on it. Setting a flag quietly here would
have been the same mistake one layer up: a thing that works for a reason nobody wrote down.

**Retroactive check, and the reason it was urgent.** The reranker's score reads
`lm_head.weight` directly (D-051). Had M5.2's checkpoints shared this problem, "the reranker
reorders the windows" would have been a measurement of a random head. Verified: both
`Qwen3-VL-Reranker-2B` and `Qwen3-VL-Embedding-2B` report `missing_keys: NONE` and tie
`lm_head` to their embeddings. **M5.2's evidence stands** — recorded as a verified fact,
because until this iteration it was an assumption.

**Also this iteration, and it found nothing.** The same mutation audit that exposed five
unprotected guards in M5.2 (D-053) was run against the §3 Stage 3/4 Gemini path — the one with
legal consequences. Eight mutations: dropping the ZDR requirement, accepting an unattributed
confirmation, skipping governance in `judge()`, in `count_request_tokens()` and in Path A's
`discover()`, skipping the 200K tier ceiling, trusting the caller's token count, and moving
temperature off 0.0. **All eight caught, each by a behavioural test** — verified separately
from lint, since three of them also happen to break `ruff` and a lint failure is not evidence
about a guard. That path is defended. Recorded because a negative result from an audit is a
result, and because it says the M5.2 gap was specific rather than systemic.

---

## D-055 · The library version is part of the measurement, and 5.x broke a model silently

**M5.4's premise check, continued.** D-054 found `VideoChat3-4B` loading with a randomly
initialised `lm_head` on `transformers` 5.14.1. Pursuing that turned up two more
incompatibilities and then a fact about every number this project has recorded for Stage 2.

**Three ways 5.14.1 breaks VideoChat3-4B**, in the order they appear:

1. **`lm_head.weight` randomly initialised.** `config.json` says `tie_word_embeddings: False`
   at the top level and `text_config.tie_word_embeddings: True` inside; 5.x resolves from the
   top. Silent — the model loads in 4.8 s and reports 4.86B parameters (D-054).
2. **`prepare_inputs_for_generation` raises `KeyError: 'inputs_embeds'`.** The checkpoint's code
   reads a key 5.x no longer provides. 5.x also warns that `cache_position`, which the code
   uses, "has been removed from the Transformers library".
3. **The vision tower calls `flash_attn_varlen_func`, which is `None`.** Not fatal on its own —
   `VL_VISION_ATTENTION_FUNCTIONS` also holds `sdpa` and `eager`, and `vision_config.attn_impl`
   selects. flash-attn has no Windows wheels, so `sdpa` is the setting here.

**On 4.57.6 with `attn_impl="sdpa"` the model works.** `missing_keys: NONE`, `lm_head` tied,
and asked to describe a real frame of the fixture it answered:

    'A red number "0" is centered on a black background.'

Coherent and specific — a working model, not a random head.

**Decision 1 — `transformers` is pinned to `==4.57.6`, not floored.** Every §7 visual checkpoint
declares 4.57.x in its own config: Qwen3-VL-Embedding 4.57.1, Qwen3-VL-Reranker 4.57.0,
TimeLens2 4.57.3, VideoChat3 4.57.0.dev0. §7 is the table this project treats as closed, and the
version those checkpoints were released against is part of what they are. A floor of `>=4.57.1`
is what installed 5.14.1 in the first place.

**Decision 2 — `sentence-transformers` leaves the `gpu` extra.** Nothing in `src/` or `tests/`
imports it; it was used once, for the D-050 cross-check recorded in evidence. 5.7 wants
`transformers>=5`, which would fight the pin, and keeping a dependency to support a footnote is
how a pin gets quietly widened later.

**The finding that outlives this pin — the library moves the numbers.** Same code, same weights,
same GPU, same fixture:

    transformers 5.14.1   retrieval 0.353194 0.337843 0.333372   rerank 0.448391 0.442759 0.400027   order [1,0,2]
    transformers 4.57.6   retrieval 0.381785 0.373741 0.342425   rerank 0.055600 0.049956 0.022751   order [0,1,2]

Retrieval order is stable; the reranker's scores differ by an order of magnitude and **the final
ordering changed**. Every *property* holds on both — unit-norm vectors, dense 1-based ranks,
retrieval scores carried through untouched, reranking changing the order — and every *value*
moved. §8.1 already requires a throughput number to carry the hardware that produced it and an
accuracy number to carry the adapter class; this extends the same rule to the library. The four
Stage 2 evidence files now state the version they were measured on, because until this iteration
they recorded numbers that could not be reproduced from the information in them.

**Decision 3 — D-049 was re-measured under the pin rather than assumed to survive it.** It
holds identically on 4.57.6: no metadata `(0.0, 0.1)`, `fps` in the content dict `(0.0, 0.1)`,
`video_metadata` top-level `(0.5, 2.5)`. So the timestamp defect is a property of the model's
chat template, not of one library version — worth knowing, and worth not having guessed.

**Not re-recorded.** M5.2's evidence keeps its 5.14.1 numbers with the version stated, rather
than being rewritten under the pin. The measurements were real, the analysis stands, and
overwriting the numbers a conclusion was drawn from is how a record stops being one. Fresh runs
under the pin belong to whatever next needs them — §8.2 above all, which is where an ordering
finally gets judged rather than just observed.

---

## D-056 · `video_metadata.duration` is `frames / fps`, not the window's length

**Context:** M5.4. `MCG-NJU/VideoChat3-4B`'s own metadata type validates
`fps × duration == total_num_frames` to within 1e-6 and refuses anything else —
*"fps * duration must be equal to total_num_frames, but got 5.6 != 6"* on a 1400 ms window at
4 fps. `window_video_metadata` reported the window's own 1.400 s, which two shipped Stage 2
models already consume.

**Decision:** report `frames.count / window.fps`. The difference is up to one frame period.

**Why this is not a loss on the Stage 2 side, measured rather than argued.** Same frames, both
forms, `Qwen3-VL-Embedding-2B` on `cuda:0`:

    4162 ms @ 1 fps, 4 frames   4.1620 vs 4.0000   stamps (0.5, 2.5) both   embeddings byte-identical
    1400 ms @ 4 fps, 6 frames   1.4000 vs 1.5000   stamps (0.2, 1.0) both   embeddings byte-identical

The field is inert for Qwen3-VL — it derives stamps from frame index over rate — and required by
VideoChat3. Confirmed a third time end to end: the reranker scores in `evidence/m5-4-path-b.md`
reproduce `evidence/m5-2-reranker.md` to six decimals under the change.

**What is given up, stated plainly.** The number no longer answers "how long is this window". It
answers "how much time do these frames represent", which is what every consumer of it actually
computes with, and the window's own length remains on `SceneWindow` where the guards read it.

---

## D-057 · The timestamp guard's bar is derived from the frames, not set at half the window

**Context:** M5.4. `assert_timestamps_span_window` refused a stamp under 50% of the window's
duration. That threshold was written against Qwen3-VL, which merges frames in **pairs**.
`MCG-NJU/VideoChat3-4B` merges **four** and resamples first, so six frames of a 1400 ms window
arrive as one temporal group stamped at their midpoint — 0.625 s, printed `0.6`, 42.9%. The
guard rejected all three of the fixture's windows **for being correct**.

**Decision:** the bar is `(count - 1) / (2 × fps) - 0.05`. A stamp is a frame index over the
sampling rate, so the largest a correct processor can write is `(count-1)/fps`; the smallest is
that halved — a single group spanning every frame, stamped at its midpoint. Any finer grouping
puts the last stamp higher, so the halved value is a floor across every grouping at once. The
0.05 is half of the last printed digit: both templates write `f"<{t:.1f} seconds>"`.

**This replaces a threshold with a derivation; it does not relax one.** The defect it exists to
catch scales every stamp by `fps / 24`, so it stays 5.4–6× below the new bar:

    window   frames  fps   floor    real stamp   at 24 fps
    s0:w0    6       4.0   0.5750   0.600        0.1000
    s1:w0    6       4.0   0.5750   0.600        0.1000
    s2:w0    5       4.0   0.4500   0.500        0.0833

It still refuses `(0.0, 0.1)` on the 4162 ms window D-049 was written for. Both directions are
pinned at the same frame count and rate in `tests/test_video_input.py`, because a floor that
accepted 0.600 and 0.100 alike would have replaced a mis-calibrated check with no check.

**Rule this cost.** The project's own rule is not to weaken a check to make something pass, and
proving the check wrong first is what that requires. The proof is that 0.625 is exactly
`(6-1)/(2×4)` — the arithmetic midpoint of frames at 0.00 … 1.25 s, computed from the rate the
processor was handed. The old bar was not measuring the defect, it was measuring Qwen3-VL's
grouping.

---

## D-058 · Path B's SV6D time is a field the model fills, and the shift onto media time is ours

**Context:** M5.4. `MCG-NJU/VideoChat3-4B` is shown one window and told it starts at zero;
`Sv6d` and `assert_sv6d_within_window` are checked against media-absolute milliseconds.

**The offset cannot be pushed into the model.** VideoChat3 computes a frame's time as
`video_start_time + index / fps` and then validates `video_start_time < duration`. For the
fixture's second window that offset is 1.4 s against a 1.4 s clip — its own validator rejects
it. Measured, not assumed.

**Decision 1 — shift in code, not in the prompt.** Asking the model to add its own offset gets
a number that is right most of the time, and the wrong ones are silent: a window-relative time
frequently lands inside the window's absolute range. Measured on the fixture, an unshifted
reading is *rejected* for two of three windows and *accepted* for the first — the one anyone
checks. `tests/test_video_reader.py` pins the silent case explicitly.

**Decision 2 — the time comes back in a field of its own.** `parse_timestamps_ms` cannot tell a
moment from a duration ("slow push-in over 3s, starting 5:04" cites both), so shifting times
found inside free text would corrupt the durations. The prompt asks for
`dimension | seconds | text` and this module builds the label. A description carrying a second
time is refused rather than shipped, because that one is on the clip's clock and nothing
downstream marks which clock a number is on. Measured: 0 of 18 real lines did it.

**Decision 3 — the score is the caller's, never the model's.** §3: *"Path B — visual.
`VideoChat3-4B` over scenes, **plus embedding/rerank retrieval**."* The ranking half is Stage
2's, so `score_window` is injected. Asking a describer for a relevance number would have
produced one, in [0, 1], about nothing — the same class of mistake as `encoder_available`
trusting a capability listing.

**Decision 4 — the prompt's wording is a measurement, not a draft.** `name: text, and cite a
timestamp` produced a constant `0.0s:` prefix on two windows and **no timestamp at all** on the
third — output §3 requires be rejected, from the model §3 names. The pipe form returned 18 of 18
lines parseable. Recorded because a prompt looks like prose and behaves like an interface.

---

## D-059 · A per-call VRAM ceiling is not a maximum episode length

**Defect.** `discover_visual` summed every scene in an episode and refused the model when the
total exceeded 256 frames. The real `VideoChat3Reader` invokes the model once per scene. A
30-minute episode could therefore be rejected for exceeding a memory budget no invocation ever
exceeded; segmentation had been implemented and then defeated by arithmetic at the next seam.

**Decision.** Pack windows in source order into deterministic calls whose planned frame totals
are each at most 256. Validate exact one-reading-per-window inside each call before continuing.
The real adapter remains free to make smaller calls (it uses one window), while any future
batched adapter receives the ceiling the blueprint's VRAM figures actually describe.

---

## D-060 · The frames handed to a model must be the frames it reads, checked on the batch

**Context:** M6.3's premise check. Every §7 visual checkpoint's
`video_preprocessor_config.json` declares `do_sample_frames: true` with `fps: 2` and
`min_frames: 4`. No adapter in this project had read those fields, so the processor was
re-sampling every window and nothing reported it. Measured off `video_grid_thw`:

    extracted  rate    model saw
            6  4 fps   4    <- M5.2's shipped index, two frames dropped
           64  4 fps   32   <- half of §3 Stage 2's own 64-frame ceiling
            3  any     4    <- the last frame repeated, a frame never filmed
            4  1 fps   4    same
           64  1 fps   64   same

**Why it was invisible.** The vector is 2048-d and unit-norm either way, and the timestamps are
computed from the rate *we* supplied — so `assert_timestamps_span_window`, the guard written for
this exact class of defect, passes. Correct arithmetic about the frames that survived, silent
about the ones that did not.

**Decision 1 — read the count back off the batch, not off the request.** `frames_seen_by_model`
takes `video_grid_thw[0][0] x temporal_patch_size`; `assert_frames_reached_model` refuses any
mismatch. Reading the artifact rather than reimplementing the sampler's arithmetic is
deliberate: that arithmetic is version-specific and a reimplementation would agree with the
library right up until it stopped.

**Decision 2 — refuse rather than accept the checkpoint's re-sampling as its recipe.** The
opposite reading is defensible — `fps: 2` *is* declared preprocessing, so extracting at 4 fps is
our error. Both readings agree on the action: extracting a rate the model will not read is the
mistake, and it should be loud. The refusal names both branches of the remedy, because the
obvious one-line version ("come back at or below 2 fps") is unachievable for a 1400 ms scene —
2 fps yields three frames, which is odd and gets padded, and 1 fps yields one, which
`extract_window_frames` already refuses.

**Decision 3 — one function tokenises a window, with all three checks inside it.** `window_batch`
replaces the same eight lines copied into the embedder, the reranker and the Path B reader. Two
of the three checks it now carries were originally found by adding one to a single call site and
discovering the others had never had it; a fourth adapter should not be able to repeat that.

**Decision 4 — M5.2's evidence index is rebuilt at 3 fps, and 3 is derived rather than chosen.**
For a 1400 ms scene: 1 fps gives one frame (refused), 2 fps gives three (padded), 3 fps gives
four (clean, because `min_frames` dominates at short durations). It is the only legal rate at
that length. Every Stage 2 number moved — the rank-1/rank-2 margin from 0.005644 to 0.015441, one
score by 0.011, which is 3.5x the bfloat16 error D-051 rejected for being 57% of a margin. The
reranker now reverses retrieval outright rather than making one swap, so M5.2's central claim is
better supported by the corrected run than by the original.

**What this costs, stated plainly.** Four evidence files carry numbers measured on partially
delivered frames and are annotated as superseded rather than rewritten, the same arrangement as
D-055's version pin. It also supplies the missing explanation for D-052's unresolved
non-monotonicity: its "4 fps" arm was eight frames read, not sixteen, so a comparison labelled
1-vs-4 was really 4-frames-vs-8. D-052's conclusion is unchanged and now overdetermined.

---

## D-061 · "Fully enforced" covered five claims and four of them were tested

**Context:** iteration 10's adversarial pass on Kurdish invariant #4. The PROGRESS row read
*"fully enforced. Shaping, stack check on a real build, font coverage on the real font, our own
line breaks, and a golden render compared per gate run with `shaping=simple` as a failing
negative control."*

**What held.** The reference reproduces **pixel-exact** on ffmpeg 8.1.1 here; it contains real
shaped text (2734 ink px, one band at rows 1731-1771, the sentence-final period at the left where
an RTL run ends); `shaping=simple` differs by 4803 px (0.232%) and the comparison is exact
equality on decoded pixels, so a subtler shaping failure cannot slip past a tolerance; six of six
mutations caught; and CI has a dedicated step that fails if the golden test *skips*.

**What did not.** "Our own line breaks" had no rendered evidence. It was asserted as a unit test
over word tuples, a `\\N` in the ASS text and the string `WrapStyle: 2` in the header — and
`GOLDEN_CAPTION_TEXT` is 28 characters against a 32-character limit, so the golden render is a
single line and cannot exercise wrapping at all. The one claim about layout was the one never
rendered.

**Decision 1 — three tests on the decoded pixels, not a second golden file.** Band counting
(contiguous rows containing ink) asserts what the claim is about — two lines out because we put a
break in, one line without it — and needs no committed reference, so it cannot fail on a
font-metric change that is still two correctly broken lines. Measured: rows 1667-1707 and
1728-1765 with `\\N`, one band at 1728-1771 without.

**Decision 2 — the `WrapStyle` claim is demonstrated on deliberately over-wide input, and the
string assertion is kept.** With our own `\\N` present, `WrapStyle: 0` renders **byte-identical**
to `WrapStyle: 2`; the setting only bites on a line wider than the play area, which our
32-character limit means production never emits. So a pixel test on production output *cannot*
catch that mutation, and pretending otherwise would be worse than saying it. The new test feeds
twelve words on one line — `WrapStyle: 2` gives 1 band clipped at the frame, `WrapStyle: 0` gives
3 — which is the first evidence that the header does anything.

**Decision 3 — no guard for the clipping case, because it was measured and cannot happen.**
`WrapStyle: 2` clips an over-wide line instead of wrapping it, and `wrap_caption_lines` refuses to
split a word longer than `max_chars` (splitting Arabic-script mid-word breaks shaping). That reads
like a path to clipped Kurdish, so the threshold was measured: ~14.3 px per character, so a single
word needs about **67 characters** to reach the 960 px play area. `بەرپرسیارێتییەکانیشیانەوە` is
25. The 32-character limit carries a >2x margin. Writing a check for a case Kurdish cannot produce
is the "invent work to look busy" the loop forbids, so it is recorded here instead.

**The generalisable part.** A summary phrase covering several claims is worth as many audits as it
has claims. "Fully enforced" was four-fifths true, and the missing fifth was invisible precisely
because the sentence read as one assertion.

---

## D-062 · A grounding model's interval is on the window's clock, and the shift lives beside the type

**Context:** M6.3. `MCG-NJU/TimeLens2-4B` is shown one scene window and answers in seconds from
**its** start. Every number `boundary.py` fuses is media-absolute. Measured: shown only scene 2 of
the fixture — 2800..4162 ms — and asked about the red "2" on blue, the model returned
`[[0.0, 0.8]]`.

**Why this is worse than D-058's version of the same trap.** Path B's offset corrupts a *label*;
this one moves a *boundary*. Put through the real selector and the real fusion, with a sentence
anchored at 0..400 ms:

    shifted     (2800, 3600) ms   overlaps False   selector None   final 0..600   extended by tail
    unshifted   (0, 800) ms       overlaps True    selector 800    final 0..800   extended by
                                                                                  timelens_interval_end

The clip is 200 ms longer and records **visual evidence** as the reason, for footage 2.8 seconds
away. Kurdish invariant #2 holds throughout — it constrains direction, not relevance. That is
verbatim the sentence M6.1 was written about, reached through the offset instead of through
`max()`.

At an anchor of 0..600 the two agree on 800 ms and differ only in `out_extended_by`. **The number
coincides and the attribution is still wrong**, which is the harder failure to see, and §8.2 reads
boundary provenance off exactly that field.

**Decision 1 — `VisualEvidenceInterval.from_window`, beside the type, not in the adapter.** A
second producer — a batch grounder, a rehydrated JSON document — cannot omit what the constructor
does. It also refuses a span outside the window the model was shown, with a tolerance of 0.05 s:
ffmpeg samples at interval centres and the model answers to one decimal, so reaching the end is
only expressible within that rounding. 1.40 s of a 1.362 s window is accepted; 1.562 s is not.

**Decision 2 — the claim is the query and the confidence is `None`.** TimeLens2 returns spans and
nothing else. `claim` records what was asked (`"evidence for: <query>"`) because
`VisualEvidenceInterval` refuses an empty one, and `confidence` stays `None` — 0.0 would be a
measurement the model never made.

**Decision 3 — the prompt is the card's wording, quoted.** A reworded question to the same weights
is a different question and the reply would still parse.

**Decision 4 — `align_to_patch_grid` uses the checkpoint's own `smart_resize`.** TimeLens2 is the
only §7 visual checkpoint shipping `do_resize: false`, so its frames must arrive a multiple of
`patch_size x merge_size` = 32; the 640x**360** fixture otherwise raises a patch-grid shape error
naming a tensor whose remedy is not guessable from it. Measured: 640x360 -> 640x352. A no-op for
the other three, so `load_window_images` takes the processor everywhere rather than making each
adapter know which kind it has.

**The parser defect the real model found on its first run.** Asked about a scene the query is not
in, TimeLens2 answered `[]`. The first `parse_spans` searched for `[[…]]` with a regex and refused
it as malformed — so the commonest correct reply would have crashed, on exactly the scenes where
the query is absent, which is most of them. It decodes from the first bracket now. This is the
second time here that "found nothing" was nearly an error; `interval_end_for_fusion` already
distinguishes absence from an out-point of zero, and the adapter now agrees with it.

**Recorded because the gate could not be run where it usually is.** A concurrent session was
editing this checkout throughout the iteration — three consecutive gate runs gave 23 failures, then
5, then 3 lint errors, all in its files. This change set was proved in a worktree at HEAD plus
these files: ruff, format and mypy clean, full suite exit 0 excluding `tests/test_gate.py`, whose
9 failures reproduce identically at plain HEAD in the same worktree and are the editable-install
path rather than a regression. Stated rather than smoothed over: a green gate claimed on a tree
that was red is the thing this project's DONE rule exists to prevent.

---

## D-063 · The checkpoints' declared 2 fps is a hard sampling ceiling

**Date:** 2026-08-08 · **Blueprint ref:** §3 Stage 2, §7 · **Type:** measured guardrail

All four local visual checkpoints declare a 2 fps video sampler. Reading `video_grid_thw` showed
that inputs above that rate are silently resampled: 64 frames at 4 fps became 32, and 45 at
3 fps became 30. Odd frame counts are padded by repeating the last frame. Both failures leave a
valid embedding or generation, so downstream code cannot detect that the model saw different
footage from the window it reports.

**Decision.** `SceneWindow` refuses rates above 2 fps. Extraction trims an odd tail only when at
least one full temporal patch remains, and the model-input boundary verifies the frame count it
actually received. The composed runner uses 2 fps by default; the uncomposed arithmetic reference
remains §3's ~1 fps. This supersedes the earlier 3 fps default rather than preserving a measured
rate that the processors discard.

---

## D-064 · Windows Stage 1 crosses one explicit WSL2 process boundary

**Date:** 2026-08-08 · **Blueprint ref:** §3 Stage 1, §6 · **Type:** architecture decision

The official `omnilingual-asr` package is the only supported loader for the two canonical model
cards, and its `fairseq2n` dependency has no Windows wheel. The target Windows host already has
WSL2, Python 3.12, 740 GB free and both RTX 3090 Ti GPUs visible through CUDA. Leaving
`--omni-asr` pointed at the host interpreter therefore made a wired runner that could never run.

**Decision.** On Windows, `--omni-asr` automatically cuts Stage 0's bounded WAV regions on the
host and invokes one WSL2 worker for the whole media item. The worker loads LLM-7B and CTC-3B
once, runs their forwards in parallel per segment, performs CTC/Viterbi alignment, shifts every
word to the media clock and exclusively publishes one validated raw transcript in the shared
work directory. Linux remains direct. `--omni-asr-runtime` exposes the choice and never silently
falls back between them.

The request accepts only relative segment paths confined to its directory. Sorani text crosses
the boundary in UTF-8 files, not console output. `hawedit-asr-setup` provisions a
source-fingerprinted runtime under local app-data, so an installed wheel does not depend on a
checkout path and a package upgrade cannot silently use an older worker. The same physical GPUs
still count as hawapc01, but benchmark metadata must name WSL2 in `Hardware.notes`; no RTF or CER
is inferred from wiring.

---

## D-065 · What the sampling ceiling moved, and the evidence it retired

**Context:** D-063 (recorded by a concurrent session) and this implementation were arrived at
independently within the same hour, from the same measurement — 64 frames at 4 fps read as 32,
45 at 3 fps read as 30, odd counts padded by repeating the last frame. The decision there is the
decision; this records only what it cost, which that entry does not cover.

**The implementation, for the record of where the guard lives.** `SceneWindow.__post_init__`
refuses `fps > DECLARED_SAMPLING_FPS`, beside the existing refusal of `fps < REFERENCE_FPS`, so
the rate is bounded from both directions in the type every planner and adapter routes through.
`extract_window_frames` trims an odd emitted count down to a whole temporal patch, and leaves the
trimmed file on disk — trimming is a decision about what to hand over, not a deletion, so revising
it needs no re-extraction. `pipeline.py`'s composed path takes the constant instead of a literal
`3.0`, and `--visual-fps` defaults to `None` so its own sentinel branch is reachable.

**Third re-measurement of the same index.** D-055 moved it with the library pin, D-060 with the
frame re-sampling, and this with the rate bound:

    rate    handed / read    rank-1 to rank-2 rerank margin
    4 fps   6 / 4            0.005644
    3 fps   4 / 4            0.015441
    2 fps   2 / 2            0.027870

The margin widened monotonically as fewer frames were discarded — a factor of five end to end —
and at 2 fps the reranker reverses retrieval outright, promoting the window retrieval ranked last.
Path B's peak VRAM fell 11.99 -> 9.56 GiB, because the discarded frames were being encoded first.

**A wider margin is not a better index, and this file does not claim one.** At 2 fps a 1400 ms
scene is **two** frames — the minimum `extract_window_frames` accepts — and whether that is a good
index entry is §8.2's question. `BLOCKED.md` #1.

**Evidence retired.** `evidence/m5-2-*.md` and `evidence/m5-4-path-b.md` record runs at 4 and 3
fps; both rates are now refused at construction, so neither run is reproducible from the code that
produced it. Annotated rather than rewritten, as D-055 and D-060 were. Three re-measurements of one
index in one day is itself the finding: every number here carries a library version, a frame
delivery rate, and now a sampling rate, and none of those was visible in the first write-up.

**Audit.** 4/4 mutations caught against a baseline verified green first. The trim survived the
first pass, because the sweep simulates the processor's arithmetic rather than running ffmpeg; a
real extraction closed it — 1400 ms at 2 fps writes three JPEGs and hands over two.

---

## D-066 · D-037 clause 4 restored: below the survivor floor, retrieval refuses

**Context:** `rerank_and_keep` was changed to `survivor_count = min(keep, len(reranked))` — it
returned however many windows existed instead of refusing. **I committed that change myself** in
`3c270f7`: I staged the whole of `visual_index.py` rather than building HEAD-plus-my-edits as I had
for the shared documents, and it carried a concurrent session's edit into main with it.

**What the change reversed.** D-037 clause 4 states the decision and the alternative it rejected,
verbatim: *"Below the survivor floor the retrieval refuses instead of shortening. §3 fixes the
count at 5–10. A three-scene video cannot satisfy it. The alternative considered was returning
whatever exists; rejected because §8.2 counts Recall@K on this list, and three results in a column
that says five is a number that does not mean what the column says."* No superseding entry was
recorded. `PROGRESS.md` still certified that `rerank_and_keep` *"correctly refuses"*, and the
function's own docstring two lines above the change still said the reranker *"may not ... drop
below the survivor count"*.

**Decision — restore the refusal, and move it before the reranker runs.** The rule this project
holds is that an invariant is not weakened to make something pass, and that a check believed wrong
is proven wrong first. Neither happened. The refusal is now checked against `len(index)` before any
scoring, so a media too short for §3's slice costs no GPU time, and the message names the caller's
option rather than the function's: *"the caller decides whether to skip the slice, and says so,
rather than this function shortening it quietly."*

**Why the short-media case does not justify it.** A three-window index is the **fixture**, not the
product. At 2 fps with a 32-second ceiling, a 40-minute Kurdish episode plans roughly 75 windows;
the only inputs that fall below five are test material. `evidence/m5-2-reranker.md` has recorded
since M5.2 that the keep-5–10 slice is *"not exercisable on this fixture"* and that
`rerank_and_keep` *"correctly refuses"* it.

**The counter-argument, recorded rather than dismissed.** §8.2's Recall@K over three candidates is
arguably still well defined — the denominator is smaller, not corrupted — and
`VisualDiscoveryResult` already reports `indexed_windows` and `retrieved`, so a reader could see
the shortfall. That is a real argument that D-037 clause 4 may be wrong. It is **not settled here**,
because settling it needs the labelled set §8.2 scores against, which is `BLOCKED.md` #1. Until
then the recorded decision stands, which is the only rule available when neither side can be
measured.

**What the other session's change got right, and is kept.** It added a check that the reranker
returns exactly as many hits as it was given — *"every retrieved window must be scored ... none may
disappear"* — which is stronger than what it replaced and is retained unchanged.

**One mutation survives, and it is redundancy rather than an unprotected guard.** Reverting the
final slice to `min(keep, len(reranked))` changes no behaviour and no test goes red. That is
provable rather than lucky: `hits` is `min(k, len(index))` and the floor now guarantees
`len(index) >= keep`, while the equal-length check guarantees `len(reranked) == len(hits)`, so
`len(reranked) >= keep` always. The plain `[:keep]` is kept because it states the contract; writing
a test for a branch that cannot be reached would be a test that measures nothing.

**Audit.** 3/3 anchors applied; 2 caught, 1 provably unreachable as above. Baseline verified green
first (1067 passed, 0 skipped).

---

## D-067 · Optional dependencies must be declared missing to mypy, and no ignore may depend on one

**Context:** `gh` became available and showed the remote gate had been red since 14:07 while
`verify.sh` printed VERIFY OK here. Four errors, all on lines I added across iterations 8-12 and
never pushed: three `import-not-found` for `PIL` and `transformers`, and one `unused-ignore`.

CI installs `.[dev,media]` and deliberately not `gpu`, so `mypy --strict` checks two different
programs in the two places. The fourth error is the same fact from the other side and the more
interesting one: `# type: ignore[no-untyped-call]` is **required** where transformers is installed
(it ships `py.typed` and leaves `AutoProcessor.from_pretrained` untyped) and **forbidden** where it
is absent. No single annotation satisfies both.

**Decision 1 — `transformers.*` and `PIL.*` join the existing `ignore_missing_imports` list.** That
list already holds `torch.*`, `klpt.*`, `scenedetect.*` and the rest; these two were never added.
Every import of them already sits inside a function behind `try: ... except ImportError`, which is
what makes them optional at runtime. The override says the same thing to the type checker.

**Decision 2 — the environment-dependent ignore is removed, not relocated.** Binding the loader
through an explicitly-`Any` local is correct in both environments and needs no ignore at all.

**Decision 3 — the gate now runs the type checker in the runner's condition.**
`mypy --strict --no-site-packages` over the two modules that import the extra, asserting exit 0.
Scoped to those two files deliberately: over all of `src` that flag is *stricter* than CI, which
installs `media`, and an override for `numpy` would discard the stubs it ships.

**Two wrong versions of that check, both worth keeping in the record.** The first parsed
`pyproject.toml` and asserted each gpu distribution appeared in the override list — it passed while
the real condition still failed, which is this very finding repeated one layer up: an assertion
about configuration is not an assertion about the type checker. The second passed for a worse
reason — the subprocess reused `.mypy_cache` written by the ordinary typecheck, which ran *with*
the packages installed, so mutating an override away changed nothing it could see.
`--no-incremental` is load-bearing, not tidiness.

**Audit.** 3/3 mutations caught against a baseline verified green first, and the cache defect was
found by exactly that audit reporting SURVIVED twice.

**What it says about the DONE rule.** `BLOCKED.md` #7 has said since it was written that the second
half of "verify.sh green AND required CI checks green" refers to nothing, because the workflow runs
without blocking. This is the first time that gap was measured rather than described: green here,
red there, for three hours, and nothing in the repository could tell.

---

## D-068 · The CUDA refusal must not sit behind an optional import, and stub tests must name a device

**Context:** D-067 fixed the runner's typecheck; the pytest step then failed on four tests, all
mine, all in `tests/test_qwen_visual.py`. The remote gate had in fact been red since the first
Stage 2 commit landed — the last green run on `main` predates it.

**Two independent causes, both the same shape: a test that only runs on the machine that wrote
it.**

**1. The CUDA refusal was unreachable where it matters most.** `load_processor_and_model` imported
`torch` and `transformers` in one `try`, so on the runner — torch present via `media`, transformers
absent from `gpu` — the ImportError fired first and "install the gpu extra" was the only error
anyone could get. The more specific refusal, *a GPU was asked for and this machine has none*, could
not be produced at all, and the test asserting it failed on the message rather than the behaviour.
Split into torch, then the CUDA check, then transformers. Verified by hiding `transformers` and
forcing `cuda.is_available()` False: the refusal now fires.

That ordering is better independently of the test. `media` is installed anywhere Stage 0 runs, so
the check that depends only on torch should not be gated behind a package from another extra.

**2. Four stub-based wiring tests defaulted to `cuda:0` and moved stub tensors there.** On a
CPU-only torch that is `AssertionError: Torch not compiled with CUDA enabled`. The device is
incidental to what they assert — `video_metadata` at the top level, the float32 weight-row score,
`add_generation_prompt` — so they now pass `device="cpu"` explicitly, as the Path B and Stage 5
wiring tests already did. `DEFAULT_DEVICE` stays `cuda:0`, and the one test that *is* about the
refusal keeps asking for `cuda:0`.

**The lesson, which is D-053's from a new direction.** That audit found five guards revertible
because the tests covered only refusals reachable without weights. These tests covered the wiring —
and still only ran on hardware the runner does not have. "Runs without weights" and "runs on the
machine that will check it" are different properties, and only the second is what CI measures.

---

## D-069

**A module described in prose after the table has no status, and eight of them had drifted
there or out entirely.** An external review reported four modules with "no PROGRESS ledger row."
Reproduced and undercounted: eight had no status, and `gate.py` was a ninth that nothing but the
new test found, because M0.1 cited `tests/test_gate.py` and never the module under it.

**The failure is structural, not clerical.** `visual_pipeline.py` and `reframe.py` each *were*
described — in a `>` blockquote below their table, naming neither the file nor a legend mark. So
the composed Stage 2 → Path B pipeline that §9's M5 row calls "DONE in code" was absent from the
35 DONE / 7 PARTIAL tally the ledger exists to publish, and unreachable by any test, because a
test that greps `PROGRESS.md` passes on the prose. This is the same shape as the corrections
problem the review named separately: M5.3's cell still advertised `run_pipeline(read_scenes=…)`,
retired and refused at `pipeline.py:618`, with the correction eight lines below the row.

**Decision: a correction belongs in the cell, and a module belongs in a row with a mark.**
`test_the_ledger_accounts_for_every_module` reads the evidence cell of rows whose *status* cell
is a legend mark — deliberately not the document — so a prose-only mention still fails. The
mutation that proves this is the control: reintroducing the original defect (module named only
in a blockquote) is CAUGHT. Two floating amendments were promoted to rows carrying measured
status: **M5.5** (`visual_pipeline.py`, PARTIAL) and **M8.1** (`reframe.py`, PARTIAL, M8's own
§3-mandated prerequisite rather than a SAM 3 substitute). **M2.9** is new for `keyframes.py`;
`smoke.py`, `collisions.py`, `asr_worker.py`, `wsl_setup.py`, `editorial_bench.py` and `gate.py`
attach to the rows that already own their deliverable.

**Statuses are measured, not judged** (`evidence/unlisted-modules.md`). M5.5 is PARTIAL because
the composed path *refuses* on the only media here — 3 planned windows against a survivor floor
of 7 — at **4.08 GiB** peak against the 8.16 GiB of both models resident, which measures D-066's
claim that the floor sits ahead of the reranker's weights rather than merely ahead of its call.
M8.1 is PARTIAL because the tracker returns **0 focus points** on a fixture with no face: the
`STATIC_CENTRE` fallback is verified on real pixels and `FACE_TRACKED` is not. M2.9 is DONE
because the transport is complete and measured — 6 JPEGs, `FFD8`, 6 distinct stamps inside the
requested span — and the *call* those bytes would ride is M2.6's shortfall, not this row's.

**Three documents claimed the survivor floor degrades gracefully; it refuses.** `README.md`,
`AUDIT_REPORT.md` and the code disagreed about the one behaviour a reader sizing a job would act
on. Fixed in both documents and bound by a test that greps all four top-level docs for the
claim.

**`collected` is not `passed`, and the README said the wrong one.** `gate.py:162` compares
`evidence.passed`; the README described the floor as tests *collected*. The two differ by
exactly the skips — the case the ratchet exists to catch — so the README documented a gate that
a creeping skip condition walks straight through.

**One test was redesigned mid-audit rather than kept.** The audit-count check first asserted the
figure equalled `scripts/test-count.floor`, and went red at baseline: these four tests ratcheted
the floor past the recorded number. A check that fails whenever anyone adds a test, whose cheap
fixes are editing a historical document or deleting the check, manufactures exactly the pressure
to weaken the gate this project forbids. It also misstated the defect — `1,063` was wrong
because nothing said *when* it was true, not because it differed from today's floor. The test
now requires a date beside any test count and lets the number age.

**No digest is recorded for the wheel, deliberately.** The review quoted a current wheel hash and
faulted `AUDIT_REPORT.md` for an obsolete one. Two consecutive `pip wheel` runs at one unchanged
commit: 309,536 bytes both times, digests `89CA7434…` and `A77FEEA01C…`. Nothing sets
`SOURCE_DATE_EPOCH`, so every wheel hash this project has recorded was obsolete when written —
the audit's figure was not stale, it was never meaningful. Quoting one reads as a supply-chain
guarantee the project does not make; the size stays, the digest goes, and reproducible builds
join the unpinned model revisions as a named gap.

Gate: `VERIFY OK — 1072 passed, 0 skipped`. Mutation audit 5/5 against a baseline verified green
first. Tally moves 35/7/4/1 → 36/9/4/1, which is the point: the program was always this size.

## D-070

**Stage 5 fused three of §3's five out-point signals, and the missing one was already being
measured.** `fuse_boundary` has always carried a `natural_silence` branch; the runner's single
`BoundaryInputs(` site never set it, so the branch was unreachable from `run_pipeline` and every
clip this project has ever cut had its out point decided by tail / shot cut / TimeLens alone.

The reason it counts as a wiring defect rather than a missing feature: `_pauses_between` derives
the silences between Stage 0's VAD speech regions a hundred and fifty lines earlier in the same
function, hands them to §4.2's `segment_sentences`, and drops them. The measurement Stage 5
needed had already been taken.

**Decision: "natural silence" is the end of the VAD speech region containing `anchor_out`.** The
mirror of `_vad_onset_for_anchor`, which takes the *start* of the region holding the first
anchor. `anchor_out` is a transcript time — a word's end, from §4.2's Viterbi alignment — while
VAD measured when the audio actually went quiet; when the audible tail runs past the last aligned
word, that is the point §3 means by ending on silence.

**Rejected: the onset of the next speech region.** That is the far side of the pause, and
reaching across an entire silence to butt against the next utterance lengthens every mid-episode
clip and clips the following speaker's first phoneme. On the fixture it puts a sentence-0 clip
at 1954 ms rather than 1790 ms. The rejected reading is pinned by the control test below, not
just by this paragraph.

**No threshold is invented, per the standing rule.** Every value returned is a measured region
edge, which is also why the result cannot run into the following region: a region's end precedes
the next region's start. `None` when `anchor_out` is not inside a speech region — the clip
already ends in silence and there is nothing to extend to; a number there would be
indistinguishable from a measurement, and §8.2 reads which signal moved the boundary.

**The control is the test that proves it, not the positive case** (`evidence/stage-5-natural-silence.md`).
On the stock fixture transcript the tail reaches 1900 ms and natural silence 1790 ms, so the tail
wins and the fix changes nothing — that case is asserted as-is. Ending the same word 200 ms
earlier inverts it to 1700 vs 1790 and the out point lands on the silence. A positive test alone
would have certified the rejected reading equally well; the control fails for it. Both assert on
`run.clip.boundary`, through a real `run_pipeline` over the real media with real VAD.

**An edge the measurement exposed:** Silero reported region 2 ending at 4180 ms on a 4162 ms file.
`media_duration_ms`'s existing clamp absorbed it at the boundary; D-086 later moved the invariant
to Stage 0 so impossible timestamps cannot enter the canonical transcript in the first place.
The boundary clamp remains defence in depth and the 200 ms tail remains in the `max()`.

§3's fifth out-point signal, `speaker_turn_end`, still needs the gated diarization model
(`BLOCKED.md` #4, measured 401 from here). Four of five, with the fifth absent for a stated
reason rather than by omission.

Gate: `VERIFY OK — 1075 passed, 0 skipped`. Mutation audit 5/5 against a baseline verified green
first, including the next-onset misreading and a mutation in `boundary.py` rather than
`pipeline.py`, which confirms the tests cover the chain from Stage 0's VAD to the emitted
boundary rather than the argument merely being present.

## D-071

**A re-run into a used work directory paid Gemini and loaded two GPU models before refusing to
overwrite.** The `FileExistsError` guard lived beside the render step, ~180 lines after the
billed Stage 4 `generateContent` at line 814 and after Stage 2/3 had put Qwen and VideoChat3 on
the GPU. The condition depends on `work_dir`, the media id and the sentence selection — nothing a
model produces — so it was knowable before any of that was spent.

**Decision: hoist the guard to each point where the selection first becomes knowable, and keep
the one before the first write.** Three call sites of one function, because they are three
different moments rather than three copies of a rule:

* after `_prepare_selection` for an explicit selection — saves the GPU work *and* the billed call;
* after `--auto-select` settles a selection, which it cannot do until Stage 3 has ranked
  candidates — saves the billed call, and the GPU work there is what produced the selection, so
  it is not savable;
* immediately before the first write — costs nothing and still catches a file that appeared while
  the models were running.

**`clip_id` and the five artifact paths now derive from `_clip_id` and
`_delivery_artifact_paths`, once each.** A guard that computes a path a second way can pass while
the write collides, which is the obvious way this fix goes wrong.

**The artifact is a request that never happened**, so the tests assert the billed call *count* is
zero, not merely that an exception was raised. `--auto-select` is a separate test because without
the second call site it still reaches the judge: the first guard sees an empty selection and
returns.

**The control did real work.** `test_a_clean_work_directory_still_reaches_the_judge` runs the same
call with nothing planted and requires the judge exactly once — a guard hoisted somewhere
`select_sentences` is always empty, or one that refused everything, passes both refusal tests and
fails this. Its first version failed on `_assert_verdict_matches_request`, the pipeline's own
refusal of a verdict whose `candidate_id` does not match the request; that only fires on a run
which truly reaches Stage 4, so the control was shown to reach the judge before it was made to
pass.

**Mutation audit 4/5 targeted, 5/5 at the gate** (`evidence/billed-before-refusing.md`). The
survivor is mutating `_clip_id`, which moves guard and writer together by design and so is
invisible to those four tests. It is still behaviour-changing and the full suite catches it —
dropping `select_sentences[-1]` collides `(0,)` with `(0, 1)` and three pre-existing tests fail,
led by `test_distinct_selections_do_not_overwrite_each_others_deliveries`. Measured by running the
whole suite under the mutation, not assumed. No test pins the filename format: that is a naming
convention, not a requirement, and pinning it would fail on an intentional rename while catching
nothing this fix concerns.

**Not fixed, and not claimed:** delivery is still not atomic. This refuses a colliding run up
front; a run that fails halfway can still strand a partial `.ass` or `.mp4` and force a new work
directory.

Gate: `VERIFY OK — 1079 passed, 0 skipped`.

## D-072

**On ordinary NTSC footage the run left four fifths of §2's delivery set on disk and it looked
whole.** The runner wrote the editing JSON, then the SRT, then *built* the EDL — and the EDL is
the one that legitimately refuses, because `build_edl` will not fake SMPTE drop-frame timecode
for 29.97 fps (non-drop drifts ~3.6 s per hour and looks correct throughout). Measured on a real
transcode: a complete, playable 1080×1920 captioned MP4 plus ASS, JSON and SRT, no EDL, stage
reported skipped (`evidence/partial-delivery-set.md`). D-071 named delivery atomicity as an open
shortfall; this closes it for the sidecar set.

**Decision: build all three, then write all three.** The defect was interleaving fallible
computation with writes, and nothing in the sequence needs a file to exist before the next step.
The `except` additionally unlinks the three sidecar paths, so a write failing partway — disk
full, permissions — is all-or-none too, and `OSError` joined the caught set for that reason.

**The MP4 and ASS are deliberately kept.** Stage 6 genuinely succeeded and `run.render` reports
that path, so deleting its output because a later stage failed would make the report a lie and
would discard an encode over a sidecar. Rejected explicitly, not overlooked — and pinned by a
mutation that deletes them and is CAUGHT.

**Mutation audit 4/4, after two corrections that are the real content here.**

*The audit first reported the original defect as SURVIVED, correctly.* The cleanup loop alone
makes the final disk state right, so reverting the build-before-write ordering changed nothing
observable: two changes were made and only one was load-bearing. The ordering still earns its
place — written-then-deleted leaves a window in which the partial set exists, and a crash inside
it strands exactly what this fixes — but an untested property is not a property. So
`test_a_refused_edl_never_writes_a_sidecar_at_all` records every `Path.write_text` and asserts
no sidecar write is *attempted*, which is the only way to distinguish "cleaned up" from "never
written".

*Then the mutation itself was wrong:* it inserted a second `build_edl` while leaving the early
one, so the refusal still fired before any write and the bug was never reintroduced. A mutation
that does not restore the defect measures nothing — the same class of error as a green baseline
nobody verified. Rewritten to remove the early build; it is CAUGHT.

*And the first write-attempt test failed for the wrong reason,* matching sidecars by suffix while
Stage 1 writes `transcript.raw.json` under the same work directory. It compares exact paths now.

**Not fixed, and not claimed:** an NTSC source still produces no EDL. That is correct — refusing
drop-frame beats shipping a conform that drifts — and the run says so. Writing real drop-frame
timecode is separate work.

Gate: `VERIFY OK — 1083 passed, 0 skipped`.

## D-073

**27 GB of weights were on this machine and nothing recorded which revision produced them.**
`fetch-models.sh` called `snapshot_download(repo_id=source, local_dir=dest)` with no `revision=`,
which resolves whatever the branch head points at on the day it runs. Measured: every §7
repository resolves to a head, and no marker on disk and no tracked file named any of them
(`evidence/model-revision-pinning.md`). So the numbers in `evidence/m5-2-embedder.md`,
`m5-2-reranker.md`, `m5-4-path-b.md` and `m6-3-grounding.md` were measured against weights whose
identity was unrecoverable — this project's own "a number carries the hardware and adapter that
produced it" rule, failing one level down at the adapter's weights.

**Decision: a tracked `models/revisions.json`, and `revision_for` refuses rather than resolving.**
Shaped deliberately like D-022's `source_for`: the fetcher does not guess a repository id, and it
does not guess a revision either. An unpinned repo is refused with the command that resolves it
honestly, and the fetcher moves on to the rest exactly as it does for an unconfigured source.
Pinning is also the checksum — the Hub resolves a commit to exact file hashes, so a pinned
download yields those bytes or fails.

**The pins are measured, not chosen.** Each was read live from `HfApi().model_info(repo).sha`
and then **verified against the weights already here**, by comparing the git blob id of the local
`config.json` with the Hub's blob id for the same path: all four visual checkpoints MATCH. So the
file names the revision that produced the existing evidence, which is what makes those
measurements reproducible rather than merely recorded.

**`pyannote/speaker-diarization-community-1` is deliberately unpinned.** It is gated, measured
401 from here, and has never been downloaded (`BLOCKED.md` #4); pinning a revision for contents
nobody in this project has seen would record a number rather than a fact. A test asserts it is
the *only* unpinned repository, so the exemption cannot spread quietly.

**The tests execute the fetcher's own download block rather than grepping it.**
`_fetcher_download_block()` pulls the real heredoc out of `fetch-models.sh` and `exec`s it against
a stubbed `huggingface_hub`, asserting the actual call carries `revision=`. A grep would have been
an assertion about the text of a command rather than about what it does — D-067's mistake, one
layer up. The control is the unpinned case: no download call at all, exit 1.

**Mutation audit 6/6**, two of them mutating `fetch-models.sh` rather than `models.py`, which is
what shows the tests cover the chain an operator actually runs.

**Not fixed, and named rather than folded in:** `fetch-ffmpeg.sh` still downloads
`…/ffmpeg_bins/main/v8.0/linux.zip` — a branch path — and unzips and executes it with no SHA-256
check. Different supply chain, different verification story (it needs a published digest to
compare against, which that repository does not appear to offer), and combining them would have
made neither testable. And the weights on disk were verified against the pin by `config.json`
blob id, not by re-downloading and hashing all 27 GB.

Gate: `VERIFY OK — 1091 passed, 0 skipped`.

## D-074

**The pin file from D-073 shipped to nobody.** `models/*` is git-ignored — with a
`!models/sources.json` exception and a comment explaining precisely this trap — so `git add -A`
skipped `models/revisions.json` in silence. The code that requires it was committed without it;
the local gate passed because the file was on this machine, and the runner failed with
`no pinned revisions found under /home/runner/work/HawEdit/HawEdit/models`. `git diff --cached
--stat` had listed nine files and not that one, and I read the total rather than the list.

**Decision: close the class with a test, not a third comment.**
`test_every_data_file_the_wheel_ships_is_tracked_by_git` reads
`[tool.setuptools.data-files]` from `pyproject.toml` and asserts every declared path appears in
`git ls-files`. Driven off the packaging declaration on purpose, so a file added to the wheel
later is covered without anyone remembering to extend a list. Verified red before the fix — it
named `models/revisions.json` — and green after, alongside the `.gitignore` exception.

**This is D-067's shape for the third time**: the local gate and the runner were checking
different programs, and only the runner could see the difference. The first two were an optional
dependency and a CUDA device; this one is a file git was told to ignore. The lesson that
generalises is not about any of those three — it is that "it works here" is a statement about
this machine until CI agrees, which is why the loop pushes and waits rather than stopping at
`VERIFY OK`.

Gate: `VERIFY OK — 1092 passed, 0 skipped`.

## D-075

**D-073 refused to pin `pyannote/speaker-diarization-community-1` for a reason that is false,
and a parallel agent pinning it is what prompted the check.** That entry argued a gated repo
nobody here has downloaded cannot honestly be pinned — "recording a number rather than a fact".
Measured from this machine with no `HF_TOKEN`:

```
model_info()      -> sha=3533c8cf8e369892e6b79ff1bf80f7b0286a54ee
list_repo_files() -> 10 files ['.gitattributes', 'README.md', 'config.yaml', …]
hf_hub_download() -> GatedRepoError: 401 Client Error
```

Gating covers **downloads**, not metadata. The revision was always a verifiable fact here. It is
pinned now, and `test_every_repository_the_fetcher_would_download_is_pinned` asserts **no**
repository is unpinned — strictly stronger than the exemption it replaces, and verified red by
removing the pin. `BLOCKED.md` #4 is unchanged and still accurate: downloads 401, so Hawa still
has to accept the licence.

**The conflict, recorded rather than resolved unilaterally.** `codex/production-readiness-20260809`
(`576dfed`, CI green, no PR open) implements the same guard independently and differently:

| | this branch (`main`) | `codex/production-readiness-20260809` |
|---|---|---|
| where | new `models/revisions.json`, keyed by repo id | `models/sources.json` restructured to name → `{repo, revision}` |
| refusal | `revision_for` raises `RevisionNotPinned` | plan omits/refuses in the shell |
| ffmpeg | untouched, named as an open gap | **pinned and verified** (`evidence/ffmpeg-source.md`) |
| pyannote | omitted, now corrected here | pinned from the start |

Both pin the same four SHAs for the visual checkpoints, so the *facts* agree; the *structure*
does not. Their single-file `name → {repo, revision}` is arguably the better shape — one file,
one entry per §7 name, no second lookup — and they covered the ffmpeg archive this branch
deferred. Neither implementation is reverted here: whoever merges must pick one deliberately,
because two divergent supply-chain guards is worse than either, and a naive merge would leave
`models.py` reading a file the fetcher no longer writes.

**This is `BLOCKED.md` #12 in a new form.** That entry describes two agents sharing one index.
They no longer do — the other works on its own branch — and the failure mode simply moved: from
silently reverting each other's files to silently duplicating each other's work. The cost this
time was one wasted implementation and one caught error; the error was caught only because the
duplicate existed, which is the one thing to say in its favour.

Gate: `VERIFY OK` recorded with the commit.

## D-076

**§3 Stage 4's Kurdish-script gate could be satisfied and then invalidated by the normalization
that runs right after it.** `_kurdish_field` tested `_is_kurdish` on the raw string and returned
`normalize_sorani(stripped)`. Measured: `'٠١٢'` is Arabic-Indic, inside the block the check tests,
so it passed — and `unify_numeral` rewrote it to `'012'`, which the function then returned. A
title, description or hashtag with no Kurdish script at all reached `JudgeVerdict`, past the guard
written to refuse precisely that, and §5 and the delivery set consume that as finished work.

**Decision: check the normalized text, not the raw.** One guard in the shared function, four call
sites. Strictly stronger than checking first — normalization never *adds* Kurdish script, so
anything the late check accepts the early one would have accepted too. The refusal names the
normalized form, because `'٠١٢'` looks Kurdish to a reader and `'012'` is what actually failed.
Controls pin both directions: Kurdish-plus-digits is still accepted with the digits unified, and
normalization is still applied to accepted fields. Mutation audit 4/4
(`evidence/adversarial-pass-2026-08-09.md`).

**Found by an adversarial pass over ten DONE rows**, ten agents in ten isolated worktrees, all
baselines verified green first. 118 claims, **19 falsified, 26 guards revertible with no test
noticing, 59 prose/code disagreements.** The full triage is in the evidence file; two entries
matter enough to record here.

**M0.3 is demoted to PARTIAL: §4.1's fifth collision is not the one the row names.** Read out of
the frozen blueprint, `BLUEPRINT.md:228-232` lists ZWNJ, Farsi/Arabic `ی`/`ک`, Numerals (**one**
row), conjunctive `و`, and **`Diacritics ř / ł`**. Conjunctive `و` is row *four*; the row reached
"four by KLPT" by counting the single Numerals row twice, and row five is unimplemented —
`normalize_sorani` leaves `ř`/`ł` untouched and no file in `src/` or `tests/` mentions either
character. Coverage is 4 of 5.

**Not fixed, because the fix needs a decision rather than code.** §4.1 says "Normalize in
Latin-script material" without saying what `ř`/`ł` normalize *to*. In Kurdish Latin orthography
they mark a trilled r and a velarized l — distinct phonemes — so folding them to `r`/`l` destroys
information and anything else is invented. Refused and recorded per the standing rule. Two
questions for Hawa, in `BLOCKED.md` #13: the target form, and whether Latin-script Kurdish is in
scope at all when §7's ASR emits `ckb_Arab`.

**The existing claim test could not have caught this**, because it encoded the same miscount:
`test_the_ledger_tracks_whether_all_five_collisions_are_handled` defined "all five handled" as
"conjunctive `و` separates". I intended to leave it for the next increment, and the demotion
removed that option — it went red the moment M0.3 stopped saying DONE, which is the test doing
its job through a wrong premise. So it is rewritten here: `_SECTION_4_1_PROBES` carries one probe
per collision, `_section_4_1_collisions()` parses the table out of `BLUEPRINT.md`, and
`test_every_section_4_1_collision_has_a_probe` asserts **set equality both ways** — the §7
discipline `tests/test_registry.py` already applies, now applied to §4.1, so a row cannot hide
behind a probe list nobody updated. The `ř`/`ł` probe asserts only that *something* changes, which
is the weakest honest form while `BLOCKED.md` #13 is open.

Mutation audit on those tests, **3/4**: dropping the unprobed row is CAUGHT, making its probe pass
trivially is CAUGHT, quietly restoring M0.3 to DONE is CAUGHT. The survivor is replacing the
blueprint parse with a retyped copy of the same five names — semantically neutral while
`BLUEPRINT.md` is frozen, and it would only diverge if §4.1 gained a row, which the freeze
forbids. Reported rather than papered over with a test about implementation.

**Also corrected in the same edit:** the demoted M0.3 cell first quoted §4.1's row with its
literal `|` delimiters, which split the markdown cell and broke
`test_every_ledger_row_marked_partial_names_its_shortfall` — a PARTIAL row whose shortfall had
become invisible to the checker that exists to require one.

Gate: `VERIFY OK — 1096 passed, 0 skipped`.

## D-077

**§8.2's collapse metric reported a zero for a measurement that never happened.** For a gold set
with no winners, `recall_at_k` returned `None` and `recall_at_k_by_path` returned `{}` — both
saying *unmeasured* — while `path_unique_wins` returned `{verbal: 0, visual: 0, both: 0}`. §8.2's
collapse test is *"If Path B never surfaces a winner Path A missed, collapse it"*, so that third
line reads as licence to delete a path: GPU 0, a segmented 4B checkpoint and the whole of §3
Stage 3's visual half, on the strength of an empty measurement. The project's own rule —
unmeasured is None, never 0.0 — held in one half of a metric pair and not the other.

**Decision: return `{}`, matching `recall_at_k_by_path`, not `None`.** For a by-path mapping the
established signal is already empty-means-unmeasured, non-empty-means-every-path-present-with-its-
real-value-including-zero. `None` was considered and rejected: it would make the two halves of one
metric pair disagree in *shape* while agreeing in meaning, and `float | None` is the right signal
for a scalar rather than a mapping. One line, no signature change; `grep` finds no production
caller, only prose and tests.

**A measured zero must still be reported, which is what keeps the fix narrow.** With a real winner
retrieved only by the verbal path, `visual: 0` is *the finding* — exactly the evidence §8.2 wants —
so "stop reporting zeros" would have been the wrong fix. The control
(`test_a_measured_zero_is_still_reported_for_every_path`) fails for a `return {}` that ignores the
distinction, and the new test also pins that the three metrics agree with each other about whether
anything was measured at all.

**Mutation audit 3/3**, run over `tests/test_repurposing.py` *and* `tests/test_discovery.py`
because the latter also calls this function — a mutation only the discovery tests caught would
otherwise have read as unprotected (`evidence/unmeasured-unique-wins.md`).

**What M7.1 shows about self-certifying rows.** That row had no evidence file: its Definition of
Done listed six §8.2 metrics and the ledger cell listed the same six back. All six exist, so the
row was not lying about coverage — the defect was that one of them answered a question nobody
asked it, which a cell restating its own DoD can never surface.

**Closed later by D-082, deliberately not bundled here:** `iou_match` was accepted unvalidated,
so `1.5` or `-1` yielded silent nonsense rather than a refusal. It was a different defect in a
different function; keeping it separate made both fixes individually auditable.

Gate: `VERIFY OK — 1099 passed, 0 skipped`.

## D-078

**Two ledger rows called the invariant sweep "exhaustive" while it covered five of seven optional
inputs.** M2.2 and M6.2 both cite
`test_the_invariant_holds_across_every_combination_of_soft_inputs` as evidence for Kurdish
invariant #2. It varied `vad_onset_ms`, `shot_cuts_ms`, both `speaker_turn_*` and
`timelens_interval_end_ms`, and omitted `media_duration_ms` and `natural_silence_ms` entirely.

**The omission is mine.** D-070 wired `natural_silence_ms` into the runner as §3's fourth
out-point signal three iterations ago and did not extend the sweep those rows lean on. The hard
rule says a change touching a Kurdish invariant must assert it; I asserted the new signal's own
behaviour and left the invariant's exhaustive check behind. The adversarial pass found it.

**Extended to all seven: 3,125 → 78,125 combinations, 0.40 s, 0 violations.** 46,875 boundaries
built and 31,250 refused — exactly the two duration offsets that place the media end before
`anchor_out`, which `fuse_boundary` refuses by design because clamping an anchor that does not fit
would violate the invariant being checked. Refusals are counted and their message asserted rather
than skipped, so a refusal arising for a different reason cannot read as coverage.

**It found nothing, as expected, and that is the honest result.** The 200 ms tail is always in the
out-point `max()`, so `final_out >= anchor_out + 200` whatever `natural_silence_ms` contributes,
and `anchor_out <= media_duration` is enforced before the clamp. This converts a false claim into
a true one and covers an input added this week; it did not uncover a defect.

**The sweep's marginal value, measured rather than assumed.** The pass claimed it catches nothing
the surrounding unit tests do not. Confirmed by running four invariant-breaking mutations against
the whole file and against the file with the sweep deselected: all four are caught either way, so
the sweep is defence-in-depth and never the sole catcher. Kept — 0.4 s of combinatorial cover on
an invariant the blueprint calls non-negotiable is cheap against a mutation nobody thought to
unit-test — but the rows now describe it instead of leaning on the adjective.

**What is uniquely load-bearing is the sweep's self-assertion of breadth.** The test asserts
`built == 46_875` and `refusals == {"ValueError": 31_250}`, summing to 5⁷. Shrinking `offsets`
from five values to four is CAUGHT at that assertion, and nothing else in the suite notices a
field dropped from the product — which is exactly how this claim went stale.

**Not done:** `media_duration_ms` is swept only as `ANCHOR_OUT + offset`. Values below `anchor_out`
and the `<= 0` refusal stay with their dedicated unit tests; sweeping duration independently would
multiply the space for behaviour already pinned. `evidence/exhaustive-sweep.md`.

Gate: `VERIFY OK — 1099 passed, 0 skipped`.

## D-079

**`viterbi_align`'s infeasibility refusal could be deleted whole and 1,099 tests stayed green.**
M1.1's row claims *"infeasible input refused rather than guessed"*. Removing the three checks that
implement it — unreachable end state, backtracking dead end, every-token-framed — left the suite at
`exit=0, 0 FAILED`, while the function degraded from a documented `AlignmentInfeasible` to a bare
`KeyError: 0` out of the span-assembly loop. §4.2's spans feed §5's sentence anchors and every
caption time, so an uninterpretable exception there is not a cosmetic difference.

**The adversarial pass's "five unprotected guards in this module" was exactly right in count and
threefold overstated in substance, and I repeated the headline figure for three iterations before
measuring it.** Removing any single member of the trio leaves the refusal intact because the next
one catches the same condition — traced, the unmutated path raises at the end-state check and with
that gone the backtracking check picks it up. That is redundancy, not exposure. A single-guard
mutation surviving is the *expected* result, and only removing the whole set distinguishes the two.
This is why the audit runs in two phases: targeted files first (anything caught there is protected),
then the full suite for survivors only (the sole way to separate "unprotected" from "caught
somewhere the row does not cite").

**Decision: pin the contract, not the implementation.** One test asserts that impossible emissions
raise `AlignmentInfeasible` with its documented message — type and message, because the whole point
is that it is *that* refusal and not whatever falls out of a broken path. Two further tests cover
the genuinely separate untested refusals, `frame_duration_ms <= 0` and a word carrying no tokens.
No test was contrived to make an individual link of the trio observable: that would assert the
implementation's shape rather than its behaviour, and the links exist to cover each other.

**Reachability was verified before any test was written**, because a contrived test for an
unreachable defensive check is theatre. All three refusals fire through the public API on ordinary
arguments.

**Two controls**, since a refusal test also passes for a function that rejects everything handed to
it: a feasible alignment of the same input shape must still produce spans, and two words with a
positive frame duration must come back with non-overlapping times.

**Measured before and after** (`evidence/alignment-refusals-untested.md`): guards caught by the
files M1.1 cites went 5/11 → 7/11, and the chain-removal test flipped from `exit=0, 0 FAILED` to
`exit=1, 1 FAILED` naming the new test.

**Carried forward:** the same two-phase treatment is owed to the other 21 guards the pass flagged
across other modules. The headline count should not be quoted again without it.

Gate: `VERIFY OK — 1104 passed, 0 skipped`.

## D-080

**§8.2's retrieval metrics accepted a cutoff and an overlap threshold that cannot mean what §8.2
asks them to, and reported 0.0 instead of refusing.** Measured against one gold winner retrieved
exactly at IoU 1.0: `iou_match=1.5` and `2.0` gave 0.0 (no overlap can ever qualify),
`iou_match=float("nan")` gave 0.0 (NaN comparisons are always false, so total failure is reported
silently), `iou_match=-1.0` gave 1.0 while matching candidates with no overlap at all, and `k=0`
and `k=-5` gave 0.0. §8.2's collapse test reads a zero as licence to delete a discovery path, so
this is D-077's defect by a second route: that one produced an unmeasured zero from an empty gold
set, this one a measured-looking zero from a bad argument.

**`k` was not in the original finding.** The adversarial pass named `iou_match`; `k` turned up while
grepping the callers and fails identically. Fixing one and leaving the other would have left half
the defect, so a single guard covers both.

**Decision: validate at the three metric entry points and Stage 3 merge, not in the shared
funnel.**
`_found_winners` is the funnel all three metrics route through and is the obvious site — but it is
skipped when the gold set has no winners, because each metric short-circuits to `None`/`{}` first.
A caller passing `k=-5` against an unlabelled set would have been handed "unmeasured" and never
told the cutoff was nonsense. The validators therefore run ahead of that short-circuit and before
an empty Stage 3 merge: one threshold rule shared by every surface that uses it.

**Correction made during branch reconciliation: `0.0` is not legal with a `>=` comparison.**
Disjoint spans have temporal IoU exactly zero, so accepting zero merged and credited footage with
no overlap at all. The threshold is a finite, non-boolean number in `(0, 1]`; `1.0` remains the
legal exact-span boundary. Recall's `k` is a positive, non-boolean integer, so `True` and `1.5`
cannot become plausible measurements.

The original narrower mutation audit and the stricter integration audit are preserved in
`evidence/metric-parameter-validation.md` and `evidence/iou-threshold-validation.md`. The latter
catches bypassing the merge guard, admitting zero, and bypassing one metric's K guard.

M7.1's cell recorded this as an open gap when D-077 landed; that note is now closed rather than
deleted, so the row records both that the gap existed and when it was shut.

Gate: `VERIFY OK — 1118 passed, 0 skipped`.

## D-081

**§4.2's VAD-pause segmentation is dead code.** M1.2's Definition of Done is "Kurdish punctuation
**plus** VAD pauses". `pause_follows` reaches its VAD branch only when the word gap is *below*
`pause_ms`, and that branch requires a silence *contained* in the inter-word interval whose own
length is *at least* `pause_ms` — which forces the gap to be at least `pause_ms`. The two conditions
are mutually exclusive. Brute-forced over 3,528 candidate silences on a 25 ms grid: **0 splits**,
including a 400 ms silence starting exactly at the first word's end
(`evidence/vad-pause-segmentation-dead.md`). Demoted to PARTIAL.

**It is computed and discarded, not merely unwired.** `pipeline.py` derives the silences from Stage
0's real Silero output via `_pauses_between` and passes them to `segment_sentences`, where they have
no effect. That is the second time the same helper's output has reached a parameter that ignores it —
D-070 was `natural_silence_ms` from the identical function.

**Decision: refuse to pick the replacement rule, and record both candidates.** The containment test
is clearly wrong, but what replaces it decides where Kurdish sentences end — and therefore §5's
anchors, every fused boundary and every rendered clip. **Overlap** (any qualifying silence
overlapping the inter-word interval) catches the case the feature exists for, since CTC alignment
stretches words across silence so the timings show a small gap where VAD saw 400 ms of quiet; it
risks over-splitting when a long silence clips the boundary by a millisecond. **Boundary
containment** (the silence must span from before `earlier.end_ms` to after `later.start_ms`) is
conservative and fires only on genuine VAD/alignment disagreement. §4.2 does not say which, and there
is no labelled Sorani audio here to measure them against. Picking by taste is what the "never guess a
threshold" rule forbids. `BLOCKED.md` #14.

**A test that asserts a feature does not work.** `test_vad_pauses_currently_cannot_split_a_sentence`
pins the measured behaviour across four silences and states in its docstring that it documents a
defect, not a desired behaviour: going red means the fix landed, at which point M1.2 is re-statused,
#14 closes and the test is deleted. Unusual, and the alternative was worse — leaving code that reads
as though VAD segmentation happens, in the module every clip boundary depends on. A control in the
same test confirms the word-gap path still splits, so the finding is specifically the VAD half.

**Methodological caveat, recorded because it weakens the source.** The second adversarial pass found
this, and that agent's baseline was **red**: a git worktree has no `.venv`, so `tests/test_gate.py`
contributes 9 failures there. It compensated by comparing failure counts against the known-red
baseline, which is weaker than this project's rule. Everything here was re-derived and re-measured in
the main checkout against a green 1,118 baseline before anything changed. Three of that pass's ten
agents had the same red baseline (M0.2, M1.2, M2.1); their remaining findings are unverified until
measured the same way, and the worktree harness needs the venv made visible before the next pass.

Gate: `VERIFY OK — 1119 passed, 0 skipped`.

---

## D-082 · NTSC fractional rates use SMPTE drop-frame EDL timecode

**Supersedes D-042's NTSC refusal and D-072's remaining drop-frame shortfall.** Refusing 29.97
was safer than rounding it, but it made §2 delivery impossible on ordinary NTSC footage. The
pipeline already passed the exact `30000/1001` rate through, so the missing piece was honest
physical-frame-count to time-address conversion.

**Decision.** Recognize only NTSC `30000/1001` (including conventional decimal `29.97`) as the
supported fractional rate. Quantize milliseconds at the physical rate, then apply SMPTE's
nominal 30-count drop-frame rule: skip counts 00 and 01 at each minute except every tenth.
Emit semicolon labels and `FCM: DROP FRAME`. Whole-number rates remain non-drop; every other
fractional rate is refused. In particular, do not infer 59.94 CMX behavior from a 29.97 rule.

**Evidence.** SMPTE EG 35:2012 §2.1 supplies the skip rule, Apple TN2310 supplies the canonical
minute transition, and FFmpeg's `av_timecode_adjust_ntsc_framenum2` supplies an independent
implementation reference. Tests cover every physical frame in the first hour plus a real
30000/1001 pipeline transcode. `evidence/m3-6-drop-frame-edl.md`.

**Amended 2026-08-10.** The earlier refusal to infer 59.94 from the 29.97 rule was correct until an
independent standard implementation was cited. FFmpeg's maintained timecode contract explicitly
defines drop-frame adjustment for multiples of nominal 30, and its implementation names 29.97 and
59.94: nominal 60 skips four counts at each non-tenth minute. HawEdit therefore also recognizes
only `60000/1001` and conventional `59.94`, while `120000/1001` and every other unsupported
fractional rate still refuse. Tests cover the first-minute, tenth-minute and hour boundaries, every
physical frame in the first ten minutes, and equal source/record EDL durations.
`evidence/m3-6-high-frame-rate-drop-frame.md`.

**At the time of D-082, still open.** This made NTSC delivery complete but did not make the full
MP4/ASS/SRT/JSON/EDL bundle one atomic transaction. D-083 immediately below closes that publication
gap; the wording is retained as the decision's historical boundary rather than a current shortfall.

---

## D-083 · Publish the complete delivery as one write-once directory

**Supersedes D-071's remaining transaction shortfall.** Atomic MP4 publication and
build-before-write sidecars prevented corrupt renders and some partial sets, but they did not
make the client delivery indivisible. A process or disk failure after the encode could expose a
valid MP4/ASS beside only some of JSON/SRT/EDL. The run then needed a new work directory, and a
consumer watching the output could mistake the partial set for completion.

**Decision.** Each clip owns one final directory. A worker creates a uniquely named hidden
sibling directory, renders there, stages the textual artifacts with exclusive creation and
`fsync`, and refuses publication unless the directory contains exactly five regular, non-empty
files: ASS, MP4, SRT, EDL and editing JSON. One same-filesystem directory rename is the public
commit point. `PipelineRun.render` is not populated until that rename succeeds. Any earlier
failure discards only the worker's private known files and reports render/delivery skipped.

**Write-once and concurrency.** The old flat artifact paths remain overwrite guards so an
upgrade cannot trample a previous run. An existing final directory is refused before billed/GPU
work and again at publication. Two workers may stage independently; exactly one non-empty
directory rename wins, the loser discards its private set, and the winner cannot contain files
from both workers. Media identifiers are validated centrally before Stage 0 so path separators,
parent references, controls and cross-platform reserved names never become output paths.

**Recovery boundary.** An orderly failure removes its private directory. A process crash may
leave a hidden staging directory; it does not block a clean retry because staging names are
unique. Cleanup deliberately refuses recursive deletion or unexpected content. This decision
guarantees atomic namespace visibility on one filesystem; it does not claim that every storage
controller preserves directory metadata across sudden power loss.

**Evidence.** `tests/test_artifact_bundle.py` covers every missing member, empty/extra content,
write-once publication, two simultaneous workers, crashed staging and cleanup confinement.
Real-media pipeline tests prove the successful exact set, inject ASS and mid-sidecar failures,
and verify neither a public MP4 nor a partial sidecar set survives. See
`evidence/atomic-delivery-bundle.md`.

---

## D-084 · Every release carries a deterministic SPDX 2.3 SBOM

**A reproducible wheel without a component manifest is reproducibly opaque.** D-074 made the
release-critical data files ship and the release tool proved exact wheel bytes, but a recipient
still had to open METADATA and the archive to discover dependencies and the bundled third-party
font. The audit correctly kept M3.7 PARTIAL with “no SBOM”.

**Decision.** Generate SPDX 2.3 JSON directly from the completed wheel, not from the mutable
build environment. The root package carries the exact wheel SHA-256, version and purl. The
bundled Noto Naskh Arabic font is a contained component with its own archive-byte SHA-256 and
OFL-1.1 declaration. Every `Requires-Dist` entry becomes a package relationship: base
requirements are `DEPENDS_ON`, extras are `OPTIONAL_DEPENDENCY_OF`, and the exact PEP 508 string
is retained as the relationship comment.

**Do not invent an installed graph.** The wheel does not bundle those dependencies. Open ranges,
platform markers and extras do not identify one installed version, so their SPDX packages omit
version/checksum and say why. The document comment also states that external model assets live
under the separately pinned model manifests. This is a release-artifact SBOM, not a claim that
one particular deployment was resolved or scanned.

**Reproducibility and binding.** Creation time comes from `SOURCE_DATE_EPOCH`; namespace contains
the full Git revision and wheel digest; package/relationship order is stable; two generations
from the same wheel are byte-identical. `SHA256SUMS` covers the wheel, SPDX JSON and provenance,
and provenance names and hashes the SBOM. All four files publish under the existing write-once
directory transaction.

**Independent evidence.** The focused regression builds a real fixture wheel twice, verifies the
exact four-file release set, wheel/font hashes, base/optional relationships and deterministic
SBOM bytes. The emitted HawEdit document was parsed and validated independently by
`spdx-tools==0.8.5` as SPDX 2.3. `evidence/release-sbom.md`.

**Still open.** Checksums prove integrity only when their source is trusted. The release has no
signature/attestation identity, and Meta's package-managed OmniASR downloads have no
project-owned byte manifest. M3.7 therefore remains PARTIAL.
---

## D-085 · Stage 1 routes real CTC disagreement through the rzgar validator

**The policy existed and the producer ignored it.** `escalation.select_for_validation` correctly
implemented §3's bottom-quartile plus material-disagreement rule, but no source caller existed.
The CTC forward returned only posteriors, not its decoded hypothesis, so the producer lacked one
of the policy's two inputs. `AsrProvenance.validated_by` could describe a validator that Stage 1
never loaded.

**Decision 1 — a routed validator result is the final raw text for that segment.** LLM-7B remains
the canonical first pass and provenance names it as such. On a selected segment, the registered
rzgar model is a correction pass, not a no-op observer: its exact output replaces the first-pass
surface, then the existing CTC model runs on the same bounded WAV and Viterbi-aligns that final
surface. A validator output never inherits timings for different words. `validated_by` is set only
when at least one segment actually took this path.

**Decision 2 — decode CTC from the forward already used for alignment.** The official
`omnilingual-asr==0.2.0` implementation takes argmax, collapses consecutive ids and decodes with
special tokens skipped. HawEdit now applies that exact recipe to the same logits whose softmax
feeds forced alignment. No second CTC model and no text-length heuristic is introduced. The
episode-level policy sees every segment before routing; duration remains reporting-only.

**Decision 3 — the official Qwen loader lives in Stage 1's isolated environment.** The rzgar
model card uses `qwen-asr`; version 0.0.6 pins Transformers 4.57.6 and Accelerate 1.12.0. The WSL
worker receives the host's registry-resolved checkpoint path and lazily loads it on GPU 1 only if
a segment is selected. Local Linux uses the same adapter. Windows does not install it into the
visual-model host venv.

That separation is necessary, not cosmetic. A real Linux resolution proved `omnilingual-asr`
forces Torch 2.8 through fairseq2n, while the verified visual stack uses Torch 2.13. Combining
`.[asr,gpu]` is unsatisfiable. Worse, OmniASR only floors torchaudio, so the first real setup chose
torchaudio 2.11 beside Torch 2.8 and failed import with missing `libcudart.so.13`. Stage 1 now pins
and runtime-checks the matched Torch/torchaudio 2.8 pair. The provisioner also sends its script on
stdin to avoid WSL argument mangling and uses a login shell so user-installed `uv`/Python 3.12 are
visible. These were three real-host failures, not hypothetical guards.

**Real proof, with its boundary stated.** On hawapc01, Qwen loaded the 4.08 GB rzgar checkpoint on
GPU 1 and reproduced the model card's `demo_04.wav` Sorani reference exactly: 128.0 seconds
including first load and 4,250,408,448 peak allocated bytes. The official 31.2 GB LLM and 12.3 GB
CTC assets were then downloaded and the real CLI ran Stage 0 → LLM/CTC → disagreement routing →
rzgar → CTC/Viterbi → immutable raw + normalized transcript. The final warm-cache run took 212.9
seconds and emitted 13 words with canonical, aligner and validator provenance.

The committed fixture is Kurmanji `espeak-ng`, explicitly a VAD positive control, so no CER or
Sorani quality claim is derived from it. M0.12/M0.13 remain blocked on labelled Sorani. It also
exposed a separate clock edge: VAD ended at 4180 ms while the media clock ended at 4162 ms.
Stage 1 measures emitted PCM rather than trusting the request; D-086 subsequently closed the
ownership gap at Stage 0 so those out-of-footage samples never become ASR input. Evidence:
`evidence/m1-4-stage1-validator.md`, `evidence/stage0-media-clock.md`.

**Mutation audit 4/4.** The focused regressions fail when routing is bypassed, when the validator
is called but its correction is discarded, when alignment trusts the requested cut instead of
the emitted PCM duration, and when the matched torchaudio pin is removed. All four exact source
mutations were restored before the final gate.

---

## D-086 · Stage 0 owns the video media clock for every speech region

**A real canonical run produced words after the footage ended.** The committed fixture probes at
4162 ms, while Silero's padded final speech region ends at 4180 ms. Stage 1 correctly used the
audio it was given and published that later timestamp. Every downstream video window, boundary,
keyframe and render uses the 4162 ms media clock, so canonical evidence could point at 18 ms of
footage that does not exist.

**Decision.** Stage 0 intersects every VAD region with `[0, media_duration_ms]` before checking
the OmniASR ceiling or handing regions to Stage 1. An overlapping region keeps its exact in-range
portion; a region wholly outside is omitted because this is video repurposing and it has no
corresponding frame. A malformed zero/negative-length VAD span is refused rather than made to
disappear through clipping, and a non-positive media duration is likewise refused.

**Evidence.** The real fixture now stores and passes 1954..4162 ms, not 1954..4180 ms. A runner
integration test captures the exact segments received by the canonical ASR producer and proves
their latest end equals Stage 0's duration. Mutation audit 3/3 catches bypassing the intersection,
removing the end clamp, and silently dropping an invalid region. See
`evidence/stage0-media-clock.md`.

---

## D-087

**§7 could both register and exclude a model, and `resolve` settled the contradiction in favour of
the excluded one.** `resolve` reads `REGISTRY` before `EXCLUDED`, nothing asserted the tables were
disjoint, and `test_exclusions_match_section_7_exactly` compares the *cells* each table
self-declares — which stays correct when an excluded id is also registered. Measured against a green
1,119 baseline: `Whisper` added to `_ENTRIES` with a cell §7 already contains, no role and an
attribution-free licence made `resolve("Whisper")` return the entry with no `ModelExcluded`, and the
full suite stayed at `exit=0, 0 FAILED`. Two of §7's nine exclusions are CC-BY-NC-4.0 hard rejects,
so the same hole routes work to a NonCommercial model
(`evidence/registry-excluded-model-resolvable.md`).

**Decision: enforce disjointness at import, not by reordering `resolve`.** Two tables naming one
model is a contradiction in the *data*; making it impossible to construct is stronger than deciding
which table wins, and it fails for every consumer of the library rather than only inside the suite.
`assert_registry_excludes_nothing_it_registers` is a pure function over both mappings, so the
refusal is testable with synthetic tables while the real ones are checked on every import.

**The same guard closes the other half.** A duplicated `blueprint_model_cell` is invisible to
set-equality — the declared set is unchanged — which is exactly how the rogue entry hid. §7 names one
model per cell and the shipped data agrees (15 entries, 15 distinct cells), so uniqueness is
enforceable. The realistic trigger is not malice: copy a `ModelEntry` as a template, edit `model_id`
and `component`, forget the cell.

**Three attempts were needed to measure this, and the two failures are the point.** My first
mutation appended a `REGISTRY` redefinition and produced 4 failures — a mypy error and three
`test_gate.py` subprocess tests, i.e. malformed code caught by the typechecker. My second used a
licence requiring attribution and produced 2 failures — README attribution bookkeeping. Both read as
CAUGHT and neither touched exclusions. **A mutation caught for the wrong reason reads as protection
that is not there**, the mirror of D-079 where a mutation surviving for the wrong reason (a redundant
sibling) read as exposure that was not there. Only a minimal mutation isolates the behaviour.

**Mutation audit 5/6.** The survivor is the import-time call itself: removing it leaves two tests
that catch the rogue entry anyway, verified by removing the call *and* adding the entry. Classified
as redundancy rather than patched, and kept for what tests cannot give — refusal at import. Two
mutations earn their keep by being caught only by controls: *"the check raises unconditionally"* and
*"the duplicate-cell check fires on a single claimant too"* would both pass every refusal test while
breaking honest tables.

**M0.2's claim is now true, and I nearly recorded the opposite.** The row and the module docstring
say "Adding a model without amending the blueprint fails the gate." I drafted an evidence paragraph
asserting that remained false in general, then checked: the set-equality *is* bidirectional, so an
invented cell was already caught. With duplicated cells and excluded ids now caught too, the four
routes are covered. The drafted-then-corrected paragraph is left in the evidence file, because
writing a plausible statement before measuring it is the same error the whole finding is about.

**This also settles a disagreement with the second adversarial pass**, which reported it from a red
worktree baseline. Its conclusion was right and its method could not have distinguished the three
mutations above, since comparing failure counts against a red baseline hides which tests failed and
why.

Gate: `VERIFY OK — 1125 passed, 0 skipped`.

---

## D-088 · A release dependency audit is a measured gate, not an SBOM substitute

**The deterministic SBOM disclosed a known-vulnerable runtime pin.** Auditing the clean wheel
environment from revision `53ecc475b7db` with `pip-audit==2.10.1` found FontTools 4.55.3 affected
by CVE-2025-66034. The affected range is 4.33.0 through 4.60.1; the upstream advisory describes
path traversal and arbitrary file writes when `fontTools.varLib.main()` processes a malicious
designspace. HawEdit uses FontTools for bundled-font coverage rather than designspace conversion,
but shipping a vulnerable, reachable library is still an unnecessary release risk.

**Decision 1 — use the smallest fixed exact pin.** Both the wheel dependency and Stage 1's
separately provisioned WSL runtime require `fonttools==4.60.2`, the upstream backport release that
contains the fix. An open-ended `>=4.60.2` range is rejected: reproducible installation is part of
the release contract, and a security floor must not silently become an unreviewed upgrade policy.

**Decision 2 — one regression covers both environments and refuses drift.** The dependency test
parses `pyproject.toml`, requires one numeric exact pin, requires at least 4.60.2, extracts both
installer branches from the generated WSL setup script, and requires their versions to equal the
base pin. The provisioner keeps one replacement constant so its `uv` and `pip` branches cannot
diverge.

**Evidence and boundary.** A fresh Python 3.12 environment resolved the edited project with
FontTools 4.60.2, passed `pip check`, and the real bundled Noto font passed
`assert_font_covers_kurdish`. `pip-audit==2.10.1` then reported no known vulnerabilities in that
environment; it correctly skipped the local editable HawEdit package itself. Bootstrap `pip`
findings seen in the baseline were removed by upgrading that audit environment and are not HawEdit
`Requires-Dist` entries. This is dated evidence, not proof against future disclosures. Upstream:
<https://github.com/fonttools/fonttools/security/advisories/GHSA-768j-98cg-p3fv> and
<https://github.com/fonttools/fonttools/releases/tag/4.60.2>. Full commands and outputs are recorded
in `evidence/dependency-security.md`.

**Mutation audit 3/3.** Reverting the base dependency to 4.55.3 fails the fixed-version floor;
changing it to `>=4.60.2` fails exact-pin parsing; changing only the WSL runtime to 4.55.3 fails
cross-environment equality. Every mutation was restored before the final gate.
---

## D-089

**A blank named-entity annotation scored 0.0 — the same value as a name transcribed perfectly.**
`""` is a substring of every string, so a blank entity satisfied `entity in normalized_hypothesis`
and counted as a name that **survived**. Measured against a green 1,125 baseline:
`named_entity_error_rate("سەرۆک لە شار", ("",))` → `0.0`, and
`CorpusItem(..., conditions={NAMED_ENTITIES}, named_entities=("",))` constructs without complaint,
so a labelled item with one blank label silently inflated §8.1's accuracy
(`evidence/blank-annotation-scored-as-found.md`). Third occurrence of "unmeasured is None, never
0.0" being broken in a metric, after D-077 and D-080.

**The sibling already had the rule.** `code_switch_error_rate` raised `ValueError` on the identical
input, calling it "a corpus defect". Two metrics in one module, one refusing and one reporting
perfection. So nothing needed inventing: `_normalized_annotation(value, kind)` extracts the
sibling's check, keeps its message shape verbatim, and both metrics call it.

**The distinction preserved deliberately:** an *empty tuple* is "nothing was annotated" and still
returns `None`; a blank entry *inside* the tuple is malformed data and now raises. Those are
different facts and a mutation collapsing the first into a refusal is CAUGHT.

**Rejected:** putting the check in `CorpusItem.__post_init__`. The metric is the last common point
every scoring path passes through and a caller can build the tuple from anywhere, so the guard
belongs at the funnel rather than at one producer.

**D-008's fourth choice was claimed as tested and was not.** That entry closes with "All four are
testable choices … see `tests/test_metrics.py`". Three were. *"Matching is exact after §4.1
normalization … a name 90% right is still the wrong name"* had no test — the behaviour was already
correct and merely revertible, and a mutation swapping exact matching for a 0.34 fuzzy threshold
would have scored a wrong name 0.0. Pinned in both directions, since either alone admits a wrong
implementation: a near-miss and a truncation score 1.0, and an Arabic-keyboard `كوردي` against
Kurdish `کوردی` still scores 0.0 — so "strict" cannot be implemented as byte equality.

**Mutation audit 6/6, and it was 5/6 first.** The survivor found a second unprotected guard:
removing the *code-switch* refusal — the one implemented correctly all along — left the suite green,
because nothing had ever tested it. The metric that got this right was exactly as revertible as the
one that got it wrong; only the behaviour differed, not the protection. One test closed it. Two of
the six are caught only by controls, which is what keeps a refusal from being implemented as
"reject everything".

Gate: `VERIFY OK — 1130 passed, 0 skipped`.

---

## D-090 · Reproducible wheel bytes require a hash-locked builder, not two ambient builds

**The release command reproduced its environment, not its artifact inputs.** It invoked
`pip wheel --no-build-isolation` twice with the caller's Python while `[build-system]` allowed
`setuptools>=68`. On clean revision `2c44e759f099`, Setuptools 79.0.1 emitted wheel SHA-256
`716908c3…`; 84.0.0 emitted `799c82b1…`. The only content change was the generator in `WHEEL` and
the consequent `RECORD` checksum, but the published bytes were different. Setuptools 68.2.2—also
allowed—failed with `invalid command 'bdist_wheel'`. A same-process double build could detect none
of this.

**Decision 1 — publication owns its builder.** `hawedit-release` creates a temporary venv and
installs exact Pip 26.2.1 and Setuptools 84.0.0 pure-Python wheels from
`requirements/release-build.txt` using `--require-hashes --only-binary=:all: --no-deps`. The two
SHA-256 values were independently computed from downloaded files and matched official PyPI JSON.
The ordinary runtime wheel does not depend on these release-only packages.

**Decision 2 — specification, lock, resolved environment and artifact must agree.** Every
`[build-system]` requirement must be an exact pin, must match the release lock, and the backend's
own package must appear in both. After installation, the command measures every locked version.
Both copies are built only with that private Python, and the output wheel must name Setuptools
84.0.0 as its generator. A caller cannot pass a plausible lock while continuing to build with its
ambient backend.

**Decision 3 — builder identity is provenance, not tribal knowledge.** Provenance schema 3 records
the measured Python, frontend, backend, full locked requirement map, lock path and lock SHA-256.
Python is recorded rather than artificially fixed to one minor: the wheel supports 3.11+. Measured
on clean revision `8d4810d28fd1`, Python 3.11.15 and 3.12.10 each emitted the identical 329,973-byte
wheel at SHA-256 `7765db5414dd…`; provenance alone differed because it names that real input.

**Mutation audit 3/3.** The gate catches reopening the Setuptools range, bypassing the private
builder for both wheel copies, and altering one nibble of the official Setuptools wheel hash. See
`evidence/release-builder-lock.md`.

**Still open.** The artifact is unsigned and the package-managed OmniASR byte supply chain remains
outside project-owned manifests, so M3.7 stays PARTIAL.
---

## D-091

**§8.1's coverage grid certified itself, and D-009's hours floor answered to nothing.**
`tests/test_corpus.py` referenced `BLUEPRINT.md` **nowhere**: it compared the `Dialect` and
`Condition` enums against literal sets typed into the test. `tests/test_registry.py` has parsed §7
out of the frozen blueprint from the start and asserts set equality both ways; §8.1 never got the
same treatment while M0.6's row claims "(3 dialects × 7 conditions)" implements its list. If §8.1
gained a category the enum and the test would agree with each other and both be wrong. Measured: an
eighth condition and a fourth dialect were both invisible.

**The mapping is explicit because §8.1's phrasing is not one-to-one with the enum.** §8.1's coverage
line yields **nine** items against a **seven**-member enum: "Kurdish–English and Kurdish–Arabic
code-switching" is one phrase covering two members. That is the shape of §4.1's single "Numerals" row
covering three numeral systems — the shape that made M0.3 claim five collisions handled when four
were (D-076). Comparing item count to `len(Condition)` would have reproduced that error, so each
phrase maps to the set of members it covers and set equality is asserted both ways.

**`MINIMUM_HOURS` was referenced by no test at all.** `grep -rn MINIMUM_HOURS tests/` returned no
matches, so D-009's recorded 3.0 could drift from the code; 3.0 → 1.0 left the whole suite green. The
value is now parsed out of D-009's heading rather than retyped, so changing the floor requires
amending the record — which is the reason for recording it. The drift is caught.

**A negative result recorded because it is worth knowing.** D-077, D-080 and D-089 were three
separate violations of "unmeasured is None, never 0.0" in metrics, so all fifteen public metric
functions were swept rather than waiting for a fourth. There is no fourth: every one answers the
unmeasured case with `None`, `{}` or a `ValueError`, and 6/6 mutations turning an unmeasured branch
into a zero are CAUGHT. The class is closed, behaviourally and by test, and nothing was changed for
it — inventing a fix there would have been work to look busy.

**Mutation audit 4/5 on the grid, plus the hours-floor drift caught.** The survivor is D-078's
neutral class: replacing the blueprint parse with a retyped literal changes nothing observable while
the blueprint is frozen. Reported rather than papered over with a test about implementation.

**BLUEPRINT.md is frozen and was touched in this audit**, because simulating §8.1 growing is the only
way to measure the property. Restored in a `finally` and verified twice — `sha256` identical before
and after (`b7e05d219be4e527`), and `git status --porcelain BLUEPRINT.md` empty. Recorded explicitly
so the touch is on the record rather than inferred.

**Kept deliberately:** the two literal-set tests stay alongside the parsed ones. They are not
redundant — the parsed test checks membership against §8.1, the literal tests pin the enum's `.value`
strings that the serialized corpus manifest depends on. Removing them would also have meant lowering
the test-count floor, which the hard rules forbid doing casually.

Gate: `VERIFY OK — 1134 passed, 0 skipped`.

## D-092

**M6.1's contract has two halves and the second is false.** The row reads "intervals as evidence,
never as cuts, and only where they are about the clip".

**Half one was true and untested.** §3 Stage 5's formula names `timelens_interval_end` in `final_out`
and nowhere in `final_in`. Adding the interval's *start* to the in-point candidate set left the
entire suite green, so nothing enforced the asymmetry that makes TimeLens evidence rather than a cut.
Pinned now — that mutation fails exactly one test — with a control requiring the interval to still
move the out point, so the test cannot pass for a boundary that ignores TimeLens altogether. This
half needed no judgment: the blueprint's formula is explicit.

**Half two is false and is a shipping defect.** `interval_for_fusion` accepts any interval that
overlaps the anchor at all, so **1 ms** of overlap qualifies. Measured at the library:
anchor 10000..14000, evidence 13999..305000 → fused clip **295.0 s** from a 4.0 s sentence. Measured
through the real `run_pipeline` and asserted on the shipped clip: a 1.60 s anchored sentence shipped
as **4.10 s**, 2.56× longer, attributed to `timelens_interval_end`.

**The runner's mitigation is real but misses the case that matters.** The uncaptioned-speech guard
refuses the expansion when unselected *words* fall in the swallowed span — verified, a second
sentence at 2000 ms produces exactly that refusal. Applause, music, silence and untranscribed tails
have no words, which is precisely what "applause five minutes later" is.

**Decision: refuse to choose the bound, and record three candidates.** §3 bounds the shot cut
explicitly ("within 400 ms") and gives nothing for TimeLens. A minimum overlap fraction rejects the
applause case but also the genuine reaction shot beginning as a sentence ends; a maximum extension
window is symmetric with §3's only stated window but may neuter a stage whose purpose is finding ends
beyond it; a cap relative to the anchor's own length scales with content but needs the multiple
chosen. All three are thresholds, the question is empirical, and there is no labelled footage here.
`BLOCKED.md` #15. M6.1 demoted to PARTIAL.

**A test that asserts a defect, for the second time in this loop** (after D-081's VAD branch).
`test_one_millisecond_of_overlap_currently_qualifies_as_relevant` records the measurement and says in
its docstring that going red means the fix landed. Its control keeps the gate from reading as inert:
an interval with no overlap at all is still refused.

**How this was found, and the correction to my own survey.** The pass-#2 M6.1 agent reported it with
a green baseline. I had listed M2.1 as the next target on the grounds that its findings were
unverified; I verified them first and **M2.1 is clean** — including its whole-set removal of
invariant #3's three guards, which I re-measured against a green baseline and which does redden the
cited file. That agent had explicitly noted that reporting its two individually-surviving guards as
gaps "would be a threefold overstatement", so the redundancy instruction added after D-079 worked as
intended.

Gate: `VERIFY OK — 1136 passed, 0 skipped`.

---

## D-093 · A full action SHA can still pin a deprecated runtime

**Exact source identity was necessary and insufficient.** GitHub Actions run 31291508018 passed on
the exact release-candidate SHA, then annotated both infrastructure actions: Checkout v4 and Setup
Python v5 target deprecated Node 20 and were being force-run on Node 24. The workflow was green only
through platform compatibility emulation. The existing regression correctly refused moving tags
but would accept those obsolete commits forever.

**Decision.** Upgrade to the latest official Node-24 releases measured on 2026-08-09 and keep full
commit pins: Checkout 7.0.1 at `3d3c42e…`, Setup Python 7.0.0 at `5fda3b95…`. GitHub's tag objects
resolve directly to those commits, and each official `action.yml` declares `runs.using: node24`.
The focused test binds action name, full commit and audited release comment; changing any one
requires a new evidence update rather than silently accepting another 40-hex value.

**Boundary.** Static inspection proves the declared runtime and source identity, not that GitHub can
execute them. Exact-SHA workflow dispatch is the required runtime proof. Sources and the resulting
run are recorded in `evidence/ci-actions.md`.

---

## D-094 · Keep the measured Transformers line, but make checkpoint config non-executable

**The optional runtime was open, and the version we must retain has published advisories.** The
real GPU measurements used Transformers 4.57.6, Accelerate 1.14.0, Pillow 12.3.0 and Torchvision
0.28.0, while three of those four declarations were floors. The cloud declaration admitted every
Google Auth 2.x release. A fresh install could therefore produce a different runtime under the
same HawEdit revision. The development pin was Pytest 8.3.4, reported as vulnerable by
PYSEC-2026-1845. All direct optional dependencies are exact now, with Pytest 9.1.1 and Google Auth
2.56.3 measured in a clean environment.

**Upgrading Transformers is not a safe security edit.** D-055 already measured that 5.x breaks
VideoChat3 three ways (one silently randomises `lm_head`) and changes reranker scores and order.
`pip-audit` nevertheless reports four records against 4.57.6. Two are unused model-specific paths:
HawEdit has no X-CLIP conversion or `Trainer`, and the latter advisory additionally requires Torch
below 2.6 while the pin is 2.13.0. Two affect config-driven loading and required controls here:
CVE-2026-4372's private implementation-field bypass and CVE-2026-5241's nested
`trust_remote_code` propagation.

**Decision: validate checkpoint configuration before the model stack sees it.** Every visual and
Sorani-validator loader now recursively refuses the two private implementation fields, a
repository-shaped public attention/expert implementation, and any config-supplied
`trust_remote_code`. Each adapter also supplies the exact model-type allowlist measured in its
pinned checkpoint, so an altered Qwen config cannot dispatch into X-CLIP, LightGlue, or any other
Transformers family. The guard runs before even CUDA discovery; a refusal cannot arrive after a
processor or model already interpreted the config.

**Evidence, without laundering the scanner.** All five real local configs pass their production
allowlists. A clean Python 3.12.13 environment containing dev, media, cloud and GPU extras passes
`pip check` and the canonical gate at 1,237/1,237 with zero skips. `pip-audit` still prints four
Transformers advisories; `evidence/optional-runtime-security.md` records each as mitigated or
unreachable with the exact independent fact, rather than claiming a clean scan. Direct pins are
reproducible; their transitive graph is not yet a hash lock, and this decision does not say it is.
---

## D-095 · Path A's whole-transcript regression must distinguish text from timings

**Path A's transcript could be deleted entirely and the whole suite stayed green.** M2.3's row
says "Sends the **whole** normalized transcript — a test asserts every fragment reaches the judge,
because sending a subset is the exact failure §3 built the dual path to prevent and would be
invisible in the output." Measured: replacing `text=transcript.text_ckb` with `text=""` — so the
judge receives a timing table and no Kurdish text at all — left `tests/test_path_a.py` at 21 passed
and the full suite at `exit=0, 0 FAILED`.

**Why the cited test could not see it.** `test_the_whole_transcript_is_sent_unfiltered` asserted
three fragments — ڕۆژنامەوانی, گرنگە, بکەین — and all three are entries in the fixture's `words`
tuple, so `_timing_table` renders each of them above the transcript. `fragment in api.prompt` was
satisfied by the timing table alone. The fixture's `text_ckb` deliberately carries material absent
from `words` (لە, هەولێر, زۆر, بۆ, ئێمە, با, باسی) and not one of those was asserted, so the test
sampled exactly the fragments that could not discriminate.

**Decision: assert the whole `text_ckb` verbatim, not sampled fragments.** A substring check on the
complete transcript cannot be satisfied by a timing table, and it needs no list of magic fragments
to maintain. The discriminating fragments are additionally derived at runtime — computed as
`text_ckb` minus `words` — with an assertion that the set is non-empty, so a future fixture whose
text adds nothing beyond its words fails loudly instead of silently blinding the test again.

**A control was added because the fix could have caused the opposite defect.** A prompt that dropped
the timing table and kept the text would satisfy every assertion above, so the test now also
requires a timing row to be present. Mutation audit **3/3**: text dropped entirely CAUGHT, text
truncated to a subset CAUGHT, timing table dropped CAUGHT.

**A claim from the same agent that I could not reproduce, recorded because it was alarming.** It
reported that a `RawTranscript` reaches `countTokens` before invariant #3 refuses — "RAW text in an
emitted request body: True". Measured with the suite's own recording transport: both
`discover(raw)` and `build_request(raw)` raise `TypeError` with **zero endpoints hit** and no raw
text in any body. Invariant #3 holds at the door on both public entry points. Whatever path that
agent constructed, it is not one I can reach, and the claim is refuted as stated rather than carried
forward. This is the third pass in which an agent's framing needed correcting before the finding was
actionable — and the first in which the correction was that the alarming half was simply wrong.

Gate at the measured source revision: `VERIFY OK — 1136 passed, 0 skipped`.

---

## D-096 · Verify every accessible project-managed checkpoint byte before model loading

**A pinned repository commit did not prove the directory a loader actually opened.** Before this
decision, any nonempty checkpoint directory counted as available. The fetcher selected an exact
remote revision, but a partial copy, a locally changed same-size tensor, or an added modelling file
could sit at that path without any comparison to the remote snapshot. Configuration allowlisting
from D-094 reduced what Transformers could dispatch; it did not prove the weights or tokenizer
files were the ones reviewed.

**Decision: bind every accessible local file set to content identities from the exact Hub commit.**
A tracked schema-1 manifest accounts for every registry entry provisioned as explicit weights.
Accessible LFS objects carry their published content SHA-256; ordinary Git files carry their
canonical Git blob id. Pyannote's gated API redacts five LFS digests, so that entry is explicitly
`blocked` and can never pass verification; asterisks are not accepted as hashes. For the other five,
the runtime requires the manifest repository/revision to equal `sources.json`/`revisions.json`,
refuses missing, extra, unsafe or symlinked paths, checks every size, and hashes every byte. A
same-size tensor mutation is a named regression, not a hypothetical assertion.

**Enforce at both truth surfaces.** The Qwen embedding/reranking loader shared by VideoChat3 and
TimeLens2, plus the Sorani Qwen-ASR validator, prove integrity before importing or invoking their
model stacks. The readiness command uses the same proof, so a corrupt nonempty directory reports
unavailable. A stage asking for one model checks only that model; the full readiness report checks
all installed checkpoints. The manifest ships in the wheel beside source and revision pins.

**Measured cost and boundary.** The production verifier accepted all 105 files / 37,268,980,562
bytes across the five locally installed checkpoints in 31.946 seconds. Pyannote's ten-file public
inventory is pinned, but its five LFS identities and gated bytes remain blocked. This establishes
local-byte integrity from a trusted checkout/wheel for the snapshots whose upstream identities are
available; it does not authenticate the unsigned release and does not cover package-managed
OmniASR downloads. `evidence/model-byte-integrity.md`.

Gate: `VERIFY OK — 1249 passed, 0 skipped`.

---

## D-097 · Caption guard wiring needs a render-path regression

**The caption guard's wiring was protected only by an import-usage lint rule.**
`assert_captions_within_clip` refuses an ASS with nothing to draw inside `[0, clip_duration_ms]` —
Kurdish invariant #4, since subtitles burn into an already-cut stream where `t=0` is the clip start.
The function is well covered in `tests/test_caption_timing.py`. Its call in `render_clip` was not.

**Two mutations, and only one is an honest catch.** Deleting the call leaves the import unused, so
`ruff` reports it and three `test_gate.py` nested-gate tests fail *because `verify.sh` runs a red
lint* — a linter noticing a dangling name, not a test noticing captions stopped being checked. The
import-preserving mutation — hand the guard a synthetic always-valid ASS instead of the file on disk —
leaves ruff clean and the **full suite at 0 failures**, and under it an ASS with source-absolute
stamps ships a valid, playable, caption-free MP4 reporting `captions_burned_in=True`.

**Decision: assert the wiring through the render path, not the function again.** The new test writes
an ASS stamped a minute into the episode and requires `render_clip` to raise `CaptionsOutsideClip`,
plus that no MP4 was written — "refused" and "refused after writing the file" are different facts. It
asserts the fixture clip ends before the planted stamp, so the fixture cannot drift into overlapping
and quietly blind the test, which is D-095's failure mode one week later.

**The control matters as much as the assertion:** the ordinary ASS this suite builds must still render
and still report `captions_burned_in`, or the test would pass for a `render_clip` that rejected every
caption file. After the fix, the import-preserving mutation fails exactly one test with ruff clean —
a behaviour catch.

**My own instrument made the same mistake first.** The initial mutation was written inline through
shell escaping and produced `Found 15 errors` from ruff, so it would have "been caught" for reasons
unrelated to captions. D-082's lesson recurring inside the tool rather than the subject; rewritten as
a file-based script with the ASS as a short constant so the only variable is the guard.
`evidence/caption-guard-wiring-unprotected.md`.

Gate: `VERIFY OK — 1137 passed, 0 skipped`.

---

## D-098 · SV6D timestamps cannot smuggle a far claim through a duration

**M5.3's headline claim was false for every window this pipeline plans.** That row says a label
citing `9999s` on a short scene "constructed cleanly" and `assert_sv6d_within_window` "closes it".
The guard's rule is *some* cited time inside the window — a documented tradeoff, because a label may
name a length as well as a moment. Pair `9999s` with a duration the window happens to contain and
the claim rides through. Measured on the three windows Stage 0 actually plans for the fixture:

```
0..1400   'speaker gestures at 9999s, held over 1s' -> ACCEPTED
1400..2800  … 'over 2s'                             -> ACCEPTED
2800..4162  … 'over 3s'                             -> ACCEPTED
300000..312000  (the window the cited tests use)    -> refused
```

The tests exercised the single distance from zero where 1000 ms falls outside the window, so the
rule bit there and nowhere the pipeline runs.

**Decision: bound the out-of-window citation by the window's own length. No invented constant.**
In the legitimate case the guard exists to permit — "slow push-in over 3s, starting 5:04" — the
out-of-window number is a small *duration* (3 000 ms) and the in-window one is the *moment*
(304 000 ms). In the defect it is reversed: the out-of-window number is vastly larger than the
scene. So a cited time outside the window is admissible only if it is shorter than the window
itself, which is the longest duration anything inside it can have. That is derived from the
arguments the function already receives, not chosen — which is why this is a fix rather than
another `BLOCKED` entry like #14 and #15.

**Verified in all four directions before writing a test:** the exploit is refused on all three
planned windows; the docstring's legitimate label stays ACCEPTED; the original headline defect
(`9999s` alone, no in-window time) is still refused by the existing rule; and an ordinary short
label on a short window still passes.

**Mutation audit 3/3.** Two of them matter for opposite reasons: *"the plausibility bound never
fires"* is the defect restored, and *"in-window times are also rejected"* is the over-strict
direction — the failure mode the original docstring explicitly warned about, caught by the control
rather than by any refusal test.

**Parametrized over the real windows on purpose.** The previous tests were correct and blind for the
same reason D-095's were: they used a fixture where the rule happened to work. These use
0..1400, 1400..2800 and 2800..4162 — what `plan_scene_windows` produces on the only media in this
checkout. `evidence/sv6d-duration-smuggling.md`.

Gate: `VERIFY OK — 1142 passed, 0 skipped`.

## D-099

**A number in the evidence was wrong, and the same file's other numbers proved it.**
`evidence/waw-separation.md` recorded `waw_initial_words: 491`. KLPT's lexicon has **504**, and the
file's own constructible count settles it: 24 894 − 504 = 24 390, whereas 24 894 − 491 = 24 403.
Every other figure in the file was already consistent with 504.

**Why it survived two adversarial passes.** The guard recomputed nothing. It asserted
`lexicon_entries > 20_000`, `dictionary_words_damaged == 0`, and that the unsplittable list matched
its own length — three of seven numbers bounded, none measured. A number nobody recomputes is a
transcription, not a measurement, which is the same failure D-069 found in `AUDIT_REPORT.md` and
D-091 found in `MINIMUM_HOURS`.

**And both passes got the true value wrong.** One reported "504 with duplicates (وسمە appears
twice) and 492 distinct"; measured, there are 504 with **zero** duplicates. `lexicon_entries: 24894`
was right all along — KLPT's `.dic` is Hunspell format whose first line is an entry count, and the
suite's `lexicon` fixture already skips it.

**Decision: recompute every recorded number, and make the arithmetic itself an assertion.** The test
now derives `waw_initial_words` and `constructible_joined_forms` from the lexicon, checks
`lexicon_entries - waw_initial_words == constructible_joined_forms`, checks
`recovered + not_recovered == constructible`, and recomputes `recall_pct`. It was red on the wrong
figure before the correction — the only version of this test that could have caught it.

**`constructible_joined_forms` was promoted from prose into the recorded JSON.** The 24 390 figure
existed only in a sentence, which is exactly how it escaped checking while being the number that
disproves 491. A figure that carries an argument belongs where the guard can read it.

**Two more stale copies of Hunspell's own header, corrected.** `tests/test_waw.py`'s module
docstring and `normalize.py:121` both cited "24,888" — the count in the `.dic`'s first line, which
is stale in KLPT's data — where the measured entry count is 24 894. Same defect as the main finding:
a number copied from a source rather than measured from it. `evidence/waw-separation.md`.

Gate: `VERIFY OK — 1142 passed, 0 skipped`.

---

## D-100 · A clean commit is not evidence that its release passed the gate

**The release command published untested revisions by design.** `_source_identity` proved only
that `HEAD` was clean and stable. It then created the private builder, built twice and emitted
schema-3 provenance without consulting the gate, JUnit or CI. The release test made the defect
executable: it initializes a new repository with no remote, workflow or gate evidence and expects
publication to succeed. A syntax-correct wheel from a commit with failing tests was therefore a
valid HawEdit release.

**Decision: require one explicit official production gate, not "the latest" and not a local
leftover.** `.gate/last-test-run.xml` is ignored, mutable and has no source SHA; binding it after the
fact would turn a timestamp into identity. Selecting the latest Actions run races concurrent
pushes. The caller must provide `--gate-run-id`, and both the CLI and exported build function query
that exact record before creating a builder or output directory.

The accepted record must name `HawzhinBlanca/HawEdit` as both repository and head repository, use
`.github/workflows/gate.yml`, be a `push` on `main`, and match the clean release SHA. The run and
its single `gate` job must be completed successfully on the same attempt. The returned job list
must be complete, and all eight mandatory install, full-gate, real-media and evidence steps must
be present, completed and successful. Fork, PR, manual, feature, queued, failed, wrong-SHA,
paginated, malformed and network-error paths fail closed. `GITHUB_TOKEN`, when needed for rate
limits, is sent only as an authorization header.

**The first fix still built the wrong thing under a race.** Both builds read the live worktree and
only checked cleanliness before and after. A concurrent writer could change a tracked source,
leave it changed through both builds so their bytes matched, then restore it before the final
check. Schema-4 provenance would name gated SHA A while the wheel contained other bytes. Both
builds now consume separate `git --no-replace-objects archive <revision>` exports. Git objects,
not mutable paths, define the source; separate extractions also prevent build 1's generated
egg-info/build files from making build 2 falsely agree. The extractor is implemented in HawEdit
rather than relying on tar's Python-3.11.4-added `filter=` API: it path-confines every member and
refuses links/special files, preserving the declared Python 3.11.0+ support range.

**Authorization cannot follow a redirect.** urllib's default redirect handler can copy headers to
the redirected request before a post-response URL check runs. The release client installs a
redirect-rejecting handler, so a 30x is an HTTP refusal and `GITHUB_TOKEN` never reaches the target.
The provenance URLs are constructed locally from already-verified official run/job ids rather
than treating GitHub's display-link formatting as a security boundary.

**Provenance schema 4 introduced the proof (schema 5 adds D-157's artifact identity).** Repository,
workflow, run id/attempt, event, branch,
revision, result, completion, job id and official URLs are now part of the checksummed provenance.
An explicit id makes the result stable and reviewable; it also prevents a newer unrelated success
from blessing an older source tree.

**Live controls, not only mocked JSON.** The verifier accepted official `main` push run
`31295014063` for exact SHA `b34d88dc734f8aefd6c7c7d10ff6953cc5e24e92`. It refused successful
run `31294726370` for `c983673...` because that was a manual feature-branch run. Focused release
tests mutate every identity/status boundary and prove failure precedes output creation.
`evidence/release-exact-gate.md`.

This closes promotion without claiming authenticity: GitHub's record is still not a project
signature, and M3.7 remains partial for release signing and external asset supply-chain coverage.

---

## D-101 · An OmniASR cache key identified a URL, not the 43.5 GB behind it

The official runtime was pinned by package name and still accepted arbitrary checkpoint bytes.
fairseq2 0.6 names its cache directory with 24 hex characters of SHA-1(URL), trusts an existing
directory without hashing it, and validates a first download only against `Content-Length`.
Package card sources can also override checkpoint fields. Adding a trailing `@` to the two model
cards was necessary and insufficient: the shared `tokenizer_ref` is resolved by its bare name, so
`omniASR_tokenizer_written_v2@user` could still redirect the tokenizer.

**Decision: HawEdit owns the content boundary even though Meta owns the transport.** The packaged
Python allowlist records exact official URL/cache-key/filename/size/SHA-256 identities for LLM-7B,
CTC-3B and the written-v2 tokenizer. Setup downloads to a private directory and atomically
publishes only exact bytes. Every worker hashes the full set again before either pipeline is
constructed. Symlinks, extra cache members, concurrent mutation and corrupt pre-existing entries
are refusals. Existing corruption is not overwritten automatically; the error names the exact
directory to move aside.

**Cards are bytes and effective policy, not trusted prose.** Runtime identity is fixed to
`omnilingual-asr==0.2.0`, fairseq2's actual PEP 440 distribution version `0.6`, and the exact 2,725
byte official card document. Both external fairseq2 card sources are replaced before its first
import with distinct existing verified-empty private directories. The effective model and bare
tokenizer cards are then resolved and compared field-for-field, catching a changed URI,
architecture, family, tokenizer reference, added `restrict: false`, or any other added field.

**`.ready` is not a permanent receipt.** Rerunning `hawedit-asr-setup` always rechecks/provisions
the assets and refreshes the fingerprinted worker copy. Inference also refuses a ready worker
snapshot whose Python fingerprint differs from the host package. An old marker is removed before
runtime mutation and a new fsynced marker is atomically published only after the complete setup
and GPU probe succeed. `omniASR_LLM_Unlimited_3B_v2` is intentionally excluded until its 17+ GB
file is actually downloaded, independently hashed and reviewed; an upstream card entry alone is
not integrity evidence.

**Verified bytes remain bound to the loader.** The three verified file descriptors stay open and
fairseq2 loads through private suffix-preserving aliases to those descriptors until both real model
pipelines exist. This prevents a cache pathname swap after hashing. It does not claim protection
from a malicious same-UID process writing the already-open inode; that needs an OS-enforced
immutable store and is outside HawEdit's application-level supply-chain threat model.

Exact identities, live WSL measurements and negative controls:
`evidence/omniasr-asset-integrity.md`.

Gate: `VERIFY OK — 1307 passed, 0 skipped`.

---

## D-102 · Retrieval depth cannot undercut the Stage 2 survivor floor

**`k` walked straight past the survivor floor.** D-037 clause 4 says Stage 2 refuses rather than
shortening the survivor slice, and D-066 restored that after it was once reverted. The check only
ever looked at `len(index)`. Measured on a 60-window index with `keep=5`:

```
  k=50 -> 5 survivors        k=3  -> 3 survivors, no error
  k=5  -> 5 survivors        k=1  -> 1 survivor
                             k=0  -> 0 survivors, empty tuple
                             k=-5 -> 5 survivors, after reranking 55 windows
```

The negative case is its own small defect: `retrieve` slices `scored[:k]`, so a negative `k` drops
the tail instead of keeping a head — 55 windows reranked where 5 were wanted, silently different
semantics and wasted GPU time on a real index.

**Decision: refuse `k < keep`, as arithmetic rather than a threshold.** Retrieving fewer candidates
than the survivor count cannot produce `keep` survivors, so the slice could only ever be short —
which is exactly what clause 4 forbids. Nothing is chosen here; the relation between the two
arguments settles it, which is why this is a fix rather than a `BLOCKED` entry like #14 and #15.

**Placed in `rerank_and_keep`, not in `retrieve`.** `retrieve`'s contract is "the top k", and that is
honest at any k — the survivor floor is Stage 2's concern, and `rerank_and_keep` is the one function
that knows both numbers. One guard, at the only place that can see the relation.

**The control is the boundary.** `k == keep` can still fill the slice exactly and must not be
refused, and §3's own `RETRIEVE_K` must keep working. Mutation audit **3/3**: the guard never firing
is CAUGHT, refusing only negative `k` is CAUGHT, and `k <= keep` — the over-strict direction that
would reject the tight boundary — is CAUGHT only by that control.

**Scope, stated plainly:** `pipeline.py` builds `VisualComposer` without `retrieve_k`, so the shipped
CLI always ran at §3's depth of 50 and could not reach this. The defect was in the public API and in
the written proof — D-037 clause 4's guarantee was weaker than its own wording. Found by the third
adversarial pass. `evidence/survivor-floor-bypassed-by-k.md`.

Gate in the original parallel branch: `VERIFY OK — 1148 passed, 0 skipped`.

---

## D-103 · A missing locale is not evidence that a Common Voice row is Sorani

**A Common Voice split that declined to name its language was imported as `ckb`.** The locale check
read `if row_locale and row_locale != locale:`. The leading truthiness clause skipped it for every
row whose `locale` was absent or blank, and the provenance name is built from the **parameter**
(`f"Mozilla Common Voice {locale} ({tsv_path.name})"`), never from the data — so the manifest
asserted the language precisely where the file had failed to state it. Measured on Kurmanji rows:

```
  A locale present, value kmr    REFUSED
  B locale column ABSENT         ACCEPTED 2 items | 'Ev pir bas e' | 'Mozilla Common Voice ckb (…)'
  C locale cell BLANK            ACCEPTED 2 items
```

`'Ev pir bas e'` is Kurmanji, stored as `reference_ckb`. This is the poisoning the module docstring
names as its fourth promise, reached without touching the locale value at all — only by omitting it.

**Decision: an unreadable locale is refused, not treated as absence of objection.** A blank or
missing cell is the file declining to confirm the language this importer is about to assert on its
behalf, and the module's own governing rule is to be pessimistic about everything the source does not
actually state. This is the same treatment duration already gets — required, never defaulted —
because both defaults would convert an interim stand-in into a number somebody quotes later.

**Rejected: inferring the locale from the path** (`cv-corpus-…/ckb/validated.tsv`). It is derivable
in the common case, which is what makes it dangerous: it would restore the accept-by-default
behaviour under a new justification, and a directory name is a claim by whoever unzipped the file,
not by the corpus. Refusing costs one column in a hand-made TSV and nothing in a real download, where
Common Voice always writes `locale`.

**The control is the point.** Refusing every row satisfies both refusal tests and imports nothing,
ever. Mutation audit **3/3**: restoring the truthiness bypass is CAUGHT, the guard never firing is
CAUGHT, and `row_locale == locale` — the over-strict direction — is CAUGHT only by the honest-`ckb`
control, which also asserts the provenance, since the defect was the two disagreeing. Fourth
consecutive iteration where over-strictness was visible only to a control (D-087, D-088, D-102).

**Scope, stated plainly:** M0.16 is BLOCKED and no corpus exists on this machine, so nothing shipped
wrong output to a client. What shipped was a false guarantee — the docstring's fourth promise and
M0.14's row both claimed a check a missing column walked around. Found by the fourth adversarial
pass; premise re-verified here rather than taken from the agent's report.
`evidence/common-voice-locale-bypass.md`.

## D-104 · The gate interpreter must prove it can execute HawEdit

**`PY` replaced every gate step at once, including the one that grades the other four.** The override
refusal is a whitelist of one — `LINT_CMD`, `FORMAT_CMD`, `TYPECHECK_CMD`, `TEST_CMD` are each exit 5
— on the recorded grounds that "no blacklist of ways to run nothing can be complete". `PY` is not
refused, because it is a deliberate feature (D-039's Windows interpreter discovery), and `PY` is the
prefix of all four commands plus the `hawedit.gate` evidence step. Measured:

```
$ PY=/usr/bin/true.exe bash scripts/verify.sh
==> lint / typecheck / format / tests / test evidence
VERIFY OK — hawedit gate green
exit=0 elapsed=1s        report exists: NO
```

Layer 3 exists so that "the exit code stops being the evidence"; layer 3 was `true.exe`, auditing four
other runs of `true.exe`. Never computed, not computed-and-discarded: no report was written for
anything to read back.

**Decision: an interpreter proves it can run this project before it is trusted to grade it.** One
probe after `PY` resolves and before any step, at the single point `--fast`, nested and full runs all
pass through: `"$PY" -c 'import hawedit; print("hawedit-interpreter-ok")'`, and the **shell checks the
value**, not the exit code — an exit code is precisely what `true.exe` is good at. Exit 3, which was
unused. Stated as a capability rather than a spelling, which is the same inversion the override
refusal already relies on.

**Rejected: refusing `PY` outright.** It would close the hole and break the project. `PY` is how the
gate runs on hawapc01 at all (`Scripts/` vs `bin/`, D-039), and CI resolves it from `.venv`. A gate
that cannot be pointed at its own interpreter is not more trustworthy, only less runnable.

**Rejected: asserting `hawedit.__file__` lives under the checkout.** It would additionally catch
"a real python from a *different* checkout", and it is exactly what breaks the worktree-isolated
adversarial passes, whose `.venv` is a junction into the main checkout — and it would refuse any
non-editable install, including a wheel smoke test. Bought a narrow case at the price of two real
workflows.

**Rejected: a shell-side check that the report file exists after the test step.** Redundant once the
interpreter is real, since `hawedit.gate` already refuses a missing report and is now genuinely
running.

**Mutation audit 5/5**, and stated precisely because a mutation caught for an unrelated reason reads
as protection it does not have (D-087): the probe never refusing is CAUGHT (3), `-n "$_probe" &&` —
the D-103 truthiness shape, which would have re-admitted `true.exe` because it says nothing — is
CAUGHT (2), swallowing the interpreter's answer is CAUGHT (1), dropping `import hawedit` from the
probe is CAUGHT (1), and refusing every interpreter is CAUGHT (10). The last two single-test catches
are the ones doing real work. **The over-strict direction was already covered** by nine pre-existing
tests of the gate's success path, so the new control makes the property explicit rather than newly
protected — unlike D-087, D-088, D-102 and D-103, where a control was the only witness. Recording
that difference rather than continuing the pattern by assertion.

**Not closed, and left as the next item:** a forged JUnit report. With a real `PY`, something else
answering to `-m pytest` on `PYTHONPATH` could write an XML that layer 3 reads back and accepts. The
probe cannot see it, because the interpreter genuinely is this project's. It needs its own
measurement — it was reported by an adversarial-pass agent and I have not reproduced it.
`evidence/py-override-bypassed-the-whole-gate.md`.

---

## D-105 · Automatic QC can advise a human; it cannot impersonate one

`Clip.assert_renderable()` said the human gate was always required and implemented
`auto_pass or human_reviewed`. The canonical test fixture used the bypass itself. A public JSON or
library caller could therefore publish a clip with no recorded human review.

**Decision:** `human_reviewed` is independently mandatory at the last render boundary. `auto_pass`
remains useful telemetry and may be true or false, but never substitutes for a person. Both the
clip gate and `render_clip` have regressions proving an automatic-only pass leaves no artifact.

## D-106 · Hosted-model numbers are parsed, never coerced

Python treats booleans as integers, and `float()`/`int()` also accept numeric strings. Gemini
verdicts, Path A candidates, TimeLens spans and Gemini token counts used those coercions at the
least-trusted boundary. Measured examples promoted `true` to a perfect score, grounded
`[[false,true]]` as 0..1 seconds and accepted `totalTokens=true` as a billable count of one.

**Decision:** model numeric fields must have their exact JSON category: non-boolean finite numbers,
exact integers where the schema says integer, and non-negative integers for token authority.
Strings, booleans, NaN, infinities and unrepresentable magnitudes fail before generation,
ranking or boundary fusion.

## D-107 · One ffmpeg call owns one frame namespace

Both visual extraction paths wrote into a reused directory and globbed every matching filename.
A retry producing five frames could silently return fifteen stale frames from the previous run,
with fresh timestamps. That contaminated Gemini, Qwen retrieval/reranking, VideoChat3 and TimeLens.

**Decision:** every ffmpeg invocation writes into an atomically created private directory and may
enumerate only that directory. Failed attempts remove only their owned directory. Stage 4 deletes
successful temporary JPEGs after copying their bytes; shared visual frames persist because the
local models still consume their paths. Regressions preserve hostile caller-owned stale files and
prove none enter the result.

## D-108 · Encoded duration has an upper privacy boundary

The render gate rejected a file that was too short but accepted one of arbitrary length. A broken
encode could therefore publish trailing source footage with no matching transcript, captions,
editorial judgment or consent.

**Decision:** measured and requested duration may differ by at most one measured frame in either
direction. Anything longer or shorter is refused before the staging file is published.

## D-109 · Transcript publication is a transaction for readers and competing writers

The digest sidecar deliberately reserved a media id before the raw hard link appeared. A losing
pipeline writer immediately caught `RawTranscriptImmutable` and read the raw path, creating a
reproducible digest-visible/raw-missing race.

**Decision:** all raw publication, read, digest and integrity operations share one per-media
thread-and-process lock. A loser cannot receive the immutable refusal until the winning raw/digest
pair is complete. A digest left without raw after process death is reported as interrupted or
tampered evidence and is never reconstructed in place.

## D-110 · Known visual component refusals belong in the pipeline report

The runner promised model-stage failures as `StageSkipped`, but the composer normalized only
`VisualIndexError`; real frame, Qwen and VideoChat3/Path B domain failures escaped and aborted the
run even when Path A had valid candidates.

**Decision:** concrete Qwen/VideoChat adapters normalize backend `RuntimeError`/`OSError`, frame
extraction normalizes ffmpeg launch errors, and `VisualComposer` converts those known component
domain errors into `VisualPipelineError`, preserving the cause. The runner already records that
type. Unexpected exceptions still escape, so programming defects are not mislabeled as an
unavailable model.

## D-111 · WSL readiness is a receipt for one source snapshot and one venv generation

The old `.ready` flag named only a source fingerprint while every fingerprint reused one mutable
`runtime/venv`. Two setup processes could mutate that venv concurrently; a failed process could
leave another marker positive, and the loader accepted a marker even when the interpreter did not
exist. Package importability also reported OmniASR ready without proving its 43.5 GB assets.

**Decision:** setup is one cross-process transaction. It publishes a fresh exact Python-only
source snapshot and a schema-2 JSON receipt only after a versioned venv generation, distro/user,
Python 3.12, pinned top-level packages, two visible CUDA devices and all canonical assets agree.
Launch re-hashes the snapshot and live-probes the recorded interpreter; `ModelStore` uses the same
proof rather than importability. The venv is described as versioned and revalidated, not
byte-immutable: transitive artifact hash locking remains open release work.

## D-112 · A predictable lock filename is untrusted filesystem input

Transcript publication, WSL setup and 43.5 GB model provisioning all used predictable lock names.
Opening one with `a+b` can follow a hardlink, symlink or reparse point and modify an unrelated
file; Windows `LK_LOCK` also stops retrying after roughly nine seconds, far shorter than model
setup can take.

**Decision:** every long-lived project lock opens the final component without following it where
the platform permits, requires one regular link, binds the pathname identity to the descriptor
before and after waiting, and initializes only after validation. Windows uses explicit bounded
`LK_NBLCK` retry. Replacement, timeout, open and release failures are domain errors, never an
unhandled platform exception.

## D-113 · Build code cannot hold the authority that attests its own output

The reproducible release directory had an exact successful gate, immutable Git-object inputs,
deterministic metadata and `SHA256SUMS`. It still had no external trust root: anyone replacing the
wheel could rewrite every self-asserted JSON file and the checksum manifest. The first attestation
workflow draft then put `id-token: write` and `attestations: write` in the build job itself. That
would let the repository code being judged request its own OIDC identity, and a background process
could change output between hashing, attestation and upload. Its one-level attestation glob also
differed from the upload action's recursive directory input, so a nested un-attested payload could
ship in a nominally attested bundle.

**Decision:** promotion is two jobs with a hosted artifact boundary. The build job has only
`contents: read` and `actions: read`, checks out the exact successful official `gate` push SHA,
invokes the existing independent gate verifier and uploads four explicit paths as a short-lived transport. A dependent
job starts on a fresh runner, checks out no repository code, validates the transport digest and
refuses anything except one regular wheel, its SPDX JSON, schema-5 provenance and `SHA256SUMS`.
Trusted workflow shell rechecks the manifest and binds repository, workflow, event, branch, gate
run, revision, wheel and SBOM fields to the event and actual bytes. Only then does that job receive
GitHub OIDC/attestation authority. `actions/attest` and the final upload receive the same explicit
four paths. Both jobs also require the release run's default-branch `github.sha` to equal the
triggering gate's `workflow_run.head_sha`. `actions/attest` derives standard provenance from the
OIDC SHA; if `main` has already advanced, stale promotion is refused rather than signing bytes from
`S` with a predicate naming `T`. Every remote action is an official release resolved to a full
commit and Node 24.

**Rejected:** attesting in the build job. A signed claim made with authority available to the code
under test is not meaningful isolation. Also rejected: attesting `dir/*` then uploading `dir/`;
different path semantics make the signed and shipped sets diverge.

**Measured locally:** the release/security tests pass, PyYAML parses both jobs, and a
release-checksum-verified `actionlint` 1.7.12 reports zero findings. This does not invent hosted
evidence. GitHub reads a `workflow_run` consumer from the default branch, so authenticity remains
an explicit live acceptance item until one protected-`main` gate triggers this workflow and every
downloaded payload passes `gh attestation verify` with the exact release-workflow, `main`, source
SHA, signer SHA and hosted-runner policy recorded in `evidence/release-attestation.md`. Repository
scope alone is not enough because another workflow in the same repository is a different signer.
`evidence/release-attestation.md`.

## D-114 · A checkpoint exists only after exact verified atomic publication

The old fetcher wrote directly into final model directories. Any interrupted first download left
an empty or partial directory that `missing_weights()` treated as installed, so every retry skipped
the broken checkpoint. The command then printed `MISS` and exited zero. A second root variable made
custom downloads invisible to the app, and a custom truthy revision such as `main` re-enabled
mutable Hub resolution.

**Decision:** plan from exact verified readiness, not path existence; accept only lowercase 40-hex
revisions at the runtime API; and use `HAWEDIT_MODELS_DIR` end to end for mutable checkpoint bytes
only. Source, revision and integrity identities always come from the separate trusted
checkout/installed metadata root. A pinned download resumes in a revision-specific private sibling,
verifies the exact packaged manifest under a writer lock and publishes only through a native
no-replace rename. Existing or concurrently appearing finals are evidence/operator data: preserve
and refuse them rather than guessing permission to delete. Attempt all planned targets, print
complete status, and exit nonzero if any target failed.

The verifier also rejects root/member reparse points, hardlinks, non-regular members, identity
changes during no-follow hashing and file-set changes. The lock coordinates HawEdit readers and
writers; it is not a claim against privileged out-of-band mutation. No live multi-gigabyte Hub
download was run for this unit. `evidence/checkpoint-provisioning.md`.

## D-115 · The values a model consumes must remain bound to the bytes verified

Qwen visual constructors read and cached checkpoint-controlled prompts, pooling and reranker token
ids before integrity ran. Restoring the pinned files before first model load made the later hash
green while the object retained attacker-controlled recipe values. Every local loader also closed
its pathname verification before Transformers/Qwen-ASR reopened the directory; a concurrent
hardlink or atomic replacement could change model/config/code bytes after they were approved.

**Decision:** `verified_checkpoint_access` takes the checkpoint's shared lock, exact-verifies, and
yields the verified directory without releasing the lock. Visual/VideoChat/TimeLens loading keeps
that context across safe config, checkpoint recipe parsing, imports, CUDA checks, processor/config
construction and every `from_pretrained` call. Qwen-ASR does the same. Constructors read no recipe;
access before verified load is a domain refusal. Tests prove integrity-first ordering, active
binding through all constructor reads, restored trusted recipe values and fail-closed malformed
JSON. Because Windows and WSL advisory locks do not interoperate on DrvFS, the Windows producer
also holds its host shared lease across the entire WSL validator subprocess and output parse; a
real child writer regression proves the host publisher remains blocked. Historical real GPU runs
identify the checkpoints but predate this held-lock path, so one
fresh full-size load remains an explicit evidence task. `evidence/checkpoint-load-binding.md`.

## D-116 · Support only resolvable Python, and execute a wheel before attesting it

The project declared Python `>=3.11`, but the pinned base graph cannot resolve on 3.13:
`klpt==0.1.7` requires `chunspell==2.0.4`, whose distributions stop at CPython 3.12. The ASR stack
also caps its official package at 3.12. Separately, release promotion ZIP-validated and attested a
wheel without ever installing or executing it; broken metadata, package-data lookup or console
entry points could therefore receive valid provenance.

**Decision:** support exactly Python 3.11 and 3.12 (`>=3.11,<3.13`) until the complete pinned graph
resolves above it. Setup checks both the base interpreter and any existing venv. The required
`gate` waits for a separate full Python 3.12 zero-skip gate while retaining one canonical job named
`gate`. Before any OIDC authority is available, a fresh no-checkout 3.11/3.12 release matrix must
install the exact transferred wheel, pass `pip check`, resolve installed data and start all six
CLIs. Attestation depends on every matrix leg. Local clean venvs on 3.11.15 and 3.12.13 passed the
same smoke; hosted execution remains required after merge. `evidence/python-support.md`.

## D-117 - A gate interpreter is an identity, not an executable-shaped string

The former `PY` override let an arbitrary program print the expected probe token and return zero
for every gate command. A success token was therefore a self-assertion by the thing being
authenticated.

**Decision:** `verify.sh` accepts only the path-identical interpreter inside this checkout's
canonical `.venv`. Before grading, an isolated environment preflight requires the supported Python
range, current project version, exact active dependency pins, and exactly one authoritative
editable installation rooted at this checkout (plus only its expected same-version egg-info).
PEP 508 markers are evaluated for the audited interpreter. An external or token-forging `PY` is
refused before execution. `evidence/environment-identity.md`.

## D-118 - Operational model failures stop at their stage boundary

Model or transport absence is expected deployment state; an assertion or invalid persisted verdict
is a programming/data error. Treating both alike either crashes routine partial runs or hides
defects.

**Decision:** only named adapter-domain failures become `StageSkipped`; programmer and schema
exceptions remain visible. Auto-selection with no complete sentence does not extract pixels or
call Stage 4. Candidate IDs are validated as one path component before filesystem use. Every
exception-derived report string is printable, whitespace-normalized and hard-bounded, including
cleanup notes. Credentials and local model availability are acquired lazily inside these stage
boundaries, while routing and governance remain eager. Billed `generateContent` is never replayed
after an ambiguous reset/5xx without provider idempotency. `evidence/pipeline-failures.md`.

## D-119 - A WSL receipt carries the code and metadata it will actually use

The worker snapshot originally copied Python only. Qwen-ASR then resolved model manifests beside a
venv where no HawEdit package data was installed, so hard-segment validation could not verify its
checkpoint. Eagerly invalidating the old receipt also made a failed long reprovision destroy a
still-valid runtime generation.

**Decision:** every source snapshot contains an exact receipt-bound copy of the three trusted model
manifests, and its digest/allowlist covers their paths and bytes. Mutable model roots never provide
identity. A prior valid receipt remains readable while a new generation is staged and after a
failed attempt. Runtime-result publication uses a random host-owned, no-follow, single-link,
fd-bound file. `evidence/wsl-runtime-receipt.md`.

## D-120 - Resume data is untrusted before a downloader writes through it

A deterministic Hugging Face resume tree was verified only after `snapshot_download`. A planted
hardlink inside it let the third-party writer overwrite an external file before post-download
verification refused the stage.

**Decision:** recursively validate ownership, privacy mode, type, link count and reparse status
before giving an existing resume tree to the downloader. Atomically move a safe resume tree to a
random private stage and revalidate its bound name; fresh stages are private and unpredictable.
Safe failures move back for retry. `evidence/checkpoint-provisioning.md`.

## D-121 - Provisioning belongs to the installed product, not a checkout shell

The verified checkpoint transaction existed only inside `scripts/fetch-models.sh`. A built wheel
could diagnose missing weights but told its user to run a script the wheel did not contain. The
script also owned dependency acquisition, so an operator command could change the Python
environment whose behavior it was meant to make reproducible.

**Decision:** `hawedit-fetch-models` is a wheel console command and `hawedit.model_fetch` is the
single owner of planning, private resume activation, exact revision/byte verification and atomic
no-replace publication. The checkout script only locates the checkout interpreter and calls that
module. Download capability is an explicit `models` extra at one reviewed
`huggingface-hub==0.36.2`; absent or drifting clients are refused, never installed or upgraded at
runtime. All model adapters name the installed command in their remedy. Legacy hardlink,
permission, invalid-final, unpinned-revision and failed-download regressions execute the Python
transaction with a fake Hub client rather than asserting shell text.
`evidence/checkpoint-provisioning.md`.

## D-122 - Host dependency graphs are reviewed artifacts, not resolver output

Exact direct pins still allowed pip to select different transitive wheels by date, platform and
Python minor. Local verification could also run in a stale editable environment while importing
the current source through `PYTHONPATH`, and the released wheel was installed against a live
resolver before attestation.

**Decision:** commit separate base, gate and minimal model-fetch locks for Linux/Windows CPython
3.11/3.12. Every line selects one exact wheel hash; sdists are forbidden. A pinned generator and
cutoff reproduce the twelve graphs, while a generated source mapping binds each lock's exact bytes
so the file cannot authorize its own edits. Setup, gate and release smoke use hash mode and audit
the complete installed inventory. Installed locks and model manifests are located from exactly one
authoritative HawEdit distribution's raw `RECORD`, authenticated by recorded size/SHA-256, so
ordinary, editable and real `pip --target` layouts cannot silently select another checkout.

This decision covers CPU host and model-fetch environments. CUDA and WSL native build outputs are
separate identities and remain explicit work. `evidence/host-dependency-locks.md`.

## D-123 - Vulnerability acceptance expires and is bound to the runtime identity

The isolated WSL ASR graph must retain Torch 2.8 for fairseq2/torchaudio compatibility. A current
OSV audit reports eight Torch advisory families and four distinct Transformers families. Calling
that graph clean would be false; ignoring scanner output would be worse.

**Decision:** a strict 30-day VEX may disposition a finding only for the exact Python, complete
package inventory, build/runtime lock digests and three OmniASR asset identities in the canonical
receipt. Unknown, missing, duplicate or stale findings, expired review, aliases not covered, and
identity drift all refuse. CVE-2026-24747's weights-only loader is affected-but-mitigated by exact
checkpoint bytes and descriptor binding, not declared unreachable; five tensor-operation families
remain affected. The policy ships as authenticated wheel data.

This is a parser/policy closure, not live acceptance evidence. A protected hardware job must still
generate the exact `pip-audit==2.10.1` report from a canonical live receipt and fail on VEX refusal.
`evidence/wsl-asr-vex.md`.

## D-124 - Crash-resumable checkpoint staging must be private by access control

D-120 moved a validated deterministic resume tree to a random active name. That reduced pathname
guessing but made hard process death strand multi-gigabyte partials which the next run could not
discover. Writing directly to a predictable resume name is recoverable only if another principal
cannot replace or mutate it; POSIX 0700 supplied that boundary, inherited Windows ACLs did not.

**Decision:** create fresh staging unpredictably, validate it, then atomically publish it as the
revision-specific active resume before the first Hub write. POSIX requires owner-only mode.
Windows creates the directory atomically with a protected DACL granting full control only to the
current user, SYSTEM and Administrators, then inspects every root/member owner and ACE without
localized command parsing. Ctrl-C, `SystemExit` and hard process death all leave the same validated
resume for the next run. Hardlinks, reparse points, permissive POSIX modes and a real injected
`Everyone:F` ACE are refused before the client writes.

The boundary excludes privileged and same-account out-of-band mutation; exact post-download byte
verification and the HawEdit reader/writer lock remain mandatory. D-124 supersedes D-120's random
active-name mechanism, not its pre-write validation rule. `evidence/checkpoint-provisioning.md`.

## D-125 - Gate evidence authenticates the real test runner

A real Python interpreter could still import a forged `pytest` from `PYTHONPATH`, write a clean
JUnit report, and ratchet the committed floor without executing the suite. The canonical gate now
checks that every invoked gate tool resolves inside the locked environment before any step runs;
checkout identity and dependency identity remain independently enforced by D-117.
`evidence/forged-test-report-accepted.md`.

## D-126 - Aggregate CER reports must carry their dialect denominators

The benchmark object enforced per-dialect results while its serialized report could omit them.
Report construction now requires the exact dialect breakdown that justifies the aggregate, and
refuses a report whose totals do not close. `evidence/aggregate-cer-without-its-dialects.md`.

## D-127 - The test floor ratchet must be idempotent under skips

Using collected tests instead of passed tests poisons the next honest run whenever a legitimate
skip exists. The evidence contract and committed floor now use passed counts, with an artifact
test proving that two identical green runs leave the second green.
`evidence/floor-ratchet-unprotected.md`.

## D-128 - Ledger test counts are measurements, not standing prose

Twenty-one recorded per-file counts had drifted. Counts that are not enforced are removed from
status claims; the canonical collected/pass totals come from the gate artifact and ratchet.
`evidence/adversarial-pass-5-2026-08-09.md`.

## D-129 - A model stub cannot satisfy real-checkpoint evidence

Availability and benchmark evidence must distinguish injected test doubles from reviewed weights.
Reports now bind the concrete adapter/checkpoint identity and reject stub-equivalent promotion
claims. `evidence/stub-indistinguishable-from-real-weights.md`.

## D-130 - Recorded thresholds are executable contracts

Threshold values cited as decisions must be asserted against the constants that enforce them.
Changing a threshold therefore requires changing the decision and its regression together rather
than silently drifting prose or code. Four existing choices are restated in canonical executable
form so the record—not a self-following fixture—is the authority:

- `MATERIAL_GAIN_RATIO = 0.10` — D-010's ≥10% relative CER improvement.
- `DEFAULT_IOU_MATCH = 0.5` — D-020's temporal match boundary.
- `RETRIEVE_K = 50` — §3's fixed retrieval depth.
- `DEFAULT_TOLERANCE_MS = 50` — one roughly 24 fps frame, reported with every alignment score.

`evidence/recorded-thresholds-unpinned.md`.

## D-131 - Downloaded weights are unavailable without their loader

An exact checkpoint on disk is not runnable when the package that implements its architecture is
absent. Model readiness first verifies the complete byte manifest, then also requires the named
runtime loader; downloaded-but-unloadable is reported as unavailable with both facts.
`evidence/downloaded-is-not-runnable.md`.

## D-132 - Readiness summaries are derived from structured status

The human report once printed the opposite of the underlying availability state. Rendering is now
a pure projection of `ModelStatus`, including a measured zero-byte checkpoint rather than treating
zero as unmeasured. `evidence/readiness-report-could-print-the-opposite.md`.

## D-133 - Delivery provenance names the path that actually found the clip

`editing.json` may not label every result as verbal merely because the selected transcript is
present. Discovery path is carried from the surviving candidate through clip construction and is
rendered distinctly for verbal, visual, and union discoveries.
`evidence/adversarial-pass-6-2026-08-09.md`.

## D-134 - WSL commands bypass the distribution shell

`wsl.exe --` still routed commands through the default shell, which consumed environment
assignments and lost the runtime PATH. One shared prefix builder now uses `--exec`; setup, probes,
path translation, the ASR worker and the live VEX gate share and test that exact argv.
`evidence/wsl-exec-and-the-38-minute-run.md`.

## D-135 - One failed speech region does not erase a completed episode

Canonical ASR records an `UnalignedSpeech` interval for each segment-level inference/alignment
failure and continues with successful regions. Only successful aligned segments enter confidence
and disagreement routing; validator provenance and the complete unaligned set are both preserved.
If every region fails, the producer still refuses because there is no transcript to publish.
`evidence/one-region-discarded-a-38-minute-run.md`.

## D-136 - Frame delivery is validated before parity normalization

The extractor used to drop an odd tail frame and then compare the shortened tuple with ffmpeg's
planned count, rejecting the valid measured 36-planned/35-emitted/34-kept case. Each invocation
still owns a private directory, but count tolerance is now applied to the raw emitted set before
the temporal-patch parity step. `evidence/frame-count-guard-graded-its-own-output.md`.

## D-137 - The video phase follows the two-GPU allocation

Stage 2 embedding/reranking and TimeLens use GPU 1; VideoChat3 uses GPU 0. The CLI exposes separate
index, reader and grounding devices, validates visible CUDA ordinals, and tests the concrete
composer wiring rather than only parser defaults. `evidence/section-6-put-the-video-phase-on-one-gpu.md`.

## D-138 - VideoChat3 planning must respect the measured eight-frame capacity

On the production RTX 3090 Ti, eight frames succeeded at 21.57 GiB and nine frames OOMed; the old
64-frame application ceiling is not runnable on this hardware. This measurement is a planning
constraint, not permission to truncate evidence inside the reader. The planner must split or
refuse windows while preserving coverage and attribution. Composed Path B now plans against the
measured eight-frame consumer capacity while the general Stage 2 ceiling remains 64; regressions
prove complete, gap-free scene coverage and refuse invalid capacities. A real full-episode rerun
must still measure retrieval quality and end-to-end memory after the increased window count.
`evidence/largest-window-a-3090ti-can-read.md`.

## D-139 - Each claimed enforcement route needs its own reachable regression

Kurdish invariant #1 was described as three independent protections while one path had no test.
Every claimed route must be reached by a mutation-sensitive regression; redundant prose does not
increase assurance. `evidence/adversarial-pass-7-2026-08-09.md`.

## D-140 - The isolated OmniASR interpreter is exact CPython 3.12.0

OmniASR 0.2.0 declares Python `<=3.12`; PEP 440 therefore rejects 3.12.13, which the unconstrained
`uv venv --python 3.12` selected during the first real native run. The WSL environment now pins
`3.12.0` exactly and binds it into the generation digest and receipt. Failed Linux-venv cleanup is
performed inside WSL only after validating one direct unpublished generation, because Windows
cannot traverse the venv's `lib64` link. `evidence/wsl-asr-live-acceptance-2026-08-09.md`.

## D-141 - Receipt-bound source must never generate bytecode in place

The first successful setup import created `__pycache__` inside the exact worker snapshot, so the
live verifier correctly refused it. Every WSL execution that imports receipt-bound HawEdit source
sets `PYTHONDONTWRITEBYTECODE=1`; the snapshot allowlist remains exact and unchanged.
`evidence/wsl-asr-live-acceptance-2026-08-09.md`.

## D-142 - Repeated OSV ranges are one advisory only when identity agrees

pip-audit 2.10.1 can emit several affected-range rows with one package, version, primary advisory
and alias set but different `fix_versions`. Those rows are canonicalized to one VEX finding.
Repeated primary IDs with conflicting aliases remain a hard refusal, and evidence retains the raw
report digest. `evidence/wsl-asr-live-acceptance-2026-08-09.md`.

## D-143 - Visual window capacity is explicit

**Windows are now planned to fit the reader, because §3's 64 does not fit it on this machine.**
D-106 measured the ceiling: `MCG-NJU/VideoChat3-4B` reads at most **8** frames per window on a
23.99 GiB 3090 Ti, and the demand is quadratic in frames. BLOCKED #17 listed three options and refused
two of them — lowering `MAX_FRAMES_PER_WINDOW` (§3's constant, frozen) and truncating a window at read
time (D-104's guard exists for exactly that). The third is this one.

**Decision: `plan_scene_windows` takes `max_frames`, defaulting to §3's ceiling and only lowerable.**
`--visual-max-frames` exposes it. The default is unchanged, so no machine silently inherits another's
limit; hawapc01 passes 8 and the run completes.

**The bounds are derived, not chosen.** Above `MAX_FRAMES_PER_WINDOW` a plan would exceed §3's
published setting. Below `TEMPORAL_PATCH_FRAMES` a window cannot fill one temporal patch, so the
processor pads it by repeating a frame that was never filmed (D-060). Both ends come from constants
already recorded.

**The cost, measured on the real media** (2,313,800 ms, 2 fps, no cuts):

```
ceiling 64  ->  73 windows, longest 31,696 ms
ceiling  8  -> 579 windows, longest  3,997 ms
```

7.9× the windows, each seeing an eighth of the context. **§8.2's Recall@K is therefore measured on a
different retrieval unit than §3 describes**, and that is a real cost rather than a free win — which is
why the default stays §3's and the lower ceiling is an explicit operator choice with a recorded reason.

**Proven end to end on the real 38-minute file**, not on the fixture. With `--visual-max-frames 8` the
visual stage **ran** rather than skipping, for the first time:

```
visual_windows planned : 641
indexed_windows        : 641
retrieved              :  50     (§3's RETRIEVE_K)
survivors              :   7     (--visual-keep 7, inside §3's 5..10)
candidate_ids          :   7
```

Both GPUs were loaded at 17,881 MiB — D-105's split carrying indexing on GPU 1 and the reader on GPU 0
— and no CUDA OOM occurred. Editorial, boundary, render and delivery are still skipped, each naming
Stage 4's absent judge (`BLOCKED.md` #3), which is Hawa's.

**Mutation audit 5/5**, after a first run that found two survivors — both of them *wiring*: the plan
ignoring the ceiling it was handed CAUGHT (3), a ceiling outside the derived bounds CAUGHT (2), the
default silently becoming one machine's limit CAUGHT (6), the pipeline dropping the flag CAUGHT (1) and
the CLI value never reaching `run_pipeline` CAUGHT (1). The last two survived the first audit for
exactly D-105's reason one iteration earlier — the planner was tested and the trip from the CLI was
not — so both new tests assert the **windows the run reports**, not the argument it was handed.

**A test premise of mine that was wrong, kept in the record.** The first version capped the fixture at
2 frames, but its 1400 ms scenes already plan exactly 2 at 1 fps, so the cap changed nothing and the
test asserted a difference that could not exist. At 2 fps those scenes plan 3, which a ceiling of 2
genuinely splits.
`evidence/planning-windows-the-reader-can-read.md`.

## D-144 - Per-segment confidence must survive ASR

**§3 Stage 1's escalation rule ranks segments, and Stage 1 averaged them away.**
`escalation.select_for_validation` — the bottom-quartile-plus-disagreement rule, implemented and
tested — has **no reference anywhere in `src/` outside its own module**. The reason is not that nobody
wired it: its input does not survive Stage 1.

`asr.py` collects every region's `mean_logprob` into a list and then stores `sum / len` as one
`AsrProvenance.mean_logprob`. Measured on the real 38-minute run: **547 regions produced 547 values,
and the artifact kept `-6.523425833753913`**. A quartile of an average is nothing. This is
**computed and discarded**, which the hard rules distinguish from never computed because they need
different fixes, and this is the fix for the first.

**Decision: each region's own confidence is kept, on the media clock, in the artifact.**
`RawTranscript.segment_confidence` carries `(start_ms, end_ms, mean_logprob)` per transcribed region.
The aggregate is untouched, so nothing that read it changes. `from_json` reads pre-D-144 transcripts
with `.get`, as D-103 established.

**Proven on the real run's own geometry.** Re-running 38 minutes of OmniASR costs about half an hour of
GPU, so the run's 547 regions were replayed through the fixed assembly:

```
the real run: 547 regions, one recorded aggregate -6.523425833753913
per-segment values in the artifact: 0
assembled: 547 per-segment values retained
§3's rule over those values: 136 of 547 escalate   (547 // 4 = 136, the bottom quartile)
before the change, over one aggregate: 0 escalate
```

**What that does and does not show.** It shows the quartile is computable at all — the count is exactly
`n // 4`, and the pre-change case is inert. The confidence *values* in the replay are spread around the
run's own aggregate rather than being the models' per-segment measurements, so **it is not a finding
about which real segments are weak**. That needs the run repeated, and it is not what this change
claims.

**Still not wired, and this is why.** `select_for_validation` needs `ctc_text` as well, and that is
**never computed**: the CTC pass produces frame-level emissions for alignment
(`OmniAsrBackend._ctc_emissions`) and nothing decodes them to text, so `SegmentTranscript` carries only
the LLM's `text_raw`. Half of §3's rule now has its input and half does not. Inventing a `ctc_text` to
make the call typecheck would fabricate the disagreement the rule is supposed to detect.

**Rejected: ranking on word confidences instead.** `Word.conf` exists per word, and §3 says segments.
Substituting a different unit to make a rule runnable is the kind of quiet redefinition this repo
refuses elsewhere.

**Mutation audit 5/5**, after a first run with two survivors — **both of them validation I had just
written on `SegmentConfidence` with no test reaching it**. That is the third iteration running where the
audit's real catch was my own new guard (D-103's blank reason, D-104's unreachable parity check). The
five: dropping the collected values CAUGHT (3), recording the running average once per segment — the
plausible wrong fix, which would leave every segment tied and the quartile empty — CAUGHT (2), losing
the segment's own bounds CAUGHT (2), accepting a positive log-probability CAUGHT (1), and accepting a
zero-length span CAUGHT (1).
`evidence/per-segment-confidence-was-averaged-away.md`.

## D-145 - Transcript gaps belong in the run report

**The run report was silent about speech the transcript does not contain.** D-103 put every
unalignable region into `transcript.raw.json`, and `PipelineRun.to_dict` reports the **normalized**
transcript, which by design carries no such field. So the fact reached the canonical artifact and not
the document an operator reads.

Measured on the real 38-minute run:

```
raw artifact:  226754..227070 ms (316 ms)  AlignmentInfeasible: 15 frames cannot emit 15 tokens
               1985346..1985694 ms (348 ms) AlignmentInfeasible: 17 frames cannot emit 16 tokens
               total speech with no transcription: 664 ms
emitted report: mentions "unaligned"        -> False
                mentions segment_confidence -> False
```

664 ms of Kurdish absent from a report whose module docstring opens with "§1: fail visible, not
silent" — the same shape as D-100, where the statuses were right and the thing a human reads was not.

**Decision: the run carries what the transcript omits, and the report totals it.**
`PipelineRun.transcript_gaps` is populated where the raw is in hand, and `to_dict` emits each gap
with its bounds, its duration and its reason, plus `speech_without_transcription_ms`. The total is
there because two entries are readable and five hundred are not.

**The empty case is reported, not omitted.** A report that mentions gaps only when there are some
makes their absence unreadable — an operator cannot tell "nothing was dropped" from "this build does
not check". It is also what would let the new test pass while every real run reported nothing.

**Rejected: making `complete` false when speech was dropped.** `complete` means every stage ran, and
the CLI's exit code follows it, so redefining it would change what automation reads from a stage-level
fact to a content-level one — and it would conflate "a stage did not run" with "some speech could not
be aligned". Whether a run that drops speech should also *fail* is a product decision about exit-code
semantics, not a reporting fix, so it is named here rather than taken. The number is now in the report
either way.

**Mutation audit 5/5**, with a no-op control that stayed green: the gaps never reaching the run
CAUGHT, the total hardcoded to zero CAUGHT, the reason emitted empty CAUGHT, and the duration negated
CAUGHT.
`evidence/the-report-did-not-say-what-the-transcript-omits.md`.

## D-146 - Successful stages report themselves

**A stage that ran reported nothing about itself.** `pipeline.py`'s docstring says "every stage
yields either a result or a `StageSkipped` that names its blocker", and `discovery` and `editorial`
are typed `StageSkipped | None` — so **`None` was how success was written**. Measured on the real
38-minute run:

```
discovery   : None        <- Stage 3 ran
candidates  : 7           <- and produced seven merged candidates
skipped list: editorial, boundary, render, delivery   <- discovery is not there either
```

A reader checking `report["discovery"]` got `null` whether Stage 3 produced seven candidates or was
never attempted, and had to cross-reference another key to tell which. The module's own §1 is "fail
visible, not silent"; a stage saying nothing about itself is the silent case, and it is the same shape
as D-100 and D-110 — the fact existed, the field a human reads did not carry it.

**Decision: derive the positive record from the evidence, not from a second flag.**
`_discovery_ran()` reports `{"skipped": false, "stage": "discovery", "candidates": N, "by_path": …}`
computed from the candidates themselves. A separate "it ran" boolean could disagree with the
candidates; a count taken from them cannot. The per-path split is included because §8.2 partitions on
`discovery_path`, and a reader deciding whether the dual-path cost was justified needs the split
rather than a bare "ran".

**An explicit refusal still wins.** `encode(self.discovery) or self._discovery_ran()` puts the
`StageSkipped` first, so a named blocker is never overwritten by an inferred success — one of the two
controls covers exactly that.

**`None` is kept for "nothing is known".** A run object that never reached Stage 3 must not claim it
ran; the other control asserts that, and it is the mutation that would otherwise pass — claiming a
positive record unconditionally satisfies the main test and lies in the other direction.

**Rejected: giving discovery a result object like `visual_index` has.** That is the tidier shape and a
larger change: Stage 3's output *is* `candidates`, so a parallel result type would duplicate it and
create a second thing to keep in sync. The reporting layer is where the ambiguity was.

**Mutation audit 5/5:** reporting `null` again CAUGHT, claiming a record when nothing ran CAUGHT (by
the control alone), emptying the per-path split CAUGHT, hardcoding the count CAUGHT, and dropping
`editorial`'s guard CAUGHT (4 — it would raise on a run with no clip).
`evidence/a-stage-that-ran-reported-nothing.md`.

## D-147 - Render-duration wiring needs an integration test

**M3.4's shipped-clip guard was tested; that it is *called with the measurement* was not.**
Adversarial pass #8 attacked the row whose own history is "`RenderResult.duration_ms` was the request
echoed back and the file was never opened". Four of six mechanisms held. Two did not:

```
RED    the measured duration is the request echoed back (the original defect)
RED    the shipped-clip guard never fires
RED    the tolerance widens to ten frames
RED    the file is never opened at all
GREEN  one frame is assumed to be 40 ms for every source          <- UNPROTECTED
GREEN  the guard compares the request against itself              <- UNPROTECTED
```

**The wiring.** Replacing the call site with `assert_encoded_span(duration_ms, duration_ms, …)` — the
guard comparing the request against itself — left the whole suite green. `assert_encoded_span` is
unit-tested with real measured numbers, but it is only ever reached through `render_clip`, and
truncation by a short source is prevented upstream by the pre-flight check, so nothing drove it. Third
time this shape has appeared: D-105 and D-108 were both "the function is tested, the trip to it is
not".

**`frame_duration_ms` returning a constant 40 also survived**, and its own docstring is the claim it
breaks: *"Not a constant: the fixture here is 25 fps (40 ms), a 30 fps source is 33 ms … 'too loose' is
the direction that ships a truncated clip."* Every fixture in the suite is 25 fps, where 40 is
**correct** — the fixture-satisfies-the-rule blindness of D-086, D-088 and D-101.

**Decision: drive the guard through `render_clip`, and generate a source whose frame is not 40 ms.**
The wiring test replaces the *output's* measurement rather than the encode, because the guard's own
arithmetic is already covered by unit tests with real numbers; what was missing was proof that
`render_clip` hands it the measured value. A control asserts an exact measurement still renders, so a
wiring that refused everything would not pass.

**A first attempt that was wrong, and what it taught.** Patching `probe_duration_ms` wholesale tripped
the **pre-flight** refusal instead — that check probes the *source* with the same helper, and it is
wired and tested, which the failure proved by firing. The patch is now keyed to the output file's name.

For the frame rate, a 30 fps source is generated with ffmpeg so the constant and the measurement differ:
33 ms against 40. The 25 fps fixture is asserted at 40 in the same test, so the pair pins both.

**Mutation audit 6/6** after the fix, each survivor caught by exactly the test written for it.
`evidence/adversarial-pass-8-2026-08-09.md`.

## D-148 - Tests must not aim credential writes at source

**A test aimed a real credential writer at its own source file, and an audit deleted 262 lines with
it.** `test_writing_to_a_tracked_path_is_refused` passed `Path(__file__)` as the target, on the sound
reasoning that the test file is certainly committed. That made `assert_ignored_by_git` — the thing
under test — the only barrier between the suite and its own source.

While sweeping for untested call sites, that guard was neutered for one run. The test then did what it
was asking the guard to prevent: it wrote a credentials dump over `tests/test_credentials.py`, leaving
eleven `KEY=VALUE` fragments scavenged from the module it had just destroyed, including
`GEMINI_API_KEY=…` and the header "hawedit credentials. Git-ignored. Never commit this file." Restored
from HEAD; nothing reached a commit.

**Decision: the target is a path that does not exist and is not ignored.** `git check-ignore` answers
from `.gitignore` patterns rather than from the filesystem, so a non-existent path exercises exactly
the same refusal. If the guard ever fails open, the worst case is one stray file instead of a deleted
test. Measured with the guard neutered by line number:

```
the guard fails open                     : test FAILS (caught)
test source still intact (280 lines)     : yes      (before: 262 lines -> 11)
damage                                   : one 109-byte stray file
```

Two assertions bracket the call — the probe must not exist before, and must not exist after — so a
refusal that happened *after* the write would also be caught.

**Rejected: asserting the probe is not gitignored inside the test.** `.gitignore` has `.env` and
`.env.*`, neither of which matches the probe (verified: `check-ignore` exits 1). If a future pattern
did match, `pytest.raises` would report DID NOT RAISE — loud, not silent — so a subprocess call to
pre-empt a hypothetical is not worth its weight.

**The sweep that caused this also found nothing.** Its purpose was to hunt the D-105/D-108/D-112
pattern — a guard whose single call site can be neutered with the suite green. Corrected result:
**15 of 15 call sites CAUGHT, 0 unprotected.** The pattern is not systemic; those three were found by
hand and fixed.

**The first run of that sweep reported 9 unprotected, and every one was false.** It judged pytest by
`re.search(r"^FAILED |failed", stdout)` instead of the process exit code. Verifying one result by hand
— `assert_tools_are_from_this_environment`, which is D-093's own claim — showed it fails three tests,
so the instrument was wrong, not the code. That is the same error as reading a CI run's step text
instead of its `conclusion` field, made a second time; the sweep now raises on any exit code that is
neither 0 nor 1.

**A second instrument error in the same iteration:** the first attempt to neuter the guard replaced
`if result.returncode != 0:` by text, and that line occurs **twice** in `credentials.py` — the replace
hit line 105, not the guard at 169, so the "proof" measured nothing and reported a pass. Mutating by
line number fixed it. Both errors were caught by checking the result rather than trusting it, which is
the only reason this entry is not a false claim.
`evidence/a-test-that-could-delete-itself.md`.

## D-149 - A fetched ffmpeg is a receipted generation, not two copied files

The archive source was already immutable: an exact upstream commit and the Git-LFS object SHA-256.
The local installation was not. `curl` and `unzip` wrote predictable shared paths, ffmpeg and
ffprobe were copied independently into their final names, and any executable `ffmpeg` caused the
download branch to be skipped even when that executable failed the RTL verification immediately
afterward. An interrupted or corrupt install was therefore a permanent manual-repair state.

**Decision:** the Linux fetch runs under an owner-controlled `.ffmpeg` root and a no-truncate,
single-link kernel lock whose descriptor is path-bound through `/proc`. It therefore releases after
process death without a stale-lock guess. The fetch downloads and extracts into an unpredictable
mode-0700 attempt, authenticates the archive
before extraction, requires exactly one ffmpeg/ffprobe pair, and verifies both before publication.
The pair moves into a unique generation with its own `SHA256SUMS`. Exact four-line launchers address
that generation; ffprobe is published first and ffmpeg last, so the path consumers discover is the
commit marker. `current-generation`, both launchers, both binary hashes, and the RTL capability are
revalidated on every reuse. A mismatch is repaired through a new private generation.

**Trust boundary:** an explicit `HAWEDIT_FFMPEG`, a Windows-local `ffmpeg.exe`, or a PATH build remains
an operator-supplied executable. The script verifies its libass/HarfBuzz/FriBidi capability and does
not mislabel it as content authenticated by HawEdit. Same-account mutation after a successful check
is outside the provisioning threat boundary; a later setup invocation detects it for fetched bytes.
GPL redistribution review remains required before bundling the external executable (D-021).

Executable tests drive the real shell transaction with controlled curl/unzip programs. They prove
repair of a corrupt executable, refusal before publication, re-download after a byte mutation that
preserves behavior, hardlink-victim preservation, linked/non-directory root refusal, private curl
output, cleanup, and lock exclusion. `evidence/ffmpeg-provisioning-transaction.md`.

## D-150 - FFmpeg remediation must survive installation of the wheel

The runtime could locate an operator-installed FFmpeg, and the checkout could provision the pinned
Linux build, but an installed wheel exposed neither the provisioner nor an executable setup command.
Its error messages told an installed operator to run `scripts/fetch-ffmpeg.sh`, a path the wheel did
not contain. A released application therefore knew that FFmpeg was missing but could not perform the
remediation it prescribed.

**Decision:** the wheel ships `scripts/fetch-ffmpeg.sh` as an authenticated data-file member and
exposes `hawedit-ffmpeg-setup`. Installed data is located through the authoritative HawEdit
distribution RECORD, not `sys.prefix` guessing. The command first validates an existing
FFmpeg/FFprobe pair and the required libass/HarfBuzz/FriBidi stack. On Linux, absence invokes the
same pinned, transactional provisioner into an absolute per-user cache, then rechecks the result.
On Windows and macOS it does not download an incompatible Linux artifact; it returns bounded
`winget`/Homebrew remediation and `--check` remains non-mutating everywhere. Source checkouts keep
their local `.ffmpeg` generation, while runtime discovery also recognizes the installed per-user
generation before falling back to `PATH`.

The release validator now requires the provisioner member and the no-checkout installed-wheel smoke
authenticates it, runs `hawedit-ffmpeg-setup --help`, and exercises `--check`. A fresh Windows wheel
environment passed its packaged hash lock, `pip check`, RECORD-authenticated script lookup, and the
real RTL probe. Linux automatic download remains exercised by the required gate and executable shell
transaction tests. This packages remediation; it does not redistribute FFmpeg or claim its GPL
review complete. `evidence/installed-ffmpeg-provisioning.md`.

## D-151 - SRT and ASS use the same word-aligned RTL breaks

`build_ass` applied §4.3.5's explicit word-aligned wrapping while `build_srt` emitted each sentence
as one line, leaving playback software to choose breaks without the word alignment. On the real
38-minute transcript, 149 of 182 clip-eligible sentences exceeded the recorded 32-character width;
the median needed four lines and the widest needed 33.

**Decision:** SRT uses the same `wrap_caption_lines` function and recorded width as ASS. A separate
SRT width would be an unmeasured threshold, and a two-line cap would require inventing an overflow
policy. Tests pin both formats to each other, exercise word rather than character splitting, and
distinguish in-cue line breaks from blank lines that create new cues. The FFmpeg round-trip is an
independent reader for preserved line breaks, but it does not enforce the blank-line grammar; the
cue parser test carries that obligation. `evidence/the-srt-let-the-player-choose-the-break-points.md`.

## D-152 - Every CLI configures UTF-8 before its first write

Redirected Python streams on the production Windows host use cp1252. A completed 38-minute pipeline
run therefore raised `UnicodeEncodeError` while emitting its Sorani JSON and left a zero-byte report;
characters that cp1252 could represent were silently written as non-UTF-8 bytes, while stderr used
backslash escapes. Console testing did not expose any of those paths.

**Decision:** `cli.use_utf8_streams()` is the first statement of every declared entry-point `main()`.
It changes only the encoding and preserves the stream error policy. The contract test reads the
entry points from `pyproject.toml`, forces cp1252, and asserts exact Sorani UTF-8 bytes on stdout and
stderr, so new commands enter the obligation automatically. Importing the library does not mutate
its caller's streams. `evidence/the-report-died-on-the-way-to-the-file.md`.

## D-153 - A rejection set needs one producer after the survivor is chosen

`RejectedCandidate` had validation and serialization, but no production site constructed it. The
runner selected one of seven real-run candidates and discarded the other six without a reason or
their discovery path, even though §5 calls that set the only measure of recall and §8.2 partitions
candidate recall by discovery path.

**Decision:** after selection settles, the runner chooses the survivor once and builds exactly one
rejection record for every other candidate. The reason reuses the same complete-sentence eligibility
and selected-span containment computations that make the decision; rank is the remaining reason.
Nothing is recorded when no decision chose a survivor. The serialized per-path split includes zero
for a path that found candidates but lost none, distinguishing that outcome from a path that never
ran. Stage 2 windows are not candidates and are excluded. `evidence/the-rejection-set-had-no-producer.md`.

## D-154 - Path B has no implicit whole-episode query

The real 38-minute run had no Path A candidate because Gemini was not configured. `run_pipeline`
then silently used the entire normalized transcript as Path B's query: 35,185 characters and 6,104
words. The reranker tried to allocate 40.89 GiB on a 23.99 GiB GPU before Stage 3 produced a single
candidate. This was not a model-capacity limit: it was an unbounded query invented by composition.

**Decision:** a visual retrieval query has exactly two authorized sources. An explicit
`--visual-query` is normalized and used as supplied, or the top Path A candidate contributes only
the aligned words inside its own time span. If neither source exists, the composer is not called and
`visual_index` reports a `StageSkipped` that names the missing authority and the measured OOM. The
serialized run records `visual_query_source` as `explicit`, `path_a:<candidate-id>`, or `null`, while
`VisualDiscoveryResult` continues to record the query bytes themselves.

The CLI rejects `--visual` without either an explicit query or a configured Path A route before it
constructs any GPU adapter. The library remains more general: an injected Path A producer may fail
at runtime, in which case both that failure and Path B's bounded-query refusal are returned in one
structured report. No character/token ceiling was guessed; an explicitly authorized oversized
query reaches the existing bounded adapter failure path, while the dangerous *implicit* whole-media
fallback is gone. The independent model-boundary sweep measured 200–8,000 characters fitting,
16,000 OOMing, and the real 35,185 characters/26,191 tokens reproducing the exact 40.89 GiB
allocation. Its five query/refusal mutations were all caught. Full measurements remain in
`evidence/adversarial-pass-9-2026-08-09.md`; the composed contract and provenance are in
`evidence/the-whole-transcript-was-a-visual-query.md`.

## D-155 - An operational Stage 0 refusal is still a pipeline run

The module contract says every stage yields either a result or a `StageSkipped`, but Stage 0 ran
before `PipelineRun` was constructed. An unavailable/denied FFmpeg process, unreadable media, or
other expected ingest `OSError` therefore escaped through `main`, made `--json` write no JSON, and
exited as a command/configuration error. Every model stage already preserved the same class of
operational failure in the report.

**Decision:** `run_pipeline` normalizes only `IngestError` and `OSError` at the ingest boundary. The
returned report contains Stage 0's bounded concrete failure plus an explicit skip for each of its
eight downstream dependants, all naming `Stage 0 ingest` as the root blocker. Missing source,
invalid media identity, transcript/schema errors, and programmer assertions remain exceptions;
this is not a broad catch. The CLI now exits 1 and emits valid JSON for an operational Stage 0
refusal, while static invocation errors retain exit 2. `evidence/stage-0-failure-reporting.md`.

## D-156 - One unreadable Path B survivor does not erase the readable survivors

The bounded real 38-minute Path B run planned and embedded 641 windows, retrieved 50 and kept seven,
then returned zero candidates because the first VideoChat3 survivor produced a time range where the
six-dimension schema requires one point. The refusal was correct; `read_scenes` aborting the other
six readings was not. Twelve cached real windows showed 72/72 parseable dimensions and 12/12 point
timestamps, so widening the parser would have guessed how to collapse an exceptional range.

**Decision:** `VideoChat3Reader` records each refused window as `UnreadableScene` and continues.
`SceneReadings`, `PathBDiscovery` and `VisualDiscoveryResult` carry those gaps into the run report,
including an explicit empty list for a clean run. Path B still refuses when no scene is readable.
The composer's exactness invariant is not weakened: candidate IDs union unreadable IDs must equal
the reranked survivor IDs, so the model cannot silently omit or invent a window. Reader cleanup
still runs after the complete survivor phase and cannot mask the primary failure. Eight mutations
are caught, including a direct trip through the real reader method.
`evidence/one-window-discarded-every-candidate.md`.

## D-119

**`--json` wrote a report no parser could read, because the runner shares stdout with every library
it loads.** Found while taking the first end-to-end composed run on the real 38-minute file: the run
succeeded, the report was complete, and `json.loads` on the captured file raised at character 0.

```
python -m hawedit.pipeline ZAR38MinTest.mp4 … --visual --auto-select --json > report.json

report.json                    1,140,793 bytes
bytes before the JSON begins         580
lines of foreign output                2
  🚨 `image_grid_thw` is part of VideoChat3ForConditionalGeneration.forward's signature, …
  🚨 `video_grid_thw` is part of VideoChat3ForConditionalGeneration.forward's signature, …
json.loads(whole file)         JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

The source is `transformers/utils/auto_docstring.py:1602` — `print("\n".join(undocumented_parameters))`,
a **bare print, not a logger**, so no `TRANSFORMERS_VERBOSITY` setting reaches it. Loading
VideoChat3's remote code fires it twice.

**The defect is ours.** A pinned dependency printing to stdout is a fact of the ecosystem; owning
the channel a documented contract writes to is this program's job. D-115 fixed what *encoding*
stdout uses; this is who is allowed to *write* to it.

**Decision: in document mode the report owns stdout and everything else goes to stderr.**
`cli.machine_readable_stdout()` yields the real stdout and redirects the ambient one to stderr for
the duration, so the pipeline's own prints and any dependency's land where a human reads them and no
parser is looking. `main` splits into a four-line front and `_run_from_args(args, report_stream)`, so
the body keeps its indentation and the report writes to the stream it was handed rather than to
whatever `print` resolves to.

**Applied at both sites, not just the one that failed.** `editorial_bench` prints its report to
stdout under the same exposure and loads the same stack.

**Rejected: silencing the dependency.** There is no handle — it is a `print`. Monkeypatching
`transformers.utils.auto_docstring` would be reaching into a pinned package's internals to protect
our own contract, and the next noisy dependency would need the same patch.

**Rejected: writing the report to a file instead.** `--json` on stdout is the contract, pipes are the
point of it, and moving it to `--json-out PATH` would break every caller to work around a problem
that has a one-line fix at the right layer.

**Rejected: stripping non-JSON from the output.** That is parsing the corruption instead of
preventing it, and a dependency that printed a `{` would defeat it.

**Coverage is split, and the reason is worth naming.** The pipeline's channel is checked on the
**artifact**: the real `main` runs in a subprocess with `run_pipeline` wrapped to print to stdout
mid-run, and the test parses what came out. `editorial_bench`'s cannot be — reaching its document
needs a valid manifest of real reviewed comparisons against real media (`BLOCKED.md` #1, M7.2) — so a
source-level invariant covers it: no `print` of a JSON payload in `src/hawedit` may omit `file=`. That
also covers the site added next year, which an artifact test for one command would not.

**Mutation audit 6/6** against a baseline verified green first: the report sharing stdout again
CAUGHT, the helper handing back the redirected stream CAUGHT, the helper not redirecting CAUGHT, the
human report redirected too CAUGHT (the control — the readable mode is what anyone runs by hand),
holding stdout swallowing the exit code CAUGHT (the second control), and `editorial_bench` printing to
the shared stream CAUGHT.
`evidence/the-report-shared-stdout-with-a-library.md`.

## D-120

**The wheel build was not reproducible, so the one artifact that leaves this repository could not be
identified at all.** `AUDIT_REPORT.md` recorded that as a deliberate omission — it quotes a byte count
and no SHA-256 — and the reason it gave was correct. Reproduced today:

```
two `pip wheel --no-deps` runs, one unchanged tree
  build 1  333,362 bytes  sha256 a7c3b2f1c280aff4…
  build 2  333,362 bytes  sha256 38d1d2475c46e120…
```

Same size, different bytes: nothing sets `SOURCE_DATE_EPOCH`, so every ZIP entry carries the mtime of
the instant it was written. "Pinned and checksummed supply chain" cannot hold when the thing being
checksummed changes between two builds of one commit.

```
with SOURCE_DATE_EPOCH taken from the commit
  build 3  333,362 bytes  sha256 c450f9310d956e90dcd4f9c711efd04aa6e1adfacd690d630c9d34988ed4fec2
  build 4  333,362 bytes  sha256 c450f9310d956e90dcd4f9c711efd04aa6e1adfacd690d630c9d34988ed4fec2
```

**Decision: `scripts/build-wheel.sh`, with the epoch taken from the commit's own author date.**
`git log -1 --format=%ct` — derived from the tree being built, so the same commit yields the same
bytes on any machine on any day. It prints the digest, which is the number that previously could not
be quoted.

**Rejected: `SOURCE_DATE_EPOCH` from the current time, or from a fixed constant.** `now` restores the
defect silently. A constant would be a number chosen rather than measured, and it would make two
different commits produce wheels stamped identically — the pin would then say nothing about which
code is inside.

**Outside a git checkout it refuses.** There is no commit to derive the epoch from, and substituting
`now` there is the one behaviour this script exists to remove. Named in the evidence as untested: the
script resolves the repository from its own location, so reaching that branch means copying the tree
out of git, which costs more than three fail-closed lines are worth.

**Rejected: quoting the digest in `AUDIT_REPORT.md`.** It is per-commit by construction — the epoch is
the commit's date — so an inlined hash would be stale on the next commit and would read as a claim
about the code rather than about one build of it. The document now says how to compute it instead.

**The control is the mechanism, not the equality.** Two builds matching is also what a build system
that happened to be deterministic today would produce, so equality alone would let the epoch be
deleted unnoticed — and a control asserting *"setuptools is non-deterministic"* would break the day
that stopped being true, which is a check whose cheapest fix is deleting it. The test asserts instead
that **every ZIP entry is stamped with the commit's timestamp in UTC**, which is false the moment the
epoch stops being set.

**Three statements in `AUDIT_REPORT.md`'s supply-chain section were stale, and one contradicted
another in the same document.** Measured against the code:

```
revisions.json pinned repositories        6   (the report says "all five")
registry entries with a download source   6
unpinned among them                       0   (the report says pyannote is "deliberately unpinned"
                                               and that "a test asserts it is the only one")
```

`tests/test_models.py` asserts `unpinned == []` with no exemptions, and its own comment records that
D-075 removed the pyannote one. And line 101 called the model revisions "unpinned" while line 66 of
the same file called them pinned. Corrected in place.

**Mutation audit 4/4** — and the first push was **red on CI while the local gate was green**, which
is the divergence the loop's own rule about the gate of record exists for. The test compared the ZIP
stamps against the raw epoch, and `450684b` happened to carry an even timestamp; ZIP stores the second
as `sec // 2`, so the runner's odd-second commit failed by exactly one second. The expectation rounds
down now — the value the format can represent, not a tolerance — and HEAD here is odd, so the fix is
verified against the parity that failed rather than the one that passed.
`evidence/two-builds-of-one-commit.md`.

## D-157 - Reproducible bytes must still identify HawEdit

The release command proved that two builds emitted the same bytes, but it never proved which
distribution those bytes claimed to be. A real HawEdit wheel reconstructed with METADATA
`Name: hawedit-impostor`, `Version: 9.9.9` and a matching wrong filename still passed
`_validate_hawedit_wheel`. It could therefore receive HawEdit gate provenance and a GitHub OIDC
attestation even though the attested artifact identity was not the project identity authorized by
the gated source.

**Decision:** publication requires one identity across three independent representations. The
archived `pyproject.toml` supplies the authorized project name/version, the wheel must contain
exactly one METADATA record, and the PEP 427 filename must encode the same normalized distribution
name and exact version. The check runs on the immutable first source export before any release
directory is created. Schema-5 provenance records the measured distribution and version.

The privileged attestation job does not trust that repository-code check. On its fresh no-checkout
runner it opens the transported wheel with the standard library, requires exactly one METADATA,
requires normalized distribution `hawedit`, checks filename/METADATA identity, and requires the
same fields in schema-5 provenance before granting OIDC attestation authority. Tests mutate source,
METADATA and filename name/version independently and pin the workflow-side verifier. This closes
artifact-identity substitution; it does not invent the still-missing version/tag policy or durable
GitHub Release. `evidence/release-identity-binding.md`.

## D-121

**The one archive this project downloads, marks executable and runs was fetched from a branch and
never verified — and two of the three places that describe it called it "pinned".** `AUDIT_REPORT.md`
was the only one that said otherwise, and the audit was right.

```
scripts/fetch-ffmpeg.sh, before
  url=…/zackees/ffmpeg_bins/main/v8.0/linux.zip     <- a branch: mutable bytes, fixed-looking name
  curl -sSL -o linux.zip "$url"                     <- no --fail: an error page becomes the archive
  unzip … && chmod +x … && "${dest}/ffmpeg" -version <- executed, never compared to anything

README.md:255                "fetches the pinned ffmpeg"          false
.github/workflows/gate.yml   "fetch the pinned ffmpeg", and
                             "fetch-ffmpeg.sh pins the URL."      false
AUDIT_REPORT.md              "`fetch-ffmpeg.sh` is still unpinned" true
```

Measured, 2026-08-09, before changing anything:

```
zackees/ffmpeg_bins main            df95abcb0ce6efff710dda5ef28a2f6f1dc21493 (2026-01-16)
…/main/v8.0/linux.zip               HTTP 200, Content-Length 142,008,975
…/df95abcb…/v8.0/linux.zip          HTTP 200, Content-Length 142,008,975
```

So the Git-LFS media endpoint **does** serve a commit ref, which is what makes the fix possible.
Both were downloaded in full and hashed:

```
linux-pinned.zip  142,008,975 bytes  ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad
linux-main.zip    142,008,975 bytes  ca75b05e887c7a97676632f673031875847be83daa9794298fed9cef8cac14ad
byte-identical today: True
```

**Decision: pin the URL to that commit, record that digest, and compare before anything is
unpacked.** The pin removes the mutability at the source; the digest catches the case a pin cannot —
the same ref serving different bytes. `curl --fail` so an HTTP error page is not mistaken for an
archive. The order is the point: verify, *then* unzip, *then* `chmod +x`.

**The digest is ours, and that is stated rather than hidden.** `AUDIT_REPORT.md` said no published
digest for the archive had been found to compare against, which was true and still is. This one was
measured here, twice, from two URLs. It attests "these are the bytes hawapc01 and CI have been
running", not "upstream says these are the bytes" — a weaker claim than a publisher's signature and a
much stronger one than none.

**`scripts/verify-sha256.sh` is its own script for one reason:** the branch it exists for must never
be reached in normal operation, so it has to be reachable from a test. The archive is 142 MB and no
test will download it to prove a mismatch is refused; three bytes give both answers.

**Rejected: `curl … | sha256sum -c -`.** Piping the download through a check still writes the bytes
before the verdict, and the exit status of a pipeline is easy to lose. The file lands, is compared,
and only then is opened.

**Rejected: leaving the digest out and pinning only the ref.** A commit ref is a promise by the
host; the digest is a fact about the bytes. §7's weights get both (`models/revisions.json` plus the
Hub's own content addressing) and the artifact invariant #1 protects gets a SHA-256 sidecar — the
thing that gets *executed* should not get less.

**Rejected: refusing when `sha256sum` is missing is not a fallback.** It exits 2 rather than
proceeding: computing no digest and continuing is the exact state this replaces.

**The download path cannot be exercised on this machine.** The archive is Linux-only and hawapc01 has
a conforming ffmpeg on `PATH`, so `fetch-ffmpeg.sh` short-circuits before the download — measured, it
reports the Gyan 8.1.1 build and exits. CI is the end-to-end proof and runs it on every push, which
is the gate of record doing its job rather than a gap. What was checked here: the recorded digest
against both real 142 MB archives, through the real script.

The readiness branch already had a stronger transactional installer when this decision arrived.
Integration retained that design: one owner-controlled root and kernel lock, a private attempt
directory, verification before unzip, staged RTL probes, an immutable content-addressed generation,
and final launcher/receipt revalidation. The standalone digest helper is now the check used on that
private staged archive, so its three-byte mismatch tests exercise the same boundary as provisioning.

**Mutation audit 7/7** — and the first run was **6/7**. The survivor was `curl --fail` removed: the
test asserted `"--fail" in fetch-ffmpeg.sh`, and the script *explains* `--fail` in a comment. Same
error as the ordering test one function above it, which had already been caught the same way minutes
earlier. Both read code lines now.
`evidence/an-archive-fetched-from-a-branch-and-never-checked.md`.

## D-122

**Adversarial pass #10 took M1.5 — §3 Stage 1's escalation rule, DONE and never attacked — and
eight of eleven mechanisms held. All three survivors were in `materially_disagree`.**

Chosen because it was the shortest DONE cell in the ledger (252 characters) on one of the rule
§3 states most precisely, and because fifteen DONE rows have never been attacked at all.

What held: the bottom quartile is `len(scores) // 4` and not half; it is the *lowest* log-probs
and not the highest; either signal escalates rather than both; **both of §3's prohibitions** —
duration and word count — are refused; disagreement is measured after §4.1 normalization; a
positive `mean_logprob` is refused at construction; and the disagreement signal is actually
consulted. The row's claims are accurate: `duration_s` really is read by no code path in that
module, and D-015 really does record 0.15.

```
CAUGHT  half the batch escalated instead of the bottom quartile
CAUGHT  the TOP quartile by confidence escalated
CAUGHT  escalation needing BOTH signals instead of either
CAUGHT  duration escalates a segment (§3's prohibition)
CAUGHT  word count escalates a segment (§3's prohibition)
CAUGHT  disagreement measured on raw text, not normalized
MISSED  the CER reference and hypothesis swapped
MISSED  the threshold becomes exclusive at the boundary
MISSED  one model producing nothing reads as agreement
CAUGHT  a positive mean_logprob accepted
CAUGHT  the disagreement signal never consulted

8/11
```

**Survivor 1 — the reference and the hypothesis are interchangeable.** Normalized CER divides by
the *reference* length, so it is asymmetric, and §3 Stage 1 makes LLM-7B the canonical transcript
with CTC-3B supplying posteriors. Measured on a pair that straddles the threshold in one direction
only:

```
llm "ڕۆژنامەوانی کور"  (15 normalized chars)
ctc "ڕۆژنامەوانی ک"    (13)
  cer(llm, ctc) = 0.1333  -> agreement      (as written)
  cer(ctc, llm) = 0.1538  -> disagreement   (arguments swapped)
```

Two earlier pairs I tried escalated either way — 0.5926/1.4545 and 4.0/0.8 — which is why the
fixture is a length relationship rather than a sentence: without a straddling pair the test would
have passed for both orders and measured nothing.

**Survivor 2 — the boundary.** The comparison is `>=` and nothing pinned it. Every other test here
passes `DEFAULT_DISAGREEMENT_CER` itself or a value far from it, so the operator was free to move —
D-098's shape exactly, where every pause test took the constant and 500→800 left 1,170 tests green.
Pinned at a measured pair sitting on it: 20 normalized characters, three edits, **cer == 0.15**.

**Survivor 3 — a silent model reads as agreement.** The module calls one model producing nothing
"the strongest disagreement available", and making it return `False` was free. This is the case the
validator exists for: a CTC pass that yields empty text where the LLM transcribed speech. Now
pinned in both directions, with a control that *both* silent is agreement — returning `True`
whenever either side is empty would satisfy the positive assertions and route every silent segment
to a 4 GiB model. And a fourth test drives it through `select_for_validation`, because the predicate
being right is not the same as the decision acting on it (D-105/D-108/D-112/D-118).

**Mutation audit 11/11 after the fix.**

**What the pass did not change, deliberately: M1.5 stays DONE.** Its Definition of Done is the rule,
and the rule is complete, faithful to §3's wording, and now fully pinned. That nothing calls it is
real — `select_for_validation` still has no caller in `src/`, because `ctc_text` is never computed
(the CTC pass yields emissions for alignment and nothing decodes them) — but that is M1.4's named
shortfall and it is recorded there, not a false DONE here. Moving it would put the same fact in two
cells and make the tally disagree with itself. The M1.5 cell now says so explicitly instead of
leaving a reader to find it under another row.
`evidence/adversarial-pass-10-2026-08-09.md`.

## D-123

**CI went red on a 142 MB download, and nothing about the code was wrong.**

```
==> downloading ffmpeg (~140 MB) from https://media.githubusercontent.com/media/…
curl: (92) HTTP/2 stream 1 was not closed cleanly: PROTOCOL_ERROR (err 1)
##[error]Process completed with exit code 92
```

100 seconds into the transfer, on the same pinned URL that had completed in **2 seconds** one run
earlier (`bba56a9`). Not `--fail`'s doing: exit 92 is a transport error, not an HTTP status, and
plain `curl` returns it either way. The defect is that the gate of record turned on a single
attempt at 142 MB.

**Decision: `--retry 3 --retry-delay 2 --retry-all-errors`.** `--retry` alone covers timeouts and
5xx and treats a transport error as final, which is exactly the class that failed. Both curls in
play are 8.x, so the flag is available.

**Retrying is only safe because D-121 landed first.** A retried or partially-resumed download is
compared against the recorded digest before it is unzipped or made executable, so the failure mode
retries introduce — a truncated file that looks complete — is the one thing already refused.

**Rejected: a bash retry loop.** It would be version-independent, and it would also reimplement
backoff, partial-file cleanup and error classification that curl already has and that nothing here
would exercise.

**Rejected: caching the archive in CI.** It would hide exactly this: the point of fetching on every
run is that the pinned URL and the digest are checked on every run.

**2/2 mutations:** dropping the retry CAUGHT, and `--retry` without `--retry-all-errors` CAUGHT —
the second matters because it is the plausible half-fix that looks right and does not cover exit 92.

## D-124

**Adversarial pass #11 took M2.5 — §3 Stage 3's dual-path merge, DONE and never attacked — and six
of ten mechanisms held. Three survivors, and every one was a fixture that could not tell the two
behaviours apart.**

§3 calls this "the most important structural decision in the system", and §8.2 spends its output on
the per-path recall that decides whether Path B is worth its cost.

```
CAUGHT  Path B's unmatched candidates dropped (intersect, not union)
CAUGHT  the merged span becomes the union, not the anchor's
CAUGHT  one visual candidate corroborates every overlapping verbal one
MISSED  rank no longer decides who claims a contested visual candidate
CAUGHT  a path dedupes itself: verbal candidates can claim each other
MISSED  the output order depends on input order
CAUGHT  candidates from different media can merge
CAUGHT  an unmeasured visual score becomes 0.0 instead of None
CAUGHT  the visual path's SV6D is dropped on the merged candidate
MISSED  §8.2's rank becomes the worse of the two paths, not the better

6/10
```

**Survivor 1 — rank versus id.** `test_a_visual_candidate_is_claimed_by_exactly_one_verbal_candidate`
asserts *"the lower-ranked verbal candidate should claim it"* and cannot see rank at all: its fixture
is `v1` at rank 1 and `v2` at rank 2, so alphabetical order and rank order agree, and
`sorted(verbal, key=lambda c: c.candidate_id)` passes. The new test makes them **disagree** — `v2` is
rank 1 — so the claim goes to `v2` while `v1` sorts first. D-086/D-088/D-101's shape again: the
fixture happens to satisfy the rule.

**Survivor 2 — the promised output order.** The docstring promises "(media, then start, then id)" and
`test_the_order_of_the_output_does_not_depend_on_the_order_of_the_input` shuffles the inputs 20 times
against a reference — but every visual in that fixture is claimed, so there are no leftovers, and the
merge's *internal* order (anchors in rank order) is already deterministic. Deleting the final sort
left it green. The new test uses a visual-only candidate that **starts before** the first verbal
anchor: leftovers are appended after the anchors, so without the sort it comes out last, and the
contract says first.

**Survivor 3 — which rank §8.2 scores against.** `to_retrieved` takes the `min` of the two paths'
ranks, with a docstring explaining why: *"a moment Path B ranked 2nd was available at position 2
whatever Path A thought of it."* `max` passed, because the one test that exercises it scores at
`k=20`, where 2 and 9 are indistinguishable. Now pinned at verbal 9 / visual 2 → rank 2, **with a
control** at verbal 2 / visual 7, because returning `verbal_rank` whenever it exists would satisfy
the first test by accident of which number is smaller.

**Mutation audit 10/10 after the fix.** One mutation had to be rewritten first: deleting
`del unclaimed[...]` emptied its `if` block and the module stopped importing, which the audit
reported as SKIPPED rather than counting — replaced by `pass`, it is CAUGHT.

**No production code changed.** Every survivor was a test that could not discriminate, not a wrong
behaviour: the merge does claim in rank order, does sort its output, and does take the better rank.
The row's claims are true; three of them were unheld.
`evidence/adversarial-pass-11-2026-08-09.md`.

## D-125

**Adversarial pass #12 took M3.5 — captions timed to the clip, DONE and never attacked — and every
one of its eight mechanisms held. The gap was where they are proved: not once through the function
the product calls.**

M3.5's cell calls its origin "the most serious defect found so far": `build_ass` wrote
source-absolute timestamps into a stream ffmpeg had already cut, and the result was a valid,
playable, entirely caption-free MP4 with **0 bytes** differing from an uncaptioned render.

```
CAUGHT  the ASS carries source-absolute timestamps again (the defect)
CAUGHT  a sentence starting before the clip is captioned anyway
CAUGHT  a sentence running past the end of the clip is captioned anyway
CAUGHT  an ASS with no Dialogue line at all is accepted
CAUGHT  an ASS whose captions all fall outside the clip is accepted
CAUGHT  full containment required instead of partial overlap
CAUGHT  the burn no longer checks the file it is handed
CAUGHT  libass wraps the captions instead of our own line breaks

8/8
```

**And then the measurement that matters.** Removing the `- clip_in_ms` shift and running only the
files that drive the real renderer:

```
tests/test_render.py + tests/test_pipeline.py     0 failures, exit 0
```

Every catcher is in `tests/test_caption_timing.py`, and its pixel proof builds the ffmpeg command by
hand. `render_clip` and `run_pipeline` never noticed.

**Why, and it is not a bug in those tests.** `test_render.py`'s `_write_ass` calls
`build_ass((_sentence(),))` with no offset, and `_sentence()` is 0..1600 **in clip time** — its
docstring says so. Handing a renderer an already-clip-relative caption file is exactly right for a
renderer test. The consequence is that the *composition* — §4.2's source-time sentences →
`build_ass(clip_in_ms=clip.in_ms)` → `render_clip` → pixels — is never assembled by any test that
uses the product's own encoder. And `run_pipeline`'s fixture clip starts at ~100 ms, where the
mistake still overlaps the window and libass draws something anyway.

That is the shape M3.5 was born from, one level up: the fix is proved where the offset is chosen by
the test, and the product path only ever sees offsets too small to matter.

**Decision: one test drives the whole composition through `render_clip` at 2000 ms, asserted on
decoded pixels, plus a control that the unshifted file is refused at the burn.**

**2000 ms is derived, not picked.** `_sentence()` is 1600 ms long, so an unshifted caption lands
*entirely* outside a clip starting at 2000 and `assert_captions_within_clip` can refuse it. At the
500 ms this file's existing clip uses, the same mistake still overlaps and draws — which is why 500
was never enough.

**The control is the refusal, not a second difference.** Without it the positive test passes for a
renderer that silently encodes a caption-free MP4, which is precisely what shipped before M3.5.

**Rejected: changing `_sentence()` to source time.** It is used by nine tests in that file as a
clip-relative caption line, which is what a renderer should be handed; rewriting it would churn
those and lose the distinction the new test exists to make.

**Rejected: asserting the ASS text instead of the pixels.** `test_caption_timing.py` already does
that, and it is the assertion that was green while the clip shipped bare.

Measured after: removing the shift now fails
`test_the_composed_path_burns_captions_into_a_clip_from_mid_media` in `test_render.py`. 8/8 held
before and after.
`evidence/adversarial-pass-12-2026-08-09.md`.

## D-126

**Adversarial pass #13 took M2.9 — Stage 4's request carrying real source pixels — and four of ten
mechanisms held. The worst result of any pass so far, on the one row whose artifact is a *billed*
request.**

The cell's measurements all reproduce exactly, to the millisecond:

```
extract_judge_frames(fixture, 0, 4162, count=6)
  frames             6
  timestamps (ms)    347 / 1040 / 1734 / 2428 / 3122 / 3815     (cell: identical)
  spacing (ms)       693 694 694 694 693
  sizes (bytes)      2624 … 3424                                 (cell: 2,624–3,424)
  every one FFD8     True        mime image/jpeg      distinct payloads 3
```

What did not reproduce is the protection. `tests/test_keyframes.py` is **27 lines and two tests** for
a module the cell credits with four refusals.

```
MISSED  frames are sampled from the start of the media, not the candidate
CAUGHT  every frame is stamped at the same moment
MISSED  a span with no duration is accepted
CAUGHT  a count outside 1..20 is accepted
MISSED  a missing ffmpeg returns no frames instead of refusing
MISSED  an ffmpeg failure returns no frames instead of refusing
MISSED  more frames than asked for are accepted
CAUGHT  JPEG bytes are declared as PNG
MISSED  a text-only judge is charged for keyframes anyway
CAUGHT  a multimodal judge is sent no frames at all

4/10
```

**The serious one: the timestamps are the request echoed back.** The existing test asserts
`[500, 1300, 2100, 2900, 3700]` for a span of `100..4100`, and those numbers are arithmetic over
`in_ms` and `out_ms` — `min(out_ms, round(in_ms + (index + 0.5) * step_ms))`. Replacing `-ss in_ms`
with `-ss 0` leaves every one of them unchanged. So the *bytes* a billed multimodal judge receives
could come from anywhere in the media while the request describes the candidate, and nothing noticed.
This is M3.4's lesson — `RenderResult.duration_ms` was the request echoed back and the file was never
opened — in the keyframe module, and the third pass in a row to find the proof one call away from the
product.

**The fix asserts on the pixels.** The fixture is three static shots, so each span has its own
picture — measured: `0..1400` → `46f2c52ce626999c` at 3,332 bytes, `1400..2800` → `51f35b218c7a4534`
at 2,624, `2800..4162` → `d700e83a931dfb52` at 3,424. Three spans must return three different images,
plus a control naming the substitution directly: the last shot's frame must differ from the first
shot's.

**The three unheld refusals are the three the cell states as verified.** "A span with `out_ms <=
in_ms`, a count outside 1..20, and a missing ffmpeg are each refused rather than returning an empty
tuple that would read as 'no frames here'" — only the count ceiling was tested, and not its floor.
`count=0` divides the span by nothing; a missing or failing ffmpeg returning `()` is indistinguishable
from a text-only request.

**The readiness branch already has the stronger D-107 boundary.** Every ffmpeg call owns a unique
private directory and enumerates only that call's files, so a re-run never sees an earlier run's
JPEGs. The adapted product-path test creates 8 frames and then requests 2 through the same caller
directory, requires exact counts for both, and proves the private namespaces are removed. A separate
hostile-stale-file regression proves caller-owned files never enter the result.

**The gate's other direction was free.** `getattr(judge, "requires_keyframes", False)` had a test for
`True` and none for absent — so making it unconditional passed, and a text-only model would be billed
for up to twenty inline images. §3 Stage 4's cost model counts them.

**Mutation audit 10/10 after.** No production code changed: every mechanism was already right, and
six of them were unheld.
`evidence/adversarial-pass-13-2026-08-09.md`.

## D-127

**Adversarial pass #14 took M1.6 — model provisioning, DONE and never attacked. Its code held 7/7.
Two of its claims were false, and this project's own commits are what made them false.**

```
CAUGHT  every component prints OK whatever its verdict
CAUGHT  every verdict is inverted
CAUGHT  a measured size of zero prints as unmeasured again
CAUGHT  the summary claims everything is available
CAUGHT  the summary counts something other than what it lists
CAUGHT  an unpinned repository resolves to a branch head instead of refusing
CAUGHT  a checkpoint whose loader is missing reports available

7/7
```

D-100's report fix survives intact, as does `revision_for`'s refusal and D-099's loader check.

**What was false, measured against the code:**

```
the cell: "pins all five downloaded repositories"
  revisions.json pins                        6
  registry entries with a download source    6
  unpinned among them                        0

the cell: pyannote is "deliberately unpinned … a test asserts it is the only one"
  pyannote pinned                            True   (D-075)
  tests/test_models.py asserts               unpinned == []   with no exemptions

the cell: "Still unpinned: fetch-ffmpeg.sh downloads a mutable main/ archive and executes
           it with no SHA-256 check"
  URL carries a 40-hex commit ref            True   (D-121)
  a 64-hex digest is recorded                True
  compared before the unzip                  True
```

**D-120 corrected the same two sentences in `AUDIT_REPORT.md` and did not look in the ledger.** That
is the failure this project keeps finding in itself — a correction landing in one document and not the
other — and it has now happened to me twice on one pair of facts.

**Decision: bind the factual half of both claims to the file it is about, in `tests/test_claims.py`.**
Reading found these; the gate did not, and reading is not a mechanism.

* Any live document stating *"all N download… repositories"* must state the number
  `models/revisions.json` actually pins. **Only the count** is checked — a number is a fact about
  that file, and binding anything looser would fail on an innocent rewording.
* No live document may describe *"mutable `main/` archive"* while the URL in `fetch-ffmpeg.sh`
  carries a commit. Keyed on the script's own URL line, and it **fails in both directions**: if the
  URL ever goes back to a branch, a document that stopped saying so is the thing that is wrong.

**`DECISIONS.md` is exempt by design.** It is append-only, and its older entries are supposed to say
what was true when they were written; a test that forced them current would be a test whose cheapest
fix is editing history.

**Rejected: a phrase list for "still unpinned".** I would be guessing which wordings a future writer
picks, and a list that misses one reads as a guarantee it does not give. The two facts chosen — a
count, and a substring of a URL — are checkable exactly.

**Both tests were verified to fail before the correction**, naming `PROGRESS.md` and the exact
sentences. A claims test that passes on the tree that motivated it measures nothing.

**The ffmpeg test's first version was wrong, and the correction exposed it.** It asserted that no
live document says *"mutable `main/` archive"* while the URL carries a commit — and it failed on the
very edit that retired the claim, because the convention here is to **quote** a wrong sentence while
correcting it. A grep cannot distinguish making a claim from retiring one. Rewritten to bind the
40-hex commit in `fetch-ffmpeg.sh` to its appearance in a live document: a reader can then verify the
pin without opening the script, a moved pin must be republished, and an unpinned archive fails the
other way. **3/3** on its own audit — the wrong count restored CAUGHT, the published commit removed
CAUGHT, the script unpinned CAUGHT.
`evidence/adversarial-pass-14-2026-08-09.md`.

## D-158 - Stage 4 promotion and billing boundaries need exact controls

Adversarial pass #15 revisited the M2.6 editorial-judge contract. The production code already
refused all nine tested mutations, but three guarantees were not held by discriminating tests:

- the old tie test used 5 wins against 5 wins, so the 20-item minimum answered before the tie rule;
- the token tests did not stand on the exclusive 200,000-token ceiling; and
- no test held the 20-keyframe maximum even though inline image bytes are billed.

The regression set now uses 10 wins against 10 wins, asserts that the floor did not answer, and
includes an 11-to-10 promotion control. A request at exactly 200,000 tokens is refused while one
token below is accepted. Twenty-one keyframes are refused while exactly twenty inside the candidate
span are accepted. This makes the cost and managed-migration boundaries mutation-sensitive without
changing production behavior. The upstream pass called this D-128; the readiness branch already
used that identifier, so the semantic integration is recorded here as D-158.

`evidence/adversarial-pass-15-2026-08-09.md`.

## D-159 - Pipeline completeness needs a real complete-run control

Adversarial pass #16 attacked the original M2.7 end-to-end runner claims. Three of seven mutations
were already caught. Four survived because no test in the suite had ever made
`PipelineRun.complete` true: removing the `not skipped`, non-empty visual-window, or non-empty
candidate requirements was indistinguishable from a no-op. Stage 5 also had no product-path
assertion that the cuts it consumed were the cuts Stage 0 measured from the same video.

The suite now constructs a fully complete result through `run_pipeline` with real ingest, indexing,
boundary fusion, render and delivery plus injected discovery, visual and judge adapters. It proves
`complete is True` and `skipped() == ()`, then independently removes each of the three requirements
and requires incompleteness. A separate real-media run records the `BoundaryInputs` passed to Stage
5 and compares its cuts to the `IngestResult` from Stage 0. The existing fixture's natural-silence
signal extends to the file end, so asserting the input—not the winning boundary label—is the only
discriminating integration proof on this media.

The pass also corrected the stale statement that a bare run names four blocked stages; the current
pipeline names eight. The upstream pass called this D-129; the readiness branch already used that
identifier, so this semantic integration is D-159.

`evidence/adversarial-pass-16-2026-08-09.md`.

## D-160 - Unmeasured benchmark aggregates remain None

Adversarial pass #17 attacked the M0.7 ASR throughput harness. Seven of nine mutations were already
caught. The two survivors violated the project's explicit rule one layer above individual
measurements: an empty score set could publish mean/worst RTF as `0.0`, and an aggregate with no
VRAM probe could publish peak VRAM as `0`. Those values mean instantaneous transcription and zero
memory use—not missing evidence—and could mislead the capacity plan.

The new tests assert on `ModelReport.to_dict()`, the document downstream planning reads. They drive
the unprobed case through `run_benchmark` so the aggregation itself is exercised, rather than
constructing a report one call after the defect. Opposite-direction controls require measured
0.25/0.75 RTF values and a 17 GiB probe to survive, preventing a blanket `None` implementation from
passing. No production code changed. The upstream pass called this D-130; the readiness branch
already used that identifier, so this semantic integration is D-160.

`evidence/adversarial-pass-17-2026-08-09.md`.

## D-161 - Alignment accuracy must reach the benchmark report

Following D-160's audit of aggregate benchmark values exposed a larger omission: `_score_item`
computed §8.1 alignment accuracy for every item with reference timings and stored it on
`ItemScore.alignment`, but `ModelReport.to_dict()` never emitted an alignment field. The last metric
in §8.1 was computed and discarded at the publication boundary.

`ModelReport.alignment` now micro-aggregates timing evidence by matched words. It publishes matched
and reference word totals, coverage, matched-word-weighted onset/offset errors and within-tolerance
rate, the one tolerance, and the count of scored items. It returns `None` when nothing aligned—zero
milliseconds is a perfect score, not absence—and refuses mixed tolerances rather than averaging
rates measured against different thresholds. Invalid matched/reference counts also fail closed.

The tests use six timed items across all three dialects, prove the emitted values at a 30 ms shift,
move beyond the 50 ms threshold with a 120 ms control, require coverage beside errors, hold the
unmeasured `None` case, and refuse a mixed 50/200 ms report. The field-by-field report schema is
updated deliberately. Upstream recorded this as D-131; the readiness branch already used that
identifier, so the integration is D-161.

`evidence/section-8-1s-last-metric-never-reached-the-report.md`.

## D-162 - Stage 0 reuse is content-bound and atomically published

Adversarial pass #19 measured a repeated real 38-minute Stage 0 run spending 100.2 seconds
recreating `audio.wav` and `proxy.mp4` that were already present: 66% of the first run's work.
Reuse is now permitted only when the current source SHA-256, destination-independent ffmpeg
command, and recorded output size all match.

The upstream implementation wrote a rerun directly onto the final artifact. This branch tightens
the publication boundary: each destination has a safe cross-thread/process lock; ffmpeg writes a
suffix-preserving private sibling; a zero-byte result or source mutation is refused; the completed
artifact and fsync'd provenance JSON are individually atomically replaced. A failed encode or
source validation therefore preserves the last good artifact and provenance, concurrent identical
reruns encode once, and a hardlinked lock is refused without modifying its victim. Audio format
validation still runs after cache reuse.

Eight new controls distinguish reuse from an implementation that never reruns or always trusts the
destination: same-input reuse, same-path source replacement, settings drift plus truncation,
failed-run preservation, mid-encode source mutation, missing output, unsafe lock, concurrent
serialization, and post-reuse audio-format validation.
Upstream recorded the performance finding as D-132; that identifier already exists on this branch,
so the semantic integration is D-162.

`evidence/two-thirds-of-stage-0-redone-on-every-run.md`.

## D-163 - Font coverage must include normalized Kurdish and run at the burn

The M3.1 font guard omitted `ک` U+06A9 and `ی` U+06CC even though §4.1's normalizer converts
Arabic kaf/yeh into exactly those Kurdish forms. The golden caption contains both. Upstream
measurement removed only U+06A9 from the shipped Noto font while retaining Arabic U+0643: the old
guard passed, and libass rendered `کوردی` as detached fallback runs with 15,999 changed subpixels.

`KURDISH_REQUIRED_GLYPHS` now includes both normalized forms and a test derives the requirement
from `normalize_sorani`, rather than trusting another handwritten alphabet list. The per-file guard
also had no product caller: tests checked the checkout font while an installed render consumed an
arbitrary runtime `fonts_dir`. `assert_fonts_dir_covers_kurdish` now requires at least one covering
font in the exact directory passed to `render_clip`; the render adapter normalizes a refusal into
`RenderError` so the pipeline keeps its structured-failure contract.

Controls require the shipped directory to pass, empty and non-covering directories to fail, and a
real render path to refuse before publishing an MP4. Upstream recorded this as D-133; that number is
already used on this branch, so the semantic integration is D-163.

`evidence/adversarial-pass-18-2026-08-10.md`.

## D-164 - BM25 retrieval documents are sentence windows, not the episode

The runner built `Bm25Index.from_transcript(normalized)`: exactly one document. On the measured
38-minute transcript that meant 6,104 words and 2,784 terms in one 322..2,313,729 ms window.
BM25 had no passages to rank; every query could return only the entire episode. The already-written
`from_sentences` factory was unused.

Sentence segmentation now precedes index construction and the runner indexes one document per
sentence. `from_sentences` accepts the `NormalizedTranscript` rather than a bare media id so Kurdish
invariant #3 remains at the factory the runner actually uses. Tests require different queries to
select different bounded windows and the emitted run report to contain the exact sentence count.
The sibling negative-slice defect is also closed: `limit <= 0` is refused rather than silently
dropping tail hits.

The index is now structurally capable of retrieval, but `Bm25Index.search` still has no production
caller. BLUEPRINT's Path A sends the full normalized transcript while the milestone describes
`transcript → BM25 → Gemini`; choosing the index's product role changes the meaning of Path A and
§8.2 recall. `BLOCKED.md` #18 records the decision and executable acceptance criteria rather than
inventing a query/filter contract. Upstream recorded this as D-134; the readiness branch already
uses that number, so this integration is D-164.

`evidence/adversarial-pass-19-2026-08-10.md`.

## D-165 - A scene-window identity is a filesystem identity at its type boundary

`SceneWindow.window_id` is not only retrieval provenance. Qwen visual embedding, the composed
Path B extractor and the TimeLens CLI all derive an extraction directory from it by replacing its
logical colons with underscores. The normal runner validates its media id, but the public frozen
type accepted direct and injected construction. Measured, `media_id="../../outside"` produced
`../../outside:s0:w0`, and the derived directory resolved outside the declared work root.

The safe contract now lives once in `SceneWindow.__post_init__`: `media_id` must satisfy the same
cross-platform `validate_media_id` rule used by transcripts and artifact publication. This rejects
POSIX and Windows separators, parent references, control characters, hidden names, reserved device
names and non-portable endings before any adapter can form a path, while preserving portable
Sorani identifiers. Tests exercise both traversal forms and Windows-only filename hazards so a
fix that checks only the current host cannot pass.

The adjacent M6.3 audit also corrects stale progress prose: TimeLens is composed in the runner and
released after use; its remaining shortfall is labelled real-footage accuracy, not missing wiring.

`evidence/adversarial-pass-20-2026-08-10.md`.

## D-166 - A rewritable normalized transcript must still publish atomically and content-bound

`transcript.norm.json` is derived and legitimately rewritable after a KLPT upgrade; it is not
write-once like raw. That distinction was incorrectly implemented as `Path.write_text` on the
predictable final name. Measured on Windows, planting that name as a hardlink changed an external
victim from `ORIGINAL` to the normalized JSON while leaving link count two. A crash during the same
call could expose truncated JSON, and a stale normalized transcript was written successfully and
only refused if a later reader happened to inspect it.

`write_norm` now takes the media's existing hardened transcript lock, verifies the immutable raw,
requires `source_sha256` to match that exact file, writes and fsyncs a securely created private
sibling, repeats raw integrity and identity checks, and atomically replaces the final name. The
replacement unlinks a planted symlink/hardlink instead of following it. A failed replace keeps the
previous complete norm; private-stage cleanup never masks the primary exception. The reader's
stale guard remains because an old build or out-of-band actor can still place an artifact.

`evidence/adversarial-pass-21-2026-08-10.md`.

## D-167 - The transcript store directory is a bound security boundary

Hardening the final normalized filename did not protect a higher-level redirect. `TranscriptStore`
called `root.mkdir(parents=True, exist_ok=True)` and then trusted the pathname forever. An existing
POSIX symlink or Windows junction at `work/transcripts` was followed, putting canonical raw bytes,
their digest, the publication lock and derived norms in an external directory. Replacing the root
after construction was likewise invisible.

The store now keeps a lexical absolute path rather than calling `resolve`, lstat-validates a real
directory without reparse indirection, records its device/inode identity, and revalidates it before
and after every publication lock and around unlocked norm reads. This is deliberately narrower
than trusting the resolved target: the declared path is the boundary, so an intentional symlink is
still indirection the application cannot distinguish from a planted one.

Controls simulate a POSIX symlink and a Windows reparse point on every host and perform a real
rename/recreate identity swap. Each is refused before a lock or transcript artifact appears in the
replacement root.

`evidence/adversarial-pass-22-2026-08-10.md`.

## D-168 - Stage 2 resumes only exact, pinned per-window embeddings

The composed visual path rebuilt every scene embedding on every run. On the real 38-minute file
that path plans hundreds of windows, so a late failure discarded the most expensive completed
work even though each vector is independently reusable. Upstream measured the defect as D-140;
that number is already used on this branch, so the semantic integration is D-168.

`VisualComposer` now owns a per-window disk cache as part of the same composition that owns
retrieval, reranking and reader provenance. Production wiring supplies the exact lowercase
40-hex Qwen embedding revision from the trusted model metadata. A cache-enabled run hashes stable
source bytes and binds every record to that digest, the complete `SceneWindow`, model id and
revision. An injected composer without an identified revision remains valid but caching is off;
an arbitrary branch/tag is refused rather than treated as identity.

Records use a SHA-256 filename derived from the canonical window document, not a media-derived
pathname. Reads are bounded, no-follow, single-link, regular-file and fd/path identity checked;
the schema and vector numbers are strict (JSON booleans are not numbers), and `VisualEmbedding`
re-applies the finite/non-zero invariant. Writes use a unique private sibling, flush and fsync it,
then atomically replace the record. Corruption, truncation, source replacement or revision drift
causes only the affected vector to be re-embedded. Cache hits/misses are emitted in
`VisualDiscoveryResult`, making reuse observable rather than inferred from wall time.

Measured with the exact hash-locked Windows/Python 3.11/CUDA 13.0 profile, Torch 2.13.0+cu130,
two visible GPUs, the real `ZAR38MinTest.mp4`, `cuda:1`, and pinned revision
`9f2f7e710d6d81056aa5c0a4f04764fec6bb7bda`: pass one embedded five windows in 36.176 s; pass two
reported five hits, zero misses, made no additional frame-embedding call and completed in 8.266 s.
All five record SHA-256s and mtimes were unchanged. The remaining time is verified model reload
and query embedding, not repeated scene work.

`evidence/stage-2-embedding-resume.md`.

## D-169 - Help names the command that can actually be invoked

Argparse previously exposed two incompatible accidents. `hawedit --help` and
`hawedit-credentials --help` hard-coded Python module names that are not installed commands, while
parsers without `prog=` showed a source filename under `python -m`. A fixed string cannot be right
for both entry modes.

`cli.program_name` now uses Python's invocation contract: under `python -m`, `sys.argv[0]` is the
module's `.py` file and help names `python -m <module>`; generated launchers name their own stem,
dropping Windows' `.exe`. Empty `argv[0]` falls back to the module form. Every parser declared in
the current nine-entry `[project.scripts]` table uses the helper, including model fetch, FFmpeg
setup, release and the WSL VEX gate that did not exist in upstream's five-entry measurement.

The regression derives module-to-launcher names from `pyproject.toml`, drives every real `main`
through help under both suffixless and `.exe` launchers, and separately drives module mode using
the native platform's path separators. The existing Linux/Python 3.12 gate supplies the other
host, so a Windows-only path literal cannot certify the rule.

`evidence/help-names-the-invoked-command.md`.

## D-170 - The README must agree with the live quality ledger and its CLI API

The README is a product surface, not an archival log. It already states that `gate` is the strict
required check on protected `main`, while `BLOCKED.md` #7 is resolved; that upstream correction is
semantically present. The statement was unbound, so reopening the blocker or deleting the claim
could drift again. A symmetric test now requires exactly one of “#7 is live” and “README says the
check is required” to be true.

The adjacent module map had real drift: its `cli.py` row described only UTF-8 output after the
module gained machine-readable stdout ownership and invocation-aware help. The row now names all
three exported helpers, and a test derives the required names from `hawedit.cli.__all__`. This is
deliberately scoped to the module whose purpose is shared entry-point behavior; imposing symbol
lists on every prose module-map row would make the documentation less useful.

`evidence/readme-quality-bar.md`.

## D-171 - Join main only after semantic equivalence, preserving the verified tree

`origin/main` and the readiness branch independently implemented the same audit findings after
their common base, producing 35 textual conflicts across older pipeline, tests and append-only
ledgers. Resolving those conflicts file-by-file with whole-side choices would either discard later
hardening or reintroduce older implementations. Before joining history, every one of main's 25
commits was classified against the readiness tree. The two findings not already present—Stage 2
embedding resume and invocation-aware help—were implemented against the newer composition, then
measured and passed clean canonical gates. README's latest claim was likewise bound to current
contracts.

The histories were joined with Git's `ours` merge strategy intentionally. This is not a claim that
main did nothing; it says its semantic effects are already in the first parent's stronger tree.
Merge `89a1641` has parents `bc12e13` and `ba52888`. Its tree
`6b1963dc27a1e0997c7e7bfa091bcf29c25c72ae` is byte-identical to the verified readiness parent's
tree. The second parent makes all main commits ancestors without replaying stale implementations.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-179 - Confidential ZDR is a property of the constructible judge class set

Protected main neutered the two §3 governance gates independently. Developer-API upload tests
reddened, but removing `assert_permits_vertex` left its suite green. Under that mutation a
confidential Vertex judge made both `countTokens` and `generateContent` calls carrying the client's
Kurdish transcript and real JPEG bytes. Production was correct; coverage had silently proved only
the other route.

Readiness's D-174 constructor inventory already names every concrete `GeminiJudge` subclass
bidirectionally. That same inventory now builds every judge under each forbidden confidential
state with a recording transport. The suite asserts zero URLs, not merely an exception, and holds
`judge`, `count_parts` and `generate_json` independently. A separating case proves attribution
cannot substitute for configured ZDR; positive controls prove the transport and allowed route
still work. Thirteen new cases make the focused Gemini suite 78/78.

Rejected one Vertex-only test: it closes today's copy while letting the next subclass repeat it.
Rejected relying on `judge()` calling `count_parts` before `generate_json`: a public boundary that
is safe only in its current caller order is not a boundary. No production code changed because the
gates were already correct.

`evidence/confidential-zdr-class-set-2026-08-10.md`.

## D-172 - Declare every way a blocker stops needing Hawa

`tests/test_claims.py` maps `BLOCKED.md` headings to live or resolved entries so a milestone cannot
remain blocked behind completed work. The parser recognized only `RESOLVED`, but the ledger also
uses `ANSWERED` on #10. That entry therefore read as live even though Hawa answered the question;
the remaining Windows loader problem was filed separately as #11 and later resolved.

The accepted vocabulary is now explicitly `{RESOLVED, ANSWERED}` and enforced in both directions.
Every bold marker in a numbered heading must start with one of those words, and every declared
word must be used by at least one heading. The specific #10 regression is pinned alongside an
unmarked-live control. This turns a future status synonym into a deliberate code review rather
than an invisible resolution.

Rejected renaming #10 to `RESOLVED`: answering Hawa's repository question and removing the loader
obstacle were distinct events, and the ledger records that distinction accurately. Rejected
treating any bold text as a resolution: it would make formatting silently change milestone state.

`evidence/a-blocker-could-resolve-invisibly.md`.

## D-173 - Rejoin main after the claims delta, without changing the audited tree

`main` advanced from `ba52888` to `7002331` while the readiness branch was being pushed. The only
new semantic delta was D-172's `ANSWERED` blocker status. It was reproduced, implemented against
the readiness claims suite, and focused-green before history was joined.

Merge `8128707` has first parent `baf11b0` and protected-main second parent `7002331`. Both its
tree and the first-parent tree are `ecb193121a6778a2ff2b9f65d643e0a4f29b7d2a`; the merge adds
ancestry and no file content. This keeps the rule from D-171: semantic equivalence is established
before an `ours` history join, never assumed from the strategy name.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-174 - Hold §7 routing for the constructor hierarchy, not one judge class

`VertexGeminiJudge` correctly owns a separate constructor because Vertex uses ADC rather than the
developer API's key. Consequently its `route(self)` call is copied wiring: the parent constructor's
routing test does not protect it. Protected main measured that deleting the Vertex call left the
suite green and made the confidential endpoint constructible for the shadow model.

The suite now declares how every concrete `GeminiJudge` subclass is minimally constructed and
compares those names bidirectionally with the transitive runtime class hierarchy. Every declared
constructor must refuse `JUDGE_SHADOW`; a positive control must accept
`KURDISH_EDITORIAL_JUDGE` and route its URL to that exact model.

Rejected delegating Vertex to `super().__init__`: the parent acquires a Gemini API key, violating
the ADC route. Rejected one Vertex-only assertion: it closes today's copy but lets the next
subclass repeat the same unheld wiring.

`evidence/confidential-judge-routing-copy.md`.

## D-175 - Rejoin main after the confidential-route finding, preserving the audited tree

Protected main advanced to `b24ce15` after the previous exact-SHA hosted gate. Its semantic delta
was D-174's confidential Vertex routing coverage. Readiness integrated that finding against the
newer Gemini transport, passed its 65-test focused suite, and ratcheted the floor before joining
history.

Merge `ccb11a3` has first parent `42aa923` and protected-main second parent `b24ce15`. Both the
merge and first parent have tree `a332a67e40983efbac9f5cf296b45577f54cca56`, so the join added
ancestry and no file content. The complete local and hosted gates remain mandatory because Git
tree equality is not execution evidence.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-176 - A rejected validator correction is evidence, not an episode failure or a gap

The first source-current full Sorani run closed the Windows/WSL loader ownership defect and then
measured a second blast radius after 34.9 minutes: canonical OmniASR had aligned a segment, rzgar
proposed a correction, and the correction needed 22 CTC frames where only 15 existed. That
`AlignmentInfeasible` escaped the per-segment boundary and discarded all 547 regions. D-135 had
made initial canonical failures survivable but did not cover validator re-alignment.

Dropping the segment would throw away admissible timed speech. Keeping it silently would make a
failed validation attempt look successful. Calling it `UnalignedSpeech` would also lie, because
canonical timed words remain. The chosen artifact is `RejectedValidatorCorrection`: media bounds,
the registered validator and a bounded reason. The canonical segment remains, the correction is
visible in raw JSON and the run report, and `asr.validated_by` names rzgar only if at least one
correction was actually accepted.

After the fix, the exact receipt-bound source completed the same 2,313.8-second episode in 45.7
minutes. Worker output and the immutable host artifact were equal; the raw sidecar authenticated
5,897 words; two genuinely unaligned regions totalled 664 ms; and two rejected corrections were
reported without becoming transcript gaps. This closes executable M1.4. It does not create a
labelled accuracy score: M0.13/M7.2 remain external corpus requirements.

`evidence/full-sorani-stage1-acceptance-2026-08-10.md`.

## D-177 - Auto-selection requires a query-capable producer, not a producer-shaped flag

Protected main measured `--visual --auto-select` without a query spending about 170 seconds on the
real 38-minute Sorani episode before Stage 2 admitted it could not retrieve. The readiness parent
already refused that exact invocation before Stage 0 through its stricter `--visual without Path A
requires --visual-query` contract, so replaying main's implementation was neither necessary nor
safe.

The adjacent auto-selection guard still counted `--visual` by presence, however, and the generic
Stage 3 skip still instructed operators that `--visual` alone enabled Path B. The rule is now
expressed once in capability terms: Path A can produce directly; Path B can produce only when
`--visual` and a normalized nonempty `--visual-query` are both present. Seven behavioral tests
hold the refusal, both positive producer paths, the no-producer case, whitespace, flag dependency
and the structured instruction.

Rejected using the whole transcript as an implicit query: it is the retrieval corpus and D-117
measured the resulting unbounded GPU demand. Rejected copying protected main wholesale: its other
delta repairs an older flat-file publisher, while readiness's hidden `ArtifactBundle` already
makes a crashed partial delivery invisible and nonblocking and publishes the exact five files with
one no-replace directory rename.

`evidence/auto-select-query-preflight-2026-08-10.md`.

## D-178 - Join main only after classifying both deltas against the stronger readiness tree

Protected main advanced through `e2c768f` with an interrupted flat-delivery repair and the
queryless auto-selection finding integrated in D-177. Readiness already superseded the former with
its hidden exact-set `ArtifactBundle`; importing flat-file recovery would weaken publication
ownership. Its stricter earlier visual-query preflight already refused the latter's exact
invocation, while D-177 aligned the adjacent producer model and evidence with that behavior.

The canonical first-parent gate passed 2,008/2,008 tests with zero skipped before the join. Merge
`ded03cc` has readiness parent `4b63c04` and protected-main parent `e2c768f`; both the first parent
and merge have tree `03b07a54ce0d40c98e3f3b0de78b2c1a27640264`. The merge therefore records ancestry without
replaying stale content. Tree equality is not runtime acceptance, so a new canonical gate is still
required at the final documented merge tip.

`evidence/main-semantic-merge-2026-08-10.md`.
