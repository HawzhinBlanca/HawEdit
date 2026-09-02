# Impact Map — Independent Measurement Module (`hawedit.measure`)

## Modified / Added Files

| File | Type | Changes |
|---|---|---|
| `src/hawedit/measure.py` | New | Independent measurement tool extracting ffprobe, ebur128, silencedetect, scene cuts, face tracking statistics, and caption ink energy into `<clip>.measured.json`. |
| `tests/test_measure.py` | New | Comprehensive unit and integration test suite covering AST independence, ffprobe parsing, loudness/silence detection, face analysis, caption ink energy, and CLI execution. |
| `specs/independent-measurement/tasks.md` | New | Tasks ledger for the independent measurement module. |

## Symbol Impact & Referencing Symbols
- **`measure_clip`** (new): Entrypoint for measuring a delivered media file. No existing callers modified (used by CLI and upcoming T1.2 reconciliation gate).
- **`ClipMeasurement`** (new): Immutable dataclass representing the complete measured reality of a clip.
- **AST Isolation**: `measure.py` is guaranteed not to reference `hawedit.render` or `hawedit.pipeline`.
