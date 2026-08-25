# Research — strict persisted editorial evidence

Date: 2026-08-17

Revision: `7295356b6d288ea0d2b30661dc83cfd23d3aa80b`

Serena is not exposed in this session, so symbol and caller discovery used read-only `rg` plus
direct source inspection, as permitted by the parent acceptance research.

## Reachable boundary

`pipeline.main` reads `--verdict` with the standard `json.loads` decoder and passes the resulting
mapping to `JudgeVerdict.from_dict`. This is the only Stage 4 source usable without a live cloud
account, so it is a production input rather than a test-only convenience. `JudgeVerdict` projects
into the shipped `Editorial` and `Output` blocks. `Clip.to_dict` then publishes those blocks beside
`Boundary`, `ClipTranscript`, `Qc`, and the final render span in the editing JSON.

The direct deserializers are also the §1 replaceable-stage contract:

- `Boundary.from_dict` is consumed by `Clip.from_dict`;
- `Editorial.from_dict`, `Output.from_dict`, `Qc.from_dict`, and `ClipTranscript.from_dict` are
  consumed by `Clip.from_dict`;
- `RejectedCandidate.from_dict` rebuilds the first-class rejection record;
- `JudgeVerdict.from_dict` is consumed by the CLI, editorial benchmark, and signed editorial
  acceptance importer.

## Measured failures

Against the revision above, all of these were accepted:

1. `Boundary.from_dict` coerced `false`/`true` time bounds through `int(...)` to `0`/`1` and kept
   `confidence=NaN`.
2. `Output.from_dict` accepted `durations=[true]`, producing a one-second setting represented by a
   boolean.
3. `Editorial.from_dict` accepted booleans for all four scores and for `payoff_at_ms`.
4. `RejectedCandidate.from_dict` accepted boolean media-clock bounds.
5. the CLI verdict decoder accepted a duplicate `hook_score` and an unknown `unexpected` member;
   the last duplicate silently won.

Python's `bool` is a subclass of `int`, and the standard JSON decoder accepts `NaN` by default.
Those language conveniences are not the §5 schema. A reviewed verdict with two values for one key
has no unique signed meaning, and ignoring an unknown field lets a producer believe it supplied a
constraint the consumer discarded.

## Scope decision

This unit hardens the persisted Stage 4 and §5 editing contract only. It preserves documented
legacy omissions (`media_sha256`, `Editorial.payoff_at_ms`, `Output.hashtags_ckb`, and other fields
already read with defaults), but rejects unknown members and wrong JSON scalar/container types.
Relational boundary violations remain representable so `assert_boundary_invariant` continues to be
the independent render gate. `MergedCandidate.from_dict` is not a CLI or persisted input on the
current production path and remains for a later discovery-contract pass.
