# Adversarial pass 28 — every constant the frozen blueprint states, and what holds it

D-168 (§7's Licence column) and D-172 (§3 Stage 5's three numbers) were the same defect twice: a
value `BLUEPRINT.md` states, checked against a literal typed into a test rather than against the
document. Rather than wait for the third instance, this pass asks the question once for the whole
repository.

## Scope, and what was deliberately left out

46 numeric `Final` constants in `src/hawedit/`; 29 have their value appearing somewhere in the
blueprint. Naive number-matching is noisy — `DEFAULT_TOLERANCE_MS = 50` "matches" *"expect ~50+
GB/s unidirectional"* — so each candidate was read in context and only values the document gives
**verbatim** were kept:

| constant | blueprint text |
|---|---|
| `TARGET_SAMPLE_RATE` | `` -ar 16000 `` in §3 Stage 0's own audio command |
| `PROXY_FPS`, `PROXY_HEIGHT`, `PROXY_CRF` | `` -vf "fps=1,scale=-2:720" … -crf 28 `` |
| `MAX_SPEECH_DURATION_S` | `` max_speech_duration_s=38 `` |
| `OMNIASR_CEILING_S` | "margin under OmniASR's **40 s** ceiling" |
| `MAX_FRAMES_PER_WINDOW` | "a maximum of **64** frames" |
| `RETRIEVE_K` | "Retrieve top **50**" |
| `DEFAULT_NGRAM_SIZE` | "BM25 + character **3-grams**" |

**Excluded on purpose:** `CONTENT_DETECTOR_THRESHOLD = 27.0` (§3 says *"threshold ~27, tuned per
content type"*) and `REFERENCE_FPS = 1.0` (*"Reference settings run ~1 fps"*). Both are written
with a tilde. Binding an approximate figure as exact would invent precision the blueprint declined
to give — the never-guess-a-threshold rule pointing the other way.

## Measured: 7 of 9 already held, 2 not

```
CAUGHT    TARGET_SAMPLE_RATE (-ar 16000)                       (68 tests)
CAUGHT    PROXY_FPS (fps=1)                                    (1 test)
CAUGHT    PROXY_HEIGHT (scale=-2:720)                          (1 test)
CAUGHT    PROXY_CRF (-crf 28)                                  (1 test)
SURVIVED  MAX_SPEECH_DURATION_S (max_speech_duration_s=38)
CAUGHT    OMNIASR_CEILING_S (OmniASR's 40 s ceiling)           (1 test)
CAUGHT    MAX_FRAMES_PER_WINDOW (maximum of 64 frames)         (18 tests)
CAUGHT    RETRIEVE_K (retrieve top 50)                         (2 tests)
SURVIVED  DEFAULT_NGRAM_SIZE (character 3-grams)

7/9 caught by the suite as it stands
```

## Survivor 1 — and the test that should have caught it

`test_the_stage_0_constants_are_the_blueprints` reddened three of the four proxy mutations. It
read:

```python
def test_the_stage_0_constants_are_the_blueprints() -> None:
    assert TARGET_SAMPLE_RATE == 16_000
    assert LOUDNORM_FILTER == "loudnorm=I=-23:TP=-2:LRA=7"
    assert (PROXY_FPS, PROXY_HEIGHT, PROXY_CRF) == (1, 720, 28)
```

Two faults, and the second is the one that bit:

1. **Literals, not the document.** `BLUEPRINT.md` is in the function's own title and is never
   opened — D-172's finding exactly, one module over.
2. **It covers four of the six Stage 0 constants.** Neither `MAX_SPEECH_DURATION_S` nor
   `OMNIASR_CEILING_S` appears. The only test touching the first asserts a *relation*:

   ```python
   assert MAX_SPEECH_DURATION_S < OMNIASR_CEILING_S
   assert OMNIASR_CEILING_S - MAX_SPEECH_DURATION_S >= 2.0
   ```

   `38 → 30` satisfies both (40 − 30 = 10 ≥ 2), so it passed. The blueprint says **38**; the suite
   permitted anything at or below it. That number decides where Silero cuts every piece of audio
   handed to ASR, so every segment boundary — and every transcript — follows it.

The margin test is right and stays: the relation is a real, separate property. What it is not is a
check that the value is the blueprint's.

## Survivor 2 — the n-gram size

`DEFAULT_NGRAM_SIZE` 3 → 4 left the whole suite green. Bound to nothing, and pinned behaviourally
by nothing either, though §2 singles the choice out: *"Character n-grams matter more than usual —
Sorani is morphologically rich with heavy clitic attachment."* That is a stated number, not a
tuning knob.

## The fix

`test_the_stage_0_constants_are_the_blueprints` now parses §3 Stage 0's two ffmpeg commands and
its VAD line for **all seven** values, and `test_the_ngram_size_is_the_one_the_blueprint_states`
does the same for §2. Non-vacuity is a required match per value: a regex that finds nothing fails
there rather than asserting nothing.

A document binding proves the *number* is the blueprint's, not that anything consults it — so
`test_the_ngram_size_is_the_one_the_index_actually_uses` asserts on the artifact, the emitted
n-grams of a word long enough to distinguish 3 from 4.

## Mutation audit — 7/7 lint-clean

```
CAUGHT  survivor 1: MAX_SPEECH_DURATION_S drifts 38 -> 30    test_the_stage_0_constants_are_the_blueprints
CAUGHT  survivor 2: DEFAULT_NGRAM_SIZE drifts 3 -> 4         test_the_ngram_size_is_the_one_the_blueprint_states
CAUGHT  the blueprint's VAD setting changes, not the code    test_the_stage_0_constants_are_the_blueprints
CAUGHT  the blueprint's n-gram size changes, not the code    test_the_ngram_size_is_the_one_the_blueprint_states
CAUGHT  the blueprint's sample rate changes, not the code    test_the_stage_0_constants_are_the_blueprints
CAUGHT  the blueprint's OmniASR ceiling changes, not the code test_the_stage_0_constants_are_the_blueprints
CAUGHT  character_ngrams hard-codes a size and ignores the constant
                                                             test_the_ngram_size_is_the_one_the_index_actually_uses

files restored byte-identical: True
7/7 caught lint-clean
```

Both directions of drift are held — code moving away from the frozen document and the document
moving away from the code — and each mutation reddens exactly the test written for it.

## What survived the pass

The other seven constants were already held, mostly *behaviourally* rather than against the
document: `TARGET_SAMPLE_RATE` reddens 68 tests because the real fixture is 16 kHz, and
`MAX_FRAMES_PER_WINDOW` reddens 18 through `test_claims.py`'s decision-log binding. That binding
already existed for `DECISIONS.md`; the equivalent for `BLUEPRINT.md` is what these two rows were
missing.

**No production code changed.** Both survivors were correct values that nothing held.
