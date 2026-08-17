# The gate cannot tell its own report from another run's

> Measured 2026-08-13 on HawaPC01 against `a7ea98c`. The repository's own `.gate/` was not
> touched; the probe grades files in a scratch directory.

`scripts/verify.sh:62` fixes the report path — `TEST_REPORT="$here/.gate/last-test-run.xml"` —
deletes it at `:128`, has pytest write it, then grades it at `:133` passing `$started_at`.
`src/hawedit/gate.py:194` is the whole recency test:

```python
if not_before is not None and report_path.stat().st_mtime < not_before:
```

That is a one-sided bound. It refuses a report older than this run began. It cannot refuse one
that is *newer than it should be* — a report written by a different run, at the same fixed path,
after this run started.

Nothing else closes the gap. `grep -n "flock\|lockfile\|\.lock\|\$\$\|PID\|trap " scripts/verify.sh`
returns nothing: no lock, no pid file, no cleanup trap. And `gate.py` records nothing about
authorship — no run id, no hostname check, no token written at `rm -f` time and verified at
grading time.

## Measured

Reproducing the ordering a concurrent run produces, rather than racing two real gates:

```
1. this run's own report, 3 failures:
   exit=6  REFUSED: 3 failed, 0 errored out of 100 collected.

2. the other session's report now sits at the same path, 0 failures:
   exit=0  test evidence OK - 100 collected, 100 passed, 0 skipped
   started_at was captured BEFORE either report existed, so freshness passes for both.

3. control - same file, not_before moved past its mtime:
   exit=6  REFUSED: ...last-test-run.xml is older than this run started. It is a
           leftover from an earlier run, not evidence about this one.
```

Step 3 matters: the freshness check is real and it works. The defect is its direction.

## Why this is not hypothetical here

`BLOCKED.md` #12 — live, refreshed 2026-08-09 under D-075 — is titled "Two sessions share this
checkout", and `BLOCKED.md:557` already records three consecutive gate runs degrading under
exactly this contention. During the session that produced this record, `.gate/last-test-run.xml`
was rewritten at 02:30 by a run that was not mine, which is the precondition this finding needs
and the reason it is being written down rather than filed as a curiosity.

The consequence runs past the gate's own output. `scripts/update-ledger.sh:78` calls `verify.sh`,
then `:88-97` greps *that same file* for every cited test name. So a ledger row can be flipped on
another session's evidence, with the provenance line at `:117-119` recording it as this run's.
AGENTS.md's rule that a row flips only against "the report that run wrote" is the thing being
defeated, and the wording of the rule is exactly right — it is the implementation that cannot
tell which run wrote it.

An earlier adversarial reviewer refused this finding on the grounds that the reproduction
"manufactures the divergence rather than deriving it from the race". That is fair about a
manufactured race and beside the point about the check: no ordering of two honest runs is
distinguishable by anything the gate inspects, because it inspects nothing that would differ.

## Scope

Local only. CI runs one gate per job on a clean runner, so `.github/workflows/gate.yml` is
unaffected and remains what AGENTS.md says it is. What is affected is every local `VERIFY OK`
made while a second session is running in the same checkout — which is the documented working
condition of this repository, not an edge case.

## Not measured

Whether two real concurrent `verify.sh` runs actually interleave this way on this machine — the
probe reproduces the ordering and shows the check cannot distinguish it, but I did not start two
gates at once and observe a corrupted verdict. The window's width is therefore unmeasured. Also
unmeasured: whether pytest's own write is atomic enough that a partially written report could be
graded, as opposed to a complete report from the wrong run. No fix is proposed here; a run token
written at `rm -f` time and checked at grading time is the obvious shape, and it edits an
enforcement file, so it needs a spec and a human.
