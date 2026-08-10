# Every reachable CLI prerequisite fails at its own boundary

> Integrated 2026-08-10 after protected main `3765add` measured that twelve of fourteen older
> argv refusals were not behaviorally held. Readiness fix: `35b6212`.

## The false-green shape

The older test supplied `--sentences`, `--qc-pass` or `--confidential` without prerequisites and
asserted only `main(...) == 2`. Exit 2 is the CLI's response to every caught setup exception. If a
targeted guard were deleted, a later missing file, malformed input or unrelated prerequisite could
still kill the run with 2 and leave the test green. Protected main demonstrated that failure by
deleting guards one at a time by AST line span after first rejecting a mutation method whose lint
failure made every result falsely red.

## Reachability audit

The current readiness preflight had 17 condition blocks. Two were not CLI-reachable:

1. a raw `visual_query.strip()` blank check was dominated by the earlier normalized Sorani blank
   check; and
2. `--auto-select requires a Stage 1 source` followed the query-capable producer check, while every
   possible producer already has an earlier source requirement—cloud discovery for Path A and
   visual retrieval for Path B.

Those branches were removed. Keeping an unreachable diagnostic would advertise behavior no
operator can observe and invite another test that can only pass for the wrong reason.

The remaining 15 guards are exercised by 21 CLI cases. Compound rules are split where the sides
can drift independently: runtime and WSL distro; Gemini and Vertex; verdict missing source and
missing selection; TimeLens and reframing; and all three governance flags. The matrix also covers
both positive producer families indirectly through D-177's controls.

## What every case proves

Each case invokes the real parser and `main` with the fixture source, then asserts all three:

- exit code 2;
- the exact target diagnostic substring; and
- the requested work directory does not exist.

The exact diagnostic prevents a later unrelated failure from satisfying the test. The absent work
directory proves the boundary ran before Stage 0 or any application-owned filesystem work.

The table is also bound bidirectionally to the source. An AST check reads every direct
`ValueError` before `_run_from_args` begins input loading and requires each message to match exactly
one case fragment; every fragment must still name a live refusal. This catches a future uncovered
guard and a stale case after deletion. A legal argv control passes every preflight and fails only
when its intentionally missing transcript is read, preventing an implementation that refuses
everything from satisfying the negative matrix.

Covered boundaries are Stage 1 exclusivity; Omni runtime/distro ownership; cloud-route and Stage 4
exclusivity; cloud, sentence, verdict and visual source prerequisites; visual-query dependency,
content and source; QC selection; query-capable auto-selection; TimeLens/reframing selection; and
governance-route ownership.

Focused acceptance: `tests/test_pipeline.py` passed 143/143, Ruff was clean, and
`src/hawedit/pipeline.py` passed strict mypy. The exact collector and canonical gate are recorded
after documentation and source-bound security rotation.
