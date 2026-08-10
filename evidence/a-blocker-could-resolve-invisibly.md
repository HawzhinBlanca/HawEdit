# A blocker could resolve invisibly

> Reproduced 2026-08-10 on the readiness branch while integrating `main` commit `7002331`.

`tests/test_claims.py` decides whether a `BLOCKED.md` entry is still live. Its parser recognized
only `RESOLVED`, while the ledger also uses `ANSWERED` on #10. Consequently #10 had read as live
since 2026-08-08 even though Hawa answered the repository question and the surviving Windows
loader obstacle was recorded separately as #11.

Current heading vocabulary:

```text
ANSWERED: #10
RESOLVED: #2, #5, #6, #7, #8, #11, #12, #16
```

Nothing currently cites #10, so the existing claim guard happened to remain green. A future
`BLOCKED` row could have cited it and passed despite needing no answer from Hawa.

The resolution vocabulary is now the explicit set `{ANSWERED, RESOLVED}`. Three regressions bind
both directions:

- every bold heading marker must start with a declared resolution word;
- #10 must parse as non-live while unmarked #1 remains live;
- every declared word must actually occur, preventing speculative status vocabulary.

This preserves the meaningful distinction between a question being answered and an obstacle
being resolved. Renaming #10 would erase that history; accepting any bold marker would recreate
the blind spot.

Focused proof: `tests/test_claims.py` passes with the three new guards, and the canonical gate at
the final merge tip records the exact whole-suite count.
