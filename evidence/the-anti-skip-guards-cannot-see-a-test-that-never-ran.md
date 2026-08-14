# The anti-skip guards cannot see a test that never ran

> Measured 2026-08-13 on HawaPC01 against `3b83897`, reproducing the shell semantics GitHub uses
> for a default `run:` block on `ubuntu-latest` — `bash -e`, no `pipefail`.

`.github/workflows/gate.yml` carries two steps whose whole purpose is to refuse a green run in
which a fenced test quietly did not execute. They are the guards on §4.3.6's golden render
(Kurdish invariant #4, a pixel comparison) and on §3 Stage 0's real-media coverage:

```yaml
- name: the golden render must have run, not skipped        # :81-90
  run: |
    test -x .ffmpeg/ffmpeg
    .venv/bin/python -m pytest tests/test_captions.py -q \
      -k "golden_reference or simple_shaping" --no-header -rs \
      | tee /tmp/golden.txt
    if grep -q "skipped" /tmp/golden.txt; then ... exit 1; fi
```

Both detect a *skip*. Neither detects a *non-run*, because the pipeline's exit status is
discarded by `tee` and the guard's only question is whether the word "skipped" appears.

## Measured

```
is pipefail on by default in bash -e ?
  exit after false|tee = 0

B. the test has been RENAMED, so -k matches nothing
  pytest alone, -k matches nothing : exit 5
  its last line: 1 deselected in 0.01s
  contains the word 'skipped': NO
  the CI step sees pipeline exit: 0
  -> step PASSES GREEN while nothing ran

C. the test FILE is missing entirely
  ERROR: file or directory not found: tests/test_captions.py
  pipeline exit = 0
  grep found nothing -> step PASSES GREEN
  last line: no tests ran in 0.00s
```

Neither "1 deselected" nor "no tests ran" nor "ERROR: file or directory not found" contains the
string the guard searches for, and each leaves the step green.

## Why this is the failure the step exists to prevent

The step's own name is the claim: *the golden render must have run, not skipped*. It enforces the
second half and not the first. A rename during an ordinary refactor — `test_golden_reference`
becoming `test_golden_render`, or `tests/test_captions.py` being split — retires the pixel
comparison that verifies Kurdish invariant #4, and CI keeps printing green. AGENTS.md calls
exactly this shape out: "A `skipif` nobody notices is worse than a red test"
(`specs/constitution.md:32-33`). A test that no longer exists is not noticed at all.

The author knew the idiom. `set -o pipefail` appears once in this workflow, at `:110` — in a
later step, not in either of these two.

## Scope

This is the CI gate, which AGENTS.md names as the only thing that means done, so it is the one
finding of this class that is not confined to a developer's machine. It does not forge a passing
test; it fails to notice an absent one. The suite's own count floor is a partial backstop for
deletions — `scripts/test-count.floor` would refuse a shrunken suite — but a *rename* keeps the
count identical, and the `-k` filter in these steps is matched against names the floor knows
nothing about.

## Not measured

Whether GitHub's runner image sets `pipefail` through some other mechanism than the workflow file
(reproduced here against documented default behaviour, not against a live runner); whether the
`test -x .ffmpeg/ffmpeg` line preceding the golden step would independently catch a subset of
these cases (it catches a missing binary, not a missing test); and whether the third anti-skip
step at `:110`, which does set `pipefail`, is correct — it was not examined.
