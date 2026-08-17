# Strict persisted editorial evidence — 2026-08-17

## Before

Measured at `7295356b6d288ea0d2b30661dc83cfd23d3aa80b`, five independently reachable
schema failures were accepted:

- `Boundary.from_dict` converted `false`/`true` media-clock fields to `0`/`1` and retained a
  `NaN` confidence;
- `Output.from_dict` accepted `durations=[true]`;
- `Editorial.from_dict` accepted booleans as its four scores and payoff time;
- `RejectedCandidate.from_dict` accepted boolean media-clock bounds;
- `--verdict` accepted duplicate and unknown members, with the last duplicate winning.

The first four are consequences of Python treating booleans as integers. The last is a review and
evidence ambiguity: the persisted Stage 4 stand-in can carry two values for the same reviewed field
or a constraint the consumer silently ignores.

## Guard

The §5 readers now require exact object members, exact JSON containers and non-coercing scalar
types. Explicit legacy omissions remain readable. `Boundary.from_dict` validates shape and scalar
types without enforcing the relational sentence invariant; `assert_boundary_invariant` remains the
independent render gate.

`JudgeVerdict.from_json` rejects duplicate keys, `NaN`/`Infinity`, non-object documents, missing
members, unknown members, and excessive nesting. The pipeline reads no more than one MiB plus one
sentinel byte—the live provider response budget—before decoding UTF-8. Its `--verdict` route runs
before Stage 0, so ambiguous or oversized evidence returns the documented exit 2 with a bounded
diagnostic and no traceback or media work.

The source-bound WSL VEX applicability digest is now
`6fc2d71fdb249ffe1b5a3d4f5af25558bdd1cbd78e21ca1aaef75cf902b33a4a`.

## Verification

- Red baseline: 38 new failures and 378 existing passes across boundary, clip, judge and pipeline.
- Focused boundary/clip/judge/pipeline surface: 422 passed.
- Combined focused plus render/delivery/editorial/VEX adjacency: 698 passed.
- Ruff check and format: clean.
- strict mypy: four production modules clean.

The canonical clean-tree gate and exact-SHA hosted checks are recorded after the explicit commit;
this file does not pre-claim them.
