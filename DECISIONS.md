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

**An edge the measurement exposed:** Silero reports region 2 ending at 4180 ms on a 4162 ms file.
`media_duration_ms`'s existing clamp absorbs it, which makes that clamp load-bearing for a second
independent reason. The boundary invariant is safe regardless, because the 200 ms tail is always
in the `max()`.

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

**Still open on this row, deliberately not bundled:** `iou_match` is accepted unvalidated, so
`1.5` or `-1` yields silent nonsense rather than a refusal. A different defect in a different
function; folding it in would have made neither individually auditable.

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

**Decision: validate at the three public entry points, not in the shared funnel.**
`_found_winners` is the funnel all three metrics route through and is the obvious site — but it is
skipped when the gold set has no winners, because each metric short-circuits to `None`/`{}` first.
A caller passing `k=-5` against an unlabelled set would have been handed "unmeasured" and never
told the cutoff was nonsense. `_assert_metric_parameters` therefore runs ahead of that
short-circuit: one rule, three places where the arguments enter, the same shape as D-071's
overwrite guard rather than three copies of a rule.

**`0.0` and `1.0` are deliberately legal and are pinned by controls.** `0.0` means "any overlap
counts", `1.0` means "the exact span only"; §8.2 forbids neither. A guard that rejected them would
break honest callers while passing every refusal test — which is exactly what the mutation *"the
legal boundary 1.0 is wrongly rejected"* demonstrates, and it is CAUGHT by the control rather than
by any refusal test.

**Mutation audit 7/7** (`evidence/metric-parameter-validation.md`), run over
`tests/test_discovery.py` as well since it also calls these metrics. *"recall_at_k stops
validating"* is CAUGHT, which is what confirms the entry-point placement is load-bearing rather
than decorative: dropping the call from one metric while leaving it in the others does not slip
through.

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

## D-082

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

## D-083

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

## D-084

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

**A negative result recorded because it is worth knowing.** D-077, D-080 and D-083 were three
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

## D-085

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

## D-086

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

Gate: `VERIFY OK — 1136 passed, 0 skipped`.

## D-087

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
and quietly blind the test, which is D-086's failure mode one week later.

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

## D-088

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
same reason D-086's were: they used a fixture where the rule happened to work. These use
0..1400, 1400..2800 and 2800..4162 — what `plan_scene_windows` produces on the only media in this
checkout. `evidence/sv6d-duration-smuggling.md`.

Gate: `VERIFY OK — 1142 passed, 0 skipped`.

## D-089

**A number in the evidence was wrong, and the same file's other numbers proved it.**
`evidence/waw-separation.md` recorded `waw_initial_words: 491`. KLPT's lexicon has **504**, and the
file's own constructible count settles it: 24 894 − 504 = 24 390, whereas 24 894 − 491 = 24 403.
Every other figure in the file was already consistent with 504.

**Why it survived two adversarial passes.** The guard recomputed nothing. It asserted
`lexicon_entries > 20_000`, `dictionary_words_damaged == 0`, and that the unsplittable list matched
its own length — three of seven numbers bounded, none measured. A number nobody recomputes is a
transcription, not a measurement, which is the same failure D-069 found in `AUDIT_REPORT.md` and
D-084 found in `MINIMUM_HOURS`.

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

## D-090

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

Gate: `VERIFY OK — 1148 passed, 0 skipped`.

## D-091

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
consecutive iteration where over-strictness was visible only to a control (D-087, D-088, D-090).

**Scope, stated plainly:** M0.16 is BLOCKED and no corpus exists on this machine, so nothing shipped
wrong output to a client. What shipped was a false guarantee — the docstring's fourth promise and
M0.14's row both claimed a check a missing column walked around. Found by the fourth adversarial
pass; premise re-verified here rather than taken from the agent's report.
`evidence/common-voice-locale-bypass.md`.

## D-092

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
as protection it does not have (D-082): the probe never refusing is CAUGHT (3), `-n "$_probe" &&` —
the D-091 truthiness shape, which would have re-admitted `true.exe` because it says nothing — is
CAUGHT (2), swallowing the interpreter's answer is CAUGHT (1), dropping `import hawedit` from the
probe is CAUGHT (1), and refusing every interpreter is CAUGHT (10). The last two single-test catches
are the ones doing real work. **The over-strict direction was already covered** by nine pre-existing
tests of the gate's success path, so the new control makes the property explicit rather than newly
protected — unlike D-087, D-088, D-090 and D-091, where a control was the only witness. Recording
that difference rather than continuing the pattern by assertion.

**Not closed, and left as the next item:** a forged JUnit report. With a real `PY`, something else
answering to `-m pytest` on `PYTHONPATH` could write an XML that layer 3 reads back and accepts. The
probe cannot see it, because the interpreter genuinely is this project's. It needs its own
measurement — it was reported by an adversarial-pass agent and I have not reproduced it.
`evidence/py-override-bypassed-the-whole-gate.md`.

## D-093

**A 30-line fake `pytest` on `PYTHONPATH` printed `VERIFY OK` and ratcheted the committed floor.**
D-092 made `PY` prove it runs this project and named this as what it could not close. Reproduced
rather than inherited from the agent's report:

```
$ PYTHONPATH=<fake> PY=$PWD/.venv/Scripts/python.exe bash scripts/verify.sh
==> lint / typecheck / format   all real, all pass
==> tests                       1200 passed in 61.50s   [forged]
==> test evidence               1200 collected, 1200 passed, 0 skipped
VERIFY OK    exit=0  elapsed=4s      floor 1155 -> 1200
```

Four seconds, zero test bodies. Only the step that produces the evidence was substituted. Freshness
cannot see it — `not_before` exists for a leftover report, and this one was written during the run by
the thing pretending to be pytest. Layer 3's reasoning ("the report is the evidence") holds only while
the report comes from pytest.

The consequence outlives the run: `write_floor` moved the committed floor to 1,200, so every honest run
afterwards would be refused for a bar a forgery invented — a fake green that leaves the gate
permanently red. Same self-poisoning shape as the `collected`-vs-`passed` bug already recorded in
`gate.py`, reached from outside.

**Decision: the gate's tools must resolve under `sys.prefix`.** `assert_tools_are_from_this_environment`
checks `pytest`, `ruff` and `mypy`, folded into D-092's existing probe so there is one call and one
refusal path before any step runs. The rule is **provenance, not a list of hostile environment
variables**: enumerating ways to redirect an import (`PYTHONPATH`, user site-packages, a directory of
that name in the working tree) is the same losing shape as the blacklist of no-op commands this repo
already replaced. Nothing is chosen — the interpreter and the module settle it.

**`hawedit` is deliberately excluded from the list.** It is installed editable here and in CI, so its
file lives in `src/` and not under `sys.prefix`; requiring otherwise would refuse the only install
layout this repo uses. That it imports at all is proved by the probe running.

**Rejected: refusing `PYTHONPATH` (or any env-var list).** Incomplete by construction — user site,
`PYTHONUSERBASE` and a `pytest/` directory in the working tree all reach the same end — and it would
break the worktree-isolated adversarial passes, which set `PYTHONPATH=$PWD/src` against a junctioned
`.venv`. Provenance lets those keep working: their `pytest` still comes from the junctioned
environment.

**Rejected: running each step with `-E -s`** (interpreter-level isolation). It closes the same class,
but silently — and it would silently drop `PYTHONIOENCODING` and `PYTHONUTF8`, which on this Windows
box are exactly the variables that decide whether Kurdish output survives the console. A gate that
quietly changes what the caller asked for is the failure mode this repo keeps paying for.

**Rejected: cross-checking the report's `<testcase>` names against files on disk.** The forger writes
those too; it raises the cost of the forgery without changing what is provable.

**Mutation audit 6/6.** The rule never firing CAUGHT (2), offenders collected and discarded CAUGHT (3),
a tool with no file falling through to `Path(None)` CAUGHT (5), `pytest` dropped from `GATE_TOOLS`
CAUGHT (2) — by a test that reads `verify.sh` and requires every `$PY -m <tool>` step to be in the
list, because a checked list that drifts behind the steps is a hole the same shape as this one — the
over-strict inversion CAUGHT (13), and reverting `verify.sh` to D-092's import-only probe CAUGHT (1),
by the end-to-end forgery test alone. The audit also reproduced the damage: with the rule mutated away
the forged run moved the floor 1,161 → 1,200, which the "floor unchanged" assertion caught and which
was restored by hand before committing.

**Not closed, precisely:** a substituted `hawedit` itself, where `--check-tools` would be the forgery's
own code. No check written in this module can outrank that. Stated rather than implied, because the
cheapest version of this fix is one that quietly claims to be complete.
`evidence/forged-test-report-accepted.md`.

## D-094

**§4.4 was enforced on the property and never on the report a reader receives.** M0.9's row says
"per-dialect always reported alongside the aggregate"; `normalized_cer_by_dialect`'s docstring says
"§4.4: never report the aggregate without these"; `bench.py:466` writes `report.to_json()` to a file
that a human reads when deciding which model becomes canonical. Deleting the field from
`ModelReport.to_dict()` left **1,161 tests green** and produced this artifact:

```
HONEST                                   FIELD DROPPED
  normalized_cer            : 0.15         normalized_cer            : 0.15
  normalized_cer_by_dialect : {            normalized_cer_by_dialect : (absent)
      "hewler": 0.04, "mukriyan": 0.26 }
```

`0.15` across "Sorani" from dialects measuring 0.04 and 0.26 — a 6.5× spread the aggregate hides.
Computed and discarded, not never-computed: the property is right, and nothing checked that it
reaches the file.

**Why the existing tests were blind.** `test_the_report_serialises_to_json` asserted
`"hewler" in payload`, which looks like the right check; with the field deleted the string still
occurred **seven** times — once in `coverage.hours_by_dialect` and six times in
`coverage.missing_cells`. A substring assertion against a whole document is satisfied by any block
that mentions the word, so the coverage section was carrying a test about per-model accuracy. The
sibling test asserted on the property, which was never at risk. Together they read as full coverage of
§4.4 — the same shape as D-086 and D-088: correct, and blind.

**Decision: assert parsed key paths, and record the whole emitted schema rather than the one field.**
`to_dict` is a hand-written key list, so any field can vanish from a written §8.1 report the same way;
fixing only `normalized_cer_by_dialect` would fix the case and leave the class. The recorded key sets
for `ModelReport.to_dict()` and `BenchmarkReport.to_dict()` make adding a field a visible line in a
diff — the same trade `scripts/test-count.floor` already makes, and the reason this is not a check
whose cheapest fix is deleting it.

**Rejected: raising inside `to_dict` when the aggregate has no breakdown.** An empty breakdown is a
legitimate state, not a defect — an interim corpus has no §4.4 dialect labels (D-012, and
`corpus_import.py` refuses to invent them), so a guard would refuse the one corpus that exists.

**Rejected: emitting the key only when it has values.** This is the plausible wrong fix and it is
worse than the defect for the interim case: on an artifact an absent key reads as *not applicable*
while `{}` reads as *we looked and the data carries no labels*. It would satisfy every other new test
here. It is caught only by the unlabelled-corpus control.

**The fixture carries the teeth.** The two dialects are deliberately far apart, so the aggregate
genuinely misleads and the breakdown genuinely informs. A run where both score the same passes whether
or not the field survives — which is how this got here, since the previous fixture was
`{"hew-1": PERFECT, "muk-1": PERFECT}`.

**Mutation audit 5/5.** Dropping the breakdown CAUGHT (4, including the strengthened serialisation
test that previously survived it), emitting the key only when non-empty CAUGHT (1, the control alone),
an *unrelated* field vanishing CAUGHT (1, the recorded schema alone — the difference between fixing
the field and fixing the class), scoring an unmeasured dialect `0.0` CAUGHT (6 — the hard rule
"unmeasured is None, never 0.0"), and every dialect reporting the aggregate CAUGHT (7).
`evidence/aggregate-cer-without-its-dialects.md`.

## D-095

**The gate's own self-poisoning fix was described in the code at length and held in place by nothing.**
`gate.py` records why the floor ratchets on `passed`: ratcheting on `collected` while gating on
`passed` once wrote a bar of 873 from a run that passed 872, and every run after it was refused for
missing a number no run had achieved. Substituting `collected` back into the ratchet, with counts read
from a JUnit report rather than a summary line:

```
baseline: collected=1164 skipped=0 failures=0 errors=0 passed=1164
mutated:  collected=1164 skipped=0 failures=0 errors=0 passed=1164
```

Two reasons, and the second matters more. Every ratchet test used a report with `skipped=0`, where the
two numbers are equal by construction — correct tests that could not tell them apart, the shape of
D-086, D-088 and D-094. And **this host skips nothing**, so the defect is invisible exactly here and
fires on a machine where something legitimately skips: a box without the pinned ffmpeg, or CI if the
golden render ever starts skipping. The regression would land on somebody else's machine.

Run directly against the 873/872 numbers in the comment: correct behaviour writes 872 and accepts an
identical second run; the reverted behaviour writes 873 and refuses it.

**Decision: pin it with the idempotence property, not with a number.** "A green run must never leave
the gate refusing an identical one" needs no knowledge of which count is right — a ratchet on
`collected` fails it, a ratchet on `passed` cannot. Alongside it, the direct assertion on the
**artifact** (the floor file reads 872, not 873) and a control requiring the floor to reach the full
count when nothing skips, so "ratchet on `passed`" is not read as "ratchet lower than collected",
which would stop the gate noticing deletions.

**Tried and backed out: binding `ran = evidence.passed` for both sites.** The reasoning was that one
name makes "gate on one, ratchet on the other" unexpressible. It does not — `ran = evidence.collected`
is the same one-word edit, so the rename only moves the single point. It also broke
`test_the_readme_describes_the_gate_floor_as_tests_that_passed`, which asserts the literal
`if evidence.passed < floor:` in the source to keep the README's wording honest (D-069). The audit
settled it: the third mutation below is caught by **that test alone**, so the rename would have traded
real protection for a cosmetic gain. `gate.py`'s diff here is comment-only.

**Mutation audit 5/5.** The ratchet writing `collected` CAUGHT (2), writing `collected` on every run
rather than only on growth CAUGHT (2), the *gate* comparing `collected` CAUGHT (1, the source-text
claims test alone), the ratchet never firing CAUGHT (4), and the floor ratcheted one below what ran —
the over-lax direction, which would leave room for a test to vanish between two green runs — CAUGHT
(4). Unlike D-087/088/090/091 the new control is not the only witness: the existing ratchet tests
already covered downward drift. What they could not see was *which of two equal numbers* was written.
`evidence/floor-ratchet-unprotected.md`.

## D-096

**The ledger carried 30 standing test counts and 21 of them were false.** Found by adversarial pass
#5, whose behavioural half found nothing: eight reverted claims across M0.7, M0.8, M1.5 and M2.5 all
went red, 8/8. The docs were where the rot was.

```
M2.7 test_pipeline      18 -> 59      M2.6 test_judge        40 -> 47
M5.2 test_video_input   16 -> 35      M5.2 test_qwen_visual  16 -> 20
M0.4 test_transcripts   17 -> 34      M1.3 test_ingest       20 -> 23
M1.6 test_models        21 -> 34      M5.3 test_path_b       26 -> 28
M2.4 test_render        21 -> 31      M5.4 test_video_reader 22 -> 23
M5.1 test_visual_index  51 -> 61      M3.6 test_delivery     25 -> 26
M0.7 test_asr           14 -> 22      M6.3 test_video_grounding 20 -> 19
M3.1 test_captions      33 -> 41      M2.2 boundary/clip     31/20 -> 38/27
M0.1 gate + evidence 29/17 -> 25/14   M2.8 credentials/gemini 20/26 -> 21/33
```

**M6.3 drifted downward**, which is the direction that means a test disappeared. It did not: the file
has had 19 since `674b43b`, the commit that wrote "20", so it was miscounted on the day. Checked
before recording, because a deleted test would have been a far larger finding.

**M0.1's pair is mine**, written one iteration earlier — "29 tests, plus 17 in test_gate_evidence.py"
against an actual 25 and 14. A hand-maintained count was false within a day, written by the same loop
now auditing it. That is the argument, in one line.

**Decision: drop all 30; keep the file references.** This generalises a decision already recorded
twice — D-083 and D-084 each say "the stale count is dropped rather than restated" — rather than
inventing one, and `tests/test_claims.py` now refuses their return.

**Rejected: enforcing each count against `--collect-only`.** It would make the numbers true, and make
every new test require a ledger edit in the same commit — turning a hand-written row into a generated
artifact, and going red on the other agent's commits as readily as on mine. The count is also the one
part of a row a reader cannot act on, and `scripts/test-count.floor` is already the instrument that
notices tests disappearing. A per-file ratchet would be a different and larger design decision, not a
side effect of tidying prose.

**Kept: the four quoted historical counts** in the "the stale `(15 tests)` count is dropped rather
than restated" sentences. Those record a past edit rather than asserting a present fact — the same
distinction `test_every_test_count_in_the_audit_is_dated` (D-069) already draws between a dated
measurement and a standing claim.

**Mutation audit 3/3 on the new check**, mutating the *document*: a standing count reintroduced on a
`tests/` reference CAUGHT, on a `src/` reference CAUGHT, and — the one that matters — an **accurate**
standing count reintroduced CAUGHT, because correctness today is not the property at issue. The
control confirms the quoted historical form is still legal, so the check does not simply ban the
digits. The cheapest way to satisfy it is to not write a rotting number.
`evidence/adversarial-pass-5-2026-08-09.md`.

## D-097

**A stub with no model produced a §8.1 report identical to the real adapter's.** M0.7 recorded
`type(adapter).__name__`, which satisfies "every measurement names its adapter class" and not the hard
rule behind it — *a number carries the hardware and adapter that produced it*. A class name asserts an
adapter; it does not carry one. `validate_adapter` resolves `adapter.model_id` against §7, so a stub
must claim a real §7 id, and claiming one is free. Measured with a stub named exactly like the
canonical adapter, no weights, no GPU, no backend:

```
adapter_impls  : ['OmniAsrAdapter']          <- the real adapter emits exactly this
normalized_cer : 0.0
mean_rtf       : 0.1
hardware       : {'host': 'hawapc01', 'accelerator': '2x RTX 3090 Ti'}
distinguishable from the real adapter in the artifact: False
```

A perfect CER and a 0.1 RTF attributed to a named GPU host, from a class that loaded nothing. Never
computed, not computed-and-discarded: the module was never read.

**Decision: record the module-qualified implementation.** One site — `asr.py` builds every
`Measurement` and is the only place in `src/` deriving an adapter identity (the other six
`type(...).__name__` uses are error messages). `test_bench.OmniAsrAdapter` carries where the code came
from; `OmniAsrAdapter` only asserts it.

**Rejected: resolving the model revision by id** from `models/revisions.json`. It would have made the
stub look *more* real — it claims a genuine §7 id, so the pinned SHA would be returned for it. The
module is a fact about the object in hand rather than a lookup keyed on a claim.

**Rejected: blocking promotion in `decide_canonical` on a foreign adapter.** It sits beside the interim
and coverage blocks and looks symmetric, but the harness's own tests promote challengers measured by
`test_bench.ScriptedAdapter` — legitimately, since that is how the decision rule is tested. The guard
would either break them or need a bypass, and a bypass is worse than disclosure. The report says what
produced the numbers; that is the property that was missing.

**Rejected: recording the backend.** `backend` is not part of the `ASRAdapter` protocol, so reading it
would be a special case keyed on one class's internals, and `Measurement` sees only the adapter.

**Measured rather than guessed:** under pytest the module reads `test_bench`, not `tests.test_bench`,
because there is no `tests/__init__.py`. The tests assert the literal string that actually appears.

**Mutation audit 4/4**, and the two new tests are complementary rather than redundant — the audit
shows which catches what. The **constant-prefix** wrong fix (`f"hawedit.asr.{name}"`, which looks
qualified and identifies nothing) is caught by the stub test and **not** by the control, because for
the real class that constant produces exactly the right answer. **Module-without-class** is caught by
the control, which pins the real adapter's own qualified name. The control is a real measurement of
`hawedit.asr.OmniAsrAdapter` with a backend that raises — no weights needed, because M0.7's "failures
are recorded not raised" keeps the measurement and its adapter. That property is now load-bearing for
a second reason.

**Not closed, named:** substituting the backend *inside* the real adapter. `OmniAsrAdapter(backend=…)`
is public, and a fake backend behind the genuine class still reports `hawedit.asr.OmniAsrAdapter`.
Closing that means the protocol exposing what it loaded — a design step, not a side effect of this one.
`evidence/stub-indistinguishable-from-real-weights.md`.

## D-098

**A threshold recorded in a decision could drift from the code with the suite green.** D-084 pinned
one — `MINIMUM_HOURS` against D-009 — after measuring that 3.0 could become 1.0 unnoticed. The same
question, asked of every constant, found the failure is a class. Measured 2026-08-09 against a green
1,170 baseline, changing the constant alone:

```
DEFAULT_PAUSE_MS         500 -> 800          GREEN, nothing noticed
NVENC_MIN_FRAME  (145,49) -> (64,64)         GREEN, nothing noticed
DEFAULT_DISAGREEMENT_CER 0.15 -> 0.25        RED, behaviour tests only
MINIMUM_HOURS            3.0 -> 1.0          RED, the record test D-084 added
```

`(64, 64)` is exactly the value D-045 records as the historical defect — the probe size that made
`encoder_available` call a working NVENC unavailable. Restoring the bug's own number changed nothing
the suite could see, because `test_render.py` asserts the *relation*
`ENCODER_PROBE_SIZE >= NVENC_MIN_FRAME`, which holds at 1080×1920 against any small pair. The
relation is the right assertion and it cannot pin the recorded measurement.

`DEFAULT_PAUSE_MS` was invisible for a more instructive reason: `tests/test_sentences.py` passes
`pause_ms=DEFAULT_PAUSE_MS`, so the tests follow the constant wherever it goes and never assert what
it is. Symbolic use reads as coverage and measures nothing — the same shape as D-094's substring
assertion and D-095's `skipped=0` reports.

**Decision: the `<constant> = <value>` form in a decision is now enforced against the code**, for
every constant, by one test rather than one pin per constant. (Written with angle brackets on purpose:
spelling the placeholder in the real form made this very entry parse as a statement about a constant
named `NAME`, and the check caught its own documentation.) The convention already existed organically;
making it load-bearing costs nothing to maintain, and it means changing a threshold requires amending
the decision that justifies it — which is D-009's own wording: "Changing the floor means amending the
decision, not only the constant." Later statements supersede earlier ones, so a decision may revise a
value a previous one set.

**Restated here in canonical form, quoting the entries that state them in prose only.** These are
transcriptions, not new choices — each value is what the code already holds and what the cited entry
already justifies:

* `MATERIAL_GAIN_RATIO = 0.10` — D-010: "**Material = ≥10% relative reduction in normalized CER**
  (`MATERIAL_GAIN_RATIO`)".
* `DEFAULT_IOU_MATCH = 0.5` — D-020: "A retrieved candidate 'found' a gold winner at temporal
  IoU ≥ 0.5 (`DEFAULT_IOU_MATCH`)".
* `RETRIEVE_K = 50` — D-090: "the shipped CLI always ran at §3's depth of 50".
* `DEFAULT_TOLERANCE_MS = 50` — recorded in **no** decision until now, justified only in
  `alignment.py`'s own comment: "50 ms is roughly one frame of 24 fps video and below the threshold at
  which a cut reads as early or late — but it is a reporting parameter, not a quality gate, and it is
  recorded alongside every result so a rate is never quoted without the tolerance that produced it."
  A chosen number with no entry is what the hard rule "refuse and record instead" exists to prevent,
  so it is recorded rather than left in a comment.

**Rejected: enforcing every constant in `src/`.** Most are not judgment calls — `TARGET_SAMPLE_RATE`,
`PROXY_HEIGHT`, a licence table — and requiring a decision for each would fill the log with entries
nobody made. What earns enforcement is a value a decision *claims*, which is exactly what the
convention already marks.

**Rejected: parsing the numeral out of prose** (D-084's approach, generalised). "≥10% relative
reduction" and "IoU ≥ 0.5" are not machine-readable in any stable way, and a regex loose enough to
catch both would match sentence numbering. Restating the value canonically once is honest and does not
touch the original reasoning.

**Still prose-only, named rather than implied:** `REFERENCE_FPS` and `DECLARED_SAMPLING_FPS` (D-065
names both constants but its numerals appear only in the surrounding argument, and transcribing them
from the code rather than the record would invert the direction this check depends on).

**Mutation audit 4/4.** `DEFAULT_PAUSE_MS` drifting from D-014 CAUGHT, `NVENC_MIN_FRAME` back to the
historical `(64, 64)` CAUGHT, `MATERIAL_GAIN_RATIO` drifting from the value just recorded CAUGHT, and
the discovery regex matching nothing — a check that silently examines zero statements — CAUGHT by the
`>= 7` floor, which fired for real while this was being written and is the reason it exists.
`evidence/recorded-thresholds-unpinned.md`.

## D-099

**The readiness report said `OK` for a checkpoint nothing on this machine can load.** I picked M1.4 to
close, on its own written shortfall: "its weights **are** present on this machine (10.1 GB, `python -m
hawedit.models` reports `OK`), so what is missing is the composition, not the download". The premise
did not survive contact.

The machine is capable — torch 2.13.0+cu130, CUDA available, 2 devices, transformers 4.57.6,
accelerate. The loader is absent:

```
config.json  architectures: ['Qwen3ASRForConditionalGeneration']  model_type: qwen3_asr
transformers.Qwen3ASRForConditionalGeneration  : NO
transformers.models.qwen3_asr                  : ModuleNotFoundError
AutoModel can map 'qwen3_asr'                  : False
```

`config.json` names the installed version, 4.57.6, and it still cannot load it. The model card gives
the reason: `from qwen_asr import Qwen3ASRModel  # pip install qwen-asr` — a separate package. So the
composition was never what was missing, and writing the adapter first would have produced code that
cannot run, provable only against a stub, which is what D-097 had just finished measuring the cost of.

**The root defect.** `models.py`'s weights branch asked one question — is the directory non-empty.
`_PIP_MODULES` already existed for components whose *runtime* is the gating fact but is consulted only
for `Provisioning.PIP` entries, so a checkpoint needing both a download **and** a loader had no way to
say so. The report is read as "can this stage run" and was answering "is it on disk".

**Decision: a weights entry may declare the loader it needs, and readiness consults it.**
`_WEIGHTS_RUNTIMES` maps the model id to an import name; a present checkpoint with a missing loader
reports unavailable, with the loader named and the size still shown — the weights really are there, and
an operator deciding what to fetch needs to know not to fetch them again. 10/15 becomes **9/15**, which
is the truer number.

**The import name is evidence, not a guess.** `qwen_asr` comes from the checkpoint's own model card,
quoted above. Only that one entry is mapped: VideoChat3-4B, TimeLens2-4B and the Qwen embedding pair
demonstrably load today with decoded-frame evidence behind M5.4 and M6.3, so declaring runtimes for
them would be inventing requirements.

**Rejected: `pip install qwen-asr`.** One command would have turned the report green. It needs a
licence under D-002 (§7 records the *model* as Apache 2.0; the loader package is a separate artifact
whose licence I have not read — "never guess a licence"), a pin and checksum under the supply-chain
rule, and it would make the local gate and CI's `.[dev,media]` disagree about which program they test,
which is the failure D-092 and D-093 were about. It is Hawa's call and belongs in a decision with the
licence quoted. `BLOCKED.md` #16.

**Rejected: leaving the report as it was and only correcting M1.4's prose.** The row was wrong because
the artifact it quoted was wrong. Fixing the sentence and not the report would leave the next reader —
or the next agent — to draw the same conclusion from the same `OK`.

**Mutation audit 4/4.** The runtime check never firing CAUGHT (2), the check not reaching `available`
CAUGHT (2), the validator's entry dropped from the map CAUGHT (1) — by the test that asserts the
*coupling* (available exactly when `qwen_asr` imports) rather than today's answer, so it holds in CI
where the loader is also absent and keeps holding the day someone installs it — and **any declared
runtime marking a component unavailable CAUGHT (1) by the control alone**. Without that control,
"every mapped entry reports MISS" passes everything else here and retires three working components.
`evidence/downloaded-is-not-runnable.md`.

## D-100

**The report an operator reads could print the opposite of the truth.** D-099 fixed the *statuses*; the
renderer went untouched, and `readiness_report` is what a human actually reads — it is the artifact
whose `OK` led M1.4's row to conclude the wrong thing in prose. Mutating the renderer alone against the
whole suite:

```
GREEN — nothing notices   every component prints OK regardless of availability
GREEN — nothing notices   the verdict is inverted
GREEN — nothing notices   the summary count claims everything is available
GREEN — nothing notices   the size disappears from every line
RED (5)                   the missing list is emptied, so nothing is named
```

Fifteen components could print `OK` with six missing. The one RED is the more instructive result: its
failures were `test_the_gpu_modules_typecheck_with_the_gpu_extra_absent` and two nested-gate tests —
mypy objecting to `missing = []`, not anything checking the report. A mutation caught for an unrelated
reason reads as protection that is not there (D-082), and here it was the only signal in five.

**Why the existing tests were blind.** Both asserted substring presence over the whole document:
`"omniASR_LLM_7B_v2" in report` and `"available" in report`. The word "available" occurs in the summary
line whatever the marks say, and every model id occurs on its own line whether that line reads `OK` or
`MISS`. The same shape as D-094's `"hewler" in payload`.

**Decision: assert the verdict on the component's own line**, by finding the row containing the model id
and reading its first token, and assert the summary against the counts it summarises. Both directions
are pinned on the same function, because the measured defect was an *inversion*: a renderer that always
prints `OK` passes every all-available test, and one that always prints `MISS` passes every
all-missing test. Neither alone is a control.

**A second defect, in the source, surfaced from writing the size test:** `if status.size_bytes` treated
a **measured zero** as unmeasured. A checkpoint directory holding only empty files is non-empty, so it
reports present with size 0, and the falsy check printed no size — the same line a pip component gets,
which reads as "no weights here to measure". Now `is not None`. Measured zero and unmeasured are
different facts, and the hard rule is that the second is `None`; this is that rule pointing the other
way, which is why it was easy to miss.

**Rejected: deriving the marks from a single source to make inversion unexpressible.** The summary
already derives from the same `available` predicate as the marks; there is no second spelling to
unify. The gap was that nothing read the output, which is a test, not a refactor — and D-095 is the
precedent for backing out a rename that only moves the single point.

**Mutation audit 7/7**, each caught by a test that names the property — including "the missing list is
emptied", which previously produced only mypy failures in unrelated tests. The last two are caught by
exactly one test each: the measured-zero case, and the dangling-`missing:` control. **The seventh
mutation exists because that control was otherwise unexercised by the set**, which would have left an
assertion nothing had ever put pressure on — the same reasoning that made D-098's `>= 7` floor worth
having.
`evidence/readiness-report-could-print-the-opposite.md`.

## D-101

**The shipped `editing.json` could mislabel which path found the clip.** Adversarial pass #6 mutated
`Clip.to_dict` to hardcode `DiscoveryPath.VERBAL.value` and `tests/test_clip.py`,
`test_pipeline.py`, `test_path_a.py`, `test_delivery.py` and `test_boundary.py` all stayed green.

The reason is the shared fixture: `a_clip()` builds a **verbal** clip, so the shape test and the
round-trip test compared "verbal" against "verbal" and could not see the field stop reading the
object. Correct tests, blind because the fixture happened to satisfy the rule — the shape of D-086
and D-088, now found in a third place.

It matters past the label. §8.2's `recall_at_k_by_path` and `path_unique_wins` partition on
`discovery_path in (path, DiscoveryPath.BOTH)`, and `Clip.from_dict` rebuilds the enum from this
field, so a run resumed from a mislabelled artifact carries the wrong attribution into the numbers
M2.5's row says still mean something. §5's own words for `RejectedCandidate` are blunter: "that set
is your only measure of recall".

**Decision: parametrize over every enum member, on both sites.** `Clip.to_dict` and
`RejectedCandidate.to_dict` each emit this field; both are asserted for all three members, and the
`Clip` case also asserts the value round-trips back to the same member. A single fixture is how this
got here, so no new test uses one.

**The control is that three members render as three distinct strings.** Both parametrized tests pass
if `to_dict` faithfully copies a field whose members collide — the artifact would then be unable to
express the distinction §8.2 partitions on, however honest the copy. Mutation audit **3/3**:
hardcoding `verbal` CAUGHT (3), hardcoding `both` CAUGHT (6), and two members rendering identically
CAUGHT (2) by the control alone.

**Also from pass #6, and left alone deliberately:** nine of ten mutations to the delivery renderers
went red — SRT times not rebased to the clip, cue start/end swapped, one-based numbering, timecode
frames/seconds swapped, hours/minutes swapped, EDL source range in clip time, the audio event
dropped, a drop-frame declaration over non-drop timecode, and an unsanitised title. The one survivor
was dropping the blank line between SRT cues, and **I could not demonstrate harm**: ffmpeg 8.1.1 read
3 of 3 cues from both forms and re-emitted the missing blank lines, and it still read 2 of 2 when a
cue's own text was the numeral "2" — the ambiguity that would make the separator load-bearing. No
test was added for a property whose consequence I cannot measure with the parser on this machine;
recorded here so the next reader knows it was examined rather than missed.
`evidence/adversarial-pass-6-2026-08-09.md`.

## D-102

**`wsl.exe --` sent every command through a shell that ate the environment, so the OmniASR runtime
could never be provisioned.** Found by running the pipeline on a real 38-minute file
(`ZAR38MinTest.mp4`, 640×360 h264 25 fps, 2313.8 s) rather than on a fixture.

`hawedit-asr-setup` failed with uv's own error, `a value is required for '[PATH]'`. Measured cause —
the same probe under both spellings:

```
wsl.exe --      env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc …
    -> RUNTIME=[UNSET]   uv=none   python3.12=none
wsl.exe --exec  env HAWEDIT_WSL_RUNTIME=/tmp/x bash -lc …
    -> RUNTIME=[/tmp/x]  uv=~/.local/bin/uv   python3.12=~/.local/bin/python3.12
```

`--` only ends option parsing; the command line still goes through the distribution's default shell,
which expanded the `$VAR` references before the `bash -lc` script saw them **and** ran with a PATH
omitting `~/.local/bin`. So `venv="$HAWEDIT_WSL_RUNTIME/venv"` was empty and
`uv venv --python 3.12 ""` had no path to create. This is why M1.4 recorded "the WSL runtime itself
is not provisioned here either" — not an absent prerequisite, a broken command.

**The same bug had a second copy.** `WslOmniAsrProducer._prefix` was its own implementation of the
same three lines, also using `--`, and it passes `env PYTHONPATH=<source>` to reach
`hawedit.asr_worker` inside WSL. That assignment was eaten too, so Stage 1 would have died on an
unimportable worker however well the runtime was provisioned — a second failure with one cause, which
is what duplicated invocation logic buys. There is one prefix now, used by both.

**Decision: `--exec`, in the shared builder.** Verified end to end, not by inspection:
`hawedit-asr-setup` now prints `OmniASR import OK; CUDA GPUs visible: 2` and `READY`, having
installed the pinned `omnilingual-asr==0.2.0`, `klpt==0.1.7`, `fonttools==4.55.3` into a Python
3.12 venv inside WSL2.

**Measured next, and not fixed here:** the runtime is fingerprinted over **every `*.py` in the
package** (`package_fingerprint` hashes all of them), so editing any module — including the lint fix
in this very change — invalidates it and the pipeline reports "not provisioned" again. Seven
fingerprint directories had already accumulated on this machine, four carrying `.ready`. The venv is
shared, so re-provisioning is cheap (`Checked 3 packages in 1.80s`), but the error message cannot
distinguish *never provisioned* from *provisioned, then the source changed*, and those need different
actions — the same conflation D-099 fixed for downloaded-versus-runnable. Recorded rather than
patched, because narrowing the fingerprint to the worker's real import closure is a design step.
`evidence/wsl-exec-and-the-38-minute-run.md`.

## D-103

**One unalignable speech region discarded a whole 38-minute run.** Measured on
`ZAR38MinTest.mp4` (2313.8 s): Stage 0 cut **547** speech regions holding 2076.5 s of speech, and
one 316 ms region produced 15 CTC frames for 15 tokens. `AlignmentInfeasible` refused it — correctly;
inventing a word boundary is exactly what Kurdish invariant #5 forbids. But both producers built
their results with a generator expression:

```python
results = tuple(
    (segment, self.backend.transcribe_segment(segment.path, segment.duration_s))
    for segment in prepared
)
```

so the first raise discarded a finished Stage 0 and every other region's inference, and the operator
got **no transcript at all** for 38 minutes of Kurdish. 6 of 547 regions sit in that duration band,
so this is not a rare input.

**Decision: a failed region becomes a recorded failure, not an aborted run.** This repo already
settled the shape in `MeasurementSession.measure` — "a raised exception becomes a recorded failure
rather than an aborted run", because a run that dies on the first bad item produces no rate at all.
The same reasoning, one stage earlier. `transcribe_prepared_segments` is shared by both producers,
because the identical generator existed twice and D-102 had just finished paying for duplicated
invocation logic.

**The record lives in the artifact, not a log.** `RawTranscript.unaligned` carries each region's
bounds on the media clock and the reason. A transcript that quietly omits speech is worse than the
refusal it replaces: `transcript.raw.json` ships to the client (invariant #1), and a reader cannot
tell speech the model refused from silence that was never there. §5 states the same principle for
candidates — "that set is your only measure of recall".

**No text is kept for a failed region.** A region whose token count exceeds what its frames can emit
has produced text the audio cannot support, so shipping it as canonical would be the invented-content
failure invariant #5 exists to prevent. The honest record is that this much speech has no
transcription, with the reason.

**§5 is not contradicted.** BLUEPRINT's only statement about this file is "EXACTLY as ASR emitted.
Never modified. Ships to client." — it enumerates no fields. `unaligned` is metadata *about* the
emission rather than a modification of it, and it defaults to `()`, so a clean run's artifact is
byte-identical to before. `from_json` reads pre-D-103 transcripts with `.get`, because refusing to
read an old canonical artifact to satisfy a new field would break invariant #1 from the other side.

**Rejected: a threshold on how many regions may fail.** Any number would be guessed, which the hard
rules forbid. The only bound that needs no number is that *something* aligned: a run where nothing
aligned is refused rather than written as an empty transcript, since a file with no words and no text
would sail past every downstream stage as though the media had no speech.

**Rejected: pre-filtering short regions before inference.** It needs a minimum-duration threshold —
guessed again — and it would drop speech silently, which is the failure this change exists to make
impossible.

**Mutation audit 6/6.** Re-raising instead of recording CAUGHT (3), failures collected then dropped
from the artifact CAUGHT (1), a nothing-aligned run written as an empty transcript CAUGHT (1),
narrowing the catch to `AlignmentInfeasible` alone CAUGHT (3), reporting every region as unaligned —
the over-strict direction — CAUGHT (6) by the clean-run control, and a blank reason accepted CAUGHT
(1). That last one survived the first audit: I had written the guard and no test exercised it, which
is the same absence-of-a-check this whole iteration is about.
`evidence/one-region-discarded-a-38-minute-run.md`.

## D-104

**The frame-count guard graded its own parity step's output and refused a good extraction.** Found by
running the visual path on the real 38-minute file. It stopped after **three** windows:

```
✗ zar38final:s2:w0 planned 36 frames over 17720 ms and ffmpeg produced 34. One frame of tail
  rounding is normal; this is 2. The window likely runs past the end of the media …
```

The diagnosis in that message is wrong, and the files on disk prove it: `s2_w0/` holds **35** JPEGs.
ffmpeg delivered 35 of 36 — exactly the one tail frame the message itself calls normal — and then
this function's own even-alignment step (D-060, which drops a frame rather than let the processor pad
by repeating one) removed a second. The guard then compared **34** against `36 - 1` and raised. The
window sits early in a 2313.8 s file; every frame it asked for existed.

Any window whose planned count is even and whose delivered count is odd hit this — roughly half of
them, since `ceil(duration × 2.0)` is even about half the time.

**Decision: judge ffmpeg's delivery before trimming, and the trim separately.** `extracted` is what
the binary wrote; the plan comparison runs against that. `paths` is what the model is handed, and the
parity step still applies. Two facts, two checks, in the order the data flows.

**Rejected: widening the tolerance to two frames.** It is the obvious one-character fix and it is
wrong: a window the media genuinely does not cover also delivers two frames short, and that must stay
refused because an embedding of whatever frames existed describes less footage than the window claims.
Judging the delivered count separates the two cases; a tolerance cannot. The mutation audit pins this
— widening to 2 is CAUGHT by the control alone.

**A guard I added and then deleted.** I also added a check that the kept count is a whole number of
temporal patches. It survived mutation, and the reason is that it is **unreachable**: after trimming,
any count above `TEMPORAL_PATCH_FRAMES` is even by construction, so the branch can never fire. A
guard that cannot fire reads as protection and is not, so it was removed and the property is asserted
in a test across every odd delivery the plan allows instead. Second iteration running in which my own
new guard was the thing the audit caught (D-103's blank reason was the first).

**Also found by the audit: `len(extracted) > window.frame_count` had no test at all.** §3 Stage 2's
64-frame ceiling was enforced by a branch nothing exercised — replacing it with `if False:` left the
suite green. `-frames:v` makes an overshoot unlikely, which is exactly how a check goes unfired for
months. Now tested.

**Mutation audit 4/4** after the dead guard was removed: grading the truncated tuple CAUGHT (9),
widening the tolerance CAUGHT (1, the control alone), accepting more frames than planned CAUGHT (1,
the newly added test), and reverting the parity trim CAUGHT (3).

**Note on the audit harness itself:** a transient Windows file lock made one restore fail and left
`video_input.py` mutated. The backup on hand predated the fix, so the line was restored by hand and
the file verified byte-identical to the verified-green version before committing. The harness now
retries every write and re-reads to confirm — an audit that can corrupt the tree it audits is worse
than no audit.
`evidence/frame-count-guard-graded-its-own-output.md`.

## D-105

**All three visual models took one device flag, so §6's two-GPU video phase ran on one GPU.**
BLUEPRINT §6 is explicit and frozen:

```
VIDEO PHASE      GPU 0 → VideoChat3-4B      (segmented)
                 GPU 1 → Embedding / Reranker / TimeLens2  (sequential)
```

`pipeline.py` handed `--visual-device` (default `cuda:0`) to the embedder, the reranker **and** the
reader, so on hawapc01 all three landed on GPU 0 while GPU 1 held 1.3 GiB. The real 38-minute run died
with `CUDA out of memory. Tried to allocate 21.83 GiB. GPU 0 has a total capacity of 23.99 GiB of
which 3.59 GiB is free. Of the allocated memory 18.30 GiB is allocated by PyTorch`.

**Decision: `--index-device` (default `cuda:1`) carries Stage 2's embedding and reranking;
`--visual-device` keeps the Path B reader on GPU 0.** §6 supplies both assignments, so nothing is
chosen here. `--timelens-device` was already `cuda:1` and is unchanged. `build_parser` was extracted
from `main` so the defaults can be asserted: a comment claiming §6 is not §6 being followed.

**A refusal, because the defaults are two-GPU defaults.** On a one-GPU machine `cuda:1` used to die
inside torch with a device-ordinal error naming neither the stage nor the remedy. It now refuses up
front, names which stage wanted which device, and gives the flag to pass instead. The control is that
the devices a machine *does* have are accepted — a check refusing every CUDA device would satisfy the
refusal test and stop the machine §6 was written for from running at all.

**The first version of this fix had a test that measured nothing.** It asserted the *parsed
defaults*, and the audit showed reverting either Qwen model to `--visual-device` left the suite green:
a default nothing reads is not an assignment — D-094's substring failure in a new place. So the
composer construction was extracted into `build_visual_composer` and the test now asserts which
device each of the three models actually receives. Mutation audit **5/5** afterwards, with both
survivors caught by that one test.

**Measured after the change, and it did not clear the OOM:**

```
before   GPU 0: 18.30 GiB allocated,  3.59 GiB free      (embedder + reranker + reader)
after    GPU 0: 10.44 GiB allocated, 12.18 GiB free      (reader alone)
still    Tried to allocate 21.83 GiB
```

7.86 GiB freed on GPU 0 and Stage 2 moved to GPU 1, exactly as §6 intends — and the reader still asks
for a single 21.83 GiB tensor. So the packing was a real divergence with a real cost, and it was not
the whole cause. Reported as such rather than as a fix that worked.

**A hypothesis I checked and dropped.** §6 says the reader is "(segmented)", and I suspected the code
batched all windows into one forward. It does not: `read_scenes` is one call per window, with the
docstring "One call per window rather than one model batch: §3 calls segmentation mandatory". The
21.83 GiB is **one window**.

**What remains, measured but not guessed:** the largest survivor window holds **64 frames**, exactly
`MAX_FRAMES_PER_WINDOW`. One 64-frame window through VideoChat3-4B's preprocessing wants 21.83 GiB
beside its own 10.44 GiB of weights, which does not fit in 24 GiB. §3's ceiling and this checkpoint's
appetite are in tension on a 3090 Ti. Lowering the frame cap would be picking a threshold, which the
hard rules forbid — the next step is to **measure** the largest window this GPU can actually read and
record that number with the hardware that produced it.
`evidence/section-6-put-the-video-phase-on-one-gpu.md`.

## D-106

**The largest scene window a 3090 Ti can read through VideoChat3-4B is 8 frames; §3 plans 64.**
Measured on hawapc01 (23.99 GiB, weights resident 8.68 GiB) through the real `VideoChat3Reader`, one
model load reused, on the frames the 38-minute run extracted:

```
 frames  window_ms  peak GiB   result
      4       2000     12.00   OK
      6       3000     16.00   OK
      7       3500     18.58   OK
      8       4000     21.57   OK        <- 90 % of the card
      9       4500     16.33   OOM, wanted a further 6.91 GiB
     12       6000     22.09   OOM, wanted a further 12.28 GiB
     16       8000        -    OOM, wanted 21.83 GiB
     24      12000        -    OOM, wanted 49.11 GiB
     32      16000        -    OOM, wanted 87.31 GiB
     48      24000        -    OOM, wanted 196.44 GiB
```

**The demand is quadratic**, and the requested allocations fit `n squared` to two decimal places:
196.44/87.31 = 2.25 against (48/32)^2 = 2.25; 87.31/49.11 = 1.78 against (32/24)^2 = 1.78; and so on
down. Attention over vision tokens. Halving a window buys a quarter of the memory, so 8 against 64 is
not a tuning margin — it is a factor of 64 in demand, and extrapolating the fit puts a 64-frame window
near 350 GiB.

**One reading that looks anomalous is not.** The 64-frame attempt reported "wanted 10.91 GiB", less
than the 48-frame attempt's 196.44. That is the first allocation to *fail*, not the total need — peak
was already 15.42 GiB. Recorded because reading the headline instead of the raw numbers would have
inverted the conclusion.

**Decision: `MAX_FRAMES_PER_WINDOW = 64` stays, and is now recorded canonically.** It is §3's number
and BLUEPRINT is frozen. Quietly lowering it to make a run pass is the "weaken the check to make
something pass" move the hard rules forbid, so the constant is stated here and D-098's check now holds
the code to it: a future fix that edits it has to amend this record first.

**Rejected: truncating a planned window to what the reader can hold.** D-104's guard exists because
"an embedding of whatever frames existed would describe less footage than the window claims", and
reading 8 frames of a 64-frame window is that failure with the numbers changed.

**Rejected: sub-segmenting a window inside the reader.** §6's "(segmented)" already means one call per
window, and splitting a window further would need a rule for combining SV6D readings across chunks —
inventing a description of the scene from pieces, which is the kind of thing §5's schema exists to
prevent. It would also silently change what a window *means* to retrieval.

**What the resolution has to be, and why it is not in this commit:** windows must be *planned* small
enough for the reader, which moves the cap into `plan_scene_windows` and changes what a window is — on
hawapc01, 4-second windows rather than up to 32-second ones, and several times as many. That reshapes
Stage 2's retrieval unit and its cost, so it gets its own iteration and its own audit rather than being
bolted onto a measurement. `BLOCKED.md` #17.
`evidence/largest-window-a-3090ti-can-read.md`.

## D-107

**M0.4 claims invariant #1 is "enforced three ways", and one of the three was reached by no test.**
Adversarial pass #7 attacked M0.4 against the artifacts of the real 38-minute run — the
820,835-byte `transcript.raw.json`, its sha256 sidecar, and the norm derived from it — and then
reverted each enforcement mechanism.

**Everything held on the real artifacts.** The sidecar matched the file; a second write of *identical*
content was refused; one digit changed at byte ~410,000 of 820,835 was detected; a norm derived from a
different raw was refused; and the written file really is `-r--r--r--` `0o444`, as the docstring says.
Zero invariants broken.

**The gap was in the tests, not the code.** Neutralising `os.link(staging, path)` — the raw file's own
write-once link — left the whole suite green. The sidecar's link refuses first in every path a test
exercised, so the second layer was never reached.

It is not dead code. It is the layer that matters when the sidecar is **gone**, which is exactly the
state someone hiding a modification would create, since `verify_raw_integrity` needs that digest to
detect anything at all. Measured in that state: the second write is refused by the raw-file layer, the
raw bytes are unchanged, no sidecar is resurrected carrying the second write's digest, and no staging
file is left behind.

**Decision: test each layer in the state where it is the only one left.** One test deletes the sidecar
and asserts the refusal, the unchanged bytes, the absent sidecar and the clean directory; a control
asserts that with both artifacts present the refusal still comes from the *first* layer. The two
messages differ — "already exists or is being written" versus "already exists." — so the control cannot
be satisfied by breaking the layer the other test is about.

**A correction to my own method, recorded because it produced five false results.** The first attempt
replaced each `raise X(` line with `pass`, which orphaned the multi-line message and made the module
unparseable: five mechanisms reported RED that were `SyntaxError`, not protection. That is D-082's
wrong-reason catch, generated by my own harness. The rewritten harness neutralises the *condition*
instead and asserts `import hawedit.transcripts` succeeds before it trusts any verdict.

Mutation audit after the fix, **5/5**: the sidecar link CAUGHT (8), the raw-file link CAUGHT (1, the
new test alone), tamper evidence CAUGHT (2), stale-norm detection CAUGHT (1), and
`assert_model_input` CAUGHT (2). A no-op edit control stayed green, so the suite is not merely failing
on any change.
`evidence/adversarial-pass-7-2026-08-09.md`.

## D-108

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

## D-109

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
The aggregate is untouched, so nothing that read it changes. `from_json` reads pre-D-109 transcripts
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

## D-110

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

## D-111

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

## D-112

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

## D-113

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

## D-114

**§4.3.5's line breaking reached one of the two subtitle formats §2 delivers.** `build_ass` breaks
every caption from the word alignment through `wrap_caption_lines`; `build_srt` wrote
`sentence.text`, which is `" ".join(words)`. So the SRT that ships beside the MP4 handed its break
points to whatever wraps the cue at playback — with no word alignment, on Arabic script.

Measured on the real 38-minute run:

```
ZAR38MinTest.transcript.raw.json   878,195 bytes, 6,104 words, 185 complete sentences
sentences <= 60 s, so a clip can carry them   182
  wider than DEFAULT_MAX_CHARS_PER_LINE (32)  149   (81.9%)
  median width                                104 chars  -> 4 lines
  widest                                      973 chars  -> 33 lines
before the fix, every one of those was a single SRT line

longest sentence by time  102.5 s, 1,702 chars, 57 lines
  §4.2 never split it — unpunctuated ASR output, and the VAD-pause branch is dead
  (BLOCKED #14). `build_srt` refuses it for any clip shorter than 102.5 s, so it does
  not reach a sidecar; it is evidence about segmentation, not about wrapping.
```

§4.3.5 is a numbered requirement under a section titled **MANDATORY**: *"Insert line breaks
yourself from the word alignment … Automatic wrapping on RTL text produces bad break points
regardless."*

**Decision: the SRT calls the same `wrap_caption_lines`, at the same width, and the two formats are
pinned to each other by a test.** Reading §4.3.5 as covering the SRT is a judgement, and it is worth
naming: the requirement's parenthetical is about libass's `wrap_unicode` and native ASS. What
generalises is the sentence after it — *bad break points regardless* — and §2's diagram delivers
`SRT/ASS` as one item. SRT has no `WrapStyle: 2` to disable, so emitting the breaks is the only way
to keep them.

**Rejected: a wider line for the SRT.** A burned-in caption is 1080 px of vertical crop and an SRT
plays at an unknown width, so a different number is arguably right — and there is no measurement
behind any particular one. `DEFAULT_MAX_CHARS_PER_LINE` is this project's one recorded caption
width; a second, invented one would be a guessed threshold, and the never-guess rule covers exactly
this. The parameter is exposed the way `build_ass` exposes it, so a measured width later is a call
site change, not a fork.

**Rejected: capping a cue at two lines**, which is the common subtitling convention. The overflow
rule is unspecified, and every way to obey a cap — drop a word, merge lines past the width, split a
sentence into two cues with invented timings — is worse than a three-line cue. Measured, the real
run's longest sentence needs up to **33** lines for a sentence a clip can carry, and 57 for the longest `segment_sentences` produced.

**The independent witness is weaker than it looked, and that was measured rather than assumed.** The
ffmpeg round-trip was added so this module's own `parse_srt_times` is not the only reader that says
the file is intact. It does prove the breaks survive as in-cue line breaks. It does **not** enforce
the format's blank-line rule: separating the wrapped lines by a blank line round-trips through
ffmpeg **byte-identical to the correct file**, so that mutation passes the ffmpeg test on its own.
The blank-line hazard is pinned by the cue-splitting test instead, and both docstrings now say so —
a control that agrees for the wrong reason reads as protection it does not have (D-082).

**Mutation audit 6/6** against a baseline verified green first: the cue back on one line CAUGHT,
every word on its own line CAUGHT (the control — always-wrap satisfies the width assertion and is
equally wrong), the wrapper losing its last line CAUGHT, lines separated by a blank line CAUGHT,
breaking by character instead of by word CAUGHT, and the two formats given different widths CAUGHT.
`evidence/the-srt-let-the-player-choose-the-break-points.md`.

## D-115

**The CLI destroyed the report of a completed run by the act of capturing it.** Python takes the
standard streams' encoding from the locale; on Windows that is the ANSI code page — cp1252 on
hawapc01, which is §6's own machine — and this product's output is Sorani. Measured, with stdout
redirected to a file:

```
locale.getpreferredencoding(False)   cp1252
redirected stdout   encoding cp1252  errors surrogateescape
redirected stderr   encoding cp1252  errors backslashreplace

python -m hawedit.pipeline ZAR38MinTest.mp4 --omni-asr --json > report.json
  38-minute Stage 0, ~10 minutes on two 3090 Ti, 547 regions transcribed
  -> UnicodeEncodeError: 'charmap' codec can't encode characters in position 45257-45260
  -> exit 1, report.json is 0 bytes
```

Three distinct behaviours, one cause:

* **outside cp1252 → raises.** That is all Kurdish, plus `✓ ✗ →`. The report is not written at all.
* **inside cp1252 → written as a cp1252 byte.** A run with no transcript exited normally and wrote
  9 high bytes — `0xB7` for `·` five times, `0xA7` for `§`, `0x96`/`0x97` for the dashes — and the
  file **fails to decode as UTF-8** at the first one. No error, wrong bytes.
* **stderr → `backslashreplace`, so it mangles instead of raising.** `✗ canonical OmniASR WSL2
  runtime is not provisioned` reached the log as the literal `\u2717`, which is how it appeared in
  this loop's own captures for days.

None of it is visible from a console, where Python writes UTF-16 straight to the Windows terminal.
It appears the moment output is redirected, which is the moment someone is keeping it.

**Decision: one `use_utf8_streams()` in a new `cli.py`, called first in all five `main()`s, and the
test drives the entry points instead of checking the call.** `tests/test_cli.py` reads
`[project.scripts]` out of `pyproject.toml` and runs each declared module under
`PYTHONIOENCODING=cp1252`, then asserts the Sorani sentinel's **UTF-8 bytes** are on both streams.
A sixth entry point added without the fix fails there rather than in a client's terminal. Forcing
the codec is what makes it discriminate on the Linux runner, where the locale is UTF-8 and all of
this passes without any fix at all.

**Rejected: reconfiguring the streams in `__init__.py`.** It is the one file
`test_the_ledger_accounts_for_every_module` exempts, so logic there is logic with no recorded
status — and a library that reconfigures the importing process's stdout is wrong whatever the
ledger says.

**Rejected: `PYTHONUTF8=1` in the docs.** It is correct and it is not a fix: it puts the burden on
whoever runs the command, and the failure it prevents is silent in one of its two forms.

**Rejected: changing the error handlers.** Only the encoding is set. UTF-8 encodes every character
this product produces, so `surrogateescape` and `backslashreplace` stop being reachable for text
and stay in place for the one thing they are for — a path that came out of the filesystem with
lone surrogates in it.

**Mutation audit 8/8** against a baseline verified green first. Five of the eight remove the call
from one `main()` at a time, because a helper five callers must remember is exactly the shape of
D-105, D-108 and D-112 — *the function is tested, the trip to it is not*. All five CAUGHT, plus the
helper as a no-op CAUGHT, pinning only stdout CAUGHT, and pinning cp1252 instead of UTF-8 CAUGHT.

Verified on the artifact by re-running the command that failed: **1,010,979 bytes, decodes as
UTF-8, 20 keys, 6,104 words, 35,185 Kurdish characters**, `speech_without_transcription_ms: 664`
and its two gaps intact. `evidence/the-report-died-on-the-way-to-the-file.md`.

## D-116

**§5's rejection set had a type, validation, `to_dict`/`from_dict` and its own tests, and nothing in
`src/` ever constructed one.** §5: *"Rejection is a first-class outcome. Every rejected candidate
keeps a `reject_reason` and its `discovery_path`. That set is your only measure of recall."* §8.2
measures candidate Recall@20 **per discovery path** and uses it to decide whether the dual-path cost
is justified — *"if Path B never surfaces a winner Path A missed, collapse it."*

Measured:

```
RejectedCandidate constructed in src/hawedit  : 0 sites
RejectedCandidate constructed in tests/       : 4 sites
```

Never computed, not computed and discarded — the difference D-103 and D-109 turn on. The runner
*decides* which candidate survives in two places and simply returns the winner: on the real
38-minute run recorded in D-108, Stage 3 produced **7** candidates, one was chosen, and the other
six left no trace in the artifact or anywhere else.

**Decision: one producer, taken once, after the selection settles.** `_rejected_candidates` builds
the record from `merged` minus the chosen survivor. The survivor is now chosen in a single place
rather than again inside Stage 4, because a candidate ruled out by two decisions would be recorded
twice and counted twice in the recall it is the only measure of. Choosing there also means the
record exists on a run whose Stage 4 is blocked, which is every run on this machine until
`BLOCKED.md` #3 clears.

**The reason is read off a computation the runner already performed, never invented for the
record.** `_complete_sentences_within` is now shared between the selector and the reason, so the two
cannot drift into a rejection that says *"no complete sentence lies inside it"* about a candidate
`_automatic_sentence_selection` would have accepted. The three reasons are eligibility, containment
of the selected span, and rank — in that order, because the earlier ones are the specific answer and
rank is what is left.

**Nothing is recorded when nothing chose.** A run that never reached a selection did not reject
anything, and claiming otherwise puts candidates in §8.2's rejection column that no decision ruled
out. That is also the mutation that would otherwise satisfy every positive test.

**`rejected_by_path` names every path that found a candidate, at zero if it lost none.** A path
missing from the split cannot be told apart from a path that was never run, which is the same reason
D-110 reports zero gaps explicitly rather than omitting the key.

**Rejected: recording Stage 2's discarded windows too.** On the real run 641 windows were indexed,
50 retrieved and 7 kept, so 634 were never retrieved and 43 were reranked and dropped — a far larger
set. They are **not candidates**: a window has no `discovery_path` of its own, and filing it under
one would credit a path with a rejection it never made, which is exactly what `_assert_path` exists
to prevent. §8.2's Recall@K over retrieval depth is a separate measurement on a separate unit, and
`BLOCKED.md` #17 already holds the question of what that unit should be.

**Mutation audit 6/6** against a baseline verified green first: the rejections never reaching the run
CAUGHT, the chosen survivor recorded as rejected too CAUGHT, one generic reason for every rejection
CAUGHT, recording rejections when nothing chose CAUGHT (by the control alone), a path that lost
nothing left out of the split CAUGHT, and the empty set omitted rather than reported CAUGHT.

**What this iteration could not re-measure, and why.** The intent was to take a fresh 38-minute
number rather than cite D-108's. That run died in Stage 2 before Stage 3: with no `--gemini` there
is no verbal candidate, so `pipeline.py`'s retrieval query falls back to `normalized.text_ckb` — the
**whole 35,185-character transcript** — and the reranker asked for **40.89 GiB** on a 23.99 GiB card.
A separate defect with its own iteration; named here so the gap in this entry's numbers is not
mistaken for a measurement.
`evidence/the-rejection-set-had-no-producer.md`.

## D-117

**§3 Stage 2's retrieval query was the corpus.** With no `--visual-query` and no Path A candidate
to anchor one, `pipeline.py` passed `normalized.text_ckb` — the whole normalized transcript — to
`VisualComposer.discover`, which embeds it and hands it to the reranker for every hit. Found by
running the real 38-minute file; reproduced at the model boundary rather than inferred from the
crash:

```
Qwen3-VL-Embedding-2B on cuda:1, weights resident 3.96 GiB, card 23.99 GiB

   chars   tokens  embed_text
     200      167  fits, peak  4.04 GiB
   1,000      755  fits, peak  4.27 GiB
   2,000    1,481  fits, peak  4.56 GiB
   4,000    2,997  fits, peak  5.69 GiB
   8,000    5,988  fits, peak  9.86 GiB
  16,000   11,908  OOM
  35,185   26,191  OOM — tried to allocate 40.89 GiB
```

35,185 chars is this media's real transcript, and 40.89 GiB is the exact figure the composed run
died on. The demand is quadratic in tokens: 5,988 tokens costs 5.9 GiB of activations, twice that
needs four times as much and there is no card here that holds it.

**It breaks in both directions at once.** Where it does *not* fit, the run dies in Stage 2 after
Stage 0 has demuxed 38 minutes. Where it *does* fit — a short media — every window is ranked
against the entire episode, which orders nothing in particular and puts a number in §8.2's
Recall@K column that means less than it looks. The second failure is the quiet one, and it is the
reason the fix is not a size limit.

**Decision: Stage 2 refuses when it has no query, and names what would give it one.**
`StageSkipped(stage="visual_index", blocked_by=("a retrieval query",))`, raised before any frame is
extracted, so a refusal costs no GPU time. §3 Stage 2 retrieves *against a query*; a run with none
has nothing to retrieve against, and this is the same shape as `rerank_and_keep` refusing a media
too short for the survivor slice rather than shortening it.

**Rejected: truncating the transcript to some length.** It is a guessed threshold — the never-guess
rule covers exactly this — and it would fix only the crash. A 4,000-character prefix of an episode
is no more a query than the whole of it.

**Rejected: a maximum query length in `qwen_visual.py`.** The measured ceiling is *this* card's, and
D-108 established the principle for the sibling case: "the default is §3's ceiling, so no machine
inherits another's limit". A ceiling written into the model boundary would be one machine's number
in a shared file, and it would still let a caller send the corpus on a bigger card.

**Rejected: making it an error rather than a skip.** Every other unavailable stage in this runner is
a named `StageSkipped`, the CLI exits non-zero on an incomplete run, and Path A alone is a legitimate
one-sided union — §3 is explicit that a verbal-only moment is what the dual path exists to protect.

**Mutation audit 5/5** against a baseline verified green first: the transcript back as the query
CAUGHT, `--visual-query` ignored so Stage 2 always refuses CAUGHT (the control — refusing everything
satisfies the positive test and deletes the one invocation that works), a verbal anchor no longer
supplying a query CAUGHT (the second control), the skip recorded while the composer runs anyway
CAUGHT, and the refusal naming no blocker CAUGHT.
`evidence/adversarial-pass-9-2026-08-09.md`.

## D-118

**One survivor Path B could not read discarded every other candidate.** `VideoChat3Reader.read_scenes`
was `tuple(self.read_window(w) for w in windows)` — no per-window failure path — so a single
`PathBError` aborted the whole of Stage 3 Path B. Found by running the real 38-minute file with a
bounded query (D-117), which reached the reader for the first time:

```
Stage 0 demux 38 min -> 641 windows planned and embedded -> 50 retrieved -> 7 survivors
window 1 of 7:
  ✗ the model returned no usable line for ['subject', 'aesthetics', 'camera', 'editing',
    'narrative', 'retention']
result: 0 candidates
```

The refusal itself is **correct**. §3 Stage 3 fixes the schema at six dimensions and rejects output
with no timeline evidence; `SV6D_PROMPT` asks for *"the number alone, no unit"* and this window — a
static logo card — answered `subject | 0.0 - 3.5 | …`, a range. What was wrong was the blast radius.
This is the shape D-103 fixed in Stage 1, where one unalignable region discarded a 38-minute
transcript.

**The format is not the defect, and that was measured before assuming it.** Twelve real windows from
the same run were read back through the real checkpoint on `cuda:0`:

```
12 windows, 4.00 / 3.50 / 2.50 s, 8.39 GiB weights resident
lines parseable : 72/72
shape of the time: {'point': 12}
```

So the prompt's contract holds on real footage and the range is the exception. Widening `_LINE` to
accept a range would mean choosing whether the moment is the start, the end or the middle — a
guessed answer to a question the model did not answer — so the refusal stays and the run survives it.

**Decision: a window the reader refuses is recorded, not raised.** `UnreadableScene(window_id, in_ms,
out_ms, reason)` carries each one; `SceneReadings` is what `read_scenes` returns and `PathBDiscovery`
what `discover_visual` returns; `VisualDiscoveryResult.unreadable` puts it in the emitted report,
empty case included (D-110's rule).

**`discover_visual` still refuses when nothing was readable.** Some readings is a partial answer with
its gaps named; none at all is Path B reporting a result having produced nothing. That is the only
bound here that needs no chosen threshold, and D-103 drew the same line.

**The exactness guard was kept, not relaxed.** It was "candidates == survivors"; it is now
"candidates ∪ unreadable == survivors". A scene still cannot go missing between the reranker and
Stage 4, which is what the guard was for — and a *model* that silently omits a window is still
refused, because the omission and the refusal are now different facts.

**Rejected: skipping the window silently.** "Six candidates" and "seven, one of which vanished" are
different, and §8.2 counts Recall@K on this list.

**Rejected: `UnreadableScene` reusing `RejectedCandidate` (D-116).** A rejected candidate is one a
decision ruled out; this is a survivor no decision ever got to see. Filing them together would put
scenes in the recall denominator that Stage 3 never scored.

**Mutation audit 8/8** — and the first run was **7/8**, with the defect itself surviving. Every test
written for it used a fake reader that builds `SceneReadings` directly, so reverting `read_scenes` to
abort left the suite green: the function is tested, the trip to it is not, for the fourth time
(D-105, D-108, D-112). Closed by driving the **real** `read_scenes` through the file's existing stub
processor with the recorded range output as one of three answers.
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

**`len(paths) > count` guards a reachable state, not a hypothetical.** The work directory is named
after the candidate, so a re-run asking for fewer frames than a previous one finds the previous run's
extra JPEGs in the glob and would send them. The test creates exactly that: 8 frames, then a request
for 2.

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

## D-128

**Adversarial pass #15 took M2.6 — the §3 Stage 4 judge contract, DONE and never attacked — and six
of nine mechanisms held. The row's own words, "promotion needs a clear win on ≥20 real items, never a
tie", were the thing that was not held.**

```
CAUGHT  the tier ceiling becomes the 360K with-video figure it exists to refuse
MISSED  the ceiling is exclusive, so a request exactly at 200,000 tokens passes
CAUGHT  an uncounted request is treated as a small one
CAUGHT  a candidate Path A already scored can be re-sent for discovery
CAUGHT  the regression floor drops to one item
CAUGHT  an empty regression set promotes the shadow
CAUGHT  a set below the floor promotes the shadow
MISSED  a tie promotes the shadow
MISSED  more than 20 keyframes are accepted

6/9
```

**The tie test measures the floor, and its assertion matches a word every decision prints.**
`test_a_shadow_that_merely_ties_is_not_promoted` calls `decide_judge(incumbent_wins=5,
shadow_wins=5)` — **10 items**, below the 20-item floor — so the answer comes from the floor branch
and the tie rule is never reached. Measured:

```
total 10   switch False   answered by "10 items is below the 20-item floor"
total 20   switch False   answered by "gemini-3.1-pro tied with the incumbent"
```

And its reason assertion looks for `"tie"`, which matches **ties 0** in the header line every
decision carries whatever it decided. Two independent reasons to pass, neither of them the tie rule,
so `shadow_wins <= incumbent_wins` → `<` left the whole suite green. Ten and ten clears the floor, so
only the tie rule can answer; the new test also asserts the floor did *not* answer, which is what
makes it stay honest if the floor ever moves.

**A control was needed in the other direction.** Refusing every tie *and* every win satisfies the
tie test and pins the incumbent for ever — §3 asks for a managed migration, not a locked door. So
eleven against ten must promote.

**The ceiling boundary.** §3: *"Keep each request **under** 200K tokens."* Exactly 200,000 is not
under it, and `>=` → `>` was free: the existing tests assert the constant and refuse requests well
over it, so the operator could move. D-098's and D-122's shape, third occurrence. Pinned at the
ceiling, with one token below it as the control — otherwise a blanket refusal of the with-video mode
§3 prescribes would pass.

**The keyframe cap.** §3 Stage 4's payload is "~20 keyframes" and nothing held the limit. Inline
image bytes are billed, so an unbounded count is a cost defect as much as a contract one — D-126
found the same module's frames could come from anywhere in the media.

**A control failed for a real reason, and the code was right.** The 20-frame control first raised
*"judge keyframes … fall outside candidate 0..0ms"*: `JudgeRequest` validates the span as well as the
count, and the count check runs first. The control now supplies a span, and the ordering is recorded
in the test — that is why the 21-frame refusal is the count and not the span.

**Mutation audit 9/9 after.** No production code changed: all nine mechanisms were already right, and
three were unheld.
`evidence/adversarial-pass-15-2026-08-09.md`.

## D-129

**Adversarial pass #16 took M2.7 — the end-to-end runner, DONE, 9,594 characters of claims and the
largest unaudited surface left. Three of seven mechanisms held, and the reason the other four were
free is that `PipelineRun.complete` was never once True in the whole suite.**

```
CAUGHT  an incomplete run exits 0
CAUGHT  an incomplete run exits 2, the code a refusal uses
MISSED  a run with skipped stages calls itself complete
MISSED  a run with no visual windows calls itself complete
MISSED  a run with no candidates calls itself complete
MISSED  Stage 5 fuses against cuts from nowhere on this video
CAUGHT  the window plan ignores the cuts Stage 0 found

3/7
```

**`complete` decides the CLI's exit code — `return 0 if run.complete else 1` — and it has eleven
conjuncts. Three of them could each be replaced by `True` with 1,302 tests green.** Measured, the
cause is that no test ever reached the True branch:

```
full_run.complete            False
  skipped                    ['visual_index', 'discovery']
  candidates                 NO      every other conjunct  OK
```

Even the six-stage `full_run` is incomplete, so a conjunct and a no-op were indistinguishable. The
suite now has a run where **every** stage produced something — `complete is True`, `skipped() == ()`
— built through the real `run_pipeline` with a discovery producer, a visual composer and a judge
rather than by fabricating dataclasses, so it cannot drift from the product. Each of the three
conjuncts is then removed from *that* run with `replace()`, which is the only construction under
which removing one proves anything.

**A stale claim: the cell says a bare run exits 1 "naming the four blocked stages". It names eight.**
Measured: `['transcript', 'index', 'visual_index', 'discovery', 'editorial', 'boundary', 'render',
'delivery']`. True when D-032 wrote it; Stage 2's visual half, boundary, render and delivery have all
been added since. Same class as M1.6's "five repositories" (D-127) — a count nobody re-derived.

**Stage 5's cuts are asserted on the input, and the reason is measured.** §3 Stage 5 takes the
**latest** of its out-point signals, and on the only media in this checkout natural silence is the
end of the VAD speech region — 4162 ms, the whole file. Driven through the real runner with an anchor
300 ms before the 2800 ms cut: `out_extended_by='natural_silence'`, `final_out=4162`. So **no anchor
makes the shot cut decide the outcome here**, and the test asserts that what Stage 5 was handed is
what Stage 0 measured off the file. The two sides come from different places, so it is not the request
echoed back.

**My own first attempt at both was wrong, and the controls are what caught it.**

* The mutation "Stage 5 fuses against a constant" first used `(1_400, 2_800)` — *the fixture's own
  cuts*. It cannot change behaviour, so its SURVIVED meant nothing. Re-run with `(9_000, 9_500)` it
  is a real survivor, and now CAUGHT.
* The first three `complete` tests were built on a synthetic run that was **already** incomplete for
  other reasons, so removing a conjunct proved nothing. The control —
  `test_a_run_where_every_stage_produced_something_is_complete` — failed, which is the only reason I
  found out. A control that cannot fail is not a control.

**Mutation audit 7/7 after.** No production code changed.
`evidence/adversarial-pass-16-2026-08-09.md`.

## D-130

**Adversarial pass #17 took M0.7 — the ASR throughput harness, DONE and never attacked. Seven of nine
mechanisms held. Both survivors were the hard rule verbatim, in the layer that publishes the report.**

Every claim in this row is a number, and the rule is *"Unmeasured is None, never 0.0 — and never a
score."* The per-measurement layer holds it. The aggregate did not:

```
CAUGHT  a corpus with no long audio reports a 0.0 failure rate
CAUGHT  the long-audio rate no longer refuses mixed hardware
CAUGHT  measurements from two machines are combined
CAUGHT  RTF is inverted — duration over wall clock
CAUGHT  a failed item reads as a successful one
CAUGHT  an unprobed VRAM figure becomes 0 instead of None      (per measurement)
MISSED  an unmeasured peak VRAM aggregates to 0                (per model report)
MISSED  an empty score set reports mean RTF 0.0
CAUGHT  the adapter is named by class alone, not module-qualified (D-097)

7/9
```

**`mean_rtf … if self.scores else 0.0` is not a missing number — it is *infinitely fast*.** The most
flattering possible wrong answer, in the one field §3 Stage 1 warns about: *"Do not derive wall-clock
promises for hawapc01 from them. Measure on your own hardware in §8.1 and put **that** number in the
capacity plan."* And `worst_rtf` would read 0.0 alongside it: never slower than instant.

**`peak_vram_bytes=max(vram) if vram else 0` reads as "measured, and it used none"** — for a model §7
sizes at ~17 GiB. §6's whole two-GPU layout is derived from that figure, so a zero is not a gap in a
report, it is a capacity plan that fits anything.

**Asserted on the written document, not the property.** Both tests read `to_dict()`, because the JSON
is what a capacity plan gets read off and a `float | None` property is not what anybody sees.

**A control was needed, and it is the interesting half.** Returning `None` unconditionally satisfies
both tests and erases every real measurement — the harness exists to produce these figures. So a
probed run must still report 17 GiB, and a scored run must still report its mean and worst RTF.

**My first VRAM test was one call away from the defect, and the audit said so.** The mutation lives in
`run_benchmark`'s aggregation; my test constructed a `ModelReport` directly and so only exercised
`to_dict`'s passthrough — it passed with the mutation in place. That is the same pattern this pass
series keeps finding in the suite, now in my own test, caught because the audit was re-run rather than
assumed. The test drives `run_benchmark` now, whose session supplies no VRAM probe, with a
probe-supplying control beside it.

**Mutation audit 9/9 after.** No production code changed: all nine mechanisms were already right and
two were unheld one layer up from where they are enforced.
`evidence/adversarial-pass-17-2026-08-09.md`.

## D-131

**§8.1's last metric was computed for every scored item and dropped at the report boundary.** M0.8 is
DONE for "Alignment-accuracy metric against CTC emissions (§8.1 last metric)", and the metric never
reached the document §8.1 *is*.

Measured, before changing anything, on a six-item corpus with reference timings and a hypothesis
shifted 30 ms:

```
per item, computed and stored on ItemScore.alignment
  hewler-1: matched 2/2  onset 30.0 ms  offset 30.0 ms  within 1.00 @ 50 ms  coverage 1.00
  hewler-2: matched 2/2  onset 30.0 ms  offset 30.0 ms  within 1.00 @ 50 ms  coverage 1.00

keys in the written model report
  model_id, adapter_impls, scored_items, failed_items, normalized_cer, spacing_free_cer,
  normalized_cer_by_dialect, named_entity_error, code_switch_error, mean_rtf, worst_rtf,
  long_audio_failure_rate, peak_vram_bytes

any key mentioning alignment            []
'align' anywhere in the whole JSON      False
```

**Computed and discarded, not never computed** — the distinction the loop asks for, and the same shape
as D-070's `natural_silence_ms` (derived, then spent on nothing) and D-109's per-segment
`mean_logprob` (averaged away). Found by following pass #17's finding: that pass showed the
`None`-versus-0.0 rule held per measurement and not in the aggregate, so the aggregate is where the
next metric's gap would be. It was worse than a gap — the field was absent.

**Decision: `ModelReport.alignment` aggregates it, weighted by matched words.** The same weighting
`_micro_cer` uses for characters, and for the same reason: a two-word item and a sixty-word one are
not equal evidence about timing.

**Coverage travels with the errors.** `AlignmentAccuracy` already says why — *"a tiny mean error over
two matched words out of sixty is not a good alignment, it is a bad transcription"* — so an aggregate
carrying the errors alone would hide exactly the case the type was written to expose. `matched_words`,
`reference_words` and `scored_items` are all emitted beside it.

**`None` when nothing was aligned, never a zero.** 0.0 ms of error is the *best possible score*, so a
zero here is the most flattering number the report could invent — pass #17's rule (D-130), applied at
the point of adding a field rather than discovered later. The key is always present so its emptiness
is readable (D-110's rule).

**Two tolerances in one report are refused, not averaged.** A within-tolerance rate mixed across a
50 ms and a 200 ms bar was measured at neither. That is `assert_one_hardware`'s objection one metric
over, and it is a refusal rather than a chosen reconciliation because no reconciliation exists.

**Rejected: a macro mean of the per-item rates.** It is one line shorter and it lets a two-word item
outweigh a sixty-word one, which is the mistake `_micro_cer`'s own docstring exists to warn about.

**Rejected: emitting the per-item `AlignmentAccuracy` list.** §8.1 is a comparison between models; a
per-item dump belongs to the evidence file, and the report already summarises every other metric.

**The recorded schema caught the new key, and that is the system working.**
`test_the_emitted_report_schema_is_recorded_field_by_field` (D-094) went red the moment `alignment`
appeared, so adding a field to the artifact is a deliberate edit to the recorded contract rather than
a silent change. Declared there with the reason.

**Mutation audit 5/5:** dropping the aggregate again CAUGHT, an unmeasured alignment returning a
perfect zero CAUGHT, coverage omitted CAUGHT, two tolerances averaged CAUGHT, and the
within-tolerance rate ignoring the timings CAUGHT — the last by the control, which shifts the
hypothesis past the 50 ms bar and requires the rate to move from 1.0 to 0.0.
`evidence/section-8-1s-last-metric-never-reached-the-report.md`.

## D-132

**Stage 0 was not re-runnable, and §1 says it is.** BLUEPRINT §1: *"Every stage emits and consumes
JSON | Stages are independently testable, replaceable, **re-runnable**"*, and the 10/10 definition
asks for atomic/resumable delivery. Measured on `ZAR38MinTest.mp4` before changing anything:

```
Stage 0, first run                    second run, same work directory
  extract_audio      69.9 s             extract_audio (again)  69.5 s   rewritten: True
  extract_proxy      30.3 s             extract_proxy (again)  30.3 s   rewritten: True
  detect_speech      18.2 s
  probe_duration_ms   0.1 s
  detect_shots       32.9 s
  TOTAL             151.4 s           -> 100.2 s of 151.4 s redone (66%)
```

Both files were rewritten byte-for-byte. Two thirds of the stage, spent re-deriving what was
already on disk — and every iteration of this loop that touched the real file paid it.

**Decision: a content digest as the cache key, not size-and-mtime.** SHA-256 of the 82,446,418-byte
source takes **0.1 s** against the 100.2 s it avoids, so the cheap key bought nothing worth having;
and it needs no threshold guessed, which size-and-mtime does the moment two runs land in the same
second. It also catches a source replaced by a different file of the same length, which is the case
`test_a_changed_source_is_extracted_again…` now pins.

**Reuse is verified, never assumed** — the shape D-121 uses for the ffmpeg archive and invariant #1
uses for `transcript.raw.json`. A `.provenance.json` sidecar beside each artifact records the source
digest, the command with the destination removed, and the output size; all three must match or the
extraction runs again. Every failure mode falls through to extracting: the expensive answer, never
the wrong one.

**The sidecar is written after the output and removed before a run.** Written after, so a truncated
output has no matching record. Removed before, so a run that dies leaves no record at all — which
matters in one case the size check alone cannot see: two settings alternating, one crashing, leaving
*exactly* the recorded byte count under a record that still names the right command and source.
Contrived deliberately in `test_a_crashed_run_leaves_no_record…`, because a guard this project keeps
has to be one a test can distinguish.

**An extraction that wrote nothing is now named.** Found by the existing command-capturing tests:
their fake `_run` recorded argv without producing a file, and the sidecar's own `stat()` raised a
bare `FileNotFoundError` pointing at provenance bookkeeping instead of at the pass that wrote
nothing. ffmpeg exiting 0 without writing is the shape `curl --fail` exists for (D-121), so it is an
`IngestError` naming the destination. Their fake now writes its output too — a fake that writes
nothing is not standing in for ffmpeg, it is standing in for this failure.

**`_assert_audio_format` runs on every call, reused or not.** The format Stage 1 and the VAD assume
is a property of the file that arrives, not of the run that happened to write it — otherwise the
guard is skipped exactly when the file has sat on disk long enough to change.

**One guard in `_extract_once`, not one per extractor,** so the proxy's 30.3 s is covered by the same
mechanism and cannot drift from the audio's.

**Rejected: reusing `detect_speech`, `detect_shots` and `probe_duration_ms` too.** They are 51.2 s of
the 151.4, and their outputs are already JSON the runner writes — caching them means a second
provenance mechanism over data the pipeline report already carries. Not worth a second mechanism
until someone measures a resume that hurts.

**Rejected: a `--force` flag.** Deleting the sidecar re-extracts, and there is no operation the flag
would enable that `rm` does not.

**Mutation audit 8/8.** After the first pass reported **7/8** with the digest comparison SURVIVING:
`test_a_changed_source_…` handed over a *differently named* file, and `-i <source>` is part of the
recorded command, so `same_command` answered first and the digest was never consulted — the eighth
consecutive instance of a test that cannot distinguish the rule it names (D-124, D-125, D-126,
D-128, D-129, D-130, D-131). Rewritten to hold the path constant and change only the content, which
is both what binds the digest and what actually happens in practice.
`evidence/two-thirds-of-stage-0-redone-on-every-run.md`.

## D-133

**Adversarial pass #18, on M3.1.** The row is DONE for four deliverables — *shaping, stack check,
font coverage, own line breaks* — and its cell substantiates one of them. Two of the four turned out
not to hold, both in the same guard, and the pass found two further unheld mechanisms by mutation.

### The required glyph set omitted the two letters §4.1's normalizer produces

`KURDISH_REQUIRED_GLYPHS` was §4.3.4's nine characters plus D-013's two heh forms. It did not
contain `ک` U+06A9 or `ی` U+06CC — and `normalize_sorani` **converts Arabic `ك`/`ي` into exactly
those**, which §4.1 calls "the Farsi forms Kurdish uses". Measured:

```
normalize_sorani('كوردي')
  in :  ك=U+0643 و=U+0648 ر=U+0631 د=U+062F ي=U+064A
  out:  ک=U+06A9 و=U+0648 ر=U+0631 د=U+062F ی=U+06CC

GOLDEN_CAPTION_TEXT = ڕۆژنامەوانی کوردی لە هەولێر.
  Kurdish-specific letters in it that no font was required to have:  ک U+06A9   ی U+06CC
```

So every normalized transcript in this product is written in two characters the font requirement
did not mention, and one of them is in the project's own §4.3.6 reference line. `captions.py`'s own
comment on `GOLDEN_CAPTION_TEXT` even said the line exercises *"ڕ ۆ ژ ە ی from §4.3.4's required
set"* — naming `ی` as required while the set contained no `ی`. The contradiction was sitting in the
file, readable, for as long as the row has said DONE.

**These are not the Arabic kaf and yeh a font is likely to have.** Proved by subsetting the real
shipped Noto Naskh Arabic to drop *only* U+06A9, keeping U+0643 and every other glyph, feature and
name:

```
subset font: U+06A9 present? False   U+0643 (Arabic kaf) present? True   codepoints 1122
assert_font_covers_kurdish: PASSED — a font with no Kurdish kaf is certified
```

And the pixels, which is where §4.3 says the failure shows up:

```
shipped    8,367 subpixels above black
no-keheh   9,267 subpixels above black
pixels differ: True   subpixels changed: 15,999 (0.26% of the frame)
```

**§4.3.4 says missing glyphs render as boxes; measured, it is worse than that.** libass falls back
to another font for the single character, so `کوردی` comes apart into a detached, differently sized
`ک` and `وردی` — the viewer reads one word as two, in a caption that looks entirely present. The
frame *gains* ink rather than losing it, which is why "there is text on screen" is no evidence.

**Decision: extend the frozen list by two, derived from the normalizer rather than from an
alphabet.** BLUEPRINT is frozen and §4.3.4's nine stay; this is the same divergence D-013 already
took for `ھ`, recorded the same way. The addition is not my reading of Sorani orthography — it is
what `normalize_sorani` returns, asserted as such: the test derives the requirement by running the
normalizer, so a future change to §4.1's target forms moves the font requirement with it.

**Rejected: requiring every Arabic-script letter the normalizer can emit.** That pulls in baseline
Arabic (ا د ر ل م ن و) which any Arabic font has, and the check's value is in naming the
*Kurdish-specific* characters a plausible font lacks. The test therefore bounds itself above
U+0660 and says so.

### The check had no caller in `src/`

`assert_font_covers_kurdish` was called from `tests/test_captions.py` and **nowhere else in the
product** — while its own docstring says "this runs at build time rather than being trusted". It ran
at neither build time nor the burn. `render_clip` takes `fonts_dir: Path` and hands it to
`subtitle_filter`; nothing ever looked inside it. And `pipeline._runtime_fonts_dir()` has an
**installed** branch — `sys.prefix/share/hawedit/assets/fonts` — so a real deployment reads a
directory no test has ever seen.

`assert_fonts_dir_covers_kurdish` is the directory-level form, called in `render_clip` beside
`assert_rtl_stack`, for the reason that call already gives: *"Checked here, not only in the golden
test."* One guard where every burn routes, not one per caller.

**Directory-level rather than by family name, and the shortfall is named.** libass searches the
directory, so a second non-covering font there is not a failure — refusing on it would fire on any
host that keeps two fonts. What this therefore does **not** verify is that the font libass resolves
*for the family name the ASS asks for* is the covering one; mapping family name to file means
reading each font's name table, and inventing that resolution without being able to check it against
libass's own is how a guard starts lying. Recorded here rather than guessed.

**Rejected: checking the burned-in frame for boxes.** The decisive artifact test, and there is no
cheap way to distinguish a tofu box from legitimate ink after the encode. The subset-font render
above is that measurement done once, by hand, as evidence.

### Two mechanisms M3.1 claimed that no test held

The audit's first pass was **9/11**, both survivors on the *stack check*:

* **`--disable-libass` beating `--enable-libass` was untested.** Every other refusal reaches `None`
  by absence, so deleting the `disabled` precedence changed nothing the suite could see. It matters
  only when both flags are present — a build script appending `--disable-libass` to an inherited
  `--enable-libass` base — which is the shape audit finding #4 was originally about. Now pinned in
  both forms, including that a linked `libass.so` must not rescue an explicitly disabled build, with
  a control requiring the same line minus the `--disable-` to be accepted.
* **`render_clip`'s own `assert_rtl_stack` call could be deleted unnoticed.** The comment beside it
  claims it is checked at the burn and nothing checked that. Same shape as the font check having no
  caller at all — wiring, which is what D-105 and D-108 were both about.

**Mutation audit 11/11** after those two tests: the required set reverted CAUGHT, the burn's font
check removed CAUGHT, an empty fonts directory accepted CAUGHT, a non-covering font accepted CAUGHT,
`shaping=auto` CAUGHT, the disable precedence CAUGHT, the burn's stack check removed CAUGHT, a
missing glyph reported as covered CAUGHT, `WrapStyle: 0` CAUGHT, the `\N` not emitted CAUGHT, and
everything on one line CAUGHT.

**What survived the pass:** shaping and own-line-breaks held completely — three mutations each
against the pixel-level tests from the 2026-08-08 pass, all caught. Nothing about §4.3.1, §4.3.3,
§4.3.5 or §4.3.6 was found wanting. `evidence/adversarial-pass-18-2026-08-10.md`.

## D-134

**Adversarial pass #19, on M2.1.** The runner's §2 text index was one document for the whole
episode, so BM25 had nothing to rank and nothing to hand Stage 5. Measured on the real
38-minute transcript (6,104 words, 35,185 chars, 186 sentences):

```
from_transcript (what the runner built)     from_sentences (what existed, unused)
  documents                   1               documents                   186
  distinct word terms      2,784               distinct word terms      2,784
  distinct idf values          1               distinct idf values         37
  idf range         0.287682..0.287682         idf range      0.855352..4.825644
  average doc length   6,123.0 tokens          average doc length    32.9 tokens

  search("کوردستان") -> 1 hit, window 322..2,313,729 ms — the whole 38.6 minutes
```

**Arithmetic, not a preference.** BM25's idf is `log(1 + (N - df + 0.5)/(df + 0.5))`. At N=1 every
term has df=1, so every term's idf is `log(1 + 0.5/1.5) = 0.287682` — a single value across the
whole vocabulary, which means rarity is invisible; length normalization compares the document to
itself; and there is exactly one document any query can return. §2's paragraph is about matching
Sorani variants *across passages*, and there was one passage.

**Decision: `pipeline.py` builds `from_sentences`, three lines later than it built the old one.**
The sentences were already being computed immediately below — `from_sentences`'s own docstring
says the per-sentence form is "what lets a hit hand Stage 5 a real time window instead of a whole
episode" — so this is a reordering plus a factory swap. After: 186 documents, 37 idf values, and
the widest window any hit can hand Stage 5 is **102,524 ms of 2,313,729 — 4.43%** of the media
instead of 100%.

**Invariant #3 moved with the runner rather than being left behind.** `from_transcript` held the
type guard (`assert_model_input`); `from_sentences` took a bare `media_id: str`, which cannot be
refused. Its signature is now `from_sentences(sentences, transcript)` — the transcript it belongs
to, from which `media_id` is read — so the guard is on the path the runner uses, in the factory
rather than at the call site. The normalization half was never at risk: `index_tokens` calls
`normalize_sorani` for every document and every query on all paths, which is the arrangement
recorded for §2 and mirrored in `embed_text`.

**Rejected: keeping `from_transcript` on the runner and giving it sentence documents.** That makes
one factory mean two shapes, and the report's `document_count` would no longer say which.

**Rejected: deleting `from_transcript`.** "Does this episode mention X" is a real question with one
document, and its docstring now says plainly that it cannot order results and returns the whole
media as its window. Dead-code removal is not worth losing the honest single-document case.

**The pipeline test asserted the defect.** `test_the_run_report_serializes_to_json` required
`payload["index"]["document_count"] == 1`. That is the defect written down as an expectation, so it
was proved wrong before being changed — the measurement above is the proof — and it now asserts the
sentence count *and* that the count exceeds one, so the shape cannot silently revert.

**A second finding, D-090's sibling.** D-090 fixed `scored[:k]` in `visual_index.retrieve` for
negative `k` and recorded that "a negative slice drops the tail instead of keeping a head".
`Bm25Index.search` ended in `hits[:limit]` and kept the defect. Measured on a 10-document index:

```
limit=  3 ->  3 hits      limit= -1 ->  9 hits      limit=-10 -> 0 hits
limit=  1 ->  1 hit       limit= -5 ->  5 hits      limit=-20 -> 0 hits
limit=  0 ->  0 hits
```

`limit=-1` returns the best nine of ten — an answer, silently a different operation. Refused as
arithmetic rather than as a threshold, the way D-090 put it: a retrieval that cannot return one
document is not a retrieval. `limit=1` is the tight boundary and must still work, which is the
control the over-strict mutation only trips against.

**Mutation audit 7/7:** the runner reverted to the single-document index CAUGHT, `from_sentences`
collapsed to one document CAUGHT, a hit carrying the media's window instead of the sentence's
CAUGHT, invariant #3's type guard dropped CAUGHT, sentence text indexed raw CAUGHT, the limit guard
removed CAUGHT, and the limit guard made over-strict CAUGHT — the last only by the control.

**What survived the pass.** M2.1's headline claim holds exactly as written: on the clitic pair, word
BM25 scores the stem query **0.000000** and the n-gram field scores **1.829909**, so n-grams are
what retrieve it. D-016's weighting, the tokenizer, the n-gram padding and the tie-break are all
held by tests that redden when reverted.

**Named as open, not invented: `Bm25Index.search` still has no production caller.** `grep -rn
"\.search(" src/` finds one match and it is `_TIMESTAMP.search` in `clip.py`. The runner builds the
index, reports its three statistics and never queries it, because §3 Path A is explicit that the
judge reads "the **full normalized Sorani transcript** in one pass. Not a filtered subset", while
§9's M2 row describes a "transcript → BM25 → Gemini" slice. Those two readings disagree about what
the text index is for, and choosing between them decides what §8.2's per-path Recall@K measures.
`BLOCKED.md` #18 records it for Hawa rather than inventing a query here.
`evidence/adversarial-pass-19-2026-08-10.md`.

## D-135

**§3 Stage 1's second escalation trigger had no input, so half the rule could not run.** §3: *"Route
the bottom quartile, and any segment where LLM-7B and CTC-3B disagree materially, to the validator."*
D-109 gave the quartile its input and named the remaining shortfall exactly: *"`select_for_validation`
still cannot be called, because `ctc_text` is never computed — the CTC pass yields emissions for
alignment and nothing decodes them."* Reproduced:

```
$ grep -rn "ctc_text" src/
src/hawedit/escalation.py:57 · 81 · 88 · 91 · 92 · 117      (the type, the predicate, nothing else)
```

**Never computed, not computed and discarded** — the distinction the loop asks for. The emissions
existed in `transcribe_segment`; `_align_emissions` spent them on timing the LLM's words and no
second hypothesis was ever produced.

**Decision: greedy-decode the posteriors Stage 1 already holds.** An argmax per frame, repeats
collapsed, blanks dropped. No model, no download, no threshold — `DEFAULT_DISAGREEMENT_CER` was
already chosen and recorded in D-015. The only new judgement is *which matrix* to decode.

**The decode must span the full vocabulary, and that is the load-bearing part.**
`_align_emissions` projects the posteriors onto only the columns the LLM's own tokens occupy,
because Viterbi never needs the rest. Decoding from *that* matrix would confine CTC to the LLM's
vocabulary, so the two hypotheses could differ only in order — a substituted word, which is the
case the disagreement trigger exists for, would be structurally unreachable. A test builds a matrix
whose acoustic peak is a symbol the reference text does not contain and requires it to survive.

**`SegmentConfidence` carries both hypotheses, not just the CTC one.** The comparison needs a pair,
and reading them off the artifact rather than from live model objects means §8.2 can re-tune the
threshold against a transcript on disk without paying for inference again.

**Empty means empty, and is not agreement by accident.** A segment whose acoustic model emitted only
blanks gets `""`, and `materially_disagree` already treats one empty side as the strongest
disagreement available. Two empty sides — every transcript written before this change — read as
agreement, so an old artifact escalates on confidence alone rather than escalating everything.
Measured on the real 38-minute transcript: **545 segments scored, 136 escalated = 545 // 4**, every
reason naming the quartile.

**The argmax runs in torch, and that was a defect in this change's own first version.** Measured on a
200-frame segment against a 32,000-token vocabulary:

```
                                   per segment      across 547 segments
  .tolist() on the full matrix        182.9 ms            100.0 s
  Python argmax over the vocabulary   210.3 ms            115.0 s
  tensor.argmax(dim=-1).tolist()        2.03 ms              1.1 s
```

~215 s of pure CPU overhead against 1.1 s. `collapse_ctc_path` is the O(frames) half and stays
pure and model-agnostic; `greedy_ctc_tokens` keeps the emissions-level API the tests drive. A test
hands `_ctc_hypothesis` a matrix wrapper that **raises** if `.tolist()` is called on the full
matrix, so the fast path is pinned behaviourally rather than by comment.

**Rejected: decoding on the compacted matrix.** One line shorter, reuses the projection
`_align_emissions` already computes, and makes the trigger unable to fire on the substitution it is
for. Rejected on that ground, and the reason is now a test.

**Rejected: routing the escalated segments anywhere.** §3 routes them to the rzgar validator, whose
loader is `BLOCKED.md` #16 and needs a licence decision under D-002. The rule now *runs* and its
decision is in the report; sending them is still Hawa's call.

**Mutation audit 12/12,** after a first pass of **6/9** on the nine mutations that existed then. The three survivors were all the same class:
the decode, the scores and the wiring were tested and the *carrying* was not — blanking either
hypothesis at the `SegmentConfidence` construction site, or skipping the CTC decode entirely, left
five suites green. One of them needed a fake one layer lower than any existing test: every backend
double replaces `transcribe_segment` itself, so the method that calls the decode was never driven —
D-118's `read_scenes` finding, repeated exactly.
`evidence/the-second-escalation-trigger-had-no-input.md`.

### The real-weights run, and what it changed

The full `--omni-asr` run finished after this was first written: **1,547 s** on hawapc01's two
3090 Ti, 545 segments, a 1,070,637-byte report. **542 of 545 segments carry a real CTC hypothesis**,
so the decode works on real weights. What it produced is the finding:

```
first script of each CTC hypothesis, over 542 segments
  ARABIC        428  ( 79.0%)      CJK            11  (  2.0%)
  LATIN          96  ( 17.7%)      MALAYALAM/HEBREW/CYRILLIC/DEVANAGARI/BENGALI  7  (1.3%)

LLM: کاکە بیلال                              CTC: കക بില                       CER 0.800
LLM: کەشوو مشتەز و بەخێوی زارکلاس …          CTC: ت زور خب انجاي اكثر حظ كم    CER 0.640
LLM: باسی گیم وڵکنیوزم بۆ بکەی               CTC: paseki molknusen bopka       CER 0.960
```

**CTC-3B's greedy decode is unconditioned.** The LLM pass is called with `lang=["ckb_Arab"]`; a
greedy argmax over the acoustic model's full multilingual vocabulary is conditioned on nothing, so a
sixth of the hypotheses are not even in Arabic script. The confound lands exactly on D-015's bar:

```
normalized CER, LLM vs CTC, all 542 hypotheses        median 0.167   (above the 0.15 bar)
                             Arabic-script only (428) median 0.125   (below it), 175/428 over
escalated on the real run    312 / 545 = 57%
  disagreement only   176      both   116      quartile only   20
```

**So the input exists and the comparison is not yet meaningful.** §3's rule is implemented as
written, with D-015's recorded threshold, and it escalates 57% of the file — where the quartile
alone is 25% by construction. 176 segments escalate on disagreement alone, and the median CER moves
from *above* the bar to *below* it once script-mismatched hypotheses are excluded, which is what
shows the confound is deciding rather than colouring the outcome.

**Not fixed here, and deliberately not guessed.** Restricting the decode to a "Kurdish subset" of the
vocabulary means naming which of ~32,000 tokens are Kurdish; conditioning the CTC pass the way the
LLM pass is conditioned is a modelling change whose effect on §8.1 is unmeasured; and lifting the
threshold to swallow the confound would be a guessed number chosen to make an output look right.
Each is a decision about which segments get validator time. `BLOCKED.md` #19.

**What the code does in the meantime:** computes and carries the hypotheses (real data, honestly
labelled), applies §3's rule as written, and reports **which trigger fired** —
`by_trigger: {quartile_only, disagreement_only, both}` — so the 312 can never be read as §3's
validated routing. A bare total would have been exactly that.

## D-136

**Stage 1 was re-run every time, and the refusal for a differing re-run arrived after the whole
spend.** D-132 made Stage 0 re-runnable; Stage 1 is the expensive stage — measured in D-135 at
**1,547 s** for 545 segments on hawapc01's two 3090 Ti — and `run_pipeline` called
`asr.transcribe(...)` **before** it consulted `TranscriptStore` at all. Measured with a counting
producer, before changing anything:

```
first run into an empty work directory
  asr.transcribe calls: 1        transcript.raw.json on disk: True
second run into the SAME work directory, transcript already stored
  asr.transcribe calls (cumulative): 2
  -> Stage 1 was re-run with a complete transcript on disk: True
if the second run's ASR returns anything different
  RawTranscriptImmutable: …transcripts\probe.transcript.raw.json already contains a different …
  the refusal arrived AFTER 1 full transcription
```

That second part is the sharper half. Greedy decoding on a GPU is not bit-reproducible in general,
so a re-run into a used work directory can spend 1,547 s and *then* be refused by invariant #1's
immutability guard. **D-071's shape one stage over** — there, an overwrite refusal fired after a
billed Gemini call, and the fix was to move the guard before the spend. Same fix here.

**Decision: consult the store before Stage 1, and verify reuse on two keys.**

* **The audio digest.** A transcript is only this run's answer if it was made from this audio. Same
  media_id over a different recording would otherwise ship one video's words for another — the
  failure that costs correctness rather than time. Stage 0's own provenance (D-132) already proves
  `audio.wav` matches the source, so hashing it is the honest link.
* **The producer.** `asr.py` states the rule this enforces: a run driven by a test double "is
  self-evident in the report and can never be read as a run on real weights". Keyed on audio alone,
  a transcript stored by a stub would be reused by a real `--omni-asr` run and the report would
  claim OmniASR output. It is also D-132's "same command" clause: a changed Stage 1 re-transcribes
  instead of silently keeping the old answer.

Absent sidecar, either key mismatched, or a failed integrity check all decline — the expensive
answer, never the wrong one. The sidecar is written **after** the transcript is published, so one
that outlived a failed write cannot claim a match; and reuse still runs `verify_raw_integrity`,
because reuse is a *read* of the canonical artifact and invariant #1's tamper evidence governs
every read of it.

**A supplied `--transcript` writes no sidecar and therefore licenses no reuse.** Words handed in
were not produced from this audio by anything here, and a later `--omni-asr` run must not present
them as canonical ASR output. `audio_sha256` and `producer` are both optional on `write_raw` for
exactly that reason: a caller that cannot say must not be able to claim a match by omission.

**Rejected: putting the audio digest in `RawTranscript`.** It would be the natural home for
provenance, and the artifact *ships to the client* and is immutable under invariant #1. Changing its
schema for bookkeeping is a bigger deviation than a sidecar, which is where D-132 put the same
information for Stage 0.

**Rejected: reusing on the audio digest alone.** One key shorter, and it lets a stub's transcript
be read as real weights. That is the rule `asr.py` opens with.

**The stale request file, reproduced and fixed with it.** A `--omni-asr` run killed mid-flight left
`stage1/omni-asr-request.json`, and the next attempt died on a bare
`[Errno 17] File exists: …omni-asr-request.json` after **78 s** — Stage 0 re-verified, nothing to
show, no instruction in the message. An identical request is now a resumed run and proceeds; one
describing different segments is refused with a message naming the file and what to delete.

**And the test written for that found a second blocker.** The worker's own
`omni-asr-worker-output.json` is exclusive-create too, so a killed run left *two* files and the next
attempt tripped on whichever came first. A finished output beside an identical request is this run's
answer, so it is now resumed rather than discarded — verified by media_id, with a truncated or
foreign output deleted and the worker re-run.

**Measured on the real 38-minute file:** two `--omni-asr` runs over one work directory,
**1,531 s then 54 s**, and the two reports are byte-identical (sha256 `0bf3b7da4bf84f61`,
1,070,737 bytes each — 6,104 words, 186 index documents, 312 of 545 escalated). The sidecar
the first run wrote records `audio_sha256 312fe70941e143ef…` and
`producer hawedit.asr.WslOmniAsrProducer`; recomputing the digest of `stage0/audio.wav`
independently gives the same value.

**Mutation audit 11/11,** after **10/11**. The survivor was the foreign-output check: dropping the
media_id comparison left every suite green because no test had ever put another episode's output in
the way. `evidence/stage-1-was-re-run-every-time.md`.

## D-137

**Adversarial pass #20, on M2.8 — the credential panel and the billed Stage 4 judge.** One mutation
per claim the cell makes. Two of the cell's claims did not hold, one guard was untested on the
platform where it is load-bearing, and the audit's own first run was contaminated by the guard it
was auditing.

### The claim the cell leads with had no test at all

*"`python -m hawedit.credentials` verifies a key against Google before storing it."* That decision
lives entirely in `main()`, and **nothing drove `main()`**. Two mutations survived:

* deleting `if not verified.valid: … return 1` — a key Google rejected is stored anyway;
* moving `write_credential` above `validate_gemini_key` — stored first, verified after.

Both leave the whole suite green. `tests/test_credentials.py` had thorough tests for
`validate_gemini_key`, `write_credential` and `mask` **separately**, and none for the panel that
sequences them — the gap is precisely between the units. Four tests now drive `main()` with the
network and the writer replaced by recorders: a rejected key writes nothing and exits 1; an accepted
key records `["validate", "write"]` **in that order**; neither path prints the key, only its mask;
and a blank entry reaches neither the API nor the writer, which is the control that stops "no key
was stored" being satisfied by a panel that never stores anything.

`write_credential` is stubbed rather than pointed at a temporary file, deliberately: its `env_file`
default is bound at definition time, so a test that redirected `ENV_FILE` would still write to the
real user config. The claim under test is the decision and its order, and that is what is recorded.

### The TOCTOU half of the O_NOFOLLOW reconstruction was untested

`_O_NOFOLLOW` is measured at **0** on this Windows host, so the guarantee is rebuilt from two
halves: refuse a symlink *before* the open, then prove *after* the open that the handle is the same
file that was checked. The pre-open half had a test. Deleting the identity comparison left the suite
green — on the one platform where that comparison actually runs. The race is now forced rather than
waited for: `os.lstat` is made to answer about a different file, which is what an attacker replacing
`.env` between the two calls achieves, and the write must refuse. With `os.lstat` telling the truth
the same call succeeds, which is the control.

### Two mutations were measured unobservable here and dropped rather than reported as gaps

* removing `_O_NOFOLLOW` from the open flags — it is `0` on Windows, so the edit is a **no-op**;
  the property it stands for is held by the pre-open refusal, whose mutation is caught.
* creating the file at `0o666` instead of `0o600` — measured, both report `0o666` on Windows;
  `restrict_to_owner` rewrites the ACL and `assert_owner_only` reads it back, and that is the
  property that exists on this platform.

Reporting either as a hole would have been a platform artefact dressed as a finding.

### And one of my mutations was simply wrong

`if attempt < self._max_attempts:` → `if True:` was labelled "retries are unbounded". It is not:
`for attempt in range(1, self._max_attempts + 1)` bounds the loop and that line only skips the final
sleep. The bound *is* tested — `test_a_rate_limit_is_retried_and_then_given_up_on` asserts exactly 3
`generateContent` calls. Replaced with a mutation that raises the ceiling, which is caught. A
survivor is a claim about the tests; a bad mutation is a claim about nothing.

### The audit was contaminated by the guard it was auditing, and that is its own finding

The first run reported 18/20 with sixteen REDs all naming `test_writing_to_a_tracked_path_is_refused`
— every mutation after the git-ignore one. Cause: that mutation made the guard fail open, the test
wrote `a-credential-must-never-be-written-here.env` into the repo root, and the test's **first**
assertion is that the probe path does not exist. So one fail-open turned into an indefinitely red
suite that only a manual `rm` of a real-looking credential file could clear, and every later result
was red for the wrong reason.

D-113 chose "one stray file instead of a deleted test" and that trade was right. It did not make the
stray file self-healing. The probe is now removed in `finally` and the pre-existence message says
what to inspect and delete. **The check is unchanged; it heals.** Verified by re-running the audit:
no contamination line, `restored and green: True`.

### The first push was refused by the gate, for the right reason

The identity test was written with `pytest.skip` where the kernel has `O_NOFOLLOW` — true on the
Linux runner, false here. CI refused the commit:

```
REFUSED: only 1372 tests passed against a floor of 1373 (1 skipped of 1373 collected). Either 1
test(s) disappeared, or a skip condition is creeping. … a shrinking suite must be a visible edit,
not a quieter green run.
```

It was right, and not only about the count: a guard only Windows exercises is a guard CI never
checks, which is the same "runs on one machine" defect the floor exists to surface. `_O_NOFOLLOW` is
patched to **0** instead, so the reconstruction branch is reached on both platforms — the constant is
the branch's own condition, so patching it is exercising the code rather than working around it.
Verified after the change: 26 tests in the file, **no skips**, and removing the identity comparison
still reddens `test_the_opened_env_must_be_the_file_the_symlink_check_looked_at`.

**Mutation audit 18/18** after the corrections, across
`credentials.py`, `gemini.py` and `judge.py`: verify-before-store both ways, header-not-URL
authentication, non-200 rejection, the git-ignore refusal and its fail-closed default, masking, the
pre-open symlink refusal, the identity test, the hardlink refusal, the deliberate absence of
`O_TRUNC`, `countTokens` before the billed call, the tier ceiling, temperature 0, the response
schema, no retry on 400, the retry ceiling, and the ZDR gate.

**What survived the pass:** everything in `gemini.py`. All seven judge claims — schema-enforced
output, real `countTokens` before the billed call, temperature 0, bounded retries on transient
failures only, the tier ceiling, the ZDR gate — are held by tests that redden when reverted.
`evidence/adversarial-pass-20-2026-08-10.md`.

## D-138

**Adversarial pass #21, on M3.6 — §2's delivery set.** Nineteen mutations, one per claim the cell
makes, and **every stated claim held**: the SRT on the clip's timeline, the comma separator, D-114's
shared wrapper at one width, invariant #2's refusal, both clip-window refusals, the EDL's source
range in *source* time with record starting at zero, the non-integer-rate refusal and its
before-the-arithmetic placement, the two events, the degenerate-clip refusals, the sanitised title,
and D-072's build-all-before-writing-any. So the pass went after what the claims do **not** say.

### Two exported formatters produced plausible nonsense below zero

```
ms_to_srt_time(       -1) = '-1:59:59,999'
ms_to_srt_time(     -500) = '-1:59:59,500'
ms_to_timecode(    -500, 25) = '-1:59:59:13'
ms_to_timecode(-3600000, 25) = '-1:00:00:00'
```

`divmod` carries the sign into the **minutes**, not the hours, so the output is not obviously broken
— it reads as a time nearly two hours before the file starts, in a field an EDL parser accepts. Both
functions are in `__all__`; `build_srt` and `build_edl` guard their own inputs, so this is the
D-090 class exactly: a public function silently wrong at an edge with no in-tree caller.

**Decision: refuse negative milliseconds in both.** Arithmetic, not a threshold — SRT and SMPTE
timecodes are unsigned formats, so there is no value to choose. Zero still formats, which is the
control.

### And the module's own reader answered "fewer cues" instead of "malformed file"

```
a cue built from a negative start:
'1\n-1:59:59,500 --> 00:00:01,000\nhello\n'
parse_srt_times sees: ()
```

A one-cue file read back as **zero** cues. `test_pipeline`'s check on the delivered SRT asserts that
*some* cue parsed and that the ones that did lie inside the clip — a dropped cue satisfies both, and
nothing anywhere compared the cue count to the sentence count. Computed and discarded: the parser saw
a timing line it could not read and forgot it.

**Decision: refuse a cue whose timing line does not parse, and read that line by position.** The SRT
grammar puts the timing on the block's second line, so only that line is examined and a `-->` inside
caption text is text. Rejected scanning the block for the first line containing `-->`: it behaves
identically on valid input — measured, that mutation **survived** — and diverges only when line 1 is
malformed, where it walks past the bad line and parses a *caption* as the cue's timing, inventing a
cue out of text instead of refusing the file. The control is now that case, not the arrow-in-text
case, which could not discriminate.

### The new guard masked an older one, and the audit caught it

Adding the negative-timestamp refusal turned *"a sentence starting before the clip is shipped
anyway"* from RED to **SURVIVED**. `test_a_sentence_before_the_clip_is_refused` matched on
`"before"`, and the new guard's message contains *"reads as a time **before** the file starts"* — so
with the specific guard deleted, the sentence's negative offset tripped the downstream guard and the
test still passed. Two guards raising one exception type have to be told apart by what they say; the
match now names `"starts before the clip does"`. That is a strengthened check, not a relaxed one.

**Verified on the real delivered artifacts.** Both SRTs on disk from earlier real runs parse
cue-for-cue under the strict reader — 2 cues against 2 timing lines each, every timestamp
non-negative — so the guard does not refuse anything this system actually writes.

**Mutation audit 23/23**, after 17/18 and then 22/23: the first survivor was the masking above, the
second was my own non-discriminating control. `evidence/adversarial-pass-21-2026-08-10.md`.

## D-139

**§10/10 asks for a "pinned and checksummed supply chain", and the packages the gate itself runs on
were neither.** D-120 made the wheel build reproducible and D-121 pinned and checksummed the ffmpeg
archive. The Python distributions were resolved fresh on every CI run. Measured:

```
declared in pyproject (all extras): 17
installed in this venv:             70
installed but NOT declared anywhere (transitive): 54
```

So 17 of 71 were pinned by version — 24% — and **zero** by checksum. `pip install -e '.[dev,media]'`
accepts whatever the index serves: a re-uploaded file, a compromised mirror or a new transitive
release changes the program under a green gate, and nothing records what was installed.

**Decision: compile a hashed lock for the gate's exact target and install with
`--require-hashes`.** `requirements/gate-linux-py311.txt` holds **33 distributions, 350 SHA-256
hashes, 0 pins without one** — the full `.[dev,media]` closure for Linux, CPython 3.11 and the
PyTorch CPU index, which is the platform the gate of record runs on. Every artifact is verified
before it is unpacked.

**Two install commands, not one.** `--require-hashes` forbids an editable install in the same
invocation, so the project goes in afterwards with `--no-deps` — safe because every dependency was
just installed from the hashed set, and asserted, because `-e .` *without* `--no-deps` would resolve
them again unpinned alongside.

**The PyTorch index stays.** The lock pins `torch==2.13.0+cpu`, and an index is still needed to
*find* that file; the hash decides which file is accepted once found. Dropping the index would fail
to resolve, not silently install something else.

**`scripts/lock-gate-deps.sh` regenerates it.** A lock nobody can reproduce is a binary blob. The
script records the target explicitly — `--python-platform linux --python-version 3.11` — because a
lock resolved on this Windows host pins different wheels, and it refuses to write a pin that carries
no continuation line.

**Rejected: locking every extra.** `gpu`, `asr` and `cloud` are not installed by the gate, `asr` is
excluded on Windows by its own marker, and resolving them here would produce pins for a platform and
a GPU stack nothing in CI exercises — a lock that is never verified is a claim, not a guarantee.

**Rejected: `uv sync`/`uv.lock` for the whole project.** It would replace how this repo installs
everywhere at once, including the developer venv this loop measures on, and the gate of record is
the thing that needed the guarantee.

**Named shortfall.** The lock covers CI. The developer venv on Windows still resolves freely, and
`gpu`/`asr`/`cloud` are unlocked. Both are stated rather than implied, because "pinned and
checksummed supply chain" now holds for the gate and not yet for every install path.

**Mutation audit 9/9,** after 8/9. The survivor was mine: deleting one pin's trailing backslash
left the block still *containing* `--hash` lines — pip reads a requirement as ending where the
continuation stops, so that pin owns none of them and `--require-hashes` rejects the whole install.
The check is structural now: every pin line must continue.

**The prose-grep trap, one file over from D-121.** The first version of the control asserted
`"-e '.[dev,media]'" not in workflow`, and the workflow *comment* quotes that command to say what it
replaced — so the test failed on its own explanation. It reads command lines only now, exactly as
`fetch-ffmpeg.sh`'s `--fail` check had to. `evidence/the-gate-installed-whatever-the-index-served.md`.

## D-140

**Stage 2's visual half is the most expensive stage in the pipeline, and it was redone in full on
every run.** D-132 made Stage 0 re-runnable (100.2 s saved) and D-136 Stage 1 (1,531 s → 54 s). This
is the third and largest. Measured on `ZAR38MinTest.mp4` with the real `Qwen3-VL-Embedding-2B` on a
3090 Ti, before changing anything:

```
Stage 2 plans 641 scene windows at 2.0 fps, max 8 frames

frame extraction of 12 windows
  first pass    1.14 s   ( 95.1 ms/window)
  second pass   1.11 s   ( 92.3 ms/window)
  jpgs on disk 81   rewritten by the second pass: 81
  -> extrapolated over 641 windows: 60.9 s

embedding 12 windows: 38.49 s (3,207 ms/window, cold)
  -> extrapolated over 641 windows: 2,055.9 s
```

`discover` built a fresh in-memory `_FrameCache` per call and embedded every window
unconditionally; `extract_window_frames` runs ffmpeg with `-y`. Every jpg was rewritten and every
vector recomputed.

**Decision: a per-window embedding cache on disk, verified on everything that changes a vector.**
One file per window, so a run killed at window 400 of 641 keeps 400 — that is what "resumable"
has to mean here, not "restart faster". Measured after, with the real weights:

```
first pass       16.49 s   embedder calls this pass: 12
second pass       0.14 s   embedder calls this pass: 0
cached vectors bit-identical to the fresh ones: True
per-window embedding: 1374 ms   (warm; the 3,207 ms above includes the first forward pass)
extrapolated over 641 windows: 880.7 s first run, 7.5 s on a re-run
```

**Frames follow the embeddings.** A cached window is never extracted, which is where the 95.1
ms/window went; survivors still get their frames later through the same `_FrameCache`, for the
reranker and the reader. One mechanism, not two.

**The key is the window, the checkpoint and the source.**

* the **window** — id, bounds, fps, frame count — so a replanned window re-embeds;
* the **model id and revision**, because vectors from two checkpoints live in different embedding
  spaces and mixing them makes every cosine similarity meaningless while looking fine. D-073
  pinned the revisions and this is what makes the pin load-bearing; D-136 established the producer
  as part of a reuse key;
* the **source digest**, because a window is a *time range* and the same range of a different
  recording is different footage.

**An unidentified checkpoint never licenses a reuse — and the first version of this code did not do
that.** An empty revision compared equal to itself, so unpinned weights reused their own unnamed
vectors. The docstring stated the rule; the code did not implement it; the test written *for the
rule* caught it. D-132's "absent evidence is not evidence of a match", one key over.

**The record is staged and renamed into place.** A store that dies partway must leave no readable
half-record, and a direct write makes the destination itself the garbage.

**A cached vector still has to clear `VisualEmbedding`'s invariants.** A zero or non-finite vector
sinks a scene below everything in every query without a trace; the cache is a store, not an
exemption.

**Named limitation, recorded rather than papered over.** The record verifies what *produced* the
vector, not the vector's content: a hand-edited vector that still parses and still satisfies the
invariants is indistinguishable from a legitimate one, because validating the content means
re-embedding it — the cost the cache exists to avoid — and any checksum stored beside it is derived
from the same file and re-derivable by whoever edited it. **The first version of the test asserted
this was caught, and it was not.** Truncation, the realistic corruption, *is* caught.

**Rejected: caching in `extract_window_frames`.** It would make the frame layer re-runnable
independently, which is 60.9 s against the embedding's 880.7 s, and a cached embedding already
skips the extraction entirely. One guard where the expensive work is.

**Rejected: one combined cache file written at the end.** Simpler, and it keeps nothing from a run
killed at window 400 — which is the whole point.

**`discover` now requires the source to exist**, because it reads its digest. Strictly no worse
than before: `extract_window_frames` would have run ffmpeg on it moments later. Four existing tests
passed a path that never existed and now create a stub file.

**Mutation audit 12/12,** after 10/12. Both survivors were the familiar shape: the staged write had
no test that made a write fail, and the runner's `embedding_revision=` argument could be dropped
with everything green — D-105, D-133 and D-135's unheld-wiring finding for the fourth time.
`evidence/stage-2-re-embedded-641-windows-every-run.md`.

## D-141

**AUDIT_REPORT.md's verification evidence named four of five console scripts, and the omitted one
handles the API key.** The loop's step 1(b) names AUDIT_REPORT as a place claims can drift, and this
one had never been checked. Reproduced:

```
[project.scripts] declares 5 entry points:
  hawedit                    -> hawedit.pipeline:main
  hawedit-asr-bench          -> hawedit.bench:main
  hawedit-asr-setup          -> hawedit.wsl_setup:main
  hawedit-credentials        -> hawedit.credentials:main
  hawedit-editorial-bench    -> hawedit.editorial_bench:main

AUDIT_REPORT names: 4
declared but NOT named in AUDIT_REPORT: ['hawedit-credentials']
```

`hawedit-credentials` arrived with M2.8 and the sentence was never re-derived — the same
uncounted-list failure as D-127's *five repositories* and D-129's *four blocked stages*, and the
third time a count in this repo aged because nothing tied it to its source of truth.

**The claims themselves are true; only the list was short.** Verified against a real wheel built
from this tree, installed into a fresh CPython 3.12.13 environment:

```
starting each one from the installed wheel (--help):
  OK   hawedit                    exit 0
  OK   hawedit-asr-bench          exit 0
  OK   hawedit-asr-setup          exit 0
  OK   hawedit-credentials        exit 0
  OK   hawedit-editorial-bench    exit 0

uv pip check -> All installed packages are compatible
wheel: hawedit-0.1.0-py3-none-any.whl, 346,694 bytes, 55 entries
  OK   the Kurdish font        assets/fonts/NotoNaskhArabic-Regular.ttf
  OK   its OFL licence         assets/fonts/OFL.txt
  OK   model-source manifest   models/revisions.json + models/sources.json
  OK   the WSL worker          hawedit/asr_worker.py
  OK   the setup module        hawedit/wsl_setup.py
```

**Decision: bind the sentence to `[project.scripts]`, set equality both ways.** The §7 registry and
§4.1's collision probes already get this discipline; the report did not. Both directions, because
either alone is satisfiable while the claim is wrong: a short list proves less than it says, and a
list naming a script that does not exist tells a reader to run a command that is not there. The
*count* is asserted separately, because D-127's lesson is that a list can be right while the number
beside it is stale — and a reader takes the number.

**The wheel-contents claim now names paths instead of categories.** *"Kurdish font/OFL,
model-source manifest, WSL worker and setup module"* was true and unverifiable from the text; the
files it names must exist in the tree that builds the wheel, or the claim is about a wheel nobody
can build from here.

**Rejected: asserting the wheel's own contents in the test.** That means building a wheel in the
gate — `tests/test_build.py` already does it for reproducibility, and doing it again to re-list the
same members costs a build per run to check what `MANIFEST`/`pyproject` already determine. The
tree-level assertion catches the realistic drift: a file renamed or removed while the report still
names it.

**Mutation audit 6/6,** after 4/6.

**The primary defect's own mutation survived the first pass, and the cause is now three for three.**
Dropping `hawedit-credentials` from the list left the suite green, because the correction note in the
same bullet *names* the entry point it records as once-omitted — so a check over the whole section
read it from the explanation. That is D-121's prose-grep trap for the third time in this repo, after
`fetch-ffmpeg.sh` explaining `--fail` in a comment (D-121) and the gate workflow quoting the command
it replaced (D-139). This project's convention is to quote the wrong thing while correcting it, so
every check over documentation has to read the *claim* and not its history. The test now takes the
bullet up to `**Corrected`.

**And one of my mutations was measuring nothing.** *"the wheel-contents claim names a file that is
not in the tree"* replaced the first `` `models/revisions.json` `` in the file — and there are two,
the other in "Secondary debt" (D-073). It changed the one the test does not read. Re-anchored on
text unique to the section, and caught. Same class as D-137's retry mutation: a survivor is a claim
about the tests, a bad mutation is a claim about nothing.

**Found in passing, measured, not fixed here.** `hawedit --help` prints
`usage: hawedit.pipeline …` and `hawedit-credentials --help` prints `usage: hawedit.credentials …`
— both set `prog=` to the module path, so the wheel's own help text names a command the user cannot
run. `smoke.py` does the same and is *not* a console script, so there its prog is right. The honest
fix derives the name from how the process was invoked (`__main__.py` in `argv[0]` means `-m`), which
belongs in `cli.py` beside `use_utf8_streams` and needs its own decision about the rule.
`evidence/four-of-five-entry-points.md`.

## D-142

**Every entry point's `--help` named something the reader cannot type, in one of its two invocation
modes.** D-141 noticed two of them in passing and recorded the finding; measured properly, all five
are affected. From the real wheel and from `python -m`, before changing anything:

```
                          console script            python -m
  hawedit                   hawedit.pipeline  ✗       hawedit.pipeline
  hawedit-asr-bench         hawedit-asr-bench         bench.py  ✗
  hawedit-asr-setup         hawedit-asr-setup         wsl_setup.py  ✗
  hawedit-credentials       hawedit.credentials  ✗    hawedit.credentials
  hawedit-editorial-bench   hawedit-editorial-bench   editorial_bench.py  ✗
```

Two set `prog=` to a module path, which is right under `-m` and not a command from the wheel. The
other three set nothing, so argparse used `basename(sys.argv[0])` — right from the wheel and, under
`-m`, a bare source filename. **Five for five wrong in one mode**, and the failure is user-facing:
`hawedit --help` told an operator to run `hawedit.pipeline`, and `python -m hawedit.bench --help`
told them to run `bench.py`. Both appear in error messages too, which is where a wrong command name
costs the most.

**Decision: derive it from `sys.argv[0]`, in `cli.py`.** Python sets `argv[0]` to the module's
*file* under `-m` and to the script itself otherwise, so a `.py` suffix distinguishes the two with
nothing guessed. Each branch returns something paste-able: `python -m hawedit.pipeline` — the form
this repo's own documentation uses — or `hawedit`, the console script's name with the `.exe` Windows
appends removed. `cli.py` is where it belongs: it already holds `use_utf8_streams` and
`machine_readable_stdout` for exactly this "what every entry point does" reason (D-115, D-119).

**All six parsers use it, including `smoke.py`.** `smoke` has no console script, so its old fixed
`prog` was already right for `-m` — it goes through the shared helper anyway, because the next
module to gain a console script must not have to remember this.

**An empty `argv[0]` falls back to the module path.** An embedded interpreter can leave it empty and
`Path("").stem` is `""`, which would print `usage:` naming nothing at all.

**Rejected: `sys.executable -m …`.** Literally correct and unreadable — an absolute interpreter path
in a usage line, different on every machine. Every document in this repo writes `python -m`, so the
usage line writes it too.

**Rejected: leaving `prog` unset everywhere.** It is right from the wheel and wrong under `-m`, which
is half the problem and the half the repo's own docs use.

### The first push was refused by CI, and the fault was in my test

```
E  AssertionError: hawedit --help says 'C:\\somewhere\\venv\\Scripts\\hawedit'
E  assert 'C:\\somewher...ipts\\hawedit' == 'hawedit'
```

The fake `argv[0]` was a `C:\…\Scripts\x.exe` string literal. On POSIX `\` is not a path
separator, so `Path.stem` returned the whole string and all five parametrised cases failed on the
Linux runner while passing here. **The rule was right on both platforms** — `/usr/bin/hawedit` and
`…\Scripts\hawedit.exe` both yield `hawedit` — and only the fixture was Windows-only. Rebuilt
with `Path(...)` so separators are native, and parametrised over the bare and `.exe` shapes, which is
strictly more than the original checked. That is the second platform-bound test of mine after
D-137's `pytest.skip`, so this one exercises both cases rather than assuming one.

**Mutation audit 9/9.** Each of the five modules reverted to its old form individually, plus the
rule inverted, the `python -m` prefix dropped, the `.exe` kept, and the empty-`argv[0]` fallback
removed.

**The tests drive both modes through the real parsers,** reading the text argparse emits rather than
the `prog=` argument echoed back, and they enumerate `[project.scripts]` the way D-119's do — so a
sixth entry point is covered the day it is declared. The control is that the two modes must print
*different* names: a fixed `prog` satisfies one of the two assertions, so asserting only one would be
satisfied by exactly the defect. `evidence/help-named-a-command-that-was-not-installed.md`.

## D-143

**README.md understated the project's own quality bar, and its `cli.py` row named none of what
`cli.py` does.** The README is the last document in the loop's step 1(b) list never checked
systematically, and it is the one a reader meets first.

### It said the required status check was not done, two days after it was

```
README.md:257  … Making that job a required status check is a repository setting, and is not done.
BLOCKED.md:260 ## #7 · The hawedit CI job is not a *required* status check — **RESOLVED 2026-08-08**
```

Measured against the live API rather than taken from the record:

```
required_status_checks: {"contexts": ["gate"], "strict": true, …}
```

So `gate` is required on `main` **and** a branch must be up to date before merging, which is
stronger than the README claimed — and every `git push` in this loop has printed
`Required status check "gate" is expected.` Understating a bar is a smaller sin than overstating
one, and it is still a document contradicting reality in the place it is read first.

### The `cli.py` module-map row named 0 of 3 exports

```
hawedit.cli.__all__: ['machine_readable_stdout', 'program_name', 'use_utf8_streams']
the row:            "What every entry point does before it writes: pin stdout and stderr to UTF-8…"
exported but not named in the row: all three
```

It described `use_utf8_streams`'s *effect* without naming it, omitted `machine_readable_stdout`
(D-119) entirely, and omitted `program_name` — which **I added two commits earlier**, in D-142.
One drift predating this loop and one created by it.

**Decision: bind the README to the two things that can contradict it.** `BLOCKED.md` is this
project's record of what is still in the way, so a resolved entry cannot be described as undone —
checked **both ways**, because with the entry live the README must not claim the check is in place
either, and overstating is the worse direction. And the `cli.py` row must name every callable in
`hawedit.cli.__all__`, because that module's whole job is collecting things every `main()` must do,
so it is the one that grows a fourth.

**Doc-to-doc on purpose.** Branch protection is a repository setting, and a test that read it would
need the network and a token — a test that skips, and a skipped test is the quiet green this suite
is written against. The live API answer is recorded here as the measurement instead.

**Rejected: checking every module-map row against its module's `__all__`.** Forty-odd rows of
deliberate prose, most of them describing an *invariant* rather than an API, and a test demanding
symbol names would push them all toward being worse documentation. `cli.py` earns the check because
its row is a list by nature.

### The prose-grep trap, four times, now fixed structurally

The first version of the README fix left the phrase `is not done` inside its own correction
sentence, and the new test failed on it. That is the fourth occurrence:

* **D-121** — `fetch-ffmpeg.sh` *explains* `--fail` in a comment; the test asserting `--fail` was
  present matched the comment.
* **D-139** — the gate workflow *quotes* `-e '.[dev,media]'` to say what it replaced; the control
  asserting its absence matched the quote.
* **D-141** — the audit report's correction *names* the entry point it had omitted; dropping that
  name from the list again survived.
* **D-143** — the README *quotes* "is not done" while correcting it.

Each was fixed locally. `tests/test_claims.py` now has one `claims_only()` helper that removes
`**Corrected …**` / `**Amended …**` spans, and both documentation checks read through it. The
convention that causes the trap — quote the wrong sentence while correcting it — is what makes the
record readable and is worth keeping; what changes is that checks read the claim, not the history.

**The helper's own first version dropped whole paragraphs** and emptied the audit report's
entry-point list, because README puts corrections in their own paragraph while AUDIT_REPORT and
PROGRESS put them mid-bullet *after* the claim. It cuts each paragraph at the marker now.

**Mutation audit 7/7,** after 6/7. The survivor was the mirror direction: reopening `BLOCKED.md`
#7 while the README still claimed the check was in place left the suite green, because the test
returned early on a live entry instead of asserting the opposite.
`evidence/the-readme-understated-its-own-bar.md`.

## D-144

**A blocker could resolve in a form the guard cannot see.** `tests/test_claims.py` decides whether a
`BLOCKED.md` entry is still live by looking for the word `RESOLVED` in its heading. Measured across
the whole file:

```
19 entries; the current rule calls these live:
  [1, 3, 4, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19]

bold markers used in headings, and which entries use them:
  ANSWERED   [10]                <- NOT recognised as a resolution
  RESOLVED   [2, 5, 6, 7, 8, 11] <- RESOLVED
```

#10 has been marked `**ANSWERED 2026-08-08**` since that date, so the one test that consumes
resolutions —
`test_every_blocked_row_points_at_a_live_blocked_entry` — has read it as live ever since. It is
cited by nobody in `PROGRESS.md`, which is luck rather than a guard: a `BLOCKED` row pointing at
#10 would have passed, and that test exists precisely because M2.4 once sat behind a resolved #5
for two days.

**Decision: declare the vocabulary and refuse anything outside it.** `_BLOCKED_RESOLUTIONS` is
`{RESOLVED, ANSWERED}`, a heading marker outside it is a test failure, and a declared word no
heading uses is also a failure — so the set stays a description of this file rather than a
prediction about it. Adding a third word is then a deliberate edit in a diff, which is the same
inversion `scripts/verify.sh` uses for its steps: no blacklist of ways to resolve invisibly can be
complete, so the allowed forms are named instead.

**`ANSWERED` means not-live, and that is a judgment call.** `README.md` defines this file as *"What
needs Hawa"*. #10's question — which repository holds §7's two omniASR checkpoints — was answered
*by* Hawa, the answer is in `models/sources.json`, and the obstacle that survived the answer was
filed separately as **#11** (`fairseq2n` has no Windows wheel), which is itself resolved. So #10
needs nothing further from Hawa. Recorded here rather than assumed, because the alternative reading
— "answered but still blocking" — would be true for a differently written entry, and the file says
plainly that this one's blocker moved.

**Rejected: renaming #10's marker to `RESOLVED`.** One character of diff and it destroys a
distinction the record makes on purpose: Hawa *answered a question*, which is not the same event as
an obstacle going away, and #10's own text depends on the difference to explain why #11 exists.

**Rejected: treating any bold marker as a resolution.** It would have swallowed this bug and every
future one, which is the property that made the old rule wrong.

**Also re-measured this iteration, and still blocked — stated plainly rather than left implied:**

```
#3  GEMINI_API_KEY: not set                      (hawedit-credentials --check, exit 1)
#4  HF_TOKEN present: False
    metadata HTTP 200 | gated: auto
    download HEAD 401 -> still gated
```

Both are Hawa's and neither is closable here. The remaining live entries are #1, #3, #4, #9, #12,
#13, #14, #15, #16, #17, #18 and #19 — twelve after #10 stops counting.

**Mutation audit 6/6,** after 5/6. The survivor was a bad mutation of mine: it made a `PROGRESS.md`
row cite the answered #10, but anchored inside **M5.5**, whose status is `PARTIAL` — a row that test
does not examine — so it measured nothing. Re-anchored inside **M0.12**, which is `BLOCKED`, and
caught. That is the third such mutation in this session after D-137's retry ceiling and D-141's
`revisions.json`; a survivor is a claim about the tests, a bad mutation is a claim about nothing.

**A measurement of mine was wrong in the same iteration and is corrected here.** Checking #3 I ran
`… --check 2>&1 | tail -6; echo "exit=$?"` and read `exit=0`, which is **`tail`'s** status, not
Python's. Re-run without the pipe, `--check` exits **1** with no key configured — so `README.md`'s
*"exits non-zero if unusable"* holds and there was no finding there.
`evidence/a-blocker-could-resolve-invisibly.md`.

## D-145

**The §7 check on the confidential route was a copy, and no test held the copy.** `README.md` says
`judge.py` is *"The judge contract: shadow never routed, 200K tier ceiling, promotion only on
evidence."* Adversarial pass #22 mutated all three claims one at a time. Eighteen mutations, one
survivor:

```
SURVIVED  VertexGeminiJudge stops resolving itself against §7
```

`VertexGeminiJudge` subclasses `GeminiJudge` but does **not** call `super().__init__` — it
reimplements it, correctly, because Vertex authenticates with ADC and has no API key to read. So
the parent's `route(self)` is *copied* into the subclass rather than inherited, and only the
parent's copy was tested (`test_the_shadow_cannot_be_constructed_as_the_judge`, which builds a
`GeminiJudge`). Deleting `route(self)` from `VertexGeminiJudge.__init__` left the judge, gemini,
path_a, editorial_bench and clip suites all green, and the artifact it then produced was a real
endpoint:

```
constructed: gemini-3.1-pro
url: https://aiplatform.googleapis.com/v1/projects/proj/locations/global/
     publishers/google/models/gemini-3.1-pro:generateContent
```

That is the *confidential* route — the ZDR path §3 reserves for material that must not train a
model — pointed at the one model §3 Stage 4 marks "evaluated, not routed", and billed. The guard
itself was never wrong; nothing would have noticed it going.

**Decision: hold the wiring for the class list, not for the class.** `tests/test_gemini.py` now
names every constructible judge in `_concrete_judges()` and checks that set **bidirectionally**
against `GeminiJudge` and its transitive subclasses — a subclass with no constructor fails, and a
constructor naming a class that no longer exists fails too. Each named judge is then built as the
shadow and must raise `NotRoutable`, with a control that the same constructor builds the pinned
incumbent and puts it in the request URL. Five tests, floor 1422 → 1427.

**Rejected: making `VertexGeminiJudge` delegate to `super().__init__`.** It reads like the real
root fix and is not: the parent's body ends by reading `GEMINI_API_KEY` and raising
`GeminiUnavailable` when it is absent, which is precisely what the ADC path must not do. Refactoring
to share the invariant would mean splitting the parent's `__init__` in two for one subclass — an
abstraction for one product — and it would still leave the *next* subclass free to skip whichever
half it liked. The class list catches that; a refactor does not.

**Rejected: one more test asserting `VertexGeminiJudge` refuses the shadow.** It closes today's hole
and none of the others. This is the fifth unheld-wiring finding in this session (D-105, D-133,
D-135, D-140), and every one of them was a call that existed and was believed rather than asserted.
A guard that enumerates is worth more than a guard that names.

**What survived, stated plainly.** The other two README claims held under every mutation: the
ceiling refuses a request at exactly 200,000 tokens and an uncounted one, in `judge.py` and again at
both real call sites (`gemini.py`'s counted-size check and `path_a.py`'s); promotion refuses an
empty regression set, a set below the 20-item floor, and a tie above it. So did four claims the row
does not make: `to_editorial()`'s second refusal, `_is_kurdish` on an English title, D-076's
check-after-normalization order, and the payoff-inside-the-clip range. **19/19** after the fix,
including a mutation of the new guard itself — dropping `VertexGeminiJudge` from the class list is
caught by the bidirectional check.

`evidence/adversarial-pass-22-2026-08-10.md`.

## D-146

**One Ctrl-C wedged a work directory for good.** D-072 built §2's three sidecars before writing
any of them and unlinks them in its `except`, and recorded that this "closes" D-071's
delivery-atomicity shortfall for the sidecar set. The clause catches
`(DeliveryError, RenderError, OSError)`. A Ctrl-C is a `KeyboardInterrupt` — a `BaseException` the
clause never sees — and a `SIGKILL` or a power cut runs no clause at all. Measured on a real run
against `tests/fixtures/kurdish-speech-3cuts.mp4`, interrupted at the second of the three writes:

```
--- run 2: interrupted the instant the SRT write begins ---
  KeyboardInterrupt propagated
on disk afterwards:
   atomicity-s0-0.ass
   atomicity-s0-0.json      <- §2's editing manifest, on its own
   atomicity-s0-0.mp4       <- playable, captioned
missing: ['atomicity-s0-0.edl', 'atomicity-s0-0.srt']
```

and then, the part that makes it worse than the partial set:

```
retry RAISED FileExistsError: refusing to overwrite existing delivery artifact(s): ...ass, ...
after the retry: ['atomicity-s0-0.ass', 'atomicity-s0-0.json', 'atomicity-s0-0.mp4']
```

D-071's guard refused when *any* of the five paths existed, so the very files the interrupted run
stranded made the retry impossible. A manifest and a playable MP4 with no captions is exactly
D-072's failure mode arriving through a door D-072 did not cover, and the work directory could only
be recovered by hand.

**Decision: a delivery is finished when it says so, and only then.** Two changes, and they are
different guarantees:

* Every §2 sidecar and the ASS go through `_write_atomic` — staged as `.<name>.tmp` and renamed —
  so a kill cannot leave a file that exists, is readable and is half-written. `transcripts.py` and
  `visual_pipeline.py` already did this for their own artifacts; the delivery set had nothing.
* `{clip_id}.delivery.provenance.json` is written **last**, after all five artifacts, and records
  each one's byte length. `_assert_no_existing_artifacts` refuses only when that record exists and
  matches. Anything else — no record, unreadable record, missing file, wrong length — answers "not
  a delivery" and the set is redone. D-132's shape, where every failure mode falls through to
  redoing the work rather than to trusting it.

The name follows the work directory's own convention: Stage 0 already writes
`proxy.mp4.provenance.json` and `audio.wav.provenance.json` beside their artifacts.

**Byte lengths rather than digests, deliberately.** The failure this addresses is truncation and
absence, which a length catches for free from `stat()`. A digest would additionally catch a
*tampered but valid-length* file, which is not a failure mode a killed process produces, and it
would mean re-hashing a 1080×1920 MP4 on every guard call — three calls per run, one of them before
any expensive stage. Recorded rather than assumed: if content authenticity is ever wanted here it
needs a different mechanism than a completion record.

**The narrowing I am accepting, stated plainly.** The old rule caught one case the new one does
not: two runs of the *same* media id and the *same* sentence selection into the *same* work
directory at the same time, where the second reached the pre-write guard after the first wrote its
ASS. That was never a real defence — if the second run passes the guard first, both proceed and
collide anyway — so it was best-effort against a duplicate invocation, and it is traded for a
certainty: every interrupted run used to be unrecoverable. Not a threshold and not a guess; a named
exchange.

**Rejected: keeping the any-file refusal and giving the operator a better error.** It documents the
wedge instead of removing it, and §10/10 asks for atomic *and resumable* delivery.

**Rejected: deciding staleness from mtime.** "Older than N minutes is abandoned" is exactly the
guessed threshold the hard rules forbid, and it would call a slow live run abandoned.

**Rejected: deleting the leftover set before redoing it.** D-072 keeps the MP4 and ASS on purpose,
and every writer here already overwrites (`ffmpeg -y`, `write_text`), so a complete retry replaces
all five files without a single `unlink`. Nothing is deleted that a retry does not immediately
rewrite.

**The overwrite is reported, not silent.** `PipelineRun.resumed_over` names the abandoned artifacts
and appears in the emitted JSON — `[]` on a clean run, for D-110's reason that an absent key cannot
be told apart from a build that does not record it. Silently overwriting another run's files is
`BLOCKED.md` #12, and this is the same shape from the other direction.

**Mutation audit 10/10,** after 9/10. The survivor was making a missing artifact `continue` instead
of falsifying the record: every other test stayed green, and "someone deleted the SRT" would have
become a permanent refusal to produce one. Now pinned by
`test_a_delivery_missing_one_of_its_files_is_not_a_delivery`. Five existing tests had to change,
and all five got stronger: `_existing_artifact` plants a *finished* delivery — five files plus the
record, written by the production writer — instead of one file, and the three tests that watch
`Path.write_text` resolve the staging name back to its target so they still assert on *which
artifact* is written.

Gate: `VERIFY OK — hawedit gate green`, 1434 tests (floor 1427 → 1434).
`evidence/delivery-set-not-atomic-against-a-kill.md`.

## D-147

**`--auto-select` accepted a Stage 3 producer that, since D-117, cannot produce.** The rule read

```python
if args.auto_select and not (args.visual or args.gemini or args.vertex_project):
    raise ValueError("--auto-select needs at least one Stage 3 producer")
```

and `--visual` satisfies it. But §3 Stage 2 retrieves against a *query*, and there are exactly two
sources for one: `--visual-query`, or Path A anchoring one from its best candidate — which needs
`--gemini`/`--vertex-project`. D-117 removed the third, the whole normalized transcript, because a
corpus is not a query (it also asked `embed_text` for 40.89 GiB on a 23.99 GiB card). So from D-117
onward `--visual` alone can never rank a window, never surface a candidate, and never answer
`--auto-select` — and the guard written to catch exactly that let it through.

**Measured on the real 38-minute `ZAR38MinTest.mp4`**, with the recorded canonical transcript
standing in for Stage 1 and every §7 visual checkpoint present on this machine:

```
$ python -m hawedit.pipeline "…/ZAR38MinTest.mp4" --work-dir … --media-id zar38final \
    --transcript work/zar38-final/transcripts/zar38final.transcript.raw.json \
    --visual --timelens --auto-select --qc-pass --json          exit 1

work dir created 07:48:33, last write 07:51:23                  → 170 s
  stage0/audio.wav              74,039,412 bytes   07:49:56
  stage0/proxy.mp4              51,124,346 bytes   07:50:23     → Stage 0 ≈ 111 s
  186 sentences · 164 visual windows planned · speech_without_transcription_ms 664

skipped: visual_index, discovery, editorial, boundary, render, delivery
  visual_index  §3 Stage 2 retrieves against a query and this run has none…
  discovery     Every enabled discovery path ran and returned no candidates…
candidates: 0
```

170 seconds of real work — a 38-minute source demuxed, scene-detected and VAD'd — to reach a
refusal that `argv` settled before the first byte moved. No checkpoint was ever loaded: the
composer's embedder is lazy and Stage 2 skipped before the first window, so `embeddings/` was never
created. The cost is Stage 0, not GPU time, and that is the whole of it.

Reproduced on the 4.2 s fixture in **3.5 s** with the same skip chain and 0 candidates. The control
discriminates: the same command *with* `--visual-query` takes **14.0 s**, actually loads the
embedder and runs retrieval, then refuses for a media-specific reason — *"the index holds 3 windows
and 7 survivors"*. The query is what makes `--visual` a producer.

**Decision: the producer test asks whether a path can produce, not whether a flag is present.**

```python
stage_3_can_produce = bool(args.gemini or args.vertex_project) or bool(
    args.visual and args.visual_query
)
```

One expression, read once, in the same argv block as the ten refusals beside it — the block where
`--visual-query requires --visual` already lives, which is this rule's mirror image.

**`--visual` on its own is still allowed, deliberately.** A run that passes it and nothing else
gets Stage 0, §4.1, the §2 index, §4.2 segmentation and an honest `visual_index` skip; that is a
legitimate thing to ask for and the report says exactly what happened. What is refused is
`--auto-select`, because that flag is a *promise to select*, and the guard exists to refuse when
nothing can. Rejected refusing `--visual` without a query outright: it would break a run that
reports itself correctly, and it decides for the user what they wanted.

**Rejected letting the runtime skip carry the whole message.** It already does, and it arrives 170
seconds late. The condition depends on `argv` alone — D-071's reasoning about the overwrite guard,
which was knowable "the whole time" and fired after the billed call.

**The runtime message was also wrong, and is corrected here.** `_STAGE_3_DISCOVERY` told the reader
*"--visual for composed Path B"*. A reader who follows that gets the run above. It now names
`--visual-query` and says why the query is not optional.

**Mutation audit 6/7, and the survivor is a bad mutation of mine.** Dropping the `args.visual`
conjunct — `bool(args.visual_query)` alone — changes no reachable behaviour, because
`--visual-query requires --visual` refuses four lines earlier: measured,
`--visual-query q --auto-select` exits 2 with that message. So the mutation asserts nothing, which
is the fourth of mine this session after D-137, D-141 and D-144. It did surface something real
though: that earlier refusal had **no test of its own**, so the ordering my expression leans on was
held by nothing. `test_a_query_without_the_visual_path_is_refused_before_the_producer_test` holds it
now. Six mutations caught, including three controls pulling in opposite directions — a test that
refuses everything and a test that refuses nothing both go red.

`evidence/auto-select-accepted-a-path-that-could-not-produce.md`. Floor 1434 → 1440.

## D-148

**§3's governance box has two gates, and only one of them reddened anything.** `Governance`
carries `assert_permits_upload` for the Gemini Developer API and `assert_permits_vertex` for the
*confidential* Vertex route — the paid, ZDR route §3 Stage 3 reserves for COMMS and KAAE material
and calls "mandatory, not advisory". Each was neutered in turn (body replaced by `return`) against
a baseline verified green first, and the whole gate suite run:

```
baseline green: True
held    the Developer API gate stops refusing (assert_permits_upload)
          red: test_confidential_material_without_zero_data_retention_is_refused,
               test_claimed_zero_data_retention_must_name_who_confirmed_it,
               test_flags_cannot_turn_the_developer_api_into_a_confidential_vertex_route,
               test_counting_tokens_cannot_send_confidential_text_before_the_zdr_gate
UNHELD  the confidential Vertex gate stops refusing (assert_permits_vertex)
```

**The artifact, with the Vertex gate neutered.** A `VertexGeminiJudge` built with
`Governance(confidential=True)` — ZDR not configured, nobody attributed — made **two** HTTPS calls
and came back with a verdict:

```
projects/client-project/locations/global/publishers/google/models/gemini-2.5-pro:countTokens
projects/client-project/locations/global/publishers/google/models/gemini-2.5-pro:generateContent
    confidential transcript present in the prompt: True
    source JPEG bytes present: True
```

100% of a client's Kurdish transcript plus the real source pixels, on the route whose entire reason
for existing is that this must not happen, and 1,440 tests stayed green.

**Why it was invisible.** All four §3-governance tests build a `GeminiJudge` through `a_judge()`,
which routes to `assert_permits_upload`. The only `VertexGeminiJudge` ever given a `Governance` is
`test_confidential_vertex_route_uses_adc_bearer_and_multimodal_payload`, and it supplies the fully
permitted triple and asserts the call *succeeds* — green whether or not the gate exists. Measured:
`grep -rn "assert_permits_vertex" tests/` returns **0 hits**.

**This corrects a recorded claim.** `PROGRESS.md` M2.8 says, from adversarial pass #20:
*"Everything in `gemini.py` survived the pass … and the ZDR gate all redden when reverted."* True
of one gate, false of the one that carries confidential material. The pass reverted the gate it
could see. Recorded as a correction in the cell rather than as prose after the table, and the M2.8
row keeps its status: the code was right, the coverage was not.

**Decision: hold governance as a property of the class *set*, the way §7 identity already is.**
D-145 built `_concrete_judges()` — every constructible judge, checked bidirectionally against
`GeminiJudge`'s transitive subclasses — to hold the §7 model-identity check. Its builders now take
an optional `governance` and `transport`, so the same enumeration is built under every confidential
state §3 forbids, with a recording transport. A future subclass inherits both checks the day it is
added, which is the only version of this that stays true.

**Asserted on the transport, not on the exception.** `pytest.raises(GeminiUnavailable)` alone is
satisfied by a gate that raises *after* the upload — the failure mode is the bytes, not the
traceback — so every case asserts `api.urls == []`. The mutation that moves the check after the
billed call is caught by exactly that assertion.

**Rejected: one test for `VertexGeminiJudge`.** It closes this hole and none of the others; the same
reasoning as D-145, and this finding is the proof that D-145's own enumeration needed extending
rather than copying.

**Rejected: making `Governance` refuse in `__post_init__`.** A `Governance` describing a state that
is legal for one route and illegal for another is not itself invalid — `confidential=True` with no
ZDR is exactly right for a run that will never touch a cloud route. The refusal belongs at the
upload boundary, which is where both gates already are.

**Mutation audit 10/10, after 6/8. Both survivors were real gaps in my own table, not bad
mutations:**

* Deleting the zero-data-retention rule *entirely* left everything green, because every forbidden
  state I had listed also lacked an attribution — so rule two caught them all. The state that
  separates them is `confidential=True, zero_data_retention=False, confirmed_by="Hawa"`: somebody
  is recorded as having approved, and ZDR is still not configured. Now its own test.
* Deleting `generate_json`'s own governance check left everything green, because its only caller in
  `src/` (`path_a.py`) calls `count_parts` first and *that* refuses. A guard that is only correct
  because of the order its one caller happens to use is a guard the next caller walks past. Both
  public entry points are now gated on their own, for both judge classes.

Ten mutations caught, including one that deletes `VertexGeminiJudge` from the enumeration (caught by
D-145's bidirectional check) and one that stops the subclass overriding `_assert_governance` at all
(caught by the permitted-route control, which must keep succeeding).

**Also measured this iteration, and not fixed here.** Twelve of the CLI's fourteen argv refusals in
`_run_from_args` are unheld — deleting the `if`/`raise` outright leaves all 1,440 tests green. Only
`--visual-query requires --visual` and the `--auto-select` producer test redden, both added by
D-147/D-148 this session. `tests/test_pipeline.py::test_the_cli_refuses_flags_whose_prerequisites_are_absent`
looks like coverage for three of them and asserts only `main(...) == 2` — the exit code for *every*
caught exception, so it passes whether the refusal fires or the run merely dies later on an empty
`source.mp4`. A test that passes for both answers measures nothing. That is the next increment, not
this one.

**A measurement of mine was wrong first and is recorded rather than quietly replaced.** The first
sweep appended ` and False` to each condition; `ruff` flags that as **SIM223**, so every mutation
broke the lint step, the nested-gate test saw a non-4 exit, and all fourteen guards reported "held"
naming one unrelated test. A uniform result across unrelated mutations is an artifact, not a
finding. Redone by deleting each statement whole by its AST line span, with the lint status printed
beside each result so the next contaminated run says so itself.

`evidence/the-confidential-routes-zdr-gate-reddened-nothing.md`. Floor 1440 → 1453.

## D-149

**Twelve of the CLI's fourteen argv refusals were held by nothing, and the test that looked like
coverage for three of them passed either way.** `_run_from_args` opens with fourteen
`if …: raise ValueError(…)` refusals for flag combinations that cannot work. Each was deleted
whole — by its AST line span, so the file still lints and typechecks — against a baseline verified
green first, whole gate suite each time:

```
held: 2   unheld: 12
  UNHELD  --transcript and --omni-asr are mutually exclusive Stage 1 sources
  UNHELD  --omni-asr-runtime and --wsl-distro require --omni-asr
  UNHELD  --gemini and --vertex-project are mutually exclusive cloud routes
  UNHELD  cloud judging and --verdict are mutually exclusive Stage 4 sources
  UNHELD  cloud discovery requires --transcript or --omni-asr
  UNHELD  --sentences requires --transcript or --omni-asr
  UNHELD  --verdict requires a Stage 1 source and --sentences
  UNHELD  --visual requires --transcript or --omni-asr
  UNHELD  --qc-pass requires --sentences or --auto-select
  UNHELD  --auto-select requires --transcript or --omni-asr
  UNHELD  --timelens and --face-reframe require --sentences or --auto-select
  UNHELD  governance flags apply only with a Gemini or Vertex route
```

The two that held are `--visual-query requires --visual` and the `--auto-select` producer test,
both given tests by D-147 and D-148 this session.

**The test that looked like coverage.** `test_the_cli_refuses_flags_whose_prerequisites_are_absent`
ran three of these combinations and asserted `main([source, *flags]) == 2`. Exit 2 is the code for
*every* exception `_run_from_args` catches. Measured, with
`--sentences requires --transcript or --omni-asr` deleted outright:

```
exit code with the guard DELETED: 2
what it actually said: ✗ ffmpeg.EXE failed (3199971767): [in#0] moov atom not found
                         [in#0] Error opening input: Invalid data found when processing input
```

It was asserting that an empty `touch()`ed `source.mp4` breaks Stage 0 — and paying for an ffmpeg
subprocess to do it. A test that passes for the right answer and the wrong one measures nothing.

**Decision: assert *which* refusal fired, and bind the set to the source.** `_REFUSAL_CASES` gives
one argv per refusal; each case asserts exit 2, the refusal's own message in stderr, and that **no
work directory exists** — the refusal is about argv, so it must land before any work. Because the
block is ordered and the first match wins, every case also pins the ordering it depends on.

`_argv_refusals()` reads the messages out of `_run_from_args`'s **AST** rather than listing them
here, and `test_every_refusal_in_the_source_has_a_case` compares the two sets **both ways**. A
fifteenth refusal is covered the day it is added, not the day someone remembers. That the set is
well defined is a fact about this function, stated rather than hoped: every `ValueError` it raises
directly is an argv refusal, and nothing later in it raises that type.

**One refusal is unreachable, and is recorded as such rather than deleted.**
`--auto-select requires --transcript or --omni-asr` cannot fire: `--auto-select` needs a producer
that can produce, and both producers need a Stage 1 source of their own — `--gemini`/
`--vertex-project` hit *"cloud discovery requires --transcript or --omni-asr"* and
`--visual --visual-query` hits *"--visual requires --transcript or --omni-asr"* — so anything
reaching it already has one. `_PRE_EMPTED_REFUSALS` names it with the guard that pre-empts it, and
a test proves the pre-emption by running the argv that would reach it. Rejected deleting it: the
unreachability is a property of the block's *order*, not of the rule, and if that order changes the
test is where it shows.

**What each assertion actually buys, measured rather than assumed.** My first differential
predicted that the message assertion was what caught a deleted guard. It is not:

```
guard deleted, message assertion present: red
guard deleted, message assertion removed: red   <- still red
    the only failure: test_every_refusal_in_the_source_has_a_case
```

The **binding** catches a deleted guard, because the case then names a refusal the source no longer
raises. What the message assertion catches is a guard whose *condition* is wrong rather than absent
— inverting `--qc-pass`'s condition:

```
condition inverted, message assertion present: test_the_cli_refuses_a_combination_that_cannot_work
                                               [passing QC on nothing] FAILED
condition inverted, message assertion removed: that failure disappears
```

Two independent nets for two different failure modes. Recorded this way because the prediction was
wrong and the measurement is the finding.

**Mutation audit 17/17,** after 15/18. The three survivors were:

* **A real gap.** `_PRE_EMPTED_REFUSALS` could absorb a *reachable* refusal and excuse it from
  needing a case — one line, and a live guard drops out of coverage. The two lists are now asserted
  disjoint.
* **Two bad mutations of mine.** Removing the message assertion, and removing the work-directory
  assertion, each *alone*, with the source intact. Neither changes behaviour on an unmutated
  source, so neither measures anything — a test's discriminating power only shows against a defect.
  Replaced by the differential above, and by a source mutation only the work-directory assertion
  can catch: making the runner `mkdir` the work directory before validating argv, so every refusal
  still fires with its own message and the run has already prepared state. That one reddens.

That is the fifth bad mutation of mine this session, after D-137, D-141, D-144 and D-147. The
pattern is worth naming: mutating a *test* in isolation asks whether the test is redundant today,
not whether it is load-bearing — the useful question needs the defect present too.

`evidence/twelve-refusals-nothing-held.md`. Floor 1453 → 1466.

## D-150

**Adversarial pass #23, on M5.2 (`qwen_visual.py`, DONE). The row's own claims survived; Kurdish
invariant #3 did not.** Both Stage 2 adapters normalize the query before the model reads it, and
both docstrings say why — the window embeddings were built from §4.1-normalized text, so a raw
query *"is comparing two different alphabets, and the failure is not an error, it is a slightly
wrong score"*. Each call removed in turn against a baseline verified green first, whole gate suite
each time:

```
baseline green: True
UNHELD  the embedder stops normalizing the query (invariant #3)
UNHELD  the reranker stops normalizing the query (invariant #3)
```

`tests/test_qwen_visual.py` did not mention normalization anywhere. `embed_text` was called by **no
test at all**, and the two tests that call `score` pass `"ڕۆژنامەوانی"` — already §4.1-normalized, so
the call under test was a no-op in the only place it ran. An invariant the hard rules call
non-negotiable was enforced in exactly two lines and asserted by nothing.

**What it costs, measured on the codepoints rather than argued.** §4.1's collisions are what an
Arabic keyboard produces:

```
'كوردي'  ->  'کوردی'     0x643 -> 0x6a9   (Arabic kaf -> Kurdish kaf)
                          0x64a -> 0x6cc   (Arabic yeh -> Kurdish yeh)
'ده\u200cست' -> 'دەست'    ZWNJ dropped, 0x647 -> 0x6d5
'٢٠٢٦'  ->  '2026'       Arabic-Indic -> ASCII
```

None of these is an error at any layer. The query embeds, the reranker scores, every number stays
in range, and the retrieval is quietly against a different alphabet from the corpus.

**Decision: assert on what the model was asked to read, and enumerate the adapters.**
`StubProcessor` now records the conversation as well as the kwargs, because invariant #3 is a claim
about that text and nothing else — the return value cannot show it, since a wrong-alphabet query
still yields a vector and still yields a score in [0, 1]. `_STAGE_2_QUERY_READERS` names both
adapters and `_classes_taking_a_query()` reads the module for every class with a method taking a
`query`, compared bidirectionally: a third adapter fails until someone says how to drive it. D-145's
shape, and the third time this session it has been the right one.

**The query used is one string carrying four collisions at once,** and the assertions name the
codepoints — `0x643`, `0x64a`, ZWNJ, Arabic-Indic digits must all be absent from what reached the
model, and the normalized form must be present. A mutation that merely *changed* the query cannot
satisfy that.

**The control is idempotence.** An already-normalized query must arrive byte-identical, so an
adapter that mangled or dropped every query — which would pass the first test — fails. Both
drop-the-query mutations are caught by it.

**Rejected: asserting the returned vector instead.** It is the artifact one layer too far: with the
real checkpoint the difference between a normalized and a raw query is a small change in a
unit-norm vector, which is exactly the "slightly wrong score" that hides. The text is where the
defect is legible, and the test runs without 4 GB of weights, on CI, where `models/` does not exist.

**Rejected: normalizing at the caller instead.** `visual_pipeline` is not the only caller a query
can arrive from, and both docstrings already argue for doing it inside — *"doing it inside means a
caller cannot forget"*. The defect was never the placement; it was that nothing checked.

**What survived the pass.** M5.2's stated claims all hold: the three cited evidence files exist
(`m5-2-embedder.md`, `m5-2-reranker.md`, `m5-2-frames-reaching-the-model.md`), and README's three
claims for this module — pooling read from the checkpoint, §7 role checked before the weights load,
no silent CPU fallback — each still have a test that reddens (`does not state how`, `cannot be used
as the visual embedding model`, `reports no CUDA`). The row was not overclaiming; it simply never
claimed the invariant, and the invariant was the unheld thing.

**Mutation audit 8/8**, including both defects restored, both adapters sending the raw query
*beside* the normalized one (caught by the raw-absent assertion), both dropping the query entirely
(caught by the idempotence control), and both directions of removing an adapter from the
enumeration.

**One methodological note, because it bit me twice this session.** A third mutation — removing both
calls at once — reported `held`, and it is not a result: with `normalize_sorani` no longer used the
import is dead, ruff raises F401, and the nested-gate test fails on lint rather than on the tests.
The probe printed `[lint dirty]` beside it and the audit now strips the import when a mutation
orphans it. Same shape as D-148's SIM223 contamination.

`evidence/adversarial-pass-23-2026-08-10.md`. Floor 1466 → 1471.

## D-151

**Kurdish invariant #1's tamper evidence had two refusals and only one of them was held.**
`verify_raw_integrity` reads the SHA-256 recorded when the canonical transcript was written and
compares it. It refuses twice: once when the digest cannot be read at all, once when it does not
match. Each neutered in turn against a baseline verified green first, whole gate suite each time:

```
baseline green: True
UNHELD  a missing or unreadable digest is treated as verified
held    a digest mismatch is treated as verified (the half with three tests)
          red: test_byte_only_tampering_with_raw_is_detected, …
```

All three existing tamper tests reach the check by **editing the transcript**. None touches the
sidecar. So the state that removes the evidence entirely — delete one file — was the state nothing
checked.

**The artifact.** With that branch neutered: write the canonical transcript, rewrite it, delete the
sidecar, and ask the two questions a run asks:

```
as written          : 'ئه‌مه‌ زۆر باشه‌'
verify_raw_integrity returned cleanly with NO sidecar and a tampered file
what a run gets back: 'ئەمە دەقێکی جیاوازە — TAMPERED'
```

Invariant #1 — *"raw is written once and never mutated"* — defeated by deleting one file, with all
1,471 tests green.

**Decision: enumerate the states that remove the evidence, and check both doors.** Five states —
deleted, empty, whitespace only, not ASCII, a directory — each asserted against both
`verify_raw_integrity` (which `pipeline.py` calls directly) and `reusable_raw` (which Stage 1 reuse
goes through). Two doors, because a guard correct only on the one its current caller happens to use
is the defect D-148 found in `generate_json`.

**Which states belong is a judgment, and it is recorded as one.** Nothing can derive the list —
there is no oracle for "ways a digest can stop being a digest". So it is written once as
`_SIDECAR_BREAKERS`, the parametrisation is *derived* from it, and a test pins that derivation.
Found by mutation: with the state list spelled out separately, dropping `"deleted"` from it left
the suite green while the code producing that state sat behind, unused and unrun. The derivation
check cannot validate the judgment, and says so in its own docstring; what it stops is the two
halves drifting apart.

**Rejected: making `read_raw` verify.** It is the obvious-looking root fix and it is wrong here.
`test_byte_only_tampering_with_raw_is_detected` asserts `store.read_raw(...) == a_raw()` on a
*tampered* file, on purpose — its point is that parsing and re-serializing would erase the edit, so
the byte digest is the only thing that sees it. `read_raw` is deliberately the unverified read and
verification is an explicit, separate step; both real callers take it.

**Rejected: treating a rewritten sidecar as a defect to fix here.** An edit that updates the
transcript *and* recomputes the sidecar passes, and no unkeyed digest can prevent that — it would
need a signature or a MAC with a key this project does not have. Named rather than quietly implied
by a test that would suggest otherwise.

**Mutation audit 6/7.** Caught: the defect restored; refusing only `FileNotFoundError`; refusing
only `UnicodeError`; the reuse door skipping verification; the comparison replaced by `actual =
recorded`; and the parametrisation dropping a state. The survivor is a bad mutation of mine —
reading the sidecar as UTF-8 with `errors="replace"` still refuses, because the garbage it decodes
to fails the *mismatch* branch instead. That is worth stating rather than hiding: the two refusals
back each other up for a sidecar that is present but wrong, and only **total absence** ever had a
single line of defence. It also printed `[lint dirty]` (my mutation ran past 100 columns), so the
run would not have counted either way.

`evidence/invariant-1-had-no-digest-no-problem.md`. Floor 1471 → 1488.

## D-152

**The one command in this project that spends money spent it and then refused.** `README.md`
offered `python -m hawedit.smoke  # two real calls, ~$0.003` and said it *"runs §3 Stage 3 Path A
over a built-in Sorani sample and §3 Stage 4 on the top candidate, then prints the Kurdish title it
got back"*. Run exactly as documented, `smoke.py` made **both** Path A calls — `countTokens` and
`generateContent` — printed the candidates, and then reached

```python
if args.video is None:
    print("✗ Stage 4 needs --video; text-only visual judging is refused", file=sys.stderr)
    return 1
```

and exited 1, having never run Stage 4 and never printed a title. `--video` appeared nowhere in the
README. This is D-071's shape a third time: a refusal `argv` settles, placed after the billed call.

**Decision: hoist it above everything billable, and above the confirmation.** The check now runs
straight after the key check and returns **2** — a refusal, not a failed run. Above the
confirmation prompt as well, because being asked to authorise spending on a run that cannot finish
is its own defect; a user who answers "y" there has agreed to nothing they will get.

**Exit 1 → 2 is deliberate.** Everywhere else in this project 2 means *refused before doing
anything* and 1 means *ran and could not finish*. Once the check precedes every call, 2 is the
honest code. No test asserted the old value — that was the whole problem.

**The measurement that made this bigger than a missing flag.** The built-in sample spans
**0..13,000 ms** (22 words). The only Kurdish video in the repository,
`tests/fixtures/kurdish-speech-3cuts.mp4`, is **4.162 s** and is a different recording. Extracting
judge keyframes from it, measured:

```
(0, 4000)     20 frames, timestamps 100, 300, 500, 700, 900, 1100 …   all inside the file
(0, 13000)     6 frames, timestamps 325, 975, 1625, 2275, 2925, 3575     all inside the file
(5000, 13000) KeyframeError: ffmpeg failed to extract judge keyframes

[corrected 2026-08-10 by D-153: this block first read `20 frames` for the 0..13000 span. It returns 6 — the 20 were leftovers from the previous span, the very defect D-153 fixes, picked up by a probe of mine that reused one output directory.]
```

So there is no video here that makes the live check runnable: a shorter one either fails outright
or returns frames stamped across a span the file does not contain. **`BLOCKED.md` #20** records it
as Hawa's, because it is a recording rather than a decision, and names what I refused to do instead
— re-cutting the sample to fit a different video (it would make the two agree by construction), and
shipping a synthetic one (`AGENTS.md` forbids the stub, and Stage 4's whole point is the actual
pixels).

**The README now states the requirement and the gap** rather than promising a check that cannot
run, and two bindings hold it: the documented invocation must carry `--video` exactly when
`smoke.py` requires it, and every `BLOCKED.md #N` the docs cite must exist.

**Two existing tests changed, and both got stronger.**
`test_it_sends_nothing_until_a_human_agrees` and `test_a_declined_prompt_at_eof_also_sends_nothing`
drove `main([])` to the confirmation prompt, which the new guard short-circuits. They now pass a
`--video`, so the run they decline is one that could otherwise have proceeded — declining a run
that would have refused anyway measures nothing.

**Mutation audit 6/6, after 3/6.** Two survivors were real gaps in my own work: nothing bound the
README's invocation to `smoke.py`'s requirement, and nothing checked that a `BLOCKED.md #N` cited
in the README exists — found by mutating `#20` to `#21`, which passed.
`test_every_blocked_row_points_at_a_live_blocked_entry` covers PROGRESS's `BLOCKED` rows only. The
third was a bad mutation of mine: I "moved" the guard by inserting a no-op line, which changes
nothing. Moving a block is a delete *plus* an insert, and applying either half alone measures
something else — the audit harness now takes a list of edits for one mutation, and that mutation is
caught by the confirmation test.

`evidence/the-live-check-spent-money-then-refused.md`. Floor 1488 → 1494.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`, exit 1. Hawa
reports billing is solved upstream; the key is not on this machine, and the credential panel is the
only way it gets here — it reads with `getpass`, writes through `O_NOFOLLOW` at `0600`, rewrites the
ACL to the owner alone, and refuses any path git tracks. Nothing in this iteration simulated a key.

## D-153

**A judge keyframe could carry a timestamp the video never had, and a run could be handed the
previous run's frames.** Two defects in `extract_judge_frames`, both found while re-checking a
number I had published the day before — and the second is why that number was wrong.

**1. The stamps came from how many frames came back, not from where they came from.**

```python
step_ms = (out_ms - in_ms) / len(paths)
```

`fps=count/duration_s` is the rate ffmpeg is *told* to sample at, so frame *i* comes from
`in_ms + (i + 0.5) × (span / count)`. Dividing by `len(paths)` instead only agrees while ffmpeg
returns exactly `count` frames. When the source runs out before the span does it returns fewer, and
the survivors are stretched across the whole request. Measured on the 4.162 s fixture, span
`0..13000 ms`:

```
before: 6 frames stamped 1083, 3250, 5417, 7583, 9750, 11917   4 past the end, 4 distinct images
after:  6 frames stamped  325,  975, 1625, 2275, 2925,  3575   0 past the end
```

The judge was being told a shot came from 9,750 ms of a video that stops at 4,162. Nothing
downstream could notice: a mis-stamped frame is a valid JPEG of real pixels, and `JudgeRequest`
checks only that the timestamp falls inside the *candidate span*, which a stretched stamp does.

**2. `glob` could return an earlier run's frames, and the existing guard could not see it.**
Adversarial pass #15 added `if len(paths) > count: raise` for exactly this, with a test. It catches
only the leftovers that push the total *over* `count`. ffmpeg overwrites `judge-001.jpg` upward, so
a run producing **fewer** frames than the last leaves the older, higher-numbered files behind and
the total is unchanged:

```
0..4000  count=20  ->  20 files
0..13000 count=20  ->  6 written, 14 left over, len(paths) == 20, no refusal
                       the call returned 20 frames, 14 from the previous extraction
```

The pipeline's Stage 4 directory is named per candidate (`stage4/<candidate_id>`), so re-running a
candidate is exactly this state.

**Decision: widen the existing refusal rather than replace it.** Pass #15's recorded intent is that
Stage 4's evidence comes from this extraction alone; the mechanism it chose — refuse — is kept, and
the check moves *before* ffmpeg writes anything and fires on **any** pre-existing `judge-*.jpg`. The
`len(paths) > count` check stays as the second net. Its test keeps its assertion, now matching on
`from an earlier run`.

**Rejected: clearing the stale frames and carrying on.** That is D-146's shape and it is tempting —
these are scratch files, not deliverables, and refusing wedges a re-run. But pass #15 chose refusal
deliberately for evidence that reaches a billed judgement, and reversing a recorded decision to save
one `rm` is not a trade I will make silently. The refusal names the directory and what to do. If the
wedge ever costs more than the risk, that is a decision to record, not to slip in.

**Rejected: clamping stamps to the source duration.** It would hide the stretch rather than fix it —
the frames would still be labelled with times they did not come from, just smaller ones. Stamping
from the rate makes the numbers true by construction, so no clamp and no threshold are needed.

**Mutation audit 5/5:** the defect restored; the stale guard removed; the stale guard reverted to
its count-only form; stamps at the bucket start instead of its centre; and `max(1, len(paths))`,
which is the same stretch wearing a guard.

**A number I published yesterday was wrong, and this is the correction.** D-152, `BLOCKED.md` #20,
`README.md` and `evidence/the-live-check-spent-money-then-refused.md` all said the `0..13000` span
*"returns 20 frames stamped across the full 13 s"*. It returns **6**. The 20 came from my own probe
reusing one output directory for three spans — defect 2 above, contaminating the measurement of
defect 2. All four are corrected in place. The substance of #20 is unchanged and it stays live: the
built-in sample still spans 13,000 ms, the only Kurdish video here is still 4.162 s, and six frames
covering the first 3.6 s of a 13 s candidate is still not a live check. What changed is that those
six are now honestly labelled.

`evidence/frames-stamped-with-times-they-did-not-come-from.md`. Floor 1494 → 1499.

## D-154

**A shipped audit document asserted the opposite of the shipped behaviour, for two days.**
`AUDIT_REPORT.md`'s first Secondary-debt bullet read:

> Interrupted delivery can require a fresh work directory, by design, because artifact overwrite
> is refused rather than repaired in place.

D-146 (`9e8f128`, 2026-08-10 07:40) replaced exactly that: `_assert_no_existing_artifacts` refuses
only a set whose completion record exists **and** whose byte lengths match, so a leftover set with
no record is an abandoned attempt, overwritten, with the names returned in
`PipelineRun.resumed_over`. Measured on this tree rather than taken from D-146's record:

```
abandoned attempt (three artifacts, no record) -> ('m-s0-0.ass', 'm-s0-0.mp4', 'm-s0-0.json')
                                                  the guard accepts and the run proceeds
finished delivery (five artifacts + record)    -> FileExistsError: refusing to overwrite …
```

The bullet was written by me in the same session that falsified it, and I deferred fixing it for
four iterations while naming it each time. Naming a known falsehood is not the same as removing it.

**Decision: correct in place with the marker, and bind the claim to the guard.** The bullet is
struck through and replaced under `**Corrected 2026-08-10 (D-154):**`, the convention this file
already uses twice. More usefully,
`test_the_audit_describes_the_delivery_behaviour_this_tree_actually_has` *runs* the guard — plants
an abandoned attempt, plants a finished one — and then requires the audit's wording to describe
whichever behaviour it found. The two cannot drift apart again without a test going red.

**The remaining debt is stated as itself rather than deleted.** D-146 did not make delivery
collision-proof; it narrowed the refusal. Two *simultaneous* runs of the same media id and
selection into one work directory are no longer caught at the pre-write guard, and the corrected
bullet says so and points at D-146 for why that trade was taken. Replacing an overclaim with
silence would have been the other way of being wrong.

**And a second binding, for a class rather than a bullet.** Nothing checked that a `D-0NN` cited in
the documents exists. Measured: **182 citations** across README, AUDIT_REPORT, PROGRESS and
BLOCKED — 8, 8, 133 and 33 — every one of which resolved today.
`test_every_decision_the_docs_cite_exists` keeps it that way. It earned itself immediately: its
first run failed on `AUDIT_REPORT.md cites decisions that do not exist: ['D-154']`, because I had
written the marker before writing this entry.

**Rejected: deleting the bullet.** The Secondary-debt list is what the audit offers as its honest
account of what is still wrong; removing an item because it improved leaves the reader unable to
tell a fixed problem from one that was never noticed. Struck through and corrected keeps both.

**Rejected: a test that only greps the audit for the new wording.** It would pass with the guard
reverted — the prose would still say "repaired in place" while the code refused everything. The
test asserts the behaviour first and the wording second, in that order, so the doc is checked
against the tree rather than against itself.

**Mutation audit 6/6, and the first pass was 1/4 — of four mutations, three survived, two of them
because the work above was wrong.**

* **I fell into the prose-grep trap inside the test written to prevent it.** My first correction
  struck the false bullet through and put the truth *after* the `**Corrected**` marker. But
  `claims_only` keeps what **precedes** a marker — this file's convention is that the live claim
  comes first and the marker records what it used to say. So the "live" text my test read was the
  struck-through *false* claim, which happens to contain the words `repaired in place` inside
  `refused rather than repaired in place`. The assertion passed on the sentence it existed to
  forbid. The bullet is now written the way the convention requires, and the test additionally
  refuses the contradicting phrases as live text — because a phrase being present is not enough
  when its opposite can sit beside it. That is the fifth occurrence of this trap in the project
  (D-121, D-139, D-141, D-143) and the first inside a test.
* **The document list was hard-coded**, so a mutation dropping `AUDIT_REPORT.md` from the citation
  check left the suite green — D-149's `_SIDECAR_STATES` lesson, one iteration later. The list is
  derived from `ROOT.glob("*.md")` now, minus the register itself, so a new root document is
  covered the day it is added.

The load-bearing mutation is the third: revert the *guard* and leave the *prose*. A grep-only test
cannot see that direction, and it reddens.

`evidence/an-audit-that-described-the-opposite-of-the-code.md`. Floor 1499 → 1501.

**BLOCKED #3 re-measured this iteration and still live:** `hawedit-credentials --check` prints
`GEMINI_API_KEY: not set` and exits **1** (measured without a pipe — D-144's trap). Nothing here
simulated a key.

## D-155

**Adversarial pass #24 took M6.2 — the HARD/SOFT rule itself, DONE and never audited. 7 of 10, and
the three survivors were all the same shape: an invariant cannot see a choice.**

M6.2's evidence is a sweep — *"invariant #2 swept over 78,125 combinations covering every sign of
all seven optional `BoundaryInputs` fields"*. That proves
`final_in <= anchor_in <= anchor_out <= final_out` for every combination of signs. §3 Stage 5's
SOFT rule is more than a bound, though: it is a set of candidates and a *selection* over them —

```
final_in  = earliest of { anchor_in, vad_onset − 120 ms, preceding shot_cut within 400 ms, … }
final_out = latest   of { anchor_out + 200 ms tail, natural silence, following shot_cut … }
```

— and every wrong selection here still satisfies the invariant, because it still only moves
outward. The sweep cannot fail on any of them.

```
CAUGHT    §3's 400 ms shot-cut window becomes 4000
CAUGHT    §3's 120 ms VAD lead-in becomes 1200
CAUGHT    §3's 200 ms tail becomes 2000
CAUGHT    the tail is dropped, so anchor_out alone competes for the out point
CAUGHT    speaker_turn_start stops being an in-point candidate
CAUGHT    natural_silence stops being an out-point candidate
SURVIVED  a cut exactly at anchor_in stops counting as preceding
SURVIVED  the nearest preceding cut wins instead of the earliest
SURVIVED  the nearest following cut wins instead of the latest
CAUGHT    the clamp at 0 is removed, so a clip may start before the media

7/10
```

**Why the two selection survivors matter.** Every existing shot-cut test supplies **exactly one
cut** — the one input where `min` and `max` agree. Measured with three cuts inside the window:

```
preceding (ANCHOR_IN − 350, −200, −50)   earliest 9650   nearest 9950   → 300 ms lost off the front
following (ANCHOR_OUT + 50, +200, +350)  latest  14350   nearest 14200  → 150 ms lost off the tail
```

§3 says *earliest* and *latest* in the frozen blueprint, so this is not taste: taking the nearest
cut hands a client a clip that starts mid-shot and ends before the shot changes, with Kurdish
invariant #2 intact throughout and 1,501 tests green. Both are now pinned, each with a control that
discriminates — the single-cut case must still give the single cut, and a following cut closer than
the 200 ms tail must lose *to* the tail.

**The third survivor is a bad mutation of mine, and I am recording it as one rather than pinning
it.** `cut <= anchor_in` → `cut <` changes nothing observable: `min(in_candidates, …)` returns the
first minimum and `(anchor_in, None)` is appended first, so a cut landing exactly on the anchor
loses the tie to the anchor either way. Measured — `fuse_boundary` with a cut at `anchor_in` gives
`final_in=10000, in_extended_by=None`, and at `anchor_out` gives `out_extended_by='tail'`. Writing a
test for it would pin a tie-break §3 does not specify and that no input can observe. Sixth bad
mutation of mine this session (D-137, D-141, D-144, D-147, D-149).

**Rejected: extending the sweep to cover selection.** 78,125 combinations of *signs* is already the
wrong axis — adding a second cut to every one of them multiplies the run time to prove two facts
that two explicit tests state in eight lines. A sweep is for invariants; a choice wants a case.

**What survived the pass.** Every numeric constant §3 names — 120 ms, 200 ms, 400 ms — reddens when
changed, as do dropping the tail, dropping either optional candidate, and removing the clamp at 0.
The row's own claim about the invariant sweep is true; what it never claimed, and what nothing
checked, was the selection.

No production code changed. **9/9 after.**

`evidence/adversarial-pass-24-2026-08-10.md`. Floor 1501 → 1503.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`, exit **1**.

## D-156

**The gate's own refusals, swept — 7 of 9, and the one real gap was the guard that only matters
when the floor cannot help.** M0.1 is the largest DONE row never attacked as a whole (12,279
characters), and it is the row everything else rests on: if the gate can be fooled, every other
claim in this project is a claim about nothing. Each of its nine refusals disabled in turn against
a baseline verified green first, whole suite each time.

```
CAUGHT    a missing report is accepted
CAUGHT    a stale report from an earlier run is accepted
CAUGHT    a report collecting 0 tests is accepted
CAUGHT    failures are only refused when there are errors too
SURVIVED  a suite that skipped every test is accepted
CAUGHT    a count below the committed floor is accepted
CAUGHT    the floor stops ratcheting, so growth is never recorded
CAUGHT    a tool from outside this interpreter's environment is accepted
SURVIVED  a report with no testsuite element is accepted as evidence

7/9
```

**The real gap.** `if evidence.passed == 0` exists because a report of *700 collected, 700
skipped* once cleared every other check and `verify.sh` printed VERIFY OK with no test bodies
executed — the comment above it says so, and credits the independent review. Replacing it with
`passed < 0` left the entire suite green, because **every existing test supplies a non-zero
floor**, and at a non-zero floor the *floor* check refuses first. The one state where this guard
is the only refusal left is a floor of **0**, which `read_floor` returns for a missing or empty
file. Nothing paired the two. Measured, with the guard neutered:

```
floor missing (0)    ACCEPTED — collected 700, skipped 700, passed 0
floor = 1503         refused by the floor
```

So the guard that exists precisely for "the suite skipped itself" was held by the floor everywhere
the tests looked, and by nothing where it counts. Three states now pin it — floor file missing,
empty, and whitespace-only, all of which `read_floor` reads as 0 — with an assertion that the
premise holds (`read_floor(floor) == 0`) so the test cannot pass because the floor quietly refused
instead.

**The control is the half that keeps it honest.** A gate that refused every zero-floor run, or
every report containing any skip, would pass all three cases above. So a healthy report — 700
collected with **one** legitimate skip — must be accepted at a zero floor *and* ratchet the floor
to **699**, the number that actually ran. That also re-pins D-095's collected-versus-passed
distinction from the other direction.

**The second survivor is a bad mutation of mine, and it is recorded rather than pinned.** Removing
the `if not suites:` refusal does not accept anything: `total()` then sums an empty list, `collected`
is 0, and the very next guard refuses. Measured — the gate still raises, with
*"check testpaths, a stray `-k` filter, or a collection error"* instead of the testsuite message.
Only the wording changes, and pinning a message would fail on an intentional rewording while
catching nothing. Seventh bad mutation of mine this session (D-137, D-141, D-144, D-147, D-149,
D-155).

**Rejected: making `read_floor` refuse a missing or empty file.** It is the tempting fix — a floor
that reads as 0 protects nothing — and it is wrong here for two reasons. A genuinely new checkout
has no floor until the first green run writes one, so refusing would make the gate unable to
bootstrap; and the floor is not the mechanism that should catch a self-skipping suite, which is
what the `passed == 0` guard is *for*. Two guards, two jobs, and the failure was that only one of
them was ever exercised. If the floor's own absence should be an error, that is a separate decision
with its own bootstrap answer, not a side effect of this one.

**Rejected: asserting the exact refusal messages.** D-072's rule — a test that pins wording fails on
a rewrite and catches nothing. Each new case matches on the phrase that identifies *which* guard
fired (`nothing actually ran`), which is the minimum needed to tell the guards apart.

No production code changed — `gate.py` is byte-identical. **8/9 after**, the ninth being the bad
mutation above.

`evidence/the-gate-guard-that-only-matters-when-the-floor-is-zero.md`. Floor 1503 → 1507.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`, exit **1**.

## D-157

**Two ledger rows had an unescaped `|` in a table cell, so every column after it shifted — and it
made a measurement of mine wrong before I noticed the cause.** Looking for DONE rows never touched
by an adversarial pass, my scan reported **M0.1** as unaudited. Its own cell says
`**Audited 2026-08-10 (D-156)**`. The scan read the evidence column as `cells[3]` after splitting
on `|`, and M0.1's evidence contains one:

```
M0.1   …`--check`'s exit through `| tail` reported…
M2.7   …`discovery` and `editorial` are typed `StageSkipped | None` and success…
```

A `|` inside a table cell splits it in GFM **even inside backticks** — there is no code-span
exemption — so both rows render with a fifth column and read as five cells to any parser. Measured:
2 of 50 milestone rows. Mine, both: the `| tail` quote is from D-144 and the `StageSkipped | None`
from D-111, each quoting something that genuinely contains a pipe.

**Decision: escape for the renderer, and make the parser respect the escape.** These are two
different fixes and only doing one leaves the other broken:

* `\|` fixes the rendering. It does **not** fix `split("|")`, which splits on the backslash's
  pipe just the same — measured, still 2 of 50 shifted after escaping.
* `row_cells()` splits on `(?<!\\)\|`, so the parser agrees with Markdown. After both, 0 of 50.

`test_every_blocked_row_points_at_a_live_blocked_entry` and `_status()` both index by column, and
both now go through it. Neither was *broken* today — both escaped pipes happen to sit in the
evidence cell, which is last, so the status column was safe by luck rather than by rule.

**The latent hole this closes.** A BLOCKED row with a stray pipe ahead of its `BLOCKED.md #N`
would have its citation searched in the wrong half of its own cell — the guard would find no
citation, or find one and miss another, and D-144's *"a blocker could resolve invisibly"* returns
by a different door. The audit reaches that state directly: injecting a pipe into a BLOCKED row's
evidence reddens both that guard and the new column check.

**Rejected: forbidding pipes in cells altogether.** The evidence column is where this project
quotes shell pipelines and type signatures; a rule against the character would push writers to
paraphrase what they measured, and the whole point of the column is to hold the literal thing.
Escaping costs one backslash.

**Rejected: parsing the ledger with a Markdown library.** A dependency to read four columns, when
one lookbehind does it and matches the renderer's own rule.

**Mutation audit 6/6, and it took three passes to get an honest one.**

* **5/6 first.** The survivor was mine: I neutered the column guard *alone*, with the ledger
  intact — and a guard for malformed rows measures nothing when no row is malformed. Replaced by a
  stray pipe injected into a clean DONE row, which neither the escape-control nor the BLOCKED check
  names, so only the column guard can see it. Second time this session I mutated a test in isolation
  and learned only that it is redundant today; D-149 was the first.
* **Then the anchors went ambiguous.** Two mutations reported `ANCHOR?(2)` because *this very
  decision's note* quotes both escaped forms, so `` `\| tail` `` now appears twice in the ledger.
  The probe refused to mutate rather than pick one, which is the behaviour that stops a sweep
  reporting a result it did not measure. Re-anchored on the surrounding words.
* **5/6 again, and the survivor was the control.** With two copies of the quote in the file,
  `"`\| tail`" in PROGRESS` passes while the *original* is deleted. The control now matches the
  full phrase — `exit through `\| tail` reported` — which is unique to the row that needs it.

**And the guard caught its own record on the way in.** The first run of the gate after writing this
entry failed on `test_every_milestone_row_has_exactly_four_columns`: my note contained
``an unescaped `|` `` and ``` `split("|")` ``` — two more unescaped pipes, in the paragraph
explaining unescaped pipes. That is the third time this session a new check has failed on the text
announcing it (D-152's BLOCKED citation, D-154's `['D-154']`), and it is the cheapest possible
proof that the check runs.

**Repairing that damaged the row a second way, and the ledger's own tests caught that too.** My
first repair rebuilt the line and left `| M0.1  |` with two spaces; `_ledger_rows` matches
`^\| M\d+\.\d+ \|` with exactly one, so the row stopped matching and `gate.py` lost its only
recorded status — `test_the_ledger_accounts_for_every_module` went red naming it. Re-padded to the
canonical `| id | title | status | evidence |`, and only the two intended rows differ.

**A fourth parser turned up while fixing the third.** `_ledger_rows` and the PARTIAL-shortfall check
both split naively too. `_ledger_rows` survived an escaped pipe only by accident — it rejoins
`cells[4:]`, which happened to undo a split it did not know about. All four now go through
`row_cells`.

**The control is the half that keeps it honest.** A `PROGRESS.md` with no pipes left anywhere would
pass the column guard by having nothing to escape, so a second test requires both quoted forms —
`` `\| tail` `` and `` `StageSkipped \| None` `` — to still be there, escaped. Deleting the quote
rather than escaping it reddens.

`evidence/two-ledger-rows-had-five-columns.md`. Floor 1507 → 1509.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`, exit **1**.

## D-158

**M0.8's aggregation rule was stated in three places and measured in none.** Adversarial pass 25
took M0.8 — DONE since D-131, never audited — and disabled its six claims one at a time. Five held.
The survivor was the one the row argues hardest for: `ModelReport.alignment` weighting by
**matched words**. Replacing `sum(x * w) / sum(w)` with `sum(x) / len(x)` left the whole suite
green.

The claim is in the docstring ("a two-word item and a sixty-word one are not equal evidence about
timing"), in the M0.8 cell, and in D-131. Nothing tested it, and the reason is arithmetic:
`_TimedAdapter` shifts **every** item by the same `shift_ms`, and every item in `_timed_corpus()`
carries the same two reference words. Uniform weight and uniform error make a weighted mean and a
mean of per-item means the same number — measured, `30.0000` against `30.0000`. Every existing
alignment assertion passes under either implementation, which is this loop's own definition of a
test that measures nothing.

**The code was right; only the claim was untested.** On unequal items the emitted JSON tracks the
weighted formula exactly. This shipped no wrong output — but any refactor of that expression would
have put a §8.1 error figure 6.5x too large into a delivered report with a green gate, and §8.1's
last metric is precisely the number D-131 exists because nobody was checking.

**Decision: fix the fixture, not the formula.** The shortest diff that holds is one test whose
corpus can tell the formulas apart, driving the real `run_benchmark` path and asserting on
`to_dict()` — the emitted document, not the property.

**The first fixture excluded only one of the two wrong answers, and the audit caught that too.**
With a 2-word item 200 ms out and a fully-covered 20-word item 10 ms out, per-item averaging
reddens but **weighting by reference words** survived 5/6. Not a bad mutation: it changes the
number whenever coverage is below 1, and at coverage 1 `matched_words == reference_words`, so the
two weightings are the same arithmetic. The same blindness as the defect, one level down, inside
the fixture I had just written to expose it.

**Decision: the long item returns 10 of its 20 words**, so coverage is 12/22 and the three
candidate weightings give three different answers, all asserted or excluded:

| weighted by | onset error | within tolerance |
|---|---|---|
| matched words (asserted) | 41.6667 ms | 0.8333 |
| reference words (excluded) | 27.2727 ms | 0.9091 |
| nothing, a mean of means (excluded) | 105.0000 ms | 0.5000 |

Matched words is the correct weight because each item's figure is a mean *over matched words*.
Weighting by reference words would give a barely-transcribed item the full say its length suggests
— the failure `coverage` is reported beside the errors to expose, per `AlignmentAccuracy`.

**Rejected: asserting the weighted value alone.** It passes under reference-word weighting on any
fully-covered corpus, which is how this survived D-131's 5/5 in the first place. Both wrong
answers are now asserted *against* by name.

**Rejected: changing `_TimedAdapter` to vary its shift.** Five other tests depend on its uniform
30 ms — `matched 2/2, onset 30.0, offset 30.0, within 1.00` is quoted in the M0.8 cell as the
measurement that found D-131. A separate corpus costs 40 lines and leaves that record intact.

**Mutation audit 7/7**, after 5/6 and a 5/5 that refused a stale anchor. Three of the seven are
controls on the *fixture* — same-length items, equally-mistimed items, a fully-covered long item —
each collapsing the corpus back to a shape where two formulas agree, and each reddening.

**The baseline check earned its keep.** The 5/6 run's first attempt reported `baseline not green`,
naming `test_nested_full_gate_refuses_instead_of_recursing` and
`test_nested_fast_run_is_still_allowed`. Neither was a regression: both run the real gate as a
subprocess, and my new helper's docstring was 101 characters, so `ruff` failed *inside* them with
`E501`. Without the green-first rule, seven mutations would have reported CAUGHT against a suite
that was already red — the false result mutation auditing exists to prevent, arriving through the
same lint-contamination door as D-148 and D-150.

**And one mutation refused to run rather than report.** `ANCHOR?(0)`: a fixture control still
quoted `{"short": 200, "long": 10}` after the adapter had moved to `(shift_ms, words_returned)`
tuples. The probe skipped it and reported `5/5` over what it actually measured, rather than a
fabricated catch — the behaviour D-157's `ANCHOR?(2)` established. Re-run with the anchor
corrected: 7/7.

`evidence/the-alignment-aggregates-weighting-was-claimed-and-never-measured.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`, and
`~/.hawedit/credentials.json` does not exist — nothing has been entered in the credential panel,
so the ZAR38MinTest end-to-end run remains blocked on it.

## D-159

**The gate's dependency lock was checked for names and never for versions.** D-139 gave the gate a
hashed lock and three guards — every distribution pinned *and* hashed, CI installing it under
`--require-hashes`, and every `pyproject.toml` dependency present in the lock. The third compares
names. Nothing compared what version arrives.

That gap is wider here than in most repositories, because CI does not install `pyproject.toml` at
all:

```
pip install --require-hashes -r requirements/gate-linux-py311.txt
pip install -e . --no-deps
```

`--no-deps` means the runner never resolves the project's dependency table. Whatever the lock says
**is** the program the gate of record runs on, so a pin bumped in `pyproject.toml` and not
recompiled does not fail, conflict or warn — the two files simply disagree, and the one every
reader consults is the one that loses.

**Measured.** 11 exact pins declared for the gate's closure, all matching the lock today except
`torch`, which is not drift (below). The hole itself reproduces exactly: `ruff==0.9.6` bumped to
`0.12.0` in `pyproject.toml` with the lock untouched left **all 1510 tests green**, and CI would
have gone on linting with 0.9.6 — the gate's own linter, at a version nobody declared. Never
computed, rather than computed and discarded.

**Decision: compare versions, and accept exactly one difference.** `torch==2.13.0` is satisfied by
the lock's `2.13.0+cpu`. That is PEP 440 — an `==` specifier carrying no local segment ignores the
candidate's — and it is deliberate here: §6 puts Stage 0 on CPU, and `scripts/lock-gate-deps.sh`
resolves against `download.pytorch.org/whl/cpu` because the CUDA build is ~2 GB of runner disk for
kernels the gate never calls. `_lock_satisfies` implements that one rule and nothing looser:

| declared | lock | satisfied | why |
|---|---|---|---|
| `2.13.0` | `2.13.0+cpu` | yes | PEP 440 local segment, the CPU wheel |
| `2.13.0` | `2.9.0+cpu` | no | a real bump wearing a local tag |
| `2.13.0` | `2.13.1` | no | a different upstream version |
| `2.13.0` | `2.13.0.post1` | no | a post-release is not a local segment |
| `2.13.0` | absent | no | nothing to satisfy it |
| `2.13.0+cpu` | `2.13.0` | no | a declared local segment names a build, so it is exact |

**The control is that the rule stays connected to something real.** The last assertion requires the
lock to still carry `+cpu` at all. Without it the first row keeps passing while describing nothing
this repository does — a rule exercised only by its own unit test is a rule that can quietly stop
applying, which is the same shape as D-158's fixture that could not tell two formulas apart.

**Decision: gate dependencies stay exact pins.** A `>=` spec in `dev` or `media` would make the
version comparison skip that distribution *in silence* — the same failure one level up — so a
third test requires them all to remain exact, and a future range fails loudly and forces the
decision. **Rejected: comparing ranges properly.** That needs a PEP 440 version comparator, which
means either a new runtime dependency in a project that pins its supply chain deliberately, or a
hand-rolled parser whose own edge cases nothing here measures. Refusing the range is smaller and
cannot be subtly wrong.

**The `gpu`, `cloud` and `asr` extras keep their ranges** (`accelerate>=1.0`, `pillow>=10`,
`torchvision>=0.28`, `google-auth>=2.40,<3`). They are not what the gate installs, and pinning a
CUDA stack for Linux from this Windows host would be guessing versions I cannot resolve — the
never-guess rule applies to a wheel as much as to a threshold. Named here so the omission is a
decision rather than an oversight.

**Rejected: asserting the lock's own header command.** The generated header records the `uv pip
compile` line, and matching it would pin the *recipe* rather than the result — it stays correct
while the file beneath it goes stale, which is the failure this entry is about.

**Mutation audit 7/7**, every mutation lint-clean. Two are the drift itself from either side, one
is the range that would make the comparison skip, three attack the local-version rule, and the
last removes the only real thing that rule describes.

`evidence/the-lock-was-checked-for-names-and-never-for-versions.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-160

**M0.15's numbers were reproducible in principle and not on this machine.** The row is DONE on a
measurement — *24,894 real entries; 0.21% of distinct forms would have failed to match* — and its
evidence file names the command that produces it. `scripts/measure_collisions.py`'s own docstring
says the numbers *"are only worth having if they are reproducible"*. They were not: the script
failed twice here, for two unrelated reasons, and no test ran it.

**First, a venv layout instead of the installed package.** `KLPT_DIC` was built as
`ROOT / ".venv/lib/python3.11/site-packages/klpt/data/ckb-Arab.dic"`, which exists on POSIX.
Windows uses `.venv/Lib/site-packages/…` — capital `L`, no version segment — so the script died
with `FileNotFoundError` before measuring anything, **exit 1**. Nothing was missing: the file is
at `.venv/Lib/site-packages/klpt/data/ckb-Arab.dic`, 946,155 bytes. The path was *assembled*
rather than asked for, and `tests/test_waw.py:45` already did it correctly with
`Path(klpt.__file__).parent / "data" / "ckb-Arab.dic"` — the right idiom was in the repository the
whole time and this one script guessed.

**Second, the finding did not survive stdout.** With the path fixed it still exited 1, on
`UnicodeEncodeError`: a script gets cp1252 stdout on Windows, so the summary line went out and the
Kurdish word pairs — *the finding itself* — died. That is the worse failure of the two, because it
is **exit 1 with the headline already printed**, which reads as success to anything checking only
the first line. `cli.use_utf8_streams` exists for this and calls itself *"the first statement of
every `main()`"*; all six argument parsers call it and this script never did.

**The claim was true.** With both fixed, `exit=0`, and every figure reproduces four days on:
24894 items, 0.84% altered, 24051 distinct raw forms → 24000 normalized, 0.21% would have failed
to match, `heh_doachashmee=204`, `arabic_kaf=1` — and all six word pairs the evidence file quotes
come back unchanged. So the fix is to the reproduce path, not to the number. Recorded because
"never mark DONE by judgment" cuts both ways: a row resting on a measurement nobody can re-run is
resting on judgment, whatever the number turns out to be.

**Decision: bind the document to the run, not to a literal.** Three tests execute the script as a
**subprocess** — an import would reach neither the module-level path resolution nor stdout's
encoding — require exit 0, and compare `evidence/collision-incidence.md` against what came out.
The figures are **parsed from the evidence file**, so a KLPT update or a `normalize_sorani` change
fails naming both numbers instead of leaving the document describing a run nobody can repeat.

**The control is that `0.21%` and `0.84%` both appear in that file.** A check asking only *"is
this percentage mentioned"* passes with the two swapped, so the collision rate is asserted **in
its own table row** and the altered-items rate asserted absent from it. A second control requires
the quoted merges themselves, because the percentages could match while the merges changed
entirely.

**Rejected: hardcoding 24,894 in the test.** That is the stale number one layer down — it would
pass while the evidence file said something else, which is the failure being fixed. **Rejected:
skipping the test when KLPT is absent.** `klpt==0.1.7` is a core dependency in the hashed lock,
not an extra; a skip here would retire the guard on exactly the platform where it fired.
**Rejected: `importlib.resources`.** `klpt.__file__` is what the neighbouring test already uses,
and matching it costs nothing.

**Mutation audit 7/7**, after a 7/7 that was not trustworthy. The first sweep flagged both
restored defects `[lint dirty]` — removing each line orphaned its import (F401), the contamination
of D-148 and D-150. Redone removing import alongside use: still caught, red lists unchanged, but
not *measured* to hold until the mutations were clean. **And the lint check itself was
over-broad**, running `ruff` over `scripts/measure_collisions.py`. `verify.sh` lints
`ruff check src tests` and mypy declares `files = ["src", "tests"]`: **`scripts/` is outside the
gate's lint and typecheck entirely**, so an error there cannot redden anything and flagging it
marks honest catches as contaminated.

**That scope gap is named, not fixed here.** The change in this commit lives in a file the gate
neither lints nor typechecks, and the only thing behind it is the subprocess test added beside it.
Widening `LINT_CMD` to `scripts` would have to survive every other script in that directory first,
which is its own increment.

**A third pass, because mutation 1 was not restoring the defect it named.** `ROOT` went away with
the fix — nothing else in the script used it — so replacing only the path line left `ROOT`
undefined, and the script died on `NameError` at import instead of `FileNotFoundError` at the read.
The test caught it either way, since it requires exit 0; but the label claimed one failure and the
run produced another, which is the same fault as a number without its provenance. Reinstating the
`ROOT` assignment alongside the old path makes it the original defect and nothing else: still 7/7,
same red lists. **Eighth bad mutation of mine** after D-137, D-141, D-144, D-147, D-149, D-155 and
D-156, and the second found by reading the committed diff rather than the sweep's own output.

**Both restored defects are platform-specific**, so this 7/7 is measured on hawapc01 (Windows).
The fix is not: asking the installed package and pinning UTF-8 are right on both platforms and CI
runs the same three tests. What a Linux runner cannot reproduce is the *failure* — which is
exactly why it survived four days. Third platform-bound finding after D-137's skip and D-142's
Windows-only fixture, and the first where the platform hid a defect rather than a test.

**And the decision log's own guard caught this entry on the way in.** The first gate after writing
it went red on `test_every_value_the_decision_log_states_is_the_value_the_code_holds`: D-098's
convention is that a `` `<NAME> = <value>` `` span in a decision is a **live claim** about a module
constant, and this entry quoted the *removed* line in exactly that form — so the guard reported
that "D-160 states `KLPT_DIC` … and no module defines KLPT_DIC", which is true twice over, since
the value is historical *and* `scripts/` is not a module. Split into two spans: the name, then the
expression it used to hold. Fifth time this session a new record has failed on the text announcing
it (D-152, D-154, D-157, D-159's neighbours), and the cheapest possible proof the check runs.
**Then it caught the sentence you are reading**, because that sentence quoted the pattern itself
as a literal example; written with angle-bracket placeholders now, which the pattern cannot match.
A guard that fires twice on one paragraph is not noise — a decision log is code to these tests.

`evidence/m0-15s-reproduce-command-could-not-run.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-161

**The gate ran the right programs over only part of the repository.** `tests/test_gate.py` already
asked *which programs* the gate runs, and refuses one whose provenance is unchecked (D-093).
Nothing asked **what they read**. Measured: the lint and format steps passed `src tests`, mypy
declared two directories, and `scripts/` therefore appeared in none of them — linted by nothing,
typechecked by nothing, while `README.md` calls the step *"lint + typecheck + format + tests —
this decides DONE"* without qualification. D-160's defect lived there for four days.

**Decision: widen to `src tests scripts`, in all three places.** It costs nothing — both tools
already pass on the wider scope, and mypy's file count goes 98 → 99. There is exactly one Python
file under `scripts/`; the other seven entries are shell and PowerShell.

**What it does not buy, measured rather than assumed.** The tempting claim is that this would have
caught D-160. It would not. Both of that iteration's defects, written the way an author who meant
them would leave the file, pass `ruff` and `mypy` at `rc=0`: a wrong path string is neither a lint
error nor a type error. A first pass appeared to catch both, but each of those edits had left an
orphaned import behind and `F401` fired on the *edit shape*. What protects that class is D-160's
subprocess test. What the widening does reach, on the same file: an undefined name (`F821` and
mypy — the shape of my own bad mutation last iteration), a wrong return annotation (mypy), an
unused import (`F401`). Worth having, and worth stating precisely rather than overclaiming.

**`models/` is not repository content, and git is the authority on that.** The new scope test
failed first on eleven files — `modeling_videochat3.py`, `qwen3_vl_reranker.py` and siblings —
which are downloaded checkpoint code. `.gitignore:27` matches `models/*`, and the only tracked
files under it are `revisions.json` and `sources.json`; tracked `.py` there: **0**. So the
enumeration asks `git ls-files`, not the filesystem. **Rejected: excluding `models/` by name.**
A blocklist goes stale the next time a checkpoint lands, and it would answer a different question
than the one that matters — what the repository *contains*. The 99 tracked Python files are
exactly the 99 mypy now reports, which is the check on the check.

**Two guards, because scope has two failure modes.**
`test_the_gates_three_python_steps_read_the_same_paths` requires lint, format and typecheck to name
the same roots: mypy's list lives in `pyproject.toml` and the other two in `verify.sh`, so nothing
else keeps them equal, and a file linted but not typechecked is checked less than it looks.
`test_the_gate_reads_every_python_file_in_the_repository` derives the requirement from the
repository rather than from a list, so the next top-level package fails until both files name it —
membership against a hard-coded list is precisely the state `scripts/` was already in.

**Rejected: adding `shellcheck`.** Six shell scripts here are unlinted, including `verify.sh`
itself and the checksummed fetchers — a larger surface than the one Python file. It needs a tool
neither the lock nor the venv carries, and pinning one into the gate of record is its own
increment with its own supply-chain question. Named as remaining debt rather than half-done.

**Mutation audit 7/7, after 6/7.** Mutation 4 is the one worth naming: it writes
`tools_for_this_audit/helper.py` and `git add -N`s it, so the repository genuinely contains a
tracked Python file outside every root — the state reached, not simulated. **The survivor was
mine, of the kind I keep repeating** (D-149, D-155, D-156, D-157): neutering the empty-scope
control while no scope is empty measures nothing. Paired with the state it describes — all three
steps naming whitespace, where set equality is satisfied by three empty sets — the same-paths test
goes **green without the control** and red with it. Its sibling still reddens, since 99 tracked
files fall outside an empty root list; that is defence in depth, not a reason to drop the control.

**And one detail cost a run:** whitespace, not emptiness, is the shape that reaches that control.
With a single space the pattern's own trailing space consumes it, `([^}]+)` matches nothing, and
`_gate_scope` fails earlier with a different message. A control can be unreachable by the shape
you happen to try and load-bearing for the one you did not.

`evidence/the-gate-checked-none-of-the-scripts-directory.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-162

**Seven shell scripts, including the gate's own, were read by no linter.** D-161 widened
`verify.sh` to `ruff check src tests scripts`; ruff reads Python. The shell beside it — this
gate's script, and the fetchers that download, checksum, unzip, `chmod +x` and execute a 140 MB
binary — was checked by nothing, and D-161 named that as remaining debt.

**Measured: shellcheck finds nothing.** 0 findings across all seven at default severity. Recorded
**with a control**, because a clean result and a result that read no files are the same output: a
deliberately bad script (`ls $file`, `cat foo | grep bar`, `[ $x == 1 ]`) draws SC2148, SC2154 and
SC2086, so the tool works and the scripts are clean. **This is a ratchet, not a repair**, and
saying otherwise would be the overclaim D-161 was careful to avoid.

**The optional checks were read, not waved through.** `--enable=all` reports 131: **122 SC2250**
(prefer `${var}` over `$var` — pure style), **6 SC2310** (a function invoked in a condition, so
`set -e` is disabled inside it), **3 SC2312** (a substitution whose return value is masked).
SC2312 is the shape of D-144's real defect — `\| tail` reported `tail`'s status — so all three
were opened: each is `$(...)` inside a `[[ ]]` test that already handles failure, e.g.
`[[ "$(uname -s)" != Linux* ]]`, which refuses when `uname` fails. The six SC2310 are `verify_rtl`
called as `if verify_rtl …`, and that function decides whether an ffmpeg can shape Arabic script —
§4.3's failure is *"invisible until a client sees the burned-in captions"* — so it was read line by
line. Every failure path is explicit (`|| return 1`, `|| missing+=(…)`), so it never relied on
`set -e` and disabling it changes nothing.

**Decision: default severity, not `--enable=all`.** Turning on 122 brace-style notes to reach
three benign ones makes the step noise, and a noisy check is one people learn to ignore.

**Decision: CI, not `verify.sh` — and this is the interesting part.** `shellcheck-py` on PyPI
ships **a binary and no importable module**. `verify.sh` runs its steps as `$PY -m <tool>` and
`assert_tools_are_from_this_environment` vouches for each by importing it
(`GATE_TOOLS = ("pytest", "ruff", "mypy")`, D-093). A binary cannot be checked that way, so adding
it as a gate step would put a program into the gate that the gate's own provenance rule cannot
see — and `tests/test_gate.py` already states the objection: *"a tool the gate runs but does not
check is a hole the shape of the one just closed."* ubuntu-latest carries shellcheck and CI **is**
the gate of record, so the step lives there. **The honest limitation:** `bash scripts/verify.sh` on
a developer machine does not run it. Recorded rather than papered over.

**Rejected: adding `shellcheck-py` to the lock anyway** and running the binary from
`.venv/Scripts/`. It would put an unvouched-for program in the gate to save a round trip, trading
a D-093 guarantee for convenience. **Rejected: extending `GATE_TOOLS` to vouch for binaries.** A
real option, and a larger one — provenance for a binary means hashing it or trusting its path, and
that is its own decision with its own supply-chain question, not a side effect of adding a linter.

**The control is that the step proves its tool ran.** `shellcheck --version` runs first, so an
absent shellcheck fails the step instead of matching no files and exiting 0.

**Mutation audit 6/6, after 5/6 — and both bad results were mine.** One mutation writes
`tools_for_this_audit/helper.sh` and `git add -N`s it, so the repository genuinely holds a tracked
script the glob cannot reach. Of the two faults: one mutation was **lint-dirty** (replacing the
`git ls-files` argv orphaned the helper's `pattern`, so ruff reddened the gate-as-subprocess tests
and the catch partly measured ruff — redone at the call site); and the survivor was the
**isolated-mutation trap again** — neutering the empty-listing control while the listing is full is
a guard with nothing to see. Paired with an empty listing, the test goes **green** without the
control and red with it: no tracked scripts means none outside the glob, so the real assertion
passes vacuously. Sixth time after D-149, D-155, D-156, D-157 and D-161; the lesson is not
learning, so it is written here as a rule — **a control must be mutated together with the state it
describes, never alone.**

`evidence/the-shell-half-of-the-repository-was-read-by-no-linter.md`.

**Also measured this iteration, and not a defect:** CI's wall clock went 2m33s to 9m23s across the
previous commit, which looked like a regression I had caused by widening mypy. The step timings
say otherwise — **install** went 43s to **7m09s** (a 140 MB download on a shared runner) while the
**gate** step went 1m28s to **1m50s**. D-161 cost ~22 seconds, not six minutes. Recorded because a
number read off a summary line is not a measurement.

**And a scan that found nothing:** 1,422 test functions, **6** with no `assert` and no
`pytest.raises`. All six are the must-not-raise half of a raise/no-raise pair — an identical
golden render that must compare clean, a wordless transcript that must construct, a substituted
stream `use_utf8_streams` must leave alone. The absence of an exception is the assertion.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-163

**Adversarial pass 26 attacked M3.2 — §4.3.6's golden-file render — and failed, 6/6.** This is the
row §0 calls failure mode #3: *"you will catch it when a client sees the burned-in captions."*
Every claim in it held: production dropping `shaping=complex` or the font directory reddens, the
golden render rendering the wrong way reddens, a comparison that accepts anything reddens, and —
the property no audit had tested — **a reference regenerated from a broken build is refused**.
`compare_golden_render` warns that "a reference produced by a broken build enshrines the bug it is
meant to catch"; rebuilding `tests/golden/kurdish-caption.png` from a `shaping=simple` render
reddens two tests, because the negative control then finds the broken render *matching* the
reference and its `pytest.raises` stops raising. The reference is checked, not trusted.

**The filter string is duplicated and that is not a hole.** `subtitle_filter` (production) and
`render_caption_png` (the golden render) build `ass=…:shaping=…:fontsdir=…` independently, so the
pixel safeguard never renders production's own string. Mutating production's copy in either
meaningful way reddens immediately, so today's elements are covered by the string tests.
Recorded rather than fixed: what is *not* covered is a future element added to one and not the
other, and unifying them is a change to the shipped render path, which this pass is not the place
for.

**One recorded measurement went stale.** D-061 recorded "the reference re-renders byte-identical
here". Re-measured on `ffmpeg 8.1.1-full_build-www.gyan.dev`: the render is **pixel**-identical
(6,220,800 bytes both) and the **file is 1,017 bytes larger** — 20,830 against 21,847. Not a
defect: `decode_to_rgb` exists because "PNG encoders differ between ffmpeg and zlib versions". The
other number holds exactly — `shaping=simple` differs on **0.2316%** of pixels (4,803 of
2,073,600) against D-061's recorded 0.232%.

**The finding, and the only change this pass makes: the decoded-pixel design was covered by
luck.** Forcing the comparison onto file bytes *is* caught here — but only because this machine's
encoder disagrees with the one the reference was made on. Where an encoder agreed, that regression
would pass unnoticed, and the golden test would be one ffmpeg upgrade away from failing on a
change no viewer can see: the "cries wolf and gets disabled" outcome `decode_to_rgb`'s own
docstring is written against.

**Decision: pin it by construction, not by the installed encoder.**
`test_the_comparison_runs_on_pixels_and_not_on_the_encoded_file` repacks the reference at
compression level **9** and level **1** — the same picture in different bytes on any ffmpeg — and
requires the decoded comparison to accept them and the byte comparison to refuse them. Measured
here: level 1 → 73,632 bytes, level 9 → 17,464, committed → 20,830, all decoding to identical
pixels.

**Rejected: comparing a repack against the committed reference.** That reintroduces the same luck.
Measured: even a *default* re-encode already differs from the committed bytes on this machine, so
the bytes-differ control would never fire here and the test would be trusting the encoder again.
**Rejected: regenerating the golden reference** so the bytes match this ffmpeg. The reference is
the artifact of a verified libass build; replacing it to make a comparison tidier is how a broken
reference gets enshrined, and the pass above exists to prevent exactly that.

**Mutation audit 4/4**, with the control mutated *together with the state it describes* — D-162's
rule, applied deliberately this time. Collapsing the two compression levels is caught twice: by
the bytes-differ control, and, if that is deleted too, by the closing `pytest.raises`, which stops
raising once the two files are identical.

**And the first version of this guard was rebuilt after its own audit.** It compared a repack
against `GOLDEN`, and both "remove the compression level" mutations **SURVIVED** — on this machine
the bytes differ regardless, so the flag changed nothing and the control could not fire. That is
the same machine-luck the test exists to remove, one level down. Reconstructed to compare two
repacks against each other, the control became demonstrable and the audit went 4/4.

`evidence/adversarial-pass-26-m3-2-golden-render.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-164

**§4.3.6's pixel safeguard rendered a filter string production does not use.** D-163 recorded this
as remaining debt: `subtitle_filter` (production) and `render_caption_png` (the golden render) each
built `ass=…:shaping=…:fontsdir=…` independently — identical character for character, and nothing
required them to stay so. The one test that looks at pixels was therefore comparing renders of a
copy.

**Decision: derive, do not duplicate.** `render_caption_png` now calls `subtitle_filter` and, for
the negative control only, replaces `shaping=complex` with the wrong value — **refusing** if that
substring is absent, because a silent no-op would make
`test_simple_shaping_fails_the_golden_test` render the *right* way, find it equal to the reference,
and fail in a way that reads as a shaping regression rather than a broken test.

**Measured, both ways.** The same production regression — `fontsdir` pointed at the wrong
directory, which is §4.3.4's whole subject — against the pixel tests alone: **coupled it is
caught** (`test_the_render_matches_the_golden_reference` red); **with the independent copy it is
missed**, pixel tests green.

**And measured honestly: this was never an uncovered hole.** With D-164's own two tests removed and
the coupling reverted, the whole suite still reddens — on **exactly one** pre-existing test,
`test_a_windows_path_is_escaped_for_both_unescaping_passes`, a string test that happens to assert
the escaped `fontsdir` path. So this is **defence in depth, not a closed gap**, and claiming
otherwise would be the overclaim D-163 was careful to avoid. What it adds is that the pixel
safeguard now sees production's string at all, so an element the string tests do not happen to
assert is rendered and compared — the case a fixed list of string assertions cannot be enumerated
against in advance.

**Rejected: giving `subtitle_filter` a `shaping` parameter.** One shared builder would be tidier,
and it would put a knob on production whose only purpose is letting a test ask for the wrong
answer. §4.3.1's requirement is that production *never* relies on anything but `complex`; a
parameter invites exactly the call the requirement forbids. The replacement lives in the
test-facing helper, where it belongs, and refuses rather than degrading.

**Rejected: asserting the two strings equal in a test instead of unifying them.** That pins today's
agreement without making the pixels come from production's string, which is the property §4.3.6
needs — the render is the evidence, not the comparison of two literals.

**Mutation audit 5/5**, including the wiring test's plausible dodge (call `subtitle_filter` and
throw the result away — caught by the `f"ass=` control beside the call, not by the call assertion)
and the new refusal, reached through a monkeypatched `subtitle_filter` so it is exercised rather
than merely present. **One correction to the sweep:** mutation 1's self-check asserted
`"subtitle_filter(ass_path" not in out`, which is also that function's own `def` line, so it fired
on the definition and reported a mutation that had applied. Narrowed to
`"filter_string = subtitle_filter("`.

`evidence/the-golden-render-burned-a-filter-production-does-not-use.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-165

**The SRT sidecar shipped cues no player can read in order.** `build_srt` refused an incomplete
sentence (invariant #2), one starting before the clip, and one ending after it — every check about
a sentence *on its own*. Nothing checked the sequence, and SRT is read sequentially.

**Measured**, driving the real writer and reading the file back with `parse_srt_times`: cues out of
order shipped (`(1000, 1400)` then `(0, 400)`), overlapping cues shipped (`(0, 1200)` beside
`(800, 1400)`), and — the sharpest — **`00:00:00,900 --> 00:00:00,400`**, a cue whose end precedes
its start, assembled entirely from words that are individually valid. `ms_to_srt_time`'s docstring
already warns about a "plausible-looking timestamp" for negative input (D-138); this one needs no
negative number.

**Why `Word` does not cover it.** `Word.__post_init__` refuses `end_ms <= start_ms`, so no single
word runs backwards and a zero-length cue is unreachable. But `Sentence.start_ms` is
`words[0].start_ms` and `end_ms` is `words[-1].end_ms`, with nothing requiring the tuple sorted —
and nothing at all constrains two sentences relative to each other. Never computed, not computed
and discarded.

**Reachability, stated rather than implied.** `segment_sentences` emits ordered sentences from
ordered words, so the pipeline does not produce these today. Both `build_srt` and `build_ass` are
exported and take any `Sequence[Sentence]`, and `pipeline.py` hands **the same sequence** to both —
so a guard on one only would burn an overlap into the video while the sidecar refused it.
`assert_deliverable_order` lives in `sentences.py` and both writers call it: one implementation,
two call sites, which is the rule's meaning rather than a check per writer.

**Decision: touching exactly is allowed.** `later.start_ms == earlier.end_ms` is ordinary
consecutive speech; refusing it would reject honest output, and that boundary is what two of the
new tests control for. The comparison is `<`, deliberately.

**Rejected: sorting the sentences instead of refusing them.** A writer that quietly reorders its
input converts a producer bug into a silent correction, and the next reader cannot tell it was
handed something wrong. §4.3's warning is about failures that "do not appear and nothing says so" —
sorting is one of them. **Rejected: putting the check in `Sentence.__post_init__`.** A sentence
with unsorted words is a legitimate intermediate for code that has not sorted yet; the property
that matters is at the point of delivery, which is where the guard is.

**Mutation audit 6/6.** Each half of the check and each call site mutated separately, so none is
carried by another. **Two catches were re-run because the first pass was contaminated:** removing
the call orphans its import, so ruff reddened the gate-as-subprocess tests and the result partly
measured ruff (D-148, D-150). Redone with the import removed alongside the call, both are caught
lint-clean by exactly the tests written for them. The over-strictness pair follows D-162's rule —
control mutated together with the state it describes.

`evidence/the-sidecar-shipped-cues-a-player-reads-in-order.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-166

**The delivery block could not catch the exception D-165 introduced one commit earlier.**
`build_srt` was given `UndeliverableOrder`; the block that calls it catches
`(DeliveryError, RenderError, OSError)`. Both are `ValueError` subclasses — **siblings**, not
parent and child — so the new type was not in the tuple.

**Demonstrated against the real tuple, not inferred from names:** raising it at the handler copied
verbatim from `pipeline.py` gives `ESCAPES -> no cleanup, no named gap`. What escaping costs is
written in the block's own comments: the `unlink(missing_ok=True)` sweep that keeps the delivery
set **all-or-none** (D-072's subject — "four fifths of a delivery set that looked whole"), the
`StageSkipped` that names the blocker, and gracefulness itself.

**Latent, not live, and recorded that way.** `build_ass` runs first on the *same* `selected`
sentences and its handler catches `ValueError`, so an undeliverable sequence is refused there and
the delivery block never sees one. No wrong output shipped. But that is an **ordering guarantee,
not an exception contract** — it holds only while `build_ass` precedes `build_srt` and keeps a
broad `except ValueError`, and the delivery block's own comment records that these statements were
reordered once already, for an unrelated reason.

**Decision: name the type, and derive the requirement from the handler itself.**
`test_the_delivery_handler_catches_everything_its_builders_refuse_with` reads the `except` clause
out of `pipeline.py` **by AST** — the tuple actually protecting the five writes, not a copy — and
requires every type the three builders raise for bad input to appear in it. A list written
elsewhere would be correct and guard nothing.

**Rejected: making `UndeliverableOrder` subclass `DeliveryError`.** It is the tidier hierarchy and
it is not available: `sentences.py` would have to import from `delivery.py`, which imports
`sentences`. **Rejected: widening the handler to bare `Exception`.** It would catch this and
everything else, including bugs this stage should not be swallowing; the block refuses *named*
failures on purpose.

**Mutation audit — 1/1 on the defect, and two results not claimed.** Restoring the exact bug
(handler without the type, import removed so nothing lints dirty) reddens the new test and nothing
else. Two further mutations — dropping `DeliveryError`, widening to bare `Exception` — were
**lint-dirty**, so those catches partly measure ruff (D-148, D-150) and are recorded as
contaminated rather than counted. **And the survivor is honest:** the sibling assertion beside the
test is *documentation, not a control* — deleting it measures nothing, because the state it would
catch cannot be constructed for the circular-import reason above. Counting it would repeat the
isolated-mutation mistake this loop keeps finding; the comment now says what it is.

`evidence/an-exception-the-delivery-handler-could-not-catch.md`.

**Also probed this iteration and sound:** `build_edl`. Its guards refuse a negative in-point, a
zero-or-negative span, a sub-frame duration and a non-integer rate, and
`test_source_and_record_ranges_use_the_same_quantized_frame_duration` already pins the property an
EDL lives or dies by. Nothing to fix; the premise was checked and disproved rather than assumed.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set` and
`~/.hawedit/credentials.json` absent, so the ZAR38MinTest end-to-end run stays blocked on it.

## D-167

**A word was allowed to be more than one line, and the caption lost everything after the
break.** `Word.__post_init__` validated its surface form as *"a non-empty string"* and nothing
else. Both formats §2 delivers subtitles in are line-structured: an ASS `Dialogue:` event is one
line, an SRT cue block ends at a blank one. A break inside a surface form does not wrap the
caption — it ends it.

**Measured on the artifact, on real ffmpeg 8.1.1-full_build and real libass.** Three renders of
the same two-word sentence — with the break, truncated *at* the break, and intact:

    broken     sha256 b01fd8a7473cf066…
    truncated  sha256 b01fd8a7473cf066…     <- byte-identical
    intact     sha256 41770c2fe65c5681…     <- 8,277 pixel bytes different

The broken render equals the one with the tail **deleted**. The identity is the finding; the
intact comparison is what stops it being vacuous, since identity would also hold if this machine
drew nothing at all.

**Both readback checks agreed with the broken file.** The orphaned word sits in `[Events]` as a
line libass does not recognise, and `parse_dialogue_times` returns *exactly* the intact file's
times. On the SRT side the cue splits in two while `parse_srt_times` reports one cue — D-138 made
it refuse an unreadable *timing* line, and nothing looks at the text, so a cue count is not a
check that the text survived.

**Live, not latent, and not through the models.** `OmniAsrBackend._align` builds every surface
with `text.split()`, so canonical ASR cannot produce one. The door is `Word(**w)`: seven
construction sites, two reading JSON off disk, one of those behind the documented
`python -m hawedit.pipeline VIDEO.mp4 --transcript FILE`. Measured, `RawTranscript.from_json`
accepted it — invariant #5's aligner check passes on `ctc_viterbi`, and the
aligned-words-appear-in-`text_ckb` cross-check passes as soon as the file is internally
consistent, which a file written by a tool that wrapped its own output would be.

**Decision: one guard at the chokepoint, `if self.w.splitlines() != [self.w]`.** `Word` is what
every construction site routes through, including both JSON readbacks, so this is one guard
rather than one per writer. `splitlines()` because the definition of a line break is then the
standard library's rather than a character list I picked; slightly stricter than libass (it also
covers `\v`, `\f`, `\x1c`, `\x85`, U+2028, U+2029) in the direction of refusing rather than
shipping. `!= [self.w]` and **not** `len(...) == 1`, because the latter accepts a *trailing*
break — `"a\n".splitlines() == ["a"]` — which is just as fatal once `" ".join` puts the next word
after it.

**Rejected: escaping the break into an ASS `\N`.** It renders, and it invents a line break the
alignment never specified; §4.3.5 is explicit that breaks come from the word alignment. **Rejected:
refusing all whitespace.** It would also reject a space or a tab inside a surface form, which
lose no text — a different complaint (one `Word`, two spoken words, one timing) that no
measurement here demonstrates. **Rejected: checking in `build_ass`/`build_srt`.** Two guards for
one property, and neither would stop the bad word entering a stored transcript.

**Mutation audit — 3/3, lint-clean, whole suite per mutation, baseline verified green first.**
Restoring the defect reddens 13 (the 12 parametrised breaks plus the `--transcript` door) and
nothing else. The two threshold mutations discriminate exactly: `len(splitlines()) != 1` reddens
**only** the trailing-break case, and refusing all whitespace reddens **only** the four accepted
cases. The pixel and SRT tests redden under no mutation and are recorded as **premise tests, not
controls** — they pin what the guard rests on, and their cheapest fix is a re-measurement.

`evidence/a-word-that-was-not-one-line.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent, so the ZAR38MinTest
end-to-end run stays blocked on it. `HF_TOKEN` is likewise unset (#4).

## D-168

**§7 has a Licence column and nothing ever read it.** Adversarial pass 27 took M0.2 — *"§7 model
registry in code; model outside §7 rejected; NC licence hard-rejected"* — and went after the
datum the second half rests on. `tests/test_registry.py` parses §7 out of the frozen blueprint and
asserts exact set equality, which is real; it reads the **Model** column. `assert_commercially_usable`
"keys off the licence, not off those two names", so the licence is the input to the whole
NonCommercial policy, and it was accountable to nothing.

**Premise checked before it was fixed, and the data is right.** All 15 §7 rows against all 15 code
entries: the only two divergences are the ones the module docstring already accounts for —
PySceneDetect restating §7's "open" more precisely, and KLPT's D-002 narrowing read out of the
shipped wheel metadata. Nothing was wrong; it was simply unheld.

**Measured, 1/4.** Four licences changed one at a time, whole suite each, baseline green first:
`omniASR_CTC_3B_v2` Apache-2.0 → MIT **survived**; KLPT CC-BY-SA-4.0 → CC-BY-4.0, which deletes
share-alike from the shipped attribution notice, **survived**; Community-1 CC-BY-4.0 →
CC-BY-SA-4.0, which invents an obligation that licence does not impose, **survived**. Only
LGPL/GPL → Apache-2.0 was caught, and for an unrelated reason: Apache requires no attribution, so
the libass *subject* vanished and the README's both-directions bookkeeping missed a bullet. A
catch for the wrong reason reads as protection that is not there (D-082's own lesson).

**And the same hole from the other side.** The README's Attribution section is the mitigation
§10 names for this risk and says the test asserts it "in both directions" — it compares
**subjects**, the text before the em dash. Editing the bullet to *"KLPT — Sina Ahmadi, MIT, no
attribution required"* left 73 tests passing: shipped product documentation making a false
statement about a third party's licence. KLPT's share-alike clause is on the bullet's second
line, which a line-by-line read never looked at either.

**Decision: bind the licence in all three places it is stated.** §7's cell and the code state the
same licence at different widths in **both** directions — `CC-BY-4.0` vs `CC-BY-4.0 (attribution
required, gated repo)`, and `open` vs `open (§7, not independently verified)` — so the rule is
that one's words must be a **contiguous run** of the other's, after normalising `Apache 2.0` and
`Apache-2.0` to the same tokens. `CC-BY-SA-4.0` is not a run of `CC-BY-4.0 …`, which is what makes
the invented-obligation case fail. Recorded restatements live in `LICENCE_DIVERGENCES` **pinned
by value**, with a control requiring each to actually diverge and to cite a `D-0NN`; the README
side is bound by comparing the licence each notice states — and its share-alike claim — against
the whole bullet, continuation lines joined.

**Rejected: requiring §7's cell and the code to be equal.** It would reject PySceneDetect and
Community-1, whose wider and narrower statements of one licence are both correct and useful.
**Rejected: exempting a model from the check by name.** An exemption that does not pin the value
is a licence-shaped hole — measured: with KLPT merely exempted, its licence could still become
anything. **Rejected: keying the NC exclusion check on `commercial_use`.** The first spelling did,
and failed on `CLIP as primary retrieval`: seven of §7's nine exclusions are `NOT_ASSESSED`, which
is `commercial_use=False` **by design** — default-deny, "we have not cleared them", which this
module's docstring is explicit is not the same claim as NonCommercial. Keyed on the licence name,
both directions, so the code cannot assert a restriction on someone else's work that the frozen
blueprint does not.

**Mutation audit — 8/8, lint-clean.** All four survivors, plus a paired control for each new
guard. The two exemption controls are the pair that matters: removing KLPT's row while its
licence still diverges reddens the §7 check, and adding a row for an entry that *agrees* with §7
reddens the staleness check. **The baseline check earned its keep again** — the first run reported
`BASELINE NOT GREEN` on `RUF022`, my own `__all__` entry out of order, which had reddened three
gate-as-subprocess tests; without it, eight catches would all have been ruff.

No production behaviour changed: one data table and five tests. Floor 1547 → 1552.
`evidence/adversarial-pass-27-m0-2-the-licence-column.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-169

**`AUDIT_REPORT.md` says "the wheel contains", and the test holding it looked at the tree.** Its
own docstring says so: *"The files it now names must exist in the tree that builds the wheel."*
`assets/` and `models/` are not Python packages — they reach the archive only through
`[tool.setuptools.data-files]` — so the tree is not the wheel.

**Premise checked on the artifact first, and the claim is true.** Built from `bed2176` and
listed: **352,754 bytes, 55 entries**, all six named paths present, the four data files under
`hawedit-0.1.0.data/data/share/hawedit/…`. Nothing to repair. The byte count has moved from the
**346,694** D-141 recorded, which is a dated measurement behaving as this report's first bullet
says dated measurements do.

**What was already held, and what was not.** `test_every_data_file_the_wheel_ships_is_tracked_by_git`
reads the same stanza and requires its paths to be git-tracked, so it catches the stanza being
*emptied*. It looks at no archive and says nothing about *which* files belong. Measured: deleting
the single line `"assets/fonts/OFL.txt",` shipped every wheel **without the licence OFL-1.1
requires to accompany the font**, with the whole suite green — the stanza test still passes
because what remains is tracked, and both tree-level tests still pass because **the file is still
in the tree**. `registry.SHIPPED_ASSETS` records that obligation with the path; the thing that
ships is the archive.

**Decision: assert on the built archive, with the path list read out of the claim.**
`tests/test_build.py` already builds wheels for D-120's reproducibility pair, so the cost is a
build it knows how to do. The list is parsed from the report's own bullet rather than copied
beside it, so the test cannot drift from the sentence it holds. **Non-vacuity is taken from a
different file than the one parsed:** the licence files in `registry.SHIPPED_ASSETS` must appear
among the claimed paths, so a reworded bullet fails rather than checking nothing — and the third
mutation proves that binding is live.

**Rejected: extending the existing tree-level test.** It would have to build a wheel, which is
what `test_build.py` is for, and its stated job — the claim names paths that exist here — is a
different and still useful one. **Rejected: pinning the byte count or the entry count.** 55 is
true today and is a fact about setuptools' layout, not about this project's obligations; a test
on it would fail on an unrelated packaging change and teach people to edit the number.

**Mutation audit — 3/3, lint-clean, whole suite each, baseline verified green first.** The
load-bearing one is dropping *only* the OFL licence, which reddens the new test and nothing else.
**The first mutation is caught two ways and one of them is pre-existing**, so it is reported as
measured rather than claimed as this guard's win. **A fourth mutation was attempted and
discarded:** pairing "stanza deleted" with "the check reads the tree", to demonstrate the archive
read is load-bearing, came back **lint dirty** and therefore measured ruff (D-148, D-150). It was
also unnecessary — mutation 2 leaves the file in the tree untouched, so a tree-reading check
cannot see it by construction.

**Also probed this iteration and disproved, rather than assumed:** `Clip.from_dict` has **no
caller anywhere**, so §5's readback door is not reachable and hardening `ClipTranscript` would
guard nothing; `JudgeVerdict.__post_init__` already refuses out-of-range scores, a payoff outside
the clip, an unlisted narrative role and non-Kurdish title/description/hashtags, and role-checks
its judge; and D-146's delivery record is genuinely written last, after all five artifacts, with
three call sites and tests for the done, partial, torn and incomplete states.

No production code changed: one test. Floor 1552 → 1553.
`evidence/the-wheel-contents-claim-checked-the-tree.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-170

**The module every caption timing comes from was checked only against itself.** §4.2 puts forced
alignment in-house and Kurdish invariant #5 makes it the sole source of word timings. M1.1 is
`DONE` with 33 tests — all of them hand-written expectations, which share one weakness: a
systematic misreading of CTC would be written into the code *and* into the numbers beside it, and
every one would still pass.

**Is it right? Measured twice before anything was touched.** Against **torchaudio's** reference
forced-alignment kernel: 354 randomized matrices compared, 46 refused as infeasible by both,
**0 mismatches**. Against an **exhaustive search** over every legal CTC state path: 259 compared,
**0 disagreements** from either implementation. The aligner is correct. It simply had nothing
holding it.

**What the 33 tests were not holding.** Five real CTC errors, one at a time, whole suite each,
baseline verified green first. Deleting `extended[state] != extended[state - 2]` — the rule the
module's own docstring calls *"the CTC rule that makes this a real algorithm rather than an
argmax"* — left **every one of the 33 green, including `test_a_repeated_token_is_separated_by_a
_blank`, the test named after it**. Its matrix is `[{1: 0.9}, {BLANK: 0.9}, {1: 0.9}]`, where the
optimal path crosses that blank whether or not the rule forces it: the test passes for the
correct implementation and the broken one alike. The other three mutations are already held by
twelve, twelve and eight existing tests, and are reported as measured rather than claimed for the
oracle.

**Decision: an exhaustive search, and no new dependency.** `torchaudio==2.11.0+cpu` is in the
hash-pinned gate lock and a differential test against it would run. **Rejected:** `pyproject.toml`
avoids torchaudio deliberately (*"WAV frames to tensor without torchaudio"*) and it reaches the
gate only transitively, so leaning the gate of record on it would be a supply-chain decision taken
for a test's convenience. The brute force needs nothing, is exact on small matrices — which is
where boundary errors live — and was validated against torchaudio once, recorded in the evidence.
**Membership, not equality:** two paths can score identically, so requiring one tie-break would
pin an implementation detail rather than the answer. **The oracle's own control** is that for
every case with more than one legal path the optimal set must be a **strict** subset of them — an
oracle that ranks everything optimal agrees with any aligner at all. Cost: 0.09 s.

**The survivor is a no-op mutation of mine, proved rather than excused.** Deleting
`extended[state] != blank_id` excludes nothing the clause beside it does not: blanks occupy the
**even** indices of the extended sequence, so when `state` is blank `state - 2` is blank too and
`extended[state] != extended[state - 2]` is already `0 != 0`. Measured across seven token
sequences, **29 transitions examined, 0** where the blank clause is the deciding one. No test can
distinguish its removal, so it is **documentation, not a control**, and it is not counted. It
stays — a reader should not have to derive the parity argument.

**And one hypothesis I chased and disproved.** Before finding that argument I assumed the survivor
was a blank-poor corpus. Matrices where stepping over a token outscores emitting it turn out to be
everywhere — **34,932 of 50,683** — but that number is about a *different* relaxation: my search
harness permitted blank→blank skips explicitly, which the real mutation cannot reach. The corpus
change it prompted is **kept on the honest argument** (real CTC posteriors are blank-dominated, and
flat random rows are a distribution this aligner never sees) and recorded as having **changed no
mutation result**.

**4/5 caught lint-clean, 1 of them by the oracle alone.** The baseline check earned its keep for
the second iteration running: the first run reported `BASELINE NOT GREEN` on mypy `--strict`
`type-arg` — my own bare `tuple` annotations — which had reddened three gate-as-subprocess tests.

No production code changed: two tests and a type alias. Floor 1553 → 1555.
`evidence/an-aligner-with-no-independent-oracle.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-171

**M2.7 promises a runner *"reporting every stage it could not run"*, and the list of stages was
hand-written beside the dataclass it describes.** `PipelineRun.skipped()` named nine stages in a
tuple. Measured: deleting `("delivery", self.delivery)` from it left the **whole suite green**,
while `visual_index`, `discovery` and `editorial` were each caught by two or three tests — 3/4.

**What it costs, on the report a reader is handed.** The same run with render and delivery
skipped printed *"INCOMPLETE — **1** stage(s) did not run"* instead of two, never named the
delivery set, and dropped `blocked_by=('§2 delivery set',)` on the floor. **Never an exit-code
defect, and recorded that way:** `complete` separately requires `isinstance(self.delivery,
Delivery)`, so the CLI still exits 1. What failed is §1 of that module — *fail visible, not
silent* — with an unnamed failure being the silent case.

**Why `delivery` and not the other three.** `complete` is eleven conjuncts, and for two stages its
evidence is a *different field*: `visual_index` is covered by `bool(self.visual_windows)` and
`discovery` by `bool(self.candidates)`, so the list is load-bearing there and the suite holds it.
`delivery` has a direct `isinstance` conjunct, so `complete` stayed right without the list — which
is precisely why nothing noticed the list was wrong.

**Decision: derive it from the dataclass rather than guard the list.** `fields(self)` filtered to
values that are `StageSkipped`. Field declaration order **is** pipeline order, so the derived
sequence is the one the tuple spelled out — verified, the same `['render', 'delivery']` — and a
stage added later cannot be forgotten. The defect becomes **unconstructible** rather than guarded,
which is D-166's preference and a shorter diff than a list plus a test policing it.

**Rejected: keeping the list and adding a test that names every stage.** That is a second
hand-written list to hold the first, and D-127/D-129/D-141/D-149 are four prior instances of a
list drifting from the thing it describes. **Rejected: enumerating every dataclass field in the
test regardless of type.** mypy refused it, correctly — `replace()` would be putting a
`StageSkipped` into fields typed `tuple[MergedCandidate, ...]` — so the test's field set is
derived twice instead: from the annotations that declare `StageSkipped`, unioned with the stage
names `pipeline.py` actually constructs one with (which is what catches `boundary`, annotated
`object | None`).

**Mutation audit — 3/3 lint-clean, with a control that must stay green.** The pre-fix text is
`git show HEAD:`, not retyped. Restoring it reddens exactly the two new tests; truncating the
derivation to one stage reddens four; dropping `blocked_by` reddens three. **The control is the
point:** the *complete* hand-written list is behaviourally identical to the derivation and stays
**green**, so the new tests pin the property rather than this implementation of it.

**Two contaminated runs of mine, discarded rather than counted.** The first sweep hand-wrote the
pre-fix method and came back lint/format dirty; rebuilt from git it was dirty again, because
restoring the list orphans the new `fields` import and F401 fires. Third time this session (D-148,
D-150 record the pattern) — the fix is always to mutate the state together with everything that
exists only to serve it.

**Also probed this iteration and disproved, rather than assumed:** §8.1's metrics (M0.5) are both
correct and well held. `edit_distance` against a breadth-first search over the edit graph —
**7,225 pairs, 0 mismatches**; `substring_edit_distance` against the minimum over every substring
— **4,840 pairs, 0 mismatches**; and six plausible defects (substitution cost, the deletion
branch, the free prefix, the free suffix, the CER denominator, one-sided whitespace stripping)
were **6/6 caught** by the suite as it stands. An oracle there would have been busywork and was
not written.

Floor 1555 → 1558. `evidence/a-skipped-stage-the-report-could-not-name.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-172

**§3 Stage 5's window edge was held by nothing, and the test named after the blueprint never
opened it.** M2.2 is `DONE` with 40 tests and had never had its own pass. Six defects that ship a
*wrong clip* rather than raising — the belt-and-braces `assert_boundary_invariant` already catches
everything that violates invariant #2 — gave **4/6**.

**Survivor one is real.** §3 Stage 5 states *"preceding shot_cut within 400 ms"* and *"following
shot_cut within 400 ms"*; "within 400" includes 400. Changing `<=` to `<` on either edge left the
whole suite green. Measured on the real `fuse_boundary`: a cut at `anchor_out + 400` gives
`final_out 14400 by 'shot_cut'`, and one millisecond further gives `14200 by 'tail'` — **200 ms of
delivered clip** at the out edge and **400 ms** at the in edge, plus the attribution §8.2 reads.

**Survivor two is a no-op, proved rather than excused.** `anchor_in` is seeded into
`in_candidates` first, so a cut at exactly `anchor_in` ties and `min` returns the seed — measured,
`final_in 10000 by None` with the cut present or absent, and with an earlier cut that one is the
minimum either way. Documented, **not counted**, and the audit keeps mutating it to confirm it
stays a no-op.

**The larger finding.** `test_the_constants_are_the_ones_section_3_stage_5_states` asserted
`VAD_LEAD_IN_MS == 120`, `TAIL_MS == 200`, `SHOT_CUT_WINDOW_MS == 400` — three **literals typed
into the test**. §3 Stage 5 is named in the function's own title and was never read, so editing a
constant and its literal together left the suite green, against a **frozen** document that is the
specification these constants implement. The same shape as D-168's licence column: the
correspondence was true and accountable to nothing. It now parses the SOFT ADJUSTMENT block for
all three.

**Decision: derive, and take non-vacuity from the document's own redundancy.** The window is
stated **twice**, once per edge, so the parse requires both to be found and to agree — structural
rather than a magic count, and a regex matching nothing fails there instead of asserting nothing.
**Rejected: asserting the constants against literals and calling it a blueprint check** — that is
the defect. **Rejected: a test that only follows the constant** (`anchor_out + SHOT_CUT_WINDOW_MS`
with no independent anchor) — D-098's lesson, where every pause test passed `DEFAULT_PAUSE_MS` and
so followed it wherever it went; the value comes from the frozen document and the boundary is
pinned behaviourally on both sides.

**Mutation audit — 7/7 lint-clean.** Both edges, all three constants, and **both directions of
drift**: code moving away from the blueprint and the blueprint moving away from the code. Each
edge test reddens exactly the one written for it.

**The floor went down by one, deliberately and visibly.** The new constants test subsumes a
separate shot-cut-window test written earlier in this iteration, so that one was merged away
rather than kept as a duplicate to hold a number up. The gate refused the shrink exactly as
designed — *"a shrinking suite must be a visible edit, not a quieter green run"*. **Nothing that
shipped was lowered:** the committed floor at `6eefbb4` is **1558**, and the 1562 the gate
compared against was written by an intermediate run of mine that counted the merged test. This
commit takes the committed floor 1558 → **1561**, a ratchet up.

`evidence/the-window-edge-and-a-test-that-never-opened-the-blueprint.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-173

**Adversarial pass 28 — the same defect had now appeared twice, so this pass swept the class
instead of a row.** D-168 (§7's Licence column) and D-172 (§3 Stage 5's three numbers) were both
*a value `BLUEPRINT.md` states, checked against a literal typed into a test*. 46 numeric `Final`
constants in `src/hawedit/`; 29 have their value somewhere in the blueprint; **9 are stated
verbatim** and were mutated one at a time. **7/9 already held. 2 did not.**

**Excluded deliberately, and this is the judgment call:** `CONTENT_DETECTOR_THRESHOLD = 27.0`
(§3: *"threshold ~27, tuned per content type"*) and `REFERENCE_FPS = 1.0` (*"Reference settings
run ~1 fps"*). Both carry a tilde. Binding an approximate figure as exact would invent precision
the frozen document declined to give — the never-guess-a-threshold rule pointing the other way.
Naive matching is also noisy and was not trusted: `DEFAULT_TOLERANCE_MS = 50` "matches" *"expect
~50+ GB/s unidirectional"*, so every candidate was read in context first.

**Survivor 1 — `MAX_SPEECH_DURATION_S`, and the test that should have caught it.**
`test_the_stage_0_constants_are_the_blueprints` asserted `== 16_000`, the loudnorm string and
`== (1, 720, 28)` — literals, with `BLUEPRINT.md` in the function's own title and never opened.
**And it covered four of the six Stage 0 constants:** neither `MAX_SPEECH_DURATION_S` nor
`OMNIASR_CEILING_S` appeared. The only test touching the first asserts a *relation* —
`OMNIASR_CEILING_S - MAX_SPEECH_DURATION_S >= 2.0` — which **38 → 30 satisfies** (40 − 30 = 10), so
it passed. The blueprint says 38; the suite permitted anything at or below it. That number decides
where Silero cuts every piece of audio handed to ASR, so every segment boundary and every
transcript follows it. The margin test is a real, separate property and stays; what it is not is a
check that the value is the blueprint's.

**Survivor 2 — `DEFAULT_NGRAM_SIZE` 3 → 4, whole suite green.** Bound to nothing and pinned
behaviourally by nothing, though §2 singles the choice out: *"Character n-grams matter more than
usual — Sorani is morphologically rich with heavy clitic attachment."* A stated number, not a
tuning knob.

**Decision: parse the document, and assert on the artifact as well.** The Stage 0 test now reads
§3's two ffmpeg commands and its VAD line for **all seven** values; the index test reads §2's
n-gram size. Non-vacuity is a required match per value — a regex finding nothing fails there
rather than asserting nothing. **A document binding proves the number is the blueprint's, not that
anything consults it**, so `test_the_ngram_size_is_the_one_the_index_actually_uses` asserts on the
emitted n-grams of a word long enough to distinguish 3 from 4 — and its mutation (hard-coding a
size in `character_ngrams`) is caught by that test and no other.

**Rejected: a generic "every constant in `src` must appear in the blueprint" check.** Most of
these 46 constants are implementation choices the blueprint never mentions, and such a test would
either be vacuous or force fake blueprint entries for them. **Rejected: extending
`test_claims.py`'s decision-log binding to the blueprint wholesale** — `DECISIONS.md` states values
in a uniform recorded form; §3 states them inside prose and shell commands, so the parse has to be
per-site and belongs beside the module it constrains.

**Mutation audit — 7/7 lint-clean.** Both survivors, **both directions of drift** for four values
(code away from the document, document away from the code), and the artifact control. Each
mutation reddens exactly the test written for it.

**What survived the pass, and why that is not luck:** the other seven constants are held mostly
*behaviourally* — `TARGET_SAMPLE_RATE` reddens 68 tests because the real fixture is 16 kHz, and
`MAX_FRAMES_PER_WINDOW` reddens 18 through `test_claims.py`'s existing decision-log binding. That
binding already existed for `DECISIONS.md`; the equivalent for `BLUEPRINT.md` is what these two
rows lacked.

**No production code changed.** Both survivors were correct values that nothing held.
Floor 1561 → 1563. `evidence/adversarial-pass-28-constants-the-blueprint-states.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-174

**The call order inside `normalize_sorani` was right; the reason recorded for it was not the
operative one.** The comment said a ZWNJ-typed word *"is not the dictionary's spelling of it, so
it would never be recognised"*. True as far as it goes. Measured, the lookup **never receives the
word**: ZWNJ is U+200C, a format character, so `_TOKEN`'s `\w+` does not match it and
`وکتێبه‌کان` arrives as **two tokens** — `['وکتێبه', 'کان']`. The fragment's remainder is not a word;
the whole word's is.

**Why the distinction is not academic.** Reading the old comment, the natural repair is to
normalize the *remainder* inside the lookup. Measured, that repair changes nothing — the token was
already broken in half before the lookup was reached — so someone would have made it, seen no test
fail, and concluded the order was no longer load-bearing.

**What the order is worth, measured across KLPT's 24,894 entries:** 11,896 contain `ە` and have a
`و`-joined form that is not itself a word; of the first 400, the shipped order separates **400**
and the reverse separates **3**. Not an edge case — §4.1's fourth collision working or not on
exactly the text §4.1 exists for, with `transcript.raw.json` untouched either way and every index,
embedding and model input reading the joined form (Kurdish invariant #3).

**Two errors of mine, recorded rather than tidied away.** A sweep reported the reversal SURVIVING;
that was a **bad mutation** — it left the trailing `separate_conjunctive_waw` in place, adding a
pass rather than reordering. The property was held all along by
`test_normalization_runs_the_encoding_fixes_before_the_lexicon_lookup`. A control written on that
false premise was then **measured vacuous** — it wrapped the comparison in `normalize()`, which
re-joins the space, so it passed for the mutated and the shipped code alike — and was **removed
rather than kept**. *"A test that passes for both measures nothing"* applies to tests written in
this loop as much as to the ones it audits.

**Decision: correct the recorded mechanism, and pin the tokenization it rests on.** The comment
now states what was measured. `test_zwnj_fragments_the_token_which_is_why_the_order_is_what_it_is`
asserts that `\w+` fragments the ZWNJ form into two tokens and does not fragment the normalized
one. **Rejected: leaving the comment and adding only a test** — the comment is what a future reader
acts on, and acting on it produces a no-op repair. **Rejected: making `_TOKEN` absorb ZWNJ so the
order stops mattering** — that is the repair the old comment invites, it would put a format
character inside a word token everywhere else too, and §4.1's answer to ZWNJ is to remove it, not
to tokenize around it.

**Mutation audit — 2/3 lint-clean.** The ZWNJ-absorbing pattern is caught by **the new test and
nothing else**, which is what earns it a place beside a property already held. **The survivor is a
demonstrated no-op and is not counted:** normalising the remainder inside the lookup changes no
output, for the structural reason the corrected comment gives — the same shape as D-170's
blank-skip clause, and its survival confirms the mechanism rather than exposing a gap.

**Also probed this iteration and found well held:** `normalize.py`'s other guards — the mis-split
refusal, the remainder requirement, the Latin numeral target and the word-aware token pattern were
**4/4** against the suite as it stands, and `normalize_sorani`'s idempotence is asserted three
ways. **And M0.3's named shortfall is still not closable here:** §4.1 does not say what `ř`/`ł`
normalize *to*, so `BLOCKED.md` #13 stands — refused rather than guessed.

No behaviour changed. Floor 1563 → 1564.
`evidence/the-ordering-comment-named-the-wrong-mechanism.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-175

**The weights half of "pinned and checksummed supply chain", probed — 3/4.** D-139 pinned the
gate's Python packages, D-121 the ffmpeg archive, D-120 made the wheel reproducible. Model
weights are the largest surface and the last one, and two lines inside heredocs in
`scripts/fetch-models.sh` carry it — embedded Python that ruff does not read.

**The pinning half is well held, and held the right way.** Dropping `revision=revision` from
`snapshot_download`, resolving an unpinned repo to `main`, and making `revision_for` hand back a
branch head were all caught, by tests that **extract the real block from the script and execute
it** against a stubbed Hub rather than grepping its text — D-067's rule, applied where it matters
most.

**The survivor: the licence gate.** `assert_commercially_usable(entry)` in the planning block,
under the comment *"NonCommercial is a hard reject — checked before a single byte moves"*, could
be **deleted with the whole suite green**.

**Dead code or defence in depth?** It cannot fire on the committed tree: `missing_weights()`
iterates §7's *production* table and D-168's `test_no_registered_model_is_non_commercial` forbids
an NC entry there, while §7's two CC-BY-NC-4.0 models sit in the exclusion table. So it is defence
in depth, written for a §7 that does not yet exist — the registry docstring says so: the check
*"keys off the licence, not off those two names, so the next NC dependency fails the same way."*

**Decision: hold it, because unlike the recent survivors this state is constructible.** D-166's
sibling assertion and D-170's blank clause were left uncounted precisely because the state they
would catch cannot be built. Here the block consumes whatever `missing_weights()` yields, so a
test can offer it a CC-BY-NC-4.0 entry and require refusal — executing the real planning block,
the same way the download block is already tested. **Rejected: deleting the gate as unreachable.**
The registry test forbids an NC entry *today*; the fetcher is where bytes move, and a licence
refusal at the download is not made redundant by a licence rule in the table it reads. **Rejected:
asserting the call appears in the script text** — that is the assertion-about-text mistake D-067
recorded, one layer up.

**Mutation audit — 4/4 lint-clean.** Deleting the gate, calling it and swallowing its exception,
and neutering `assert_commercially_usable` are all caught. **The fourth is the control:** making
the gate refuse *everything* is caught by the positive test alone — without it, the refusal test
would pass for a gate that blocks every model §7 permits.

**One defect of mine, recorded rather than tidied away.** The first version patched
`ModelStore.missing_weights` on the class this test module imported at the top. Other tests in the
same file `importlib.reload(hawedit.models)`, so the executed block imported a **different class
object**, the patch landed on the stale one, and the refusal never fired — passing in isolation and
failing in the file, which is the signature. The helper resolves `hawedit.models.ModelStore` at
call time now, with a comment saying why.

No production code changed. Floor 1564 → 1566.
`evidence/the-licence-gate-before-the-first-byte.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-176

**M2.8 claims the panel "never prints it", and the branch that prints a *stored* key was driven
by no test.** Four escape routes for the Gemini key, mutated one at a time: the API-key header,
the mask, the unreachable-API message and the status readout. **3/4** — the readout survived.

**Why it survived, and why the existing test is not at fault.**
`test_the_panel_prints_the_mask_and_never_the_key` asserts both directions and is not weak; it
drives the **entry** path, where the key comes from `getpass`. The surviving line is on the
**status** path, and `_drive_main` stubs the validator, the writer and `getpass` but **not**
`credential_status` — so on a machine with no key configured it returns `None`, `main` takes the
`key is None` branch, and the `else` executes in no test at all. That `else` is what every user
with a key stored sees on every run, and its output lands in terminal scrollback. `--check`, the
scriptable path most likely to be piped into a log, was driven by nothing either.

**Decision: drive `main()` with `credential_status` stubbed to a stored key, and assert both
directions.** The key must be **absent** and the mask **present** — the second half is the
control, without which both tests pass for a panel that prints nothing and *"never prints it"*
becomes true by silence. **Rejected: asserting only the absence of the key**, which is the
vacuity above. **Rejected: pointing the panel at a temporary credential file** — `ENV_FILE` is
bound at definition time, the reason `_drive_main` stubs the writer rather than redirecting it
(recorded there), and the claim under test is what the readout prints, not where it reads from.

**Mutation audit — 3/4 lint-clean, and two of them are caught by the new guards alone.** The
restored defect is one. **The other was not what this iteration set out to find:** `--check`
returning 0 whatever the API said, so a script gating on `hawedit-credentials --check` would
proceed with a revoked key — which is the whole purpose of the flag. The fourth mutation (the
readout prints nothing) reddened the new guards too but left the block **format-dirty**, so it
measured ruff as well and is not counted (D-148, D-150); the non-vacuity it was testing is
established inside the guards by the `mask(...) in out` assertion.

**What the pass found already held, and held well:** the credential goes in the `x-goog-api-key`
**header** rather than the URL — pinned by `test_key_validation_authenticates_by_header_never_by_url`
— the mask is tested against two keys, and the unreachable-API message is asserted not to contain
the key. Pass 20 covered the panel's *sequencing* (validate before write); this covers its
*output*.

No production code changed. Floor 1566 → 1568.
`evidence/the-status-readout-nothing-drove.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-177

**Eleven refusals probed; ten held. The survivor is on today's only Stage 4 route.** `main()`
refuses fourteen argument combinations and `run_pipeline` refuses one more — a supplied verdict
whose span is not the selected sentence anchors. The argument refusals are exemplary, and
`test_every_refusal_in_the_source_has_a_case` is *derived from the source*, so a new one cannot
arrive uncovered; it reads the arg-parsing block, and the surviving check lives outside it.

**Why this one matters now:** `--verdict` is the **only** Stage 4 route while `BLOCKED.md` #3
stands. `JudgeVerdict.__post_init__` cannot catch a mismatch — it requires
`clip_in_ms <= payoff_at_ms <= clip_out_ms`, which a verdict for a *different* clip satisfies
perfectly. Internally valid, externally wrong.

**Measured on the §5 block that ships:** a verdict scored 900000..904000 ms carries
`payoff_at_ms: 902000` into the editorial block of a clip running 100..4100 ms — §5's payoff
marker 898 seconds past the end — with `hook_score`, `meaning_fidelity`, `misleading_edit_risk`
and `cultural_landing` all reached on footage the clip does not contain.

**Decision: cover each end of the span separately.** **Rejected: one test moving both ends**,
which is what the first version did — and the audit showed that comparing only `clip_in_ms` still
caught it, leaving unheld the case an operator is most likely to produce by hand: the right start
and the wrong end. Each end now moves alone, and that mutation is caught by this guard and no
other.

**Two results recorded rather than claimed.** The `judge is None` clause **survived**, and the
control I wrote for it measured nothing: with discovery driving the run, `boundary` is
`StageSkipped` and `anchors` is `None`, so that path never reaches the check — measured, the judge
answered `(0, 1700)` with no anchors in existence. Defence in depth whose state I could not
construct, the category of D-166's sibling assertion and D-170's blank clause; the vacuous test
was **removed** rather than kept, as D-174's was. And two mutations first came back
**format-dirty**; re-run through `ruff format` so they measured behaviour rather than layout,
they changed answer — which is why they were re-run rather than reported.

**2 of 3 counted mutations caught by the new guard alone**; the third (refuse every supplied
verdict) is caught broadly, by the positive control and by every existing test that supplies a
matching verdict. No production code changed. Floor 1568 → 1570.
`evidence/a-verdict-for-other-footage.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-178

**Adversarial pass 29 — every refusal in `src/`, and which the suite never reaches.**
`tests/test_credentials.py` states this project's thesis: *"the tests that matter are refusals"*.
Four consecutive iterations then found one unreached refusal apiece (D-175, D-176 twice, D-177),
so this pass measured the whole surface instead of continuing one at a time.

**Method, and a rejected one.** `coverage` is not installed and installing it would change what
the gate's environment contains — D-139 fixed that deliberately with a hash-pinned lock, and a
one-off measurement does not justify reopening it. **Rejected**, in favour of a stdlib
`sys.settrace` line tracer whose local trace function returns `None` for every file outside
`src/hawedit`, so per-line tracing runs only on the code being measured; `ast` supplies every
`raise` and its enclosing function. **Caveat recorded, not hidden:** subprocess-based tests are
not traced, so a refusal reached only there reads as unreached.

**Measured: 438 raise statements in `src/hawedit`, 125 never executed by the suite.** Largest
first: `asr.py` 14, `pipeline.py` 10, `asr_worker.py` 9, `editorial_bench.py` 8, `transcripts.py`
8, `gemini.py` 7. **125 is not 125 defects and this decision does not claim it is** — much is
legitimately unreachable here (`OmniAsrBackend` and `WslOmniAsrProducer` need weights and a WSL
runtime, `gemini.py` needs a key, several are `SystemExit` under `__main__`). Naming the number
without calling it a defect count is the point; the opposite would be exactly the uncounted-list
claim this project keeps finding in its own documents.

**The standout, and it is the twin of D-177.** `_assert_verdict_matches_request` runs on every
judged run: its call site and **both** comparisons execute, and **neither of its two refusals ever
fires**. It is the only thing between a judge adapter's answer and §5's editorial block — and
D-177 measured one iteration earlier what a verdict for other footage carries there:
`payoff_at_ms` outside the clip, every editorial score reached on footage the clip does not
contain. Same state as the persisted-verdict door: correct, load-bearing, accountable to nothing.

**Decision: drive Stage 4 with an adapter whose verdict comes from an injected factory.** The two
refusals get a test each — **separately**, because an adapter answering the right candidate over
the wrong seconds passes the identifier check completely — plus a control requiring an adapter
that answers its own request to be accepted. **Rejected: one test for both refusals**, which is
the mistake D-177's first version made (moving both ends of a span at once let a half-check pass).

**Mutation audit — 4/4 lint-clean, three caught by the new guards alone:** each refusal
separately, and the call site that reaches them. The fourth, a guard that refuses *everything*, is
caught broadly by the positive control and by every existing test that drives a judge — which is
what makes the first three meaningful rather than satisfiable by a pipeline that refuses all.

**A mutation left on disk, recorded because the hazard is real.** This pass's first audit run was
killed with the session and its `finally` never ran, leaving mutation 4 — `if True:` in place of
the candidate-identity comparison — in `src/hawedit/pipeline.py`. `git add <file>` stages the file
**as it is on disk**, which is precisely what BLOCKED #12 records carrying into main under someone
else's message. Caught by diffing the tree against `HEAD` before staging anything and restored
with `git checkout --`; the habit is the only thing that catches it.

No production code changed. Floor 1570 → 1573.
`evidence/adversarial-pass-29-refusals-nothing-reaches.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-179

**A route into `BLOCKED.md` #1, and the one default that would have destroyed the number it
exists to produce.** #1 asks first for *"your own labelled material with reference transcripts"*.
Cortex Speech Studio (`HawzhinBlanca/cortex-speech`, Hawa's own product) is a Sorani
transcription and dataset-curation app with human review and JSON export — the first half of
that. `import_cortex_speech` reads it.

**Schema read from a committed artifact, not from type declarations.**
`manifests/real_audio_tests/B7871-esv2-speech-89p.user_dataset_output.json` is an export the tool
has actually produced: a JSON array of ~27-field camelCase segment records. Four fields map
directly (`id`, `audioPath`, `rawTranscript`, `durationMs`), and the four §8.1 labels are absent.

**The defect the importer exists to prevent.** `transcript_export.rs` filters on
`!is_human_rejected` and `!is_effective_placeholder` and **not** on `verified`; its own comment
says so — *"the owner wants THEIR transcripts"* — and the sample artifact carries
`"verified": false`. Correct for Cortex, catastrophic here: read as `reference_ckb`, unverified
records score **OmniASR against OmniASR's own transcript**, CER collapses toward zero and reads
as a triumph, and §3 Stage 1's escalation quartile plus every M7 quality gate are derived from
that number.

**Decision: import only what a human confirmed, and make the remainder visible.** `verified`
**or** `isGold` — two independent doors, because keying on `verified` alone would silently drop
every gold segment, the most trustworthy records in the file. The count left behind goes in the
provenance note. **Rejected: returning an empty corpus** when nothing is confirmed — that is the
quiet version of the same answer, so it raises `NoVerifiedTranscripts` naming the count.
**Rejected: skipping unconfirmed records silently**, which is how a corpus quietly shrinks
(D-091's lesson on this same module).

**Four more refusals, each a plausible default declined.** No dialect and no conditions — Cortex
captures neither, so every item is unlabelled and the coverage check still refuses the set.
No `reference_words`: Cortex aligns with OmniASR-CTC-**300M** through sherpa-onnx while §7 pins the
**3B**, and invariant #5 says timings come from CTC Viterbi alignment only — so §8.1's alignment
metric scores none of these items, `None` rather than `0.0`. No `normalizedTranscript`: Cortex
ships its own under its own `normalizerVersion`, and importing it would put a foreign
normalization into the artifact every index, embedding and model input reads (invariant #3). **No
default licence**: Common Voice has a published one this module can name, a private export does
not, and "unknown" is not a licence.

**Mutation audit — 6/8 lint-clean.** All eight reddened exactly the tests written for them; two
left the file format-dirty, so they also measure ruff (D-148, D-150) and are **not counted** —
reported because they were run, not claimed as coverage.

**What this does not discharge, and it is the important half.** The import produces real material
with real transcripts and **no §8.1 coverage at all**, so M0 stays blocked and M0.14 stays
`PARTIAL`. Four fields captured at review time in Cortex would change that: `dialect` (one of
three), `conditions` (any of seven), `named_entities` where that condition is set, and
`code_switch_spans` where either code-switch condition is set.

**And a licence question that is Hawa's to answer.** Cortex Speech Studio is **PolyForm
Noncommercial 1.0.0**. The *data* it produces is Hawa's own and is not encumbered by the tool's
licence — the provenance records whatever terms cover the recordings, which is why `licence` is a
required parameter. Whether *using* NC-licensed software to produce assets for a product that
ships commercially counts as commercial use of that software is a question only the copyright
holder can answer, and he holds it for both repositories. Recorded rather than assumed. **No code
was taken from Cortex**: nothing would port — it is Rust/Tauri against this project's Python — and
taking any would put NC-licensed source inside the system whose own registry hard-rejects NC.

Floor 1573 → 1585. `evidence/the-cortex-export-imports-machine-output-as-reference.md`.

**BLOCKED #3 re-measured this iteration and still live:** `GEMINI_API_KEY: not set`,
`GOOGLE_API_KEY: not set` and `~/.hawedit/credentials.json` absent; `HF_TOKEN` unset (#4). The
ZAR38MinTest end-to-end run stays blocked on #3.

## D-180

**The documented recovery from an OOM failed on the first window every time, and the guard blamed
the wrong thing.** Found by running the real 38-minute file, the same way D-104 was.

`BLOCKED.md` #17 / D-108 record that this 3090 Ti reads at most 8 frames per window and that
`--visual-max-frames` is lowerable precisely so a run can be retried under that ceiling. Run 1 at
§3's default 64 OOMed in the reader (`Tried to allocate 98.56 GiB` — D-106's measured behaviour,
not a defect). Run 2, the retry at 8 into the same work directory, was refused:
`ZAR38MinTest:s0:w0 planned 8 frames and ffmpeg produced 16`. **ffmpeg had produced 8.** The
directory held 16, because `extract_window_frames` writes with `-y` — which overwrites
`000_0001..000_000N` and leaves anything above N — and then grades the extraction by globbing the
directory. So the retry's count read 8 fresh frames plus 8 leftovers from the run that OOMed.

**This is the second half of D-104.** That entry fixed this same count being taken over the
*parity step's* output. It was also being taken over *the previous run's* output, and only a retry
at a lower frame budget exposes it — which is why it sat behind the one instruction the OOM
documentation gives.

**Fix: clear this window's frames before extracting**, scoped by `window_index` to match the glob
it repairs. **Rejected: emptying `dest_dir`** — shorter, passes every other test in the file, and
silently discards a neighbouring window's extraction; `_FrameCache` happens to give each window
its own directory but this function takes `dest_dir` from its caller, so the scoping cannot rest
on a caller's habit. That rejection is the second mutation, and it is what the new control test
exists for. **Rejected: relaxing the `> frame_count` check** — the check is right and D-104 gave
it its first test; what was wrong is what the count was allowed to see, not what it refuses.
`test_more_frames_than_planned_is_refused` still drives a fake ffmpeg writing 37 files for a
36-frame plan into a clean directory and still raises, unchanged.

**Proved on the artifact, against the directory that raised.** Re-run deliberately without
clearing it by hand: `frames/ZAR38MinTest_s0_w0/` went from 16 files and a `FrameCountMismatch` to
8 files and a run that proceeds past w0.

**2/2 mutations, lint-clean, file restored byte-identical.**
`evidence/a-retry-at-fewer-frames-inherited-the-previous-extraction.md`.

## D-181

**A fine-tuned decoder would have shipped the base model's words under its own name.** Asked to
run Stage 1 with Hawa's own fine-tuned OmniASR-7B ("champion"), `--omni-asr` had no way to load an
adapter — and giving it one exposed three defects, the first of which ships wrong output.

**1. The reuse key could not tell an adapted run from a stock one.** `run_pipeline` keys Stage 1
reuse on `f"{module}.{qualname}"` of the producer, and every OmniASR run is
`hawedit.asr.WslOmniAsrProducer`. A stock run then an adapted run over one work directory returned
the **stock transcript in 0 s** and reported the adapter: 545 segments of words the champion never
read, presented as the champion's. That is D-136's own rule — a transcript "must not be reused
by a run that did not make it" — on the axis that did not exist when D-136 was written.
**2. The artifact hardcoded the base model**: `_assemble_canonical_transcript` wrote
`canonical="omniASR_LLM_7B_v2"` as a literal, so an adapted transcript claimed stock provenance in
the file that ships to the client. **3. `peft` was absent from the runtime venv** — measured
`peft MISSING` against `%LOCALAPPDATA%\HawEdit\wsl-asr\venv` — so the adapter path would
have raised `ImportError` inside WSL *after* Stage 0 and 545 WAV cuts.

**The judgement: `adapter` is a new `AsrProvenance` field beside `canonical`, never inside it.**
Folding the digest into `canonical` was written first and `AsrProvenance` **refused** it with
`ModelNotInRegistry`: §7 role-checks that field, and a fine-tune of a §7 model is still
that model. The cheapest way to make that pass would have been to loosen the §7 check —
refused; the guard is right. **Rejected: recording the adapter only in the run report** — the
transcript is the artifact that ships, and D-103 already settled that what a transcript does not
contain belongs *in* it. **Rejected: a §7 registry row for the champion** — that needs a
licence for weights Hawa trained, and this loop does not guess a licence. `BLOCKED.md` #21.

**Nothing guessed.** The `vocab_size = 10288` the trainer's server hardcodes is the bundle
tokenizer's own `vocab_info.size` (verified: `10288`, `derivable: True`), so it is read, not
written down — a literal would be a guess for the next adapter. The base checkpoint is the
official card's own `checkpoint` field (`https://dl.fbaipublicfiles.com/mms/omniASR-LLM-7B-v2.pt`)
handed back to fairseq2 so its cache answers, rather than the `~/.cache/…` path the trainer's
server hardcodes about its own disk. `peft==0.19.1` is the version `adapter_config.json` records
as having written the bundle. **One deviation recorded rather than resolved:** the in-memory card
uses `model_arch: "7b"` where the official card declares `7b_v2`. The trainer's recipe uses `7b`,
an adapter is only valid against the shapes it was trained on, and `7b` is what was measured
end-to-end — so `7b` it is, and this sentence is why.

**Kurdish invariant #5 is untouched and asserted.** Only the LLM decoder is adapted; CTC-3B, its
tokenizer and its device are identical between the two backends, and every timing still comes from
the Viterbi path over CTC emissions. An adapter changes which words are read, never when they are
said.

**The adapter is not cosmetic**, measured against the same in-memory checkpoint on three real
clips from `ZAR38MinTest.mp4` differing only in whether it was applied: **3/3 changed**. At 19:15
the base drops the opening line and the champion recovers it
(`هەستەکەم درۆم لە
گەڵ ناکا …`); at 1:00 the base opens with a hallucinated
`سانە` the champion does not emit.

**9/9 mutations, lint-clean, every file restored byte-identical.**
`evidence/the-champion-adapter-would-have-shipped-the-base-models-words.md`.

**One operational finding, because it cost a real run.** A Stage 1 run died on `runtime is not
provisioned` while the mutation audit was running: `_runtime` resolves the WSL snapshot by
`package_fingerprint`, a digest over `src/hawedit/*.py`, and the audit was rewriting those files.
Not a defect — a real run and any edit to `src/hawedit` cannot overlap.

## D-182

**A complete, correct SV6D answer was discarded for citing a span — the second half of
D-118.** That entry found this exact message on the real 38-minute run and fixed its *blast
radius*: one unreadable window no longer discards every other candidate. It treated the refusal
itself as correct. It was not. Measured on `path_b_result.json`, the one window of seven that came
back `unreadable`:

```
ZAR38MinTest:s54:w4   1040.287s .. 1043.818s   (3.531 s)
reason: the model returned no usable line for ['subject', … all six …]

subject | 0.0-3.5 | Two men in a studio setting, one speaking and gesturing, the other listening
… and five more, every dimension present, described and timed
```

Six lines, six dimensions, each with a description — and the description is **right**, since
frames decoded from this file show exactly two men across a table in a studio. `_LINE` required a
bare number, so against `0.0-3.5` the `at` group matched `0.0`, the next character was `-` rather
than `|`, the line failed, and `if match is None: continue` dropped all six as noise. Verified
before changing anything: `_LINE.match('subject | 0.0-3.5 | …') -> None`, `… 0.0 …
-> matched`. **Computed and discarded, not never computed.**

**The root defect is the silence, not the span.** Supporting `0.0-3.5` alone would fix one line
and leave the next unanticipated format to vanish identically. So: a span is read *and* a line
naming a real dimension is never skipped — it parses or is refused **by name**. A line naming
no dimension is still left alone, because the model's prose and a stray markdown rule are noise,
and that distinction is what keeps this from turning chatter into refusals. It is also the control
the mutation audit needed.

**The judgement: a span anchors at its start**, a number the model itself wrote, with **both** ends
bounds-checked. **Rejected: the midpoint** — nobody observed it, and inventing it is the same
defect as filling a missing dimension with a default, which the very next branch already refuses.
**Rejected: keeping the refusal** because `SV6D_PROMPT` asks for a bare number — the prompt
asks, the model answers as it answers, and §3's rule is *"Reject output where a claim has no
timeline evidence."* `0.0-3.5` **is** timeline evidence, more of it than a point. Refusing it
enforced the prompt's formatting, not the blueprint's rule.

**This reverses a position the repo already held, and it is reversed openly.**
`tests/test_video_reader.py` carried `REAL_RANGE_OUTPUT` commented as a span that §3
*"refuses all six"*. That fixture is **kept** and is still unreadable in D-118's test — for the
reason it should be, since it cites 3.5 s of a 1.4 s window. Its comment now says so and the
assertion names the clip length. D-118's own guard, that one unreadable window does not discard the
others, is untouched and still driven through the real `read_scenes`.

**Proved on the artifact:** the real discarded window re-parses **0/6 → 6/6** and shifts onto
the media clock as `1040.287s Two men in a studio setting…`. Re-run end to end after the fix, the run goes from **6 candidates and 1 unreadable to 7 and
0**, the recovered window landing at rank 4 (retrieval 0.5614, rerank 0.3601) while the other six
keep their ranks and scores — an addition, not a reshuffle. **6/6 mutations, lint-clean, file restored
byte-identical.** `evidence/a-complete-sv6d-answer-was-discarded-for-citing-a-span.md`.

## D-183

**The printed report never said what Stage 3 found — D-111's finding, one representation
over.** D-111 fixed `report["discovery"]` reading `null` whether Stage 3 produced candidates or was
never attempted, and stated the rule: *"a stage reporting nothing about itself is the silent
case."* It fixed the **JSON**. The **printed** report — what the documented invocation
produces — said nothing about Stage 3 at all, and the asymmetry is the tell: a *skipped*
discovery printed a `SKIPPED discovery:` line, a *successful* one printed nothing.

Measured on the full composed pipeline over the real 38-minute file with the champion adapter
(Stage 0 and Stage 1 both reused, Stage 2 and Path B live). The whole printed report went straight
from Stage 2's survivors to §4.2's sentences:

```
stage 2 641 scene window(s) · 4873 frame(s) at 2.0 fps · 7 reranked survivor(s)
§4.2    185 sentence(s)
```

while the same run's `--json` carried
`"discovery": {"skipped": false, "candidates": 7, "by_path": {"visual": 7}}`. Among those 7 is
`zar38champion:s54:w4` — the window D-182 recovered — so the stage the operator cannot see
is the one producing the run's actual output. Computed, carried, and reported in one representation
but not the other.

**Fixed with one line in `_print_report`**, in pipeline order between Stage 2 and §4.2:
`stage 3 7 candidate(s) [visual 7] · 0 rejected [visual 0]`. **The judgement: it is read off
`_discovery_ran()`**, the same helper `to_dict` uses, rather than recounted from `run.candidates`
— two reports of one run must not be able to disagree about what it did, and that is a guard
with its own mutation, not a convenience. **Rejections print even at zero**: §5 makes rejection
first-class and calls that set *"your only measure of recall"*, the set was computed so `0` is a
measurement rather than an absence, and a line appearing only when something had been rejected
could not be told from one that never ran — D-110's reasoning, which `to_dict` already applies
to these same two fields. **Rejected: printing a bare total** — §8.2 measures Recall@20
*per discovery path* and "if Path B never surfaces a winner Path A missed, collapse it" is decided
on that split, which a total cannot support.

**5/5 mutations, lint-clean, file restored byte-identical — after 3/5, and the audit caught a
test of mine that measured nothing.** The per-path split test first asserted only that each path's
*name* appeared in the output; the rejection split prints the same names, so deleting the candidate
split entirely left `visual` in the line and the test stayed green. It now asserts each path's
*count*, which the all-zero rejection split cannot satisfy.
`evidence/the-printed-report-never-said-what-stage-3-found.md`.

## D-184

**Adversarial pass 30 — M0.4's "enforced three ways" claim survives, and the pass's own first
attempt did not.** `transcripts.py` claims invariant #1 is enforced by three independent
mechanisms *"because any one of them alone is bypassable"*. That is falsifiable: remove each and
see whether the suite notices. Each was reverted in turn against a baseline verified green first,
against the **whole** suite rather than `tests/test_transcripts.py`, since a guard defended only by
its own module's tests is the shape D-105, D-108, D-112 and D-118 each found separately.

**Nothing survived.** Write-once **refuted by 13 tests**; `frozen=True` refuted by
`test_raw_transcript_is_immutable_in_memory`; the SHA-256 comparison refuted by
`test_tampering_with_raw_on_disk_is_detected`. Files restored byte-identical, suite green after
restore. **M0.4 stays DONE and no code changed.**

**The judgement worth recording is about the pass, not the claim.** The first attempt at mechanism
1 removed only the digest reservation and left `os.link(staging, path)` — which still raises
`FileExistsError` on a second write. It reported REFUTED, and that verdict was worthless: it had
tested a sub-part while the mechanism itself stood, and it failed in the flattering direction. It
was caught by reading *which* test fired: under `pytest -x` the first failure was
`test_distinct_selections_do_not_overwrite_each_others_deliveries`, a **delivery** test rather than
a transcript one, and a guard whose only visible defender is incidental is worth a second look. The
second look found the reversal at fault, not the coverage.

**Method fixed for later passes: no `-x`.** It answers "does anything notice?" and hides "how
much" — and for an adversarial pass the second question is the one that matters, because a
mechanism defended by a single incidental test is one deletion away from being defended by nothing.
Re-run properly: 13 defenders, several named for exactly this.
`evidence/adversarial-pass-30-invariant-1-enforced-three-ways.md`.

## D-185

**`--auto-select` chose nothing on the real file and would not say why.** The composed pipeline
runs to completion on the 38-minute media and produces no clip, which is not a defect — but the
only thing the report said was `boundary did not run because complete selected sentences was not
available`, the symptom, which reads as a broken selector.

**Measured on the champion run:** 7 candidates spanning **3.48–3.96 s** against **184** complete
sentences of **0.41–102.52 s**, median **6.72 s**, and **0** wholly inside any candidate
(57–63 per candidate are short enough *in principle*). §5 selects complete sentences
*wholly inside* a candidate, so a retrieval unit shorter than a sentence contains none however good
the retrieval was.

**Why the windows are 3.5 s, from the code's own arithmetic.** `_max_window_ms` is
`floor(max_frames * 1000 / fps)`, so the ceiling is `max_frames / fps`: §3's 64 frames at
2.0 fps gives **32.0 s**, this machine's 8-frame limit at the same rate gives **4.0 s**, and 8
frames at **0.25 fps** gives **32.0 s** again. `BLOCKED.md` #17 / D-108 record the 8-frame limit and
that lowering it "changes what a window *is*"; what they do not say, and this adds, is that the
limit constrains the **product** and therefore the window *duration*. **Corrected 2026-08-12
(D-186):** this entry then concluded that §3's ~32 s unit was therefore reachable at a lower
sampling rate. It is not — `SceneWindow` enforces a **1.0 fps floor**, so the reachable ceiling
here is 8 frames @ 1.0 fps = **8.0 s**, and the 0.25 fps route is refused at plan time. **#17
refreshed, then corrected with that measurement.**

**No default changed.** `DECLARED_SAMPLING_FPS = 2.0` is a declared constant and §8.2's
Recall@K is measured on whatever unit it yields; picking a new rate is a threshold decision with a
real cost, and this loop does not guess thresholds. The option and its measured trade are recorded
for whoever makes that call.

**Fixed** by making the boundary skip state the cause in the numbers the run already holds —
candidate count and span, complete-sentence count, range and median, and the pointer to #17. Same
family as D-111 and D-183: a step that decided something reported nothing about the decision.

**5/5 mutations lint-clean, file restored byte-identical — after 2/5, then 3/5.** Two of the
first mutations were *broken programs* rather than mutations (deleting an assignment while the
f-string still referenced the name), and rewriting them to substitute values forced the test to
assert the span values and the median **value** instead of the word "median". **One equivalent
mutant is reported rather than counted:** attaching the explanation unconditionally survives
because `run.boundary` is overwritten downstream on every path where a selection succeeds —
verified by applying it and re-running the wide-window case. The guard stays `if not automatic:`
because it is intention-revealing, not because a test defends it.
`evidence/auto-select-chose-nothing-and-would-not-say-why.md`.

## D-186

**D-185 recorded a route the code refuses; the real ceiling is 8 s, not 32 s.** D-185 concluded
that §3's ~32 s unit *"is reachable on this 24 GB card at a lower sampling rate"* — derived
from `_max_window_ms` arithmetic and never run. `SceneWindow.__post_init__` enforces a **1.0 fps
floor** (`REFERENCE_FPS = 1.0`), and its refusal names the reasoning D-185 missed: *"Lowering the
rate is how a long scene fits under the 64-frame ceiling without being segmented, and the resulting
embedding is indistinguishable from an honest one. Split the scene instead."* The repo had already
considered and rejected that exact trade.

**The arithmetic was right and the conclusion was wrong, because it never asked whether the code
permitted the setting** — the same failure the D-182 verification caught one iteration
earlier, in the same shape: a prediction recorded where a measurement belongs. It reached `main` in
330b430 before it was checked, and §4 of this loop's own instructions say to assert on the
artifact, never on the reasoning.

**Measured, what is actually reachable here:** §3's 64 frames @ 2.0 fps = 32.0 s, out of reach
(`BLOCKED.md` #17); 8 frames @ 2.0 fps = **4.0 s**, which runs and fits **0** of 184 complete
sentences; 8 frames @ 0.25 fps = 32.0 s, **refused at plan time**; 8 frames @ **1.0 fps = 8.0 s**,
the real ceiling. The median complete sentence is **6.72 s**, so D-185's question stays live —
the answer is **8 s via `--visual-fps 1.0`**, not 32 s via 0.25.

**A second defect found by trying it, recorded not fixed.** `--visual-fps 1.0` is supported and on
the real file it does not refuse — it dies inside the reader with
`t:1 must be larger than temporal_factor:2`, after Stage 0 and a full re-embed, naming neither the
window nor the cause. `frame_count` is `ceil(duration_ms * fps / 1000)`, so a scene under ~1.5 s
yields 1–2 frames at 1.0 fps where it yielded 3 at 2.0, and the reader needs more than 2. Not
fixed here: the minimum is a property of each §7 reader and must be read from the checkpoints
rather than guessed — `_MIN_SAMPLED_FRAMES = 4` already sits nearby for a *different* quantity,
which is exactly how a guessed constant looks right and is wrong. `BLOCKED.md` #22.

**No code changed.** The error was in the record. `evidence/d-185-recorded-a-route-the-code-refuses.md`.

## D-187

**`BLOCKED.md` #22's root cause found, and the obvious fix reverted because it is worse than the
defect.** #22 said the minimum frame count must be read from the §7 checkpoints rather than
guessed. Read: `video_preprocessor_config.json` for `MCG-NJU/VideoChat3-4B` declares `fps: 2`,
`min_frames: 4`, `temporal_patch_size: 1`, `temporal_merge_size: 4` — confirming both
`DECLARED_SAMPLING_FPS = 2.0` and `_MIN_SAMPLED_FRAMES = 4` against the weights.

**The root, reproduced with no GPU** on the real file's own Stage 0 output: `plan_scene_windows`
at 2.0 fps emits **641** windows of which **1** is below `min_frames` (`s22:w0`, 1000 ms → **2**
frames); at 1.0 fps it emits **364** of which **31** are, the smallest being that same scene at
**1** frame — which is the crash, `t:1`.

**And the sweep that appears to rule this out exempts it.**
`test_every_plannable_window_is_delivered_to_the_model_whole` claims *"every window a planner can
produce is delivered whole"* and its body reads `if emitted < 2: continue`. Its own arithmetic on
the real counterexample: 1 frame @ 1.0 fps → the model reads **2**, not whole. The claim holds
only of the windows the sweep did not skip, and real media produces the skipped one.

**The fix that was tried and reverted.** `SceneWindow` already refuses the *upper* bound, so the
symmetric lower bound looked obviously right, and measured it did exactly what #22 asked: 2.0 fps
unaffected, 1.0 fps **refused at plan time** naming the window instead of dying inside the model
after a full re-embed. **It also broke two existing tests, and they were right.**
`plan_scene_windows` defaults to `REFERENCE_FPS = 1.0`, so at the default rate *any scene shorter
than 2 s cannot be planned at all* — an ordinary 1-second tail scene fails planning outright.
§3 requires windows to **tile** the media and `assert_window_coverage` exists because "a hole
here makes a moment invisible to Path B"; refusing a short scene is exactly such a hole. **Trading
a padded frame for missing footage is the wrong trade.** Reverted; `visual_index.py` is unchanged
and the suite is green.

**Rejected, with their opposite failure modes, rather than chosen:** *let it through* (today —
the processor pads by repeating the last frame, so the model reads a frame that was never filmed
and the embedding is "indistinguishable from an honest one"); *merge the short scene into its
neighbour* (keeps coverage, but the window then spans the shot cut §3 Stage 2 segments on);
*extend the window past the scene* (keeps coverage and count, embeds footage the window does not
claim). None is free and none is measurable without deciding what a window is *for*.

**Also left deliberately unfixed:** the sweep's `if emitted < 2: continue`. Removing the exemption
turns it red against real planner output, which is honest — but red with no fix available, and
a permanently red gate is not a signal. Named in #22 so the exemption cannot be read as coverage.
`evidence/the-sweep-exempts-the-window-that-crashes.md`.

## D-188

**The Common Voice import shrank the corpus in silence, against a rule this module states in its
own refusal.** `import_common_voice` raises, for a clip missing from the durations file, *"Every
item needs a real duration; **skipping it silently would quietly shrink the corpus**, and defaulting
it would fabricate a measurement."* Ten lines above that refusal it skipped rows silently. The
Cortex importer in the same file obeys the rule — `unconfirmed += 1`, carried into the manifest
under the comment *"Skipped, and counted"*.

**Measured by executing the importer** on a Common Voice-shaped TSV of four rows, two unusable (one
empty `sentence`, one whitespace-only): **4 rows in, 2 items out, and the provenance note mentioned
neither a skip nor a count.** Corpus size is the denominator of §8.1's hours-of-coverage, so a
quietly smaller corpus reports a quietly wrong coverage figure with nothing naming the loss.

**The TSV is constructed, not downloaded**, and that is stated rather than glossed: there is no
Common Voice `ckb` release on this machine (M0.16 is BLOCKED). It is adequate because the defect is
in the *shape* of the code — a skip no artifact records — and the reproduction is by
execution, not by reading. It is weaker than this project's usual real-media standard, which is why
the finding was **deferred for six iterations** after it was first spotted rather than reported on
sight.

**Fixed** by counting `unusable` into the `Provenance` note, mirroring `unconfirmed`:
*"2 row(s) skipped as unusable — no validated sentence, or no clip path — so this corpus
is 2 of 4 rows read."* **Reported even at zero** (D-110's rule, and what the control test pins): a
line appearing only when something was skipped cannot be told from an import that does not count
skips at all. **The denominator is carried too**, because a count without a total says how many
were lost but not out of what.

**3/3 mutations, lint-clean, file restored byte-identical.** The third is the control's own target
— it keeps the counter and the total and only hides the line on a clean import, which is
exactly the version that looks correct in review.
`evidence/the-common-voice-import-shrank-the-corpus-in-silence.md`.

## D-189

**Adversarial pass 31 — M0.1's claim attacked six ways and held, and the pass's own first
harness reported it false.** Everything in this repository rests on *"the gate refuses a no-op
command instead of printing green"*: every DONE row, every `N/N mutations`, every "CI green" is an
assertion the gate made. It has been fooled twice — D-092 (`PY=true.exe`) and D-093 (a forged
`pytest` on PYTHONPATH, which also ratcheted the floor 1155 → 1200, so every honest run
afterwards would fail a bar the forgery invented).

**6/6 refused, floor unmoved at 1619.** Two defences, both doing their documented job: **exit 3**
from the interpreter probe (`PY=/usr/bin/true`, and the forged pytest — refused *by name*,
because the probe asks where the steps' programs came from), and **exit 5** from the override
refusal, which `${VAR+set}` catches even for an *empty* assignment, so `TEST_CMD=` is refused
rather than silently replaced by the default. A substituted `hawedit` package remains out of reach
and stays recorded as such, so 6/6 is not read as "unfoolable".

**The judgement worth recording is about the pass.** Its first harness built the environment as a
Python dict for `subprocess.run` and printed `*** M0.1's CLAIM IS FALSE ***`. **That was wrong.** On
Windows the constructed environment did not reach `bash` as intended: the overrides leaked into the
suite's own gate-invoking tests — all four "HELD" lines named
`test_nested_full_gate_refuses_instead_of_recursing`, a *test* failing rather than a *gate*
refusing — and the matched `VERIFY OK` came from somewhere other than a verdict. Run directly,
the identical attack gives exit 3 and a `REFUSED` banner with no `VERIFY OK` in the log at all.

Caught by reading *which line* the harness had matched instead of trusting its summary — the
same failure as the two `pgrep` false positives earlier in this session, where a pattern matched its
own command line. **Method for later passes: invoke the thing under attack the way an attacker
would, one shell, directly, and grep the raw log.** A harness that constructs the environment is a
second program that can be wrong, and when it is wrong it fails in whichever direction its author
expected. `evidence/adversarial-pass-31-the-gate-itself.md`.

## D-190

**A constant justified by a comment that is false of one of the four checkpoints it cites.**
`visual_index.py` stated as measured fact that *"all four §7 visual models ship
`do_sample_frames: true` with `fps: 2`, `min_frames: 4` and `temporal_patch_size: 2`"*, and
`video_input.py` repeats it. Read off the four `video_preprocessor_config.json` files on disk:

```
Qwen3-VL-Embedding-2B    fps 2  min_frames 4  temporal_patch_size 2
Qwen3-VL-Reranker-2B     fps 2  min_frames 4  temporal_patch_size 2
MCG-NJU/VideoChat3-4B    fps 2  min_frames 4  temporal_patch_size 1   <-
MCG-NJU/TimeLens2-4B     fps 2  min_frames 4  temporal_patch_size 2
```

"All four" is right about the count, `fps: 2` and `min_frames: 4` hold for all four, and
`temporal_patch_size: 2` holds for **three**.

**The constant stays 2 and nothing behaves differently — the justification was wrong, not the
number.** `TEMPORAL_PATCH_FRAMES` is the **strictest** of the declared sizes, not a shared
declaration, and that distinction is why it is correct: `extract_window_frames` extracts a window
**once** and D-140's `_FrameCache` hands the same files to the embedder *and* the reader
(`VideoChat3Reader` takes `read_frames` precisely so the frames a window was embedded from are the
frames it is read from). One extraction feeding patches of 1 and 2 has to satisfy the coarser. The
trim costs VideoChat3 at most one frame it would have accepted and saves Qwen from padding an odd
count by repeating the last frame — a frame never filmed, which is the defect D-060 exists to
prevent.

**Pinned so it cannot drift again — by three tests that run everywhere**, asserting against
`DECLARED_VIDEO_PREPROCESSORS` rather than reading the checkpoints (see the correction below; the
first version read the files behind a `skipif` and CI refused it): the rate and minimum must be the
single value every recorded checkpoint declares; `TEMPORAL_PATCH_FRAMES == max(recorded)` —
**`max`, not equality** — carrying its own control that the sizes are **not** all equal, since
a uniform set would make `max` indistinguishable from "what they all declare", which is exactly the
claim that was wrong; and every §7 model with a visual role must appear in the table, because
one missing from it drops out of the `max` silently.

**3/3 mutations, lint-clean, file restored byte-identical.** Before these tests, all three
constants could be set to a wrong value with the whole suite green — justified by a comment
and checked by nothing.

**The first version of this fix was pinned to the weights and CI refused it — correctly.** The
tests read the four config files directly behind a `skipif`; locally 1621 passed, on the runner
`1619 passed, 2 skipped` and `REFUSED: only 1619 tests passed against a floor of 1621 (2 skipped of
1621 collected)`, exit 6. **Main was red for one commit (5995d87).** The mechanism is D-095's: the
floor compares **passed**, never `collected`, because "the two differ by exactly the skips, which
is the case the ratchet exists to catch". A test that passes where the weights are and skips where
they are not cannot count toward a global floor — it raises the bar on the machine that has
them and fails on the machine that grades. This repo had **zero** skips before; the two I added
were the first and broke the invariant immediately.

**Redesigned better than what CI rejected:** the declarations moved out of prose into
`DECLARED_VIDEO_PREPROCESSORS`, a table in `visual_index.py` that three tests assert against on
**every** machine — the rate and minimum are the single declared value, `TEMPORAL_PATCH_FRAMES
== max(recorded)` with the not-all-equal control, and every §7 model with a visual role appears
in the table (a model missing from it drops out of the `max` silently, the same defect one level
up). The table was verified equal to all four configs on disk before committing; that check is a
**measurement in the evidence file rather than a test**, because the test that would perform it is
precisely the one CI cannot run — so the numbers are data the suite asserts against, carrying
the date and machine they were read on. **1622 passed, 0 skipped, floor 1622.**
`evidence/three-of-four-checkpoints-declare-what-the-comment-claimed-for-all-four.md`.

## D-191

**A refusal that named the state it had already created, found by sweeping every `raise` in the
credential store.** D-149's method — each refusal deleted whole by its AST span, one at a time,
whole suite each time, against a baseline verified green first — pointed at
`src/hawedit/credentials.py` because that module writes secrets to disk. **6 of 10 held, 4 did
not.** One of the four is `raise SystemExit(main())`, a `raise` by grammar and not a refusal;
counting it and then saying so is the difference between reporting the repository and reporting
the probe.

**The finding is bigger than the sweep's.** `restrict_to_owner` was called *after* the body was
written, so a failed narrowing left the plaintext key on disk at inherited permissions while
`main()` printed `✗ … Refusing to leave a credential at inherited permissions` and returned 2 —
the operator reads "nothing was stored". Measured on hawapc01 with a **real** `icacls` failure
(`getpass.getuser()` reads `USERNAME`, an unresolvable principal gives exit 1332, "No mapping
between account names and security IDs was done") in a directory granting `Everyone:(OI)(CI)F`:
95 bytes containing the key, readable by Everyone — **identically whether the refusal was present
or deleted.** The guard's only contribution was the exception.

**Why it was Windows-only.** The comment above `os.open` is correct on POSIX — a file cannot be
created wider than the mode passed to `O_CREAT`, so there is no window. On Windows that mode
argument carries only the read-only bit and the file inherits its directory's ACL, so everything
between the open and `restrict_to_owner` is a window there and nothing here. The key was written
inside it.

**Decision: the narrowing moves above the write, and stays above `os.ftruncate`.** Above the write
so a failure exposes an empty file; above the truncate for the reason the code already declines
`O_TRUNC` — a refusal after truncation destroys the previous credential on the way out and leaves
the operator with neither key. Re-measured against the same real failure: new key absent, previous
key intact, refusal raised; and the control, a real account, still writes and still comes out
`HAWAPC01\Wareen` alone with `icacls` rewriting the DACL under an open handle.

**`_IS_WINDOWS` is now a module constant** because `os.name != "nt"` made the `icacls` refusal a
branch the Linux runner can never execute — the guard protecting the machine that will hold the
real key was the one the grading machine could not reach. The test patches the constant rather
than skipping on POSIX, which is what `_O_NOFOLLOW` already does and what D-095's floor
(`passed`, never `collected`) exists to force. **Rejected: `pytest.mark.skipif(os.name != "nt")`**
— it is the exact commit shape the gate refused at 5995d87 with *"a skip condition is creeping"*,
and this repo still runs 0 skips.

**Lines 247 and 252 are the same defect from the other side.** `_O_NOFOLLOW` is 0 here, so the
pre-open check answers first and the kernel's `ELOOP` arm is unreachable on this host — while on
the POSIX runner it is the live path the symlink test drives. Unheld *here*, held *there*; now
held on both by supplying the kernel's answer rather than waiting for a privilege Windows will not
grant, which is what the symlink test one file over already does.

**Mutation audit 5/5**, file restored byte-identical, suite green after restore. Recorded honestly:
the fifth mutation (`_IS_WINDOWS = False`) is caught by four tests *on this host* and is a no-op on
the runner, where that is already the value.

**A filter lied again, and it was mine.** The first audit run died with `IndexError` hunting the
`N passed` line: `addopts` already carries `-q`, so a second `-q` makes it `-qq` and suppresses the
count entirely. The earlier sweep had printed a pytest docs URL as its "baseline: GREEN (…)" for
the same reason. Both harnesses now take green from the **exit code** and print a count only when
one exists. That is the fifth filter-over-raw-output mistake this session and the first one where
the harness was wrong in my favour rather than against me.
`evidence/the-refusal-named-the-state-it-had-already-created.md`.

## D-192

**Artifact identity is the bytes on disk, not a re-serialisation of the parsed object.**
`read_norm` decided whether a norm belonged to its raw by calling `read_raw(media_id).sha256()` —
parsing the file, walking it back through today's dataclasses, and hashing *that*. D-181 added one
optional `adapter` field to `AsrProvenance` on 2026-08-11, and from that moment every normalized
transcript ever written was rejected as stale.

**Measured on four real artifacts**, including the 38-minute `ZAR38MinTest.mp4` run: the stored
`.sha256` file, and the sha256 of the bytes on disk, are both `7912e7bd1d35…`; `RawTranscript
.sha256()` today returns `4748ac2a3e02…`. `verify_raw_integrity` **passed** on all four — the files
are byte-identical to what was published — while `read_norm` refused them as *"derived from raw
7912e7bd1d35… but the stored raw is 4748ac2a3e02…"*. Every particular of that message was wrong:
the norm was derived from that raw, and `4748ac…` hashes a file that has never existed. Its
prescribed remedy — re-run normalization — stamped the same unstable value again, so the next
added field would break it identically. **Nothing shipped wrong to a client**: the pipeline writes
and reads the norm inside one run, where the schema cannot change underneath it. What was lost is
every stored artifact — 35,185 characters of Kurdish and 6,104 word timings from the real run,
unreadable through the API that exists to read them.

**Decision: the digest of the raw *file* is the identity, in all four places that touch it.**
`write_raw` already computes and stores `sha256(raw.to_json().encode())`; `read_norm` compares
against `raw_digest(media_id)`; `normalize_transcript` takes `source_sha256`; the pipeline passes
`store.raw_digest(identifier)`, the same value `verify_raw_integrity` checked one line above. All
four artifacts read again after the change.

**`normalize_transcript`'s default stays `raw.sha256()`.** An in-memory transcript has no file, and
there the object hash is the only identity available. **Rejected: making the parameter required** —
it would touch eight call sites, six of them tests with no store at all, to protect the two that
have one.

**The guard lives in `write_norm`, not at the call site.** Every producer can forget the digest and
only one of them is in `src/`. It is invisible while a release is young — a raw written by today's
schema hashes the same either way — and fires exactly when it matters: a second run over a work
directory holding a raw from an earlier release. Refusing at write time beats storing a norm that
reads back as stale forever. `test_a_stale_normalized_transcript_is_detected` now asserts both
ends: the write refuses, and a norm that reaches the directory by other means is still refused at
read.

**Mutation audit 3/4, and the survivor is recorded rather than papered over.** "The pipeline stops
stamping the file digest" survives because for an artifact written by the running release
`raw.sha256()` and `raw_digest()` are the same number — which is exactly why the defect stayed
invisible for a day. It is observable only against a raw written by an earlier schema, which inside
the pipeline means a release boundary no unit test can stage. **Rejected: an
`inspect.getsource`-style assertion that the call passes `source_sha256`** — it would check the
spelling of a line rather than its effect. What the `write_norm` guard changes is the failure mode:
with the stamp forgotten the pipeline now stops loudly at the write instead of storing a norm every
later read rejects.

**Also rejected: calling `verify_raw_integrity` from inside `read_norm`.** It would name tampering
correctly instead of reporting it as staleness, but it is a separate concern from this defect, and
the pipeline already calls it one line before normalizing.
`evidence/adding-a-field-re-dated-every-transcript-ever-written.md`.

## D-193

**Adversarial pass 32 — the embedding reuse key did not cover which frames reach the model.**
`_EmbeddingCache`'s own docstring claimed reuse was verified *"on everything that changes the
vector"* and listed three keys: the window, the model id and revision, and the source digest.
`discover` consults the cache **before** extracting frames — that is where D-140's 95.1 ms/window
saving comes from — so the key must describe the pixels by describing the settings that make them,
and one was missing.

**Measured on `ZAR38MinTest.mp4` (82,446,418 bytes), real ffmpeg, real jpgs.** Window
`zar38:s2:w0`, 60,000–77,500 ms at 2 fps: `TEMPORAL_PATCH_FRAMES=2` yields **34** frames
(`387be9116d335d85…`), `=4` yields **32** (`51a2cbdf826a26b2…`), and every element of the key is
byte-identical across both. The cache would have served the 34-frame vector for the 32-frame
extraction and retrieval, rerank and the reader would all have worked from an embedding of footage
it was not describing. **The window's own `frame_count` does not cover it** — it records the
*planned* **35**, arithmetic over `duration_ms` and `fps` computed before ffmpeg ran, a number
neither extraction produced.

**This is reachable without anyone editing a constant.** D-190 defines `TEMPORAL_PATCH_FRAMES` as
`max()` over the §7 checkpoints' declared `temporal_patch_size`, so adding a checkpoint that
declares 4 moves it — and every cached vector on disk silently becomes a vector of frames the model
will no longer be shown.

**Decision: the trim goes in the record, read through the module that applies it**
(`video_input.TEMPORAL_PATCH_FRAMES`, not a re-import of `visual_index`'s). `load` compares the
whole record, so entries written before the key existed fail to match and re-embed once — the
behaviour the cache already documents. **Rejected: reading it from `visual_index`** — the two are
always equal in a real process, but the value that must be fingerprinted is the one that does the
trimming, and the mutation that hardcodes `2` (correct today, wrong in principle) is caught only
because the test pins where it is read from.

**`video_input.__all__` now declares the re-export.** Reading it from outside is an implicit
re-export, which this repo forbids: *"Module `hawedit.video_input` does not explicitly export
attribute `TEMPORAL_PATCH_FRAMES` [attr-defined]"*. **Rejected: silencing it with a type ignore** —
the binding genuinely is part of that module's contract now.

**The docstring is corrected rather than left aspirational.** It names what the key covers and
states what it does not: the ffmpeg invocation itself, where a change to the filters or output
quality would produce different pixels under an unchanged fingerprint. That is code rather than
data and is not fingerprinted anywhere in this repo's on-disk caches. Saying so beats a claim that
reads as total and is not — which is the defect this pass just found.

**Mutation audit 3/3, and the first run of it was worthless while reporting the same 3/3.** Every
mutation came back `[lint dirty]`: deleting the record entry leaves `video_input` imported and
unused, and `tests/test_gate.py` runs the real `verify.sh`, lint included — so three gate tests sat
in the CAUGHT lists having failed on the mutation's tidiness rather than on the guard. Re-run with
each mutation dropping the unused import, the first two are clean and fail by exactly the two tests
written for them. Pass 30's lesson from a new direction: **check which test failed, not that one
did.** The third mutation remains lint-dirty and is reported as such.

**The gate caught what a targeted run could not.** `pytest tests/test_visual_pipeline.py` passed on
a program mypy rejects; what surfaced it was this audit's *baseline* going red on four `test_gate
.py` tests, which invoke `scripts/verify.sh` as a subprocess. A per-file run is not a substitute for
the gate even when the change looks local to that file.
`evidence/adversarial-pass-32-the-reuse-key-did-not-cover-the-frames.md`.

## D-194

**A guard-revert sweep over the two modules that build the deliverable: 20 of 23 refusals held.**
D-149's method — every `raise` located by AST, deleted one at a time, whole suite each time,
against a baseline verified green first — pointed at `delivery.py` (the SRT/EDL/ASS/JSON a client
opens) and `render.py` (the MP4). `delivery.py` came back **12/12 held**, each by a test named for
the property. Worth recording as a null result: the sweep's value is as much in the modules it
clears as in the ones it does not.

**`render.py` had three refusals nothing would have missed**, and **no production code changed** —
all three were already there and already correct. What was missing was anything that would notice
their removal.

**The encode failure is the one that matters.** `if result.returncode != 0 or not output.exists()`
is the last check between ffmpeg and a client, and deleting it left the suite green. The
fall-through is not harmless: the next line probes `output` for its duration, so a failed encode
becomes whatever `probe_duration_ms` says about a file that may not be there. Reproduced with a
**real** ffmpeg failure rather than a mock — the output path is a directory, which is what a stale
run directory looks like, and `output.parent.mkdir` runs first and succeeds so this reaches the
encoder as a real fault would: exit **4294967283**, *"Error opening output …: Permission denied"*.
The test asserts ffmpeg's own words are in the message. **Rejected: matching only on "encode
failed"** — a generic message satisfies that and tells an operator nothing, and ffmpeg is the only
thing that knows why it stopped.

**The other two.** A source too small to crop — `1x1000`, `1000x1` and `2x2` all reduce to a zero
dimension once `yuv420p`'s even-number rounding is applied, and without the refusal that is an
ffmpeg error at encode time or a frame of nothing. And a frame rate of `0/0`, which is what ffprobe
reports for a stream whose rate it cannot determine: without the refusal the ratio is evaluated and
the caller gets `ZeroDivisionError` from inside a rate probe, one function further away than the
fault. ffprobe's answer is **supplied** rather than hunted for, the way the symlink tests supply the
kernel's — what is scarce is a file that provokes it, not the refusal under test.

**The control earned its place inside one edit.** `test_a_source_too_small_to_crop_is_refused`
asserts the fixture's own `640x360` still produces a filter; the first version passed the target
size positionally, where `crop_filter` takes `focus_x` and `focus_points`, and got
`TypeError: 'int' object is not iterable`. Every refusal in the loop still fired, because all three
degenerate sources raise *before* the focus-point branch — so the `pytest.raises` half alone would
have passed while calling the function wrongly. The scratch probe that measured these cases had the
same bug and printed clean output.

**Mutation audit 3/3 lint-clean, and the first run of it was not.** Deleting the whole `if` around
the encode refusal leaves `result` unused, ruff says so, and `tests/test_gate.py` runs the real
`verify.sh` — so three gate tests failed alongside the genuine defender. The mutation now replaces
only the `raise`, which is the sweep's own form, and each guard is caught by exactly the one test
written for it. **The audit harness now prints `[LINT DIRTY — the gate tests fail for free]`**
rather than a quiet marker: this is the third time this session a lint-dirty mutation has dressed
itself up as a held guard, and a marker I skim past is not a check.
`evidence/three-refusals-in-the-renderer-that-nothing-would-miss.md`.

## D-195

**`assert_renderable` — the gate `render_clip` calls before starting an encoder — was half
covered.** A guard-revert sweep over `clip.py`, the module whose dict *is* the §5 client sidecar:
every `raise` located by AST, deleted one at a time, whole suite each time, against a baseline
verified green first. **11 of 15 held.** The four that did not include both of the judge's halves of
that gate:

```
if self.qc is None:                                   held, by 11 tests
if not (self.qc.auto_pass or self.qc.human_reviewed): held, by 3
if self.editorial is None:                            HELD BY NOTHING
if self.output is None:                               HELD BY NOTHING
```

Its docstring says *"§8.3 requires this on every shipped clip"*. A clip with no editorial block has
no meaning-fidelity and no misleading-edit score — the number §8.2 calls the one that matters for a
media organisation — and one with no output block has no title, crop target or caption style to
render with. Either could have reached ffmpeg if the check were refactored away, suite green. The
shape worth noticing: the QC guards written under "audit finding #3" got tests, and the two added
beside them in the same function did not.

The other two were `Output.durations` having to be positive seconds (a zero is not a short clip, it
is `-t 0` and an empty file) and `Qc.flags` having to be a tuple of non-empty strings — whose
`from_dict` sibling **is** held, so the JSON door was covered and the constructor was not.

**No production code changed.** All four refusals were already correct; only the tests were missing.

**Decision: the sweep harness now reports a third outcome, `GATE`.** A mutation whose only failures
are `test_gate.py`'s four subprocess tests was caught by the real `verify.sh`'s lint or typecheck
step, not by anything behavioural — which happened three times earlier this session and read as
coverage each time. `clip.py` came back **gate-only 0**, so its 11 held are held by named tests.
**Rejected: keeping the two-outcome HELD/UNHELD report** — it cannot distinguish a guard a test
defends from a guard ruff defends, and I have already been fooled by that distinction.

**Each new test asserts the precondition of the guard above it.** The unjudged-clip test asserts
`qc.auto_pass` first, so it cannot pass on the QC refusal one line earlier; the output-block test
asserts `editorial is not None` for the same reason. Without those, both tests would pass against a
`assert_renderable` that refuses for the wrong reason — which is the defect one line up.

**One case in the flags test is worth naming:** `flags="not a tuple at all"` is refused by the
`isinstance(self.flags, tuple)` half specifically. Without it, `any(...)` iterates the string
**character by character** and accepts it, because every character of a non-empty string is itself a
non-empty string.

**Mutation audit 4/4 lint-clean**, each guard caught by exactly the one test written for it and by no
gate test, file restored byte-identical. Every module that builds or ships the deliverable —
`delivery.py` 12/12, `credentials.py` 6/10, `render.py` 8/11, `clip.py` 11/15 — has now been swept
once.
`evidence/the-gate-before-the-encoder-had-two-refusals-nothing-held.md`.

## D-196

**`Qc.to_dict` could stop emitting `flags` and `human_reviewed` with the whole suite green.** The
review reasons, and whether a human looked at the clip at all — the field §2's "human QC gate before
output, always" is recorded in. A sidecar that stopped carrying it would read back `False` for every
clip a human had in fact approved.

**Why the existing round-trip could not see it.** `clip.py` pairs `to_dict` with `from_dict` for
every block and `test_the_clip_round_trips_through_json` has always asserted
`from_dict(to_dict(x)) == x`. That catches a dropped field only when its value differs from what
`from_dict` supplies in its absence, and `a_clip()` leaves four optional fields at exactly their
defaults. Measured by deleting each emitted key and rebuilding: `Editorial.payoff_at_ms` (None),
`Output.hashtags_ckb` ([]), `Qc.flags` ([]) and `Qc.human_reviewed` (False) all rebuilt identically.

**This is the third instance of one defect.** D-101 (`Clip.to_dict` hardcoding
`DiscoveryPath.VERBAL.value`, five test files green because the fixture was verbal) and D-181
(`AsrProvenance.adapter` missing from the hand-enumerated dict) were each found by hand, one field at
a time. Two of the four here were held elsewhere — D-033's projection test asserts `payoff_at_ms` and
`hashtags_ckb` — which is luck rather than design. The two `Qc` fields were held by nothing.

**Decision: a fixture whose optional fields are all non-default, run through the round-trip that
already existed.** `a_fully_populated_clip()` sets every optional field in all five blocks away from
its default, whole-clip and per-block so a failure names which block lost the field. A second test
asserts no field in that fixture still carries its default — without it, a later edit could return
the fixture to `a_clip()`'s values and the round-trip would go green by **losing** coverage rather
than gaining it.

**Rejected, after building it and proving it useless: a "no emitted key is redundant" property.**
Delete each emitted key in turn and require the round-trip to notice. It passed, it read well, and it
**could not detect the defect it named** — it iterated the keys `to_dict` *emits*, so a key that
stopped being emitted was never examined. The mutation audit reported **3/5**: the two `Qc` mutations
survived outright, and the two that were caught named a pre-existing test rather than the new one,
which appeared in exactly one row — the mutation against its own fixture. It was guarding itself and
nothing else. The rewrite is 5/5. **A cleverer test that measures nothing is worse than the obvious
one, and only the audit could tell them apart.**

**The fifth mutation attacks the test rather than the code** — returning the fixture to the defaults —
because that is the failure mode this whole entry is about. It is now caught too.

**Process, twice in two iterations:** `pytest tests/test_clip.py` passed 40/40 on a file ruff and
mypy both reject (`Any` unimported, then `union-attr` because `clip.editorial` is `Editorial | None`).
Both surfaced only as the audit's **baseline** going red on `test_gate.py`'s four subprocess tests —
15 minutes to learn what `ruff check` and `mypy` answer in twenty seconds. **The habit is now: lint
and typecheck the whole tree before launching any audit.**
`evidence/whether-a-human-reviewed-the-clip-could-leave-the-sidecar-in-silence.md`.

## D-197

**§3 Stage 1 never said what the validator's answer does to the canonical text. It is evidence,
never a replacement.**

BLUEPRINT.md:128 says *"Route the bottom quartile, and any segment where LLM-7B and CTC-3B disagree
materially, to the validator"* — and stops. There is no rule for whether the validator's reading
replaces the canonical text, is merged with it, or is merely recorded. `select_for_validation` is
implemented and tested and has no consumer, so nothing implements any of the three. The gap was
found while answering Hawa's question "why are we using qwen asr?".

**The rule.** The validator's reading may flag a span. It may never rewrite one.

1. **It cannot become canonical text.** Kurdish invariant #1 makes `transcript.raw.json` *exactly as
   canonical ASR emitted*, write-once, digest-verified. A validator reading written into it would
   make "canonical" mean whichever model was written there last.
2. **It cannot occupy the canonical slot.** `AsrProvenance` role-checks `canonical` against
   `canonical_asr` and `validated_by` against `asr_validator`, so §7's roles are the enforcement,
   not a convention. Measured: the validator in `canonical`, the emissions model in `canonical`, and
   the canonical model validating *itself* are all `WrongRole` today; only §7's own pairing is
   accepted. Now pinned by four tests, three refusals and the control.
3. **Disagreement routes to a human, not to a merge.** §2 puts a human QC gate before output,
   always. A span where the validator disagrees is a span with a `qc.flags` entry, which is a
   mechanism that already exists and already blocks rendering (`assert_renderable`, D-195).

**Why one-directional.** Hawa's assessment, recorded as an assessment: the Sorani checkpoint is
weaker on Kurdish than the champion LoRA they trained. **Nothing in this repo measures that** — no
CER, no WER, no side-by-side on Kurdish audio — and the labelled set that could is BLOCKED #1, so
this is judgement, not a number, and is recorded as judgement. But the rule follows either way: a
second opinion that can overwrite is only safe if it is *better*, and escalation sends it precisely
the hardest spans, where being wrong costs most. Evidence-only is correct whether or not the
assessment holds, which is why it does not wait on BLOCKED #1.

**Precedent, in this repo.** M6.1 settled the same question for TimeLens2: *"intervals as evidence,
never as cuts"*. Same shape, one stage over.

**Rejected: dropping the validator from §7.** Hawa chose to keep it and specify the rule first
(2026-08-12). It is a frozen-BLUEPRINT model and removing it would be a divergence; keeping it
costs nothing while it cannot load.

**Still missing before it can run, and not decided here:** where a validator reading is *stored*.
`validated_by` records that a validator read a span and which one — not what it said. Adding a field
for the reading is only worth doing against a loader that exists, which is BLOCKED #16, and D-097
measured what building against a stub costs.

**Audit and process, recorded with D-197.** Mutation audit **3/3**, each mutation loosening one
`resolve_role` call to the `ASR_ROLES` union that already exists in the registry and reads like the
natural refactor, each carrying the import it needs so it is a real program rather than a
`NameError`. Run **three times** because the first two overlapped other background work; reported
only because all three agree exactly, file restored byte-identical each time.

**A sweep over `gemini.py` was killed mid-mutation and left the file on disk with a Vertex location
check replaced by `pass`.** Caught by a routine `git status` before staging — BLOCKED #12's rule
earning its keep — and restored from HEAD. I then compounded it by starting a second audit while
that sweep still ran: each mutated its own file while the other ran the whole suite, contaminating
results in both directions. **The gemini sweep's output is discarded entirely** rather than reported
with a caveat, and that module remains unswept.

**Root cause, three repetitions of one mistake:** an empty output file plus a momentary gap in `ps`
is not evidence a background job has died. Output is block-buffered until exit, and `ps` misses the
gaps between subprocess spawns. **The completion notification is the only reliable signal** — the
same class as this session's two `pgrep` false positives, where a pattern matched its own command
line. The sweep harness now takes a lock, refuses to start while another holds it, and restores its
target on normal exit, on exception and on SIGTERM.
`evidence/the-validators-answer-had-no-specified-effect.md`.

## D-198

**The CODYSTEM operating rules governed this repository from another repository, which means
they governed nothing.** `AGENTS.md`, the Research → Plan → Implement skills, the PreToolUse
guard and the Stop-hook gate all lived in the Codystem checkout. Agent context files are
discovered by walking *up* from the working directory, so opening an editor at this repo loaded
none of them — and opening one at the parent of both loads a sibling's `CLAUDE.md` never. The
rules were real, and they applied to a different directory. This commit moves the harness into
this repository, where the working directory is the repository the rules are about.

**The gate did not change and is not wrapped.** `scripts/verify.sh` remains the single source of
"does it work", still refusing overridden steps, still probing that its interpreter can import
this project, still grading `.gate/last-test-run.xml` rather than trusting an exit code. The
harness added around it only decides *when* it runs and *who may edit what*.

**The Stop hook needed an exit-code translation, and this is the interesting half.** Claude
Code's hook contract gives exit 2 one meaning — block, and hand stderr back to the agent —
while every other non-zero code is a notice shown to the human. `verify.sh` already spends 2 on
"no interpreter in `.venv`". Wired up directly, as the Codystem original does against a gate
whose codes differ, the two land exactly backwards: **a red test suite (exit 1) would be a
notice the agent never reads and can stop straight through, while a checkout that has simply not
run `scripts/setup.sh` yet would block an agent on a condition nothing had told it about.** A
gate that fails open on the failure it exists to catch is worse than no gate, because the hook
in `settings.json` reads as protection either way. `scripts/claude-stop-verify.sh` maps
1/3/5/unknown → block and 2/4 → notice, and honours `stop_hook_active` so a red gate cannot turn
into an agent that is unable to stop at all.

**`.gate/` is hard-protected, with no escape.** D-093 moved the evidence out of the exit code
and into the test report because a run that executed nothing was printing VERIFY OK. An agent
able to write `.gate/last-test-run.xml` by hand puts that forgery straight back, one redirect at
a time — so the guard blocks writes to it as a path *and* scans shell commands for redirects,
`tee`, `cp`, `mv`, `dd` and `install` aimed at it. `scripts/test-count.floor` and
`src/hawedit/gate.py` are protected for the same reason, one layer up.

**The guard reads its payload with jq, or with Python.** The Codystem original requires jq.
This project requires a Python 3.11+ and does not require jq, and both `setup.sh` and
`verify.sh` go to real lengths to work on the Windows box §6 names. A guard absent on one of two
supported platforms while still appearing in the settings file is the quiet green this repo is
written against. With neither reader present it warns on stderr and allows the call — failing
closed would block every tool call for a reason no message would connect back to this file.

**Editing the harness is allowed, and made visible rather than prevented.** The gate, the guard,
its test, the ledger flipper, the hook config, CI, the test floor, `gate.py`, and the golden and
fixture corpora are all editable once `.codystem-allow-self-edit` exists — a file that shows up
in `git status` and in the diff. Improving a harness is real work; doing it silently is not.

**What was measured, and by what.** `shellcheck scripts/*.sh` clean across all eleven scripts,
which is the command CI already runs. `scripts/guard-test.sh` — added here and wired into
`gate.yml` before the install step, since it needs no venv — passes **56 checks**: every
hard-protected path in both relative and absolute form, both `models/` files that must stay
editable, the enforcement surface with and without the sentinel, the dangerous-command set,
six shell routes to a protected path, six ordinary commands that must not be blocked, and three
malformed payloads that must not wedge the agent. The jq-absent path was exercised by running
the guard with a PATH containing no jq; the neither-reader path by a PATH with neither. The
Stop hook's mapping was exercised against a stub gate returning each of 0,1,2,3,4,5,9.

**What was NOT measured, stated because this file does not accept a green that was not run.**
`bash scripts/verify.sh` has **not** been run against this commit. The environment the harness
was assembled in has no `.venv` and no network budget for a ~2 GB torch install, so the Python
gate is unverified here and CI is the first thing that will run it. Nothing in this commit
touches `src/`, `tests/`, `pyproject.toml` or the gate's steps, and no pytest test was added —
deliberately, so `scripts/test-count.floor` stays untouched and the final CI step that fails a
run which ratcheted it keeps its meaning. The guard's coverage is bash-level only; a Python
test of it would have moved that floor and is left as separate work.

**Honest limit, unchanged from the original.** An unrestricted Bash tool runs arbitrary code, so
the command scanning is a tripwire for obvious cases and not a security boundary. The exact
boundary is the `file_path` check plus filesystem permissions. The real gate is
`.github/workflows/gate.yml` on a clean runner, re-running from committed source with no shell
of the agent's — which is why the local hooks can afford to be helpful rather than airtight.

## D-199

**The two CODYSTEM scripts that decide what "done" means had no automated test, and the ledger
flipper had never once run.** D-198 recorded the first half deliberately — "a Python test of it
would have moved that floor and is left as separate work" — because ratcheting
`scripts/test-count.floor` in a commit whose gate had never run would have cost the final CI step
its meaning. This is that separate work. The second half was not known: `scripts/update-ledger.sh`
computes its target as `specs/<feature>/tasks.md`, `specs/` held only `constitution.md`, and the
script refuses a missing ledger before it does anything else. It had therefore refused every
invocation ever made of it, which means AGENTS.md's rule that only the flipper may flip a row was
true the way a rule about an empty room is true. The 33 DONE rows in `PROGRESS.md` are a different
ledger, hand-maintained, and no script wrote them.

**What the tests do.** Sixteen of them, in `tests/test_harness_scripts.py`. Both scripts locate
the repository by walking up from their own path, so copying one into a tmpdir makes that tmpdir
its whole world; each test runs against a stub gate there and never the real one. That keeps the
suite at roughly a second instead of the gate's two and a half minutes, keeps
`.gate/last-test-run.xml` and the committed floor untouched while a second session shares this
checkout (BLOCKED #12), and lets the stub record *that it was invoked* — which is how "this
refusal fires before the gate" became an assertion instead of a reading of the source.

**A stub gate is not the forgery D-092 and D-093 closed.** Those refused a fake `pytest` on
`PYTHONPATH` and an interpreter override that replaced every step including the one grading the
others — fakes of the gate's own tools, standing in for the thing under test. Neither script here
is the gate. The Stop wrapper's entire job is translating an exit code it did not produce, and
enumerating the codes it must translate requires producing them; D-198 exercised exactly this by
hand against a stub returning 0,1,2,3,4,5,9, and this commits that exercise rather than leaving it
a sentence. The flipper's refusals are asserted never to reach a gate at all.

**What remains structurally untestable from pytest, stated because this file does not accept a
green that was not run.** Everything below the flipper's invocation of the gate: the citation
check against the report, the awk flip, and the provenance line. Reaching them needs the gate to
exit 0, but pytest runs underneath that same gate, which exports a depth variable and refuses a
nested full run with exit 4 — so the inner call cannot return 0 by construction, not by accident.
The only honest proof is running the real script by hand, which this commit also does: the three
rows in `specs/harness-integrity/tasks.md` were flipped by `scripts/update-ledger.sh` itself, each
after its own green gate, with `specs/harness-integrity/ledger.log` carrying one provenance line
per flip. Those are the first successful executions of that script in this repository.

**A defect found while writing the prefix test, reported and not fixed here.** The flipper
constrains a task id to `[A-Za-z0-9_.-]+` and then interpolates it into a `grep -E` pattern. A dot
is legal in that set and is also a regex metacharacter, so the task id `T.` passes validation and
then matches the row `T1`. `T-` is harmless and `T10` correctly does not match `T1`, so the
anchoring is right and only the dot leaks. Fixing it means editing an enforcement script, which
was not in this feature's approved plan; it is recorded here rather than absorbed silently, and
the plan for it belongs in its own spec with its own row.

**Measured, on this machine only.** Windows 11, Python 3.11.15, pytest 8.3.4, in this checkout:
the suite went from 1643 to 1659 collected, all passing, none skipped; the gate ran green three
times at 155.41 s, 142.94 s and 153.81 s. The floor was ratcheted by the gate, not by hand, and is
committed alongside the tests so that CI's final step — which fails a run that ratcheted it — keeps
saying what it was built to say. No CI run has yet seen any of this; a local green cannot speak
for a clean runner, and until that check is green nothing here is done.

---

## D-200

**The licence gate ran before the merge, and found the real blocker was not a licence.**

Task T0 of `specs/production-hardening/plan.md`, promoted ahead of the merge by Hawa on
2026-08-14 for the reason the ordering exists: finding a NonCommercial dependency after it is
already in the tree and the history is the failure D-002's hard reject is meant to prevent.

**Scope.** Every runtime dependency `origin/codex/production-readiness-20260809` adds or
re-pins relative to this branch. D-002's own table covers only `klpt`, `chunspell`, `pytest`,
`ruff` and `mypy`; D-024 covers the Stage 0 media stack. Neither covers the pins below, so an
inline comment in `pyproject.toml` was the only claim on record, and a comment is a claim rather
than a reading.

**Method, D-002's.** Licence read from installed wheel metadata, never from a README or from the
pyproject comment being checked. Two of them required `License-Expression:` rather than the
legacy `License:` field, which is why a naive `grep '^License:'` reported nothing for the two
largest dependencies in the project.

| Dependency | Version read | Licence, as the metadata states it | Verdict |
|---|---|---|---|
| `torch` | 2.13.0+cu130 | `Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT` | ACCEPT |
| `pillow` | 12.3.0 | `MIT-CMU` | ACCEPT |
| `torchaudio` | 2.11.0+cpu | BSD (OSI classifier) | ACCEPT |
| `torchvision` | 0.28.0+cu130 | BSD | ACCEPT |
| `accelerate` | 1.14.0 | Apache | ACCEPT |
| `fonttools` | 4.55.3 | MIT | ACCEPT |
| `huggingface-hub` | 0.36.2 | Apache | ACCEPT |

**No NonCommercial term appears in any of them. The gate is clear for these seven.**

Two readings are weaker than they look and are recorded as such rather than rounded up.
`torch`'s licence is a **conjunction of six**, not the "BSD-3-Clause" its pyproject comment
claims; the comment understates it. And the version installed here is 2.13.0, while readiness
pins `torch==2.8.0` and `torchaudio==2.8.0` for non-Windows — so this is a reading of a
neighbouring version, not of the pinned one. Licences rarely change across a minor, but "rarely"
is not "did not", and D-002's whole point is reading rather than assuming.

**Four could not be read and are therefore not cleared:** `peft==0.19.1`, `fairseq2==0.6`,
`qwen-asr==0.0.6` and `google-auth==2.56.3`. None is installed in the host venv — the first three
live only in the WSL2 runtime `hawedit-asr-setup` provisions, and `peft` is this branch's
dependency rather than readiness's, reached only through `wsl_setup.py`'s bootstrap. They are
listed in `BLOCKED.md` rather than waved through. **T0 is not complete while they stand.**

**What the audit found instead, and it blocks more than a licence would.**

The merge-base tops out at `D-154`. Both branches then assigned D-numbers independently, so
`D-155` through `D-191` — **thirty-seven numbers** — name a different decision on each side.
Concretely, on this branch `D-165` is the SRT cue-ordering refusal, `D-171` is deriving
`PipelineRun.skipped()` from `fields(self)`, `D-181` is the fine-tuned decoder's adapter
provenance and `D-182` is the SV6D span parse; on readiness those same four numbers are a
scene-window filesystem identity, a semantic-equivalence join, a prerequisite diagnostic and a
future-guard binding.

This is not cosmetic. AGENTS.md's grounding rules require citing `DECISIONS.md` by D-number when
a choice was already settled, and after the merge every such citation in code comments, test
docstrings and commit messages across both branches is ambiguous over a 37-number range. Worse,
all four numbers quoted above are cited by `plan.md`'s own preservation list — the document
whose entire purpose is to stop the merge losing those decisions.

**Decision.** The colliding ADRs on the **incoming** branch are renumbered to `D-201` and up as
part of T13, and its in-code citations rewritten with them. The merge direction is
readiness → HEAD, so HEAD is the base and its numbering is what the preserved code and the
approved plan already cite; renumbering the incoming side is the mechanical, greppable change
and leaves no citation on this branch stale. The cost is honest and stated: it touches comments
across readiness's 254 changed files, and a missed one is a citation pointing at the wrong
decision rather than at none, which is the harder failure to notice.

`plan.md` gains T0b for the renumber, and it blocks T13 rather than the merge itself.

**Blueprint ref:** §7 · **Type:** dependency + licence check, and a merge hazard

---

## D-201

**BLOCKED #23 is closed: all five remaining licences read, and a second wrong comment found.**

D-200 cleared seven dependencies from installed wheel metadata and listed four it could not
read, because `peft`, `fairseq2` and `qwen-asr` install only inside the WSL2 runtime the
provisioner builds and `google-auth` was simply absent from this venv.

Hawa approved provisioning WSL and installing the `[cloud]` extra to read them. That is not what
happened, for two reasons, and the substitute is stronger rather than weaker.

**Why the approved route was not taken.** `pip install` writes into `.venv/Lib/site-packages/`,
and AGENTS.md lists `.venv/**` as a hard boundary with no sentinel escape. The PreToolUse guard
refused the command, correctly — this was not a false positive, and reshaping the command until
it passed would have been the bypass the guard exists to prevent. `scripts/setup.sh` installs
only `.[dev,media]`, so the sanctioned route does not reach `[cloud]` either, and editing it to
add one would push a dependency onto every fresh clone to settle an audit question.

**What was done instead.** The licences were read from the published wheel metadata on the index
itself, which is what D-002 specifies — its own worked example is
`klpt-0.1.7-py3-none-any.whl → METADATA`. Reading the index serves the same metadata the wheel
carries, and it does something installing cannot: it reads **the exact pinned version**. D-200
had to record `torch` as a reading of 2.13.0 against a pin of 2.8.0, and every reading below is
of the pin itself.

| Dependency | Version read | `info.license` | Classifier | Verdict |
|---|---|---|---|---|
| `peft` | 0.19.1 | `Apache` | `License :: OSI Approved :: Apache Software License` | ACCEPT |
| `google-auth` | 2.56.3 | `Apache 2.0` | none | ACCEPT |
| `fairseq2` | 0.6 | **`MIT`** | `License :: OSI Approved :: MIT License` | ACCEPT |
| `fairseq2n` | 0.6 | `MIT` | `License :: OSI Approved :: MIT License` | ACCEPT |
| `qwen-asr` | 0.0.6 | `Apache-2.0` | none | ACCEPT |

`fairseq2n` is not named in any pyproject; it is audited because `fairseq2` requires it, it ships
the native code, and D-002 set that precedent by auditing `chunspell` as a `klpt` dependency.

**No NonCommercial term in any of the twelve dependencies now audited. The gate is clear and the
merge is unblocked on licence grounds.**

**The finding worth keeping.** `pyproject.toml` annotates `fairseq2==0.6` as `BSD-3-Clause`. The
published metadata says `MIT`. Both are permissive so nothing is rejected, but this is the second
comment this audit has caught misstating a licence — D-200 found `torch` annotated
`BSD-3-Clause` where the metadata is a conjunction of six terms — and D-024 already records a
PyPI classifier for `scenedetect` that is flatly wrong in the other direction.

Three independent wrong readings, in a project whose gate treats one licence class as a hard
reject. The rule D-002 stated as method is now stated as a finding: **a licence annotation
beside a pin is a claim, and the only reading that counts is the distribution's own metadata at
the pinned version.** The comments are left in place and corrected during the merge rather than
edited here, because `pyproject.toml` is a conflicted path and T4 owns it.

**Blueprint ref:** §7 · **Type:** licence check · **Closes:** `BLOCKED.md` #23 · **Unblocks:** T1

---

> **The 37 ADRs below arrived with the readiness integration; 37 were
> renumbered on merge (D-200, task T0b).** The merge-base tops out at D-154 and both branches
> counted on from there independently, so D-155..D-191 each already named a
> different decision here. They were remapped to D-202..D-238.
> Citations *within* these entries moved with them; citations of shared history are untouched.

## D-202 - An operational Stage 0 refusal is still a pipeline run

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

## D-203 - One unreadable Path B survivor does not erase the readable survivors

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

## D-204 - Reproducible bytes must still identify HawEdit

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

## D-205 - Stage 4 promotion and billing boundaries need exact controls

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
used that identifier, so the semantic integration is recorded here as D-205.

`evidence/adversarial-pass-15-2026-08-09.md`.

## D-206 - Pipeline completeness needs a real complete-run control

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
identifier, so this semantic integration is D-206.

`evidence/adversarial-pass-16-2026-08-09.md`.

## D-207 - Unmeasured benchmark aggregates remain None

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
already used that identifier, so this semantic integration is D-207.

`evidence/adversarial-pass-17-2026-08-09.md`.

## D-208 - Alignment accuracy must reach the benchmark report

Following D-207's audit of aggregate benchmark values exposed a larger omission: `_score_item`
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
identifier, so the integration is D-208.

`evidence/section-8-1s-last-metric-never-reached-the-report.md`.

## D-209 - Stage 0 reuse is content-bound and atomically published

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
so the semantic integration is D-209.

`evidence/two-thirds-of-stage-0-redone-on-every-run.md`.

## D-210 - Font coverage must include normalized Kurdish and run at the burn

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
already used on this branch, so the semantic integration is D-210.

`evidence/adversarial-pass-18-2026-08-10.md`.

## D-211 - BM25 retrieval documents are sentence windows, not the episode

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
uses that number, so this integration is D-211.

`evidence/adversarial-pass-19-2026-08-10.md`.

## D-212 - A scene-window identity is a filesystem identity at its type boundary

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

## D-213 - A rewritable normalized transcript must still publish atomically and content-bound

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

## D-214 - The transcript store directory is a bound security boundary

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

## D-215 - Stage 2 resumes only exact, pinned per-window embeddings

The composed visual path rebuilt every scene embedding on every run. On the real 38-minute file
that path plans hundreds of windows, so a late failure discarded the most expensive completed
work even though each vector is independently reusable. Upstream measured the defect as D-140;
that number is already used on this branch, so the semantic integration is D-215.

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

## D-216 - Help names the command that can actually be invoked

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

## D-217 - The README must agree with the live quality ledger and its CLI API

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

## D-218 - Join main only after semantic equivalence, preserving the verified tree

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

## D-239 - Production releases are pre-tagged, draft-verified, immutable, and forward-only

The attestation workflow had an authenticated four-file artifact but no durable publication
identity. Publishing every accepted `main` commit would make the unchanged `0.1.0` project version
ambiguous; allowing the workflow to create a missing tag would also turn a CI event into an
implicit release decision.

Production intent is therefore a pre-existing strict `vMAJOR.MINOR.PATCH` tag derived exactly from
the wheel/provenance version. It must resolve to the exact accepted main SHA. No tag means the
workflow keeps its attested Actions artifact and exits without a public release; an operator may
create the approved tag and rerun that same release workflow event. The publisher is a fresh
no-checkout job with only `contents: write` and attestation-read authority. It verifies the exact
signer/source policy, creates a draft with four explicit assets, downloads and byte-compares the
draft, then publishes. Repository-level immutable releases were enabled before any tag existed.

Rejected auto-tagging: it collapses version approval into CI and would try to reuse `v0.1.0` on
later main commits. Rejected direct public upload: GitHub's own immutable-release guidance stages
all assets on a draft before publication. Rejected delete-and-retry or clobber: production history
is an audit record. Operators must never move, delete, or reuse a published tag; rollback is a new
patch release that records the superseded version.

The automation and repository setting close the policy/code gap, not live acceptance. M3.7 stays
PARTIAL until an approved exact tag produces an immutable release URL whose downloaded assets and
attestations verify.

`evidence/versioned-immutable-release.md`.

## D-237 - Adapt main's audit correction to the atomic delivery publisher

Protected main corrected an audit statement that contradicted its flat-file recovery guard: an
abandoned flat artifact set was repairable there. Readiness no longer has that publication model.
It writes into a unique hidden directory and publishes the exact five-file set with one no-replace
directory rename. A crashed private attempt is nonblocking; any visible final namespace or legacy
flat artifact is refused rather than overwritten.

The semantic import therefore preserves main's intent instead of its obsolete sentence. One
regression executes both current guard outcomes before asserting the audit's atomic-delivery text.
A second derives every root Markdown document and refuses any `D-NNN` citation absent from the
decision register. This avoids the two failures main identified without weakening the newer
publisher or colliding with main's unrelated D-154 number.

`evidence/main-delivery-audit-adaptation-2026-08-10.md`.

## D-238 - Join main's delivery-audit history without replaying the flat publisher

The adapted first parent `e8a411edd2da296dec4a2f6f87f8dbfce7fc9e3b` passed the focused
claims/pipeline suite before the join. Merge `5a9099abe6d2ff7ac3342c291bd27695f9fac987`
records protected-main parent `5eba372931eb6aa97edfca70cce6fbcc0718d8e3`. Both the merge and
first parent have tree `ef2a73250462f8835b5d2a65f617753bb73ebd7c`, proving that the join
added ancestry without replacing the newer atomic publisher or its adapted audit tests.

Tree equality is not runtime evidence. The canonical gate must pass again at the documented tip,
and only that post-join result is promotion evidence.

`evidence/main-delivery-audit-merge-2026-08-10.md`.

## D-235 - An impossible live smoke refuses before confirmation and billing

The documented live check omitted `--video`, made its billed Path A calls and only then refused
pixel-grounded Stage 4. Video presence and file existence are now checked immediately after
credential presence, before the estimate, confirmation prompt, model construction or transport;
the refusal is exit 2 because nothing ran. Tests prove no billed boundary or confirmation is
reached, and a legal existing-video control must reach the billed boundary.

The built-in timed sample lasts 13 seconds and no matching video ships. The unrelated 4.162-second
fixture cannot honestly supply later pixels, so `BLOCKED.md` #19 requests a real recording. The
text is not shortened to fit another clip and synthetic pixels are not used to make Stage 4 appear
accepted.

`evidence/smoke-video-preflight-2026-08-10.md`.

The source change rotates the receipt/VEX identity to `df74ba00dcae757e…`. The exact WSL runtime
was reprovisioned and the live gate accepted all 12 audit findings against 12 reviewed
dispositions with three authenticated assets (43,546,500,168 bytes) and two CUDA devices; this is
affected/mitigated evidence, not a claim of zero vulnerabilities.

## D-236 - Judge frames carry the requested sampling cadence, not stretched time

When ffmpeg returned fewer frames because the source ended before an overlong candidate span,
timestamps were derived from `duration / frames_returned`. That stretched surviving images across
moments the video never had. Timestamps now use the cadence given to ffmpeg,
`duration / requested_count`, at bucket centres. Real-media tests include a 13-second request over
the 4.162-second fixture and require genuine partial JPEG output with no stamp past source end.

Readiness already owns a unique private extraction directory per call, so prior-run JPEGs cannot
enter enumeration; main's shared-directory stale refusal is not replayed. This change rotates the
receipt/VEX source identity again and requires new live acceptance.

`evidence/keyframe-timestamp-cadence-2026-08-10.md`.

The rotated `59a1e500…` WSL receipt and live VEX gate are accepted: 140 packages, two GPUs, three
authenticated assets totaling 43,546,500,168 bytes, and 12/12 explicit dispositions. This records
affected/mitigated state; it does not re-label findings as absent.

## D-230 - Hold Kurdish invariant #3 at every Stage 2 query-reading model

Protected main removed query normalization independently from the Qwen embedder and reranker. Both
mutations left its full gate green: the score remained in range, the embedding remained a vector,
and existing calls used already-normalized Sorani. Production was correct; the suite never
observed what either processor actually read.

The shared stub processor now records complete conversations. One Arabic-keyboard query carries
kaf/yeh collisions, a ZWNJ-heh fold and Arabic-Indic digits. Each adapter must send the §4.1
normalized form, omit every raw codepoint and preserve an already-normalized query unchanged. An
introspection contract binds every production class with a query-taking method to the driver table,
so another adapter cannot inherit invariant #3 only by assumption.

Rejected checking the returned vector or score: a different alphabet changes relevance slightly,
not the return type or range. Rejected normalizing only at the caller: the adapters are public
model-input boundaries and already own the correct implementation. The focused visual slice passes
95/95 without changing production code.

`evidence/stage2-query-normalization-2026-08-10.md`.

## D-231 - Join main after adapting its Stage 2 invariant test to the newer loaders

Protected main `ba2a445` contained the D-230 finding and tests but no production-code change.
Readiness adapted the processor-conversation assertions, raw-codepoint checks, idempotence control
and query-reader class inventory against its newer verified-checkpoint and GPU-lifecycle code. The
focused visual slice passed 95/95, the exact floor rose to 2,044, and the canonical gate passed
before histories were joined.

Merge `b663cd3` has readiness parent `8ee40e9` and protected-main parent `ba2a445`. Both its tree
and the first-parent tree are `64fd3068d0b4b6374b8a7d3ef6b60cc0e5b05634`; protected main's
older tests, evidence, decision numbering and floor therefore cannot replace the audited readiness
versions. The merged identity still requires local and hosted acceptance.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-232 - Git archive bytes are part of the authenticated release input

The source and hosted gates at `fb17959` were green, yet a clean installed wheel refused its own
packaged base lock.  Windows `core.autocrlf=true` had converted the unclassified `.txt` member
from the committed LF bytes to CRLF during `git archive`; the code-bound SHA-256 correctly detected
the mismatch.  A reproducible wheel can therefore be reproducibly wrong when archive conversion
changes authenticated data before both builds.

Every tracked `.txt` is now `text eol=lf`, including dependency locks, the release-builder lock
and the font license.  The regression forces the Windows autocrlf setting and compares every
archived text member with its Git blob, rather than merely inspecting the working tree.  The exact
`9322f28` wheel then built twice identically and passed fresh installed-wheel proofs on CPython
3.11.15 and 3.12.10: hash-only dependency install, `pip check`, exact environment audit, seven
installed data members and all nine CLIs.

Rejected updating trusted hashes to the CRLF wheel bytes: Linux would then disagree and the digest
would authenticate a platform conversion rather than the committed lock.  Rejected normalizing
on read: the raw wheel member, RECORD and provenance must identify the same reviewed bytes.

`evidence/release-text-byte-integrity-2026-08-10.md`.

## D-233 - Missing tamper evidence is a refusal at both transcript runtime doors

Protected main neutralized the missing/unreadable digest branch while leaving its full suite
green.  Every older tamper test edited the canonical transcript and reached the digest-mismatch
branch; none removed the evidence.  Rewriting the raw and deleting its sidecar could therefore be
made to verify cleanly without reddening a test, even though production already contained the
right refusal.

Five explicit evidence-destruction states are now derived into a two-door matrix for
`verify_raw_integrity` and the independent verification inside `write_norm`, then repeated against
an actually tampered canonical file.  Unreadable states require the missing-evidence diagnostic;
readable empty/whitespace states require digest mismatch.  An intact pair must still verify and
publish/read its normalized artifact, preventing unconditional refusal from passing the matrix.

Rejected moving verification into `read_raw`: that method deliberately exposes exact parsed bytes
so byte-only JSON changes remain observable to the separate digest check.  Rejected claiming an
unkeyed SHA-256 proves origin: an actor able to rewrite both files needs a signature or keyed MAC,
which is a distinct unsatisfied trust requirement.

`evidence/invariant-1-digest-evidence-2026-08-10.md`.

## D-234 - Join main only after adapting its missing-digest mutation to current APIs

Protected main `f189b19` added no production change; it proved the missing/unreadable digest
refusal could be neutralized while its older 1,471-test suite remained green.  Readiness adapted
the finding to its newer API: direct verification and the independent check inside normalized
artifact publication, not the removed `reusable_raw` method.  Seventeen new cases passed in a
289-test transcript/pipeline/concurrency slice, the floor rose to 2,062, and the canonical gate
passed before the history join.

Merge `003963d` has accepted readiness parent `227e1bc` and protected-main parent `f189b19`.
Its tree and the first-parent tree are both `e41b8c6624664bb95aabcf3f70f529f754b091a2`;
the join therefore records main's ancestry without replacing newer transcript storage, release,
pipeline, evidence or ledger content.  The merged identity still requires its own local and hosted
acceptance.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-228 - A prerequisite is held by its own diagnostic, not by a shared exit code

Protected main measured that deleting twelve of fourteen older argv guards left their tests green.
The test asserted only exit 2, which every caught setup failure returns, so a later unrelated error
could impersonate the intended refusal. Readiness's newer surface had 17 condition blocks: 15
reachable guards and two dominated branches that no CLI invocation could reach.

The dead raw blank-query check was already preceded by the stronger normalized Sorani check. The
dead auto-selection source check followed the query-capable producer check, while every possible
producer's own source guard fires earlier. Both were removed instead of inventing direct-internal
tests for behavior an operator cannot observe.

Twenty-one real-CLI cases now cover every reachable guard and both sides of compound rules. Each
asserts the target diagnostic and that no work directory exists, in addition to exit 2. A
bidirectional AST contract requires every pre-input `ValueError` to match exactly one case and
every case to name a live refusal. A legal-argv control gets beyond the whole block. A guard added,
deleted, made uniformly strict or reordered behind filesystem work therefore fails for the reason
the boundary exists. The focused pipeline suite passes 143/143.

Rejected a generic traceback assertion: it still cannot tell which boundary ran. Rejected keeping
unreachable messages as defensive duplication: duplicated policy drifts, cannot be behaviorally
held, and misleads operators about which prerequisite owns the refusal.

`evidence/cli-preflight-boundaries-2026-08-10.md`.

## D-229 - Join main after adding its future-guard binding to the broader preflight matrix

Protected main `2fd2e55` implemented the CLI-refusal finding recorded in D-228 and added a valuable
AST contract: a future refusal cannot arrive without a test case. Readiness retained its broader
21-case matrix, removal of two unreachable branches, distinct compound-rule cases and legal-argv
control, then adapted the bidirectional source binding. The focused pipeline suite passed 143/143,
the exact floor rose to 2,039, and the canonical gate passed before the join.

Merge `f356804` has readiness parent `f5087bf` and protected-main parent `2fd2e55`. Its tree and the
first parent's tree are both `a40298ea3654e74eef9f681b32507fde602b35a1`, so the history join
cannot replace the audited code, tests, evidence or floor with protected main's older versions.
The final merged identity still needs local and hosted acceptance.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-226 - Confidential ZDR is a property of the constructible judge class set

Protected main neutered the two §3 governance gates independently. Developer-API upload tests
reddened, but removing `assert_permits_vertex` left its suite green. Under that mutation a
confidential Vertex judge made both `countTokens` and `generateContent` calls carrying the client's
Kurdish transcript and real JPEG bytes. Production was correct; coverage had silently proved only
the other route.

Readiness's D-221 constructor inventory already names every concrete `GeminiJudge` subclass
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

## D-227 - Join the confidential-ZDR coverage history without replacing the newer matrix

Protected main `3765add` contained the D-226 finding, tests, evidence and ledger changes but no
production-code delta. Readiness adapted its behavioral claim into the existing bidirectional
judge-class inventory, added independent public-entry-point controls, passed the 78-test Gemini
suite, ratcheted the exact floor to 2,021, and passed the canonical gate before joining histories.

Merge `8cf878d` has readiness parent `8bd2974` and protected-main parent `3765add`. Both its tree
and the first-parent tree are `32bb011f1195b1f063d51efd5a59f34b327b9c3f`, so no older test,
documentation or floor content replaced the audited readiness versions. A post-merge canonical
gate remains mandatory because identical Git trees do not prove the new commit identity executes.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-219 - Declare every way a blocker stops needing Hawa

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

## D-220 - Rejoin main after the claims delta, without changing the audited tree

`main` advanced from `ba52888` to `7002331` while the readiness branch was being pushed. The only
new semantic delta was D-219's `ANSWERED` blocker status. It was reproduced, implemented against
the readiness claims suite, and focused-green before history was joined.

Merge `8128707` has first parent `baf11b0` and protected-main second parent `7002331`. Both its
tree and the first-parent tree are `ecb193121a6778a2ff2b9f65d643e0a4f29b7d2a`; the merge adds
ancestry and no file content. This keeps the rule from D-218: semantic equivalence is established
before an `ours` history join, never assumed from the strategy name.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-221 - Hold §7 routing for the constructor hierarchy, not one judge class

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

## D-222 - Rejoin main after the confidential-route finding, preserving the audited tree

Protected main advanced to `b24ce15` after the previous exact-SHA hosted gate. Its semantic delta
was D-221's confidential Vertex routing coverage. Readiness integrated that finding against the
newer Gemini transport, passed its 65-test focused suite, and ratcheted the floor before joining
history.

Merge `ccb11a3` has first parent `42aa923` and protected-main second parent `b24ce15`. Both the
merge and first parent have tree `a332a67e40983efbac9f5cf296b45577f54cca56`, so the join added
ancestry and no file content. The complete local and hosted gates remain mandatory because Git
tree equality is not execution evidence.

`evidence/main-semantic-merge-2026-08-10.md`.

## D-223 - A rejected validator correction is evidence, not an episode failure or a gap

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

## D-224 - Auto-selection requires a query-capable producer, not a producer-shaped flag

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

## D-225 - Join main only after classifying both deltas against the stronger readiness tree

Protected main advanced through `e2c768f` with an interrupted flat-delivery repair and the
queryless auto-selection finding integrated in D-224. Readiness already superseded the former with
its hidden exact-set `ArtifactBundle`; importing flat-file recovery would weaken publication
ownership. Its stricter earlier visual-query preflight already refused the latter's exact
invocation, while D-224 aligned the adjacent producer model and evidence with that behavior.

The canonical first-parent gate passed 2,008/2,008 tests with zero skipped before the join. Merge
`ded03cc` has readiness parent `4b63c04` and protected-main parent `e2c768f`; both the first parent
and merge have tree `03b07a54ce0d40c98e3f3b0de78b2c1a27640264`. The merge therefore records ancestry without
replaying stale content. Tree equality is not runtime acceptance, so a new canonical gate is still
required at the final documented merge tip.

`evidence/main-semantic-merge-2026-08-10.md`.
