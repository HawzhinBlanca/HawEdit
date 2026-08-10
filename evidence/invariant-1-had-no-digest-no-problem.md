# Invariant #1: no digest, no problem

> Measured 2026-08-10 on hawapc01 against `ba2a445`, Python 3.11 in `.venv`.

`transcripts.py`'s module docstring, item 3: *"`verify_raw_integrity` compares a sidecar SHA-256
against the file."* That sidecar is the whole of Kurdish invariant #1's tamper evidence — the
canonical transcript is written once, made read-only, and its bytes are hashed at write time.

## Two refusals, one of them held

`verify_raw_integrity` refuses twice: when the digest cannot be read at all, and when it does not
match. Each neutered in turn against a baseline verified green first, whole gate suite each time:

```
baseline green: True

UNHELD  a missing or unreadable digest is treated as verified
held    a digest mismatch is treated as verified (the half with three tests)
          red: test_byte_only_tampering_with_raw_is_detected, …

restored and green: True
```

All three existing tamper tests reach the check by editing the **transcript**:
`test_editing_the_raw_transcript_is_detected`, `test_byte_only_tampering_with_raw_is_detected`,
`test_reuse_still_verifies_the_transcript_against_its_digest`. None of them touches the sidecar. The
cheapest way to erase tamper evidence — delete the file that would contradict you — was the one
state nothing checked.

## The artifact

With the missing-digest refusal neutered:

```
as written        : 'ئه‌مه‌ زۆر باشه‌'
sidecar present   : True

# rewrite the canonical transcript, then delete the sidecar

verify_raw_integrity returned cleanly with NO sidecar and a tampered file
what a run gets back: 'ئەمە دەقێکی جیاوازە — TAMPERED'
```

Invariant #1 defeated by one `unlink`, with all 1,471 tests green.

## The fix

Five states that remove the evidence — deleted, empty, whitespace only, not ASCII, a directory —
each asserted against **both** doors: `verify_raw_integrity`, which `pipeline.py` calls directly,
and `reusable_raw`, which Stage 1 reuse goes through. Plus the tampered-file case for every state,
asserted on the text that would otherwise ship.

Which states belong is a judgment; nothing derives it. So the list is written once as
`_SIDECAR_BREAKERS`, the parametrisation is derived from it, and a test pins the derivation — found
by mutation, because with the list written out separately, dropping `"deleted"` left the suite
green while the code producing that state sat behind unused.

The control requires the intact pair to verify *and* to come back through the reuse door with the
text that was written — otherwise a `verify_raw_integrity` that raised unconditionally, or a
`reusable_raw` that never returned anything, would pass every case above.

## Proof

```
baseline green: True

RED       the defect restored: a missing or unreadable digest is treated as verified
RED       only a missing file is refused, an unreadable one is not
RED       only an unreadable file is refused, a missing one is not
SURVIVED  the digest is read as UTF-8, so a non-ASCII sidecar decodes instead of refusing  [lint dirty]
RED       the reuse door stops verifying, so only the direct call is protected
RED       the parametrisation stops deriving from the breakers and drops a state
RED       the digest is recorded but never compared, so any sidecar verifies

6/7
restored and green: True
```

**The survivor is a bad mutation of mine.** Reading the sidecar as UTF-8 with `errors="replace"`
still refuses: the replacement characters it decodes to fail the *mismatch* branch instead. The two
refusals back each other up for a sidecar that is present but wrong — only **total absence** ever
had a single line of defence, which is exactly the state that had no test. It also printed
`[lint dirty]` (the mutated line ran past 100 columns), so it would not have counted either way.

## What this does not protect against, stated rather than implied

An edit that rewrites the transcript *and* recomputes the sidecar passes. No unkeyed digest can
prevent that; it needs a signature or a keyed MAC, and this project has no key. Recorded here so
the tests are not read as claiming more than they check.

Gate: `VERIFY OK — hawedit gate green`, 1488 tests (floor 1471 → 1488).
