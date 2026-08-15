# Research — bounded Path B refusal diagnostics

## Finding

`VideoChat3Reader.read_scenes` converts a per-window `PathBError` into
`UnreadableScene.reason` with `f"{type(exc).__name__}: {exc}"`. `UnreadableScene` checks only
that the reason is non-blank. A direct reproduction accepted 1,000,009 characters, a NUL and a
newline, and `VisualDiscoveryResult.to_dict` serializes that value into the pipeline report.

The rest of the runner already bounds and single-lines exception-derived `StageSkipped` reasons.
The unreadable-survivor path is different because it records a partial Path B result instead of a
stage failure, so it bypasses that boundary.

## Caller map

Serena is required by `AGENTS.md` but is unavailable in this Codex session. Exact `rg` symbol and
reference searches were used instead.

| Symbol | Producers/consumers | Impact |
|---|---|---|
| `UnreadableScene` | `VideoChat3Reader`, injected readers in Path B tests | Central place to make every refusal safe. |
| `UnreadableScene.to_dict` | `VisualDiscoveryResult.to_dict`, pipeline JSON | Must never emit unbounded/control-bearing diagnostic text. |
| `VideoChat3Reader.read_scenes` | `discover_visual`, `VisualComposer` | Must preserve useful exception type/detail while obeying the record invariant. |

## Chosen boundary

Normalize refusal reasons at `UnreadableScene` construction: require an actual string, replace
non-printable characters with spaces, collapse whitespace, retain ordinary short messages exactly,
and cap the serialized reason at 1,024 characters with a deterministic ellipsis. This matches the
existing pipeline exception-detail budget and protects every producer, including injected readers.

This is report-integrity hardening. It does not reinterpret model output, change survivor ranking,
or hide the fact that a window was unreadable.
