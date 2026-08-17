# Impact map — strict persisted editorial evidence

| Symbol | Direct callers/consumers | Required regression surface |
|---|---|---|
| `Boundary.from_dict` | `Clip.from_dict`, boundary/clip tests | boundary + clip |
| `Editorial.from_dict` | `Clip.from_dict`, legacy §5 reader tests | clip + judge |
| `Output.from_dict` | `Clip.from_dict`, legacy §5 reader tests | clip + judge |
| `Qc.from_dict` | `Clip.from_dict` | clip |
| `ClipTranscript.from_dict` | `Clip.from_dict` | clip + transcript adjacency |
| `RejectedCandidate.from_dict` | public §5 rejection reader | clip + pipeline artifact round-trip |
| `Clip.from_dict` | public editing-JSON reader and tests | clip + render/delivery adjacency |
| `JudgeVerdict.from_dict` | pipeline CLI, editorial benchmark, editorial acceptance | judge + pipeline + editorial suites |
| new `JudgeVerdict.from_json` | pipeline `--verdict` | judge + CLI |

`pipeline.main` is the only production call changed: its standard decoder is replaced with the
strict verdict decoder. No cloud transport, GPU adapter, render command, or frozen blueprint field
changes.
