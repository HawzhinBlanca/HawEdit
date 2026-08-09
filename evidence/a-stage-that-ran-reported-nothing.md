# A stage that ran reported nothing about itself

> Measured 2026-08-09 on hawapc01 against `4f08217`, on the real 38-minute run's own report.

`pipeline.py` opens by promising that "every stage yields either a result or a `StageSkipped` that
names its blocker", and that a skipped stage is never reported as an empty result. This checks the
converse: what a stage that *ran* reports.

## Measured

```
discovery    : None      <- Stage 3 ran
candidates   : 7         <- and produced seven merged candidates, all Path B
skipped list : editorial, boundary, render, delivery    <- discovery is absent from it too
complete     : False     <- for the four stages above, not for discovery
```

`discovery` and `editorial` are typed `StageSkipped | None`, and the code writes success as `None`:

```python
discovery=None if merged else _STAGE_3_NOTHING_FOUND
```

So `null` means "produced candidates" in one run and "never attempted" in another, and only
`candidates` disambiguates. Same shape as D-100 (the readiness renderer) and D-110 (the transcript's
gaps): the fact existed and the field a human reads did not carry it.

## The change

```json
"discovery": {"skipped": false, "stage": "discovery", "candidates": 7, "by_path": {"visual": 7}}
```

Derived from the candidates themselves rather than from a second "it ran" flag, which could disagree
with them. The per-path split is there because §8.2 partitions on `discovery_path` — a reader judging
whether the dual-path cost was justified needs the split, not a bare "ran".

`encode(self.discovery) or self._discovery_ran()` keeps an explicit `StageSkipped` first, so a named
blocker is never overwritten by an inferred success. And `None` still means "nothing is known", so a
run that never reached Stage 3 cannot claim it ran.

## Mutation audit

```
baseline FAILED=0
CAUGHT   a discovery that ran reports null again (the defect)
CAUGHT   a positive record is claimed even when nothing ran (over-strict)   <- control alone
CAUGHT   the per-path split §8.2 partitions on is emptied
CAUGHT   the candidate count is hardcoded to zero
CAUGHT   editorial claims a verdict with no clip

5/5
```

Two controls, and they pull in opposite directions: one says a stage that ran must not report null,
the other says a stage nobody attempted must not report that it ran. A single test in either direction
is satisfied by a constant.

Gate: `VERIFY OK — 1228 passed, 0 skipped`.
