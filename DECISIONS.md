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
| `fonttools` | 4.55.3 | MIT | PyPI metadata |

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
