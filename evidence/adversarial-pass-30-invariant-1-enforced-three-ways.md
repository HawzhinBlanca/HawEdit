# Adversarial pass 30 — "enforced three ways, because any one of them alone is bypassable"

**Target: M0.4, DONE.** `transcripts.py` opens with a claim precise enough to be falsifiable:

> **Invariant #1 — raw is never mutated after write.** Enforced three ways, because any one of
> them alone is bypassable:
> 1. `TranscriptStore.write_raw` refuses a second write, even with identical content.
> 2. `RawTranscript` is a frozen dataclass holding a tuple of words.
> 3. `verify_raw_integrity` compares a sidecar SHA-256 against the file.

A claim naming three *independent* mechanisms fails if any one of them can be removed with the
suite green. So each was reverted in turn, against a baseline verified green first, and the file
restored byte-identical after each.

Run against the **whole** suite, not `tests/test_transcripts.py`: the claim is about the project,
and a guard defended only by its own module's tests is the shape D-105, D-108, D-112 and D-118
each found separately.

## Result — nothing survived

| Mechanism | Reversal | Verdict |
|---|---|---|
| 1 · write-once | both the digest reservation **and** the raw-file link accept a second write | **REFUTED by 13 tests** |
| 2 · frozen in memory | `@dataclass(frozen=False, slots=True)` | **REFUTED** — `test_raw_transcript_is_immutable_in_memory` |
| 3 · tamper evidence | the SHA-256 comparison made vacuous | **REFUTED** — `test_tampering_with_raw_on_disk_is_detected` |

```
file restored byte-identical: True
3/3 mechanisms are actually defended
suite after restore: GREEN
```

The 13 that catch mechanism 1, several named for exactly this and none of them incidental:

```
test_rewriting_raw_with_identical_content_is_still_refused
test_write_once_is_atomic_not_check_then_write
test_write_once_survives_the_new_write_path
test_the_first_layer_still_refuses_while_the_digest_is_present
test_refused_rewrite_does_not_replace_the_existing_digest
test_deleting_the_digest_does_not_open_the_raw_file_to_a_second_write
test_competing_writers_publish_one_matching_raw_and_digest
test_the_raw_transcript_is_written_once_and_never_rewritten
test_a_reused_work_dir_refuses_a_different_supplied_transcript
test_stage_1_is_not_re_run_when_its_output_is_already_in_the_work_directory
test_an_adapted_stage_1_does_not_reuse_the_stock_run_s_transcript
test_distinct_selections_do_not_overwrite_each_others_deliveries
… and one more
```

**The claim holds as written.** M0.4 stays DONE, and nothing in this pass changes code.

## The pass's own defect, and why it is recorded

The first attempt at mechanism 1 removed **only the digest reservation** and left
`os.link(staging, path)` in place — which still raises `FileExistsError` on a second write. It was
reported REFUTED, and that verdict was worthless: it had tested a sub-part while the mechanism
itself remained. A reversal that does not actually remove the thing proves nothing about whether
the thing is defended, and it fails in the flattering direction.

It was caught by reading which test fired. Under `pytest -x` the first failure was
`test_distinct_selections_do_not_overwrite_each_others_deliveries` — a *delivery* test, not a
transcript one. A guard whose only visible defender is incidental is worth a second look, and the
second look showed the reversal was the problem, not the coverage.

Corrected on both counts: remove both refusals, and drop `-x` so every defender is counted rather
than whichever runs first. 13, not 1.

**Method note for later passes.** `-x` answers "does anything notice?" and hides "how much".
For an adversarial pass the second question is the one that matters, because a mechanism defended
by one incidental test is one deletion away from being defended by nothing.
