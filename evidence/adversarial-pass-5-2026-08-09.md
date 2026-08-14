# Adversarial pass #5 â€” four DONE rows attacked, twenty-one false counts found

> Run 2026-08-09 on hawapc01 against `2bfde57`, against a green 1,167 baseline.
> Done by hand, one mutation at a time, rather than by a fleet of agents.

## Part 1 â€” revert the behaviour, check the test goes red

Four DONE rows, eight claims, each reverted alone in the source and reverted back before the next.
Every run covered `test_asr`, `test_alignment`, `test_transcripts`, `test_escalation`,
`test_discovery`, `test_bench`, `test_claims`, `test_pipeline`.

```
baseline FAILED=0

[M0.8] RED  AsrProvenance stops checking the aligner is CTC Viterbi
              -> test_word_timings_from_a_non_ctc_aligner_are_refused
[M0.8] RED  words with no declared aligner are accepted
              -> test_a_transcript_with_words_must_declare_an_aligner
[M0.7] RED  a mixed-hardware set is combined into one figure
              -> test_measurements_from_different_hardware_refuse_to_be_compared
[M0.7] RED  a failed item aborts the run instead of being recorded          (3 tests)
[M0.7] RED  the measurement stops naming its adapter                        (2 tests)
[M1.5] RED  duration is added to the escalation decision (Â§3's prohibition)
              -> test_duration_does_not_influence_the_decision
[M2.5] RED  the merge widens spans to the union of both paths               (2 tests)
[M2.5] RED  the merge intersects: a one-path candidate is dropped          (17 tests)

8/8 â€” all four rows survived the attack. unprotected claims: 0
```

One suspicion I raised and then refuted myself: `RawTranscript.__post_init__` checks
`self.asr.aligner is None`, which is presence rather than identity, and looked like the D-103
truthiness shape. It is not â€” `AsrProvenance.__post_init__` calls `assert_ctc_viterbi` on any
non-`None` aligner, so a forbidden aligner is refused one layer earlier and the two checks compose.
Measured before writing it down.

## Part 2 â€” do the docs still match the code

They did not. `PROGRESS.md` carried **30 standing test counts**, and **21 of them were false**:

```
row     file                    claims  actual   verdict
M2.7    test_pipeline               18      59   STALE by +41
M5.2    test_video_input            16      35   STALE by +19
M0.4    test_transcripts            17      34   STALE by +17
M1.6    test_models                 21      34   STALE by +13
M2.4    test_render                 21      31   STALE by +10
M5.1    test_visual_index           51      61   STALE by +10
M0.7    test_asr                    14      22   STALE by +8
M3.1    test_captions               33      41   STALE by +8
M2.6    test_judge                  40      47   STALE by +7
M5.2    test_qwen_visual            16      20   STALE by +4
M1.3    test_ingest                 20      23   STALE by +3
M5.3    test_path_b                 26      28   STALE by +2
M5.4    test_video_reader           22      23   STALE by +1
M3.6    test_delivery               25      26   STALE by +1
M6.3    test_video_grounding        20      19   STALE by -1
M2.2    boundary / clip          31/20   38/27   STALE (attached to src/)
M2.8    credentials / gemini     20/26   21/33   STALE (attached to src/)
M0.1    test_gate + evidence     29/17   25/14   STALE â€” written by this loop yesterday
```

Two of these deserve naming:

* **M6.3 drifted *downward*** â€” the direction that means "a test disappeared". It did not: the file
  has had 19 since the commit that wrote the claim (`674b43b`), so the number was miscounted on the
  day it was recorded. Checked before reporting, because a deleted test would have been a much
  larger finding than a stale number.
* **M0.1's pair is mine**, written one iteration earlier: "29 tests, plus 17 in
  test_gate_evidence.py" against an actual 25 and 14. A hand-maintained count was wrong within
  24 hours of being written, by the same process that is auditing it.

### The fix, and why dropping rather than enforcing

All 30 removed; the file references stay. This generalises a decision already recorded twice â€”
D-083 and D-084 each say "the stale count is dropped rather than restated" â€” rather than inventing
one.

The alternative, enforcing every count against `--collect-only`, was rejected: it makes each new
test require a ledger edit in the same commit, turns the row into a generated artifact, and would go
red on the other agent's commits as readily as on mine. The count is also the one part of a row a
reader cannot act on, and `scripts/test-count.floor` is already the instrument that notices tests
disappearing.

Four **quoted historical** counts survive untouched â€” the "the stale `(15 tests)` count is dropped
rather than restated" sentences. Those record a past edit rather than claiming a present fact, which
is the same distinction `test_every_test_count_in_the_audit_is_dated` already draws.

### Mutation audit on the new check

```
baseline FAILED=0
CAUGHT   a standing count is reintroduced on a tests/ reference
CAUGHT   a standing count is reintroduced on a src/ reference
CAUGHT   an ACCURATE standing count is reintroduced (it rots tomorrow)
OK       a quoted historical count in correction prose is NOT flagged   <- CONTROL

3/3
```

The third mutation is the one that matters: the check refuses a count that is *correct today*,
because correctness today is not the property at issue. The control proves it does not simply ban
the digits.

Gate: `VERIFY OK â€” 1168 passed, 0 skipped`.
