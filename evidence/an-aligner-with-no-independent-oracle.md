# The aligner every caption timing comes from, checked only against itself

§4.2 puts forced alignment in-house: *"This is a real engineering module with its own tests,
not a library call."* Kurdish invariant #5 says every word timing comes from it. `M1.1` is
`DONE`, with 33 tests.

All 33 are hand-written expectations. That is not a criticism of any one of them — it is a
single shared weakness: a systematic misreading of CTC would be written into the code **and**
into the numbers beside it, and every one would still pass. There was no independent answer to
the question the module answers.

## Is the aligner right? Measured, twice, before touching anything

**Against torchaudio's reference forced-alignment kernel**, 400 randomized matrices —
vocabularies 3–8, 3–24 frames, 1–8 tokens with repeats reachable:

```
trials compared against torchaudio : 354
refused as infeasible by both      : 46
mismatches                         : 0
```

**Against an exhaustive search** — every legal CTC state path enumerated and scored, no dynamic
programming — cross-checked with torchaudio on the same matrices:

```
compared                                : 259
refused as infeasible                   : 41
viterbi_align disagreeing with oracle   : 0
torchaudio disagreeing with oracle      : 0
```

**The aligner is correct.** Nothing to fix. What it did not have was anything holding it.

## What the 33 tests were not holding

Five real CTC errors, one at a time, whole suite each, baseline verified green first:

```
CAUGHT    the skip may cross two identical tokens (CTC would collapse the repeat)  <- ONLY the oracle
            tests/test_forced_alignment.py::test_the_aligner_agrees_with_an_exhaustive_search_of_every_legal_path
SURVIVED  the skip may land on a blank state
CAUGHT    frame 0 can only be a blank                            (12 existing tests)
CAUGHT    the path must end on the trailing blank                (12 existing tests)
CAUGHT    minimum_frames counts a blank between different tokens  (8 existing tests)

4/5 caught lint-clean; 1 of them by the new oracle alone
```

**The finding is the first line.** Deleting `extended[state] != extended[state - 2]` — the rule
the module's own docstring calls *"the CTC rule that makes this a real algorithm rather than an
argmax"* — left every one of the 33 tests green, **including
`test_a_repeated_token_is_separated_by_a_blank`, the test named after it**. Its matrix is
`[{1: 0.9}, {BLANK: 0.9}, {1: 0.9}]`: the optimal path goes through that blank whether or not
the rule forces it, so the test passes for the correct implementation and for the broken one
alike. A guard no test would notice being reverted, on the module that times every caption.

The other three are well held already, by twelve, twelve and eight existing tests. Reported as
measured, not claimed for the oracle.

## The survivor is a no-op mutation of mine, and here is the proof

Deleting `extended[state] != blank_id` changes nothing, because the clause beside it already
excludes every state it would exclude. Blanks occupy the **even** indices of the extended
sequence, so when `state` is blank, `state - 2` is blank too:

```
  tokens=[2, 3, 2] extended=[0, 2, 0, 3, 0, 2, 0]
    even states (state, symbol, symbol two back): [(2, 0, 0), (4, 0, 0), (6, 0, 0)]

  transitions examined: 29
  where the blank clause excludes something the repeat clause does not: 0
```

`extended[state] != extended[state - 2]` is `0 != 0` — already False. No test can distinguish
its removal, so it is **documentation, not a control**, and it is not counted. It stays: it says
what the transition means, and the reader should not have to derive the parity argument.

## One hypothesis I chased and disproved

Before finding the parity argument I assumed the survivor was a corpus problem — that a
blank-poor corpus could not produce a matrix where stepping over a token wins. I searched for
one, and matrices like that are everywhere:

```
matrices searched (feasible)          : 50,683
where the blank-skip path outscores   : 34,932
example                               : tokens [2, 3, 2], 4 frames — strict -11.10, relaxed -0.44
```

That number is real but it is about a **different** relaxation: my search harness permitted
blank→blank skips explicitly, which the actual code mutation cannot reach. The corpus change it
prompted is kept, on the honest argument — real CTC posteriors are blank-dominated, and a corpus
of flat random rows is a distribution this aligner never sees — and recorded as having **changed
no mutation result**.

## The oracle, and why it carries no new dependency

`torchaudio==2.11.0+cpu` is in the hash-pinned gate lock, so a differential test against it would
run. It is not used: `pyproject.toml` avoids torchaudio deliberately (*"WAV frames to tensor
without torchaudio"*) and it reaches the gate only transitively, so leaning the gate on it would
be a supply-chain decision taken for a test's convenience. The exhaustive search needs nothing,
is exact, and was validated against torchaudio once — recorded above.

Its own control is
`test_the_exhaustive_search_rejects_paths_as_well_as_accepting_them`: for every case with more
than one legal path, the optimal set must be a **strict** subset of them. An oracle that ranks
everything equally optimal agrees with any aligner at all, and would make the test above vacuous.

Cost: 0.09 s for both tests.
