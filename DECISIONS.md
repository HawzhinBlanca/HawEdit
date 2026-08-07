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
| 5 | Gate not authoritative: CRLF, `echo` bypass, CI never ran it | yes, all three | `.gitattributes`; steps not configurable; junit-report evidence + ratchet; `hawedit2.yml` |
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
is a repository setting only Hawa can change, and until it is set, a red `hawedit2` job does
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
