# An audit that described the opposite of the code

> Measured 2026-08-10 on hawapc01 against `3265402`.

## The claim

`AUDIT_REPORT.md`, Secondary debt, first bullet:

> Interrupted delivery can require a fresh work directory, by design, because artifact overwrite
> is refused rather than repaired in place.

## The behaviour

D-146 landed at `9e8f128` earlier the same day. Running the guard on this tree:

```
abandoned attempt — three artifacts on disk, no completion record
  _assert_no_existing_artifacts(...) -> ('m-s0-0.ass', 'm-s0-0.mp4', 'm-s0-0.json')
  accepted; the names are what `PipelineRun.resumed_over` reports

finished delivery — all five artifacts and the record written last
  _assert_no_existing_artifacts(...) -> FileExistsError: refusing to overwrite …
```

An interrupted delivery is repaired in place. The audit said the reverse, and had done for two
days — written by me in the session that falsified it, then named as "next" for four iterations
without being fixed. Naming a known falsehood is not removing it.

## The fix

The bullet is struck through and corrected under `**Corrected 2026-08-10 (D-154):**`, stating what
the guard does now and keeping the debt that genuinely remains — two *simultaneous* runs of the
same media id and selection are no longer caught at the pre-write guard, which D-146 records as a
deliberate trade.

The binding matters more than the wording. `test_the_audit_describes_the_delivery_behaviour_this_
tree_actually_has` plants an abandoned attempt and a finished one, runs the guard on both, asserts
the premise it depends on, and *then* requires the audit's wording to match. A test that only
grepped the prose would pass with the guard reverted.

## A second binding, for the class

Nothing checked that a decision cited in the documents exists:

```
README.md          cites   8   missing from DECISIONS: []
AUDIT_REPORT.md    cites   8   missing from DECISIONS: []
PROGRESS.md        cites 133   missing from DECISIONS: []
BLOCKED.md         cites  33   missing from DECISIONS: []
```

All 182 resolve today. `test_every_decision_the_docs_cite_exists` keeps it so — and caught its
first real case immediately, failing on `AUDIT_REPORT.md cites decisions that do not exist:
['D-154']` because the correction marker was written before this entry was.

## Proof

```
baseline green: True

RED  the audit's live claim goes back to "refused rather than repaired in place"
RED  the audit hedges instead: the phrase goes, the contradiction does not arrive
RED  the contradiction is added beside the live claim rather than replacing it
RED  the guard reverts to refusing any leftover, while the audit still says repaired
RED  a document cites a decision that was never written
RED  the citation check stops covering one of the root documents

6/6
restored and green: True
```

The fourth mutation is the one that matters: it reverts the *code* and leaves the *prose*, which is
the direction a grep-only test cannot see.

## The first pass was 1/4, and two survivors were my own work

**I fell into the prose-grep trap inside the test written to prevent it.** The first correction
struck the false bullet through and put the truth *after* the `**Corrected**` marker.
`claims_only` keeps what **precedes** a marker — the convention is live claim first, marker
second — so the text my test read as live was the struck-through *false* claim, and it contains
`repaired in place` inside the phrase `refused rather than repaired in place`. The assertion
passed on the very sentence it existed to forbid. Fifth occurrence of this trap in the project
after D-121, D-139, D-141 and D-143; the first inside a test.

Fixed two ways: the bullet is rewritten so the live claim comes first, and the test now also
refuses the contradicting phrases as live text — a phrase being present is not enough when its
opposite can sit beside it, which is what the second and third mutations above check.

**The document list was hard-coded**, so dropping `AUDIT_REPORT.md` from the citation check left
the suite green. It is derived from `ROOT.glob("*.md")` now, minus the register itself. D-149's
`_SIDECAR_STATES` lesson, one iteration later.

Gate: `VERIFY OK — hawedit gate green`, 1501 tests (floor 1499 → 1501).
