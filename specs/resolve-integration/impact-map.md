# Impact Map — DaVinci Resolve Studio Live Integration (`specs/resolve-integration`)

## 1. New Files
- `src/hawedit/resolve.py`: DaVinci Resolve live integration bridge and CLI.
- `tests/test_resolve.py`: Unit tests for Resolve bridge, CLI, and mock execution.
- `specs/resolve-integration/tasks.md`: Task tracking ledger.

## 2. Modified Files
- `README.md`: Document `python -m hawedit.resolve import` command in editorial handoff section.

## 3. Downstream Callers & Invariants
- `hawedit.timeline`: Reuses `build_clip_markers` logic to ensure marker colors and frames match OTIO timeline contract.
- `hawedit.delivery`: Reads standard bundle structure (`.edl`, `.srt`, `.json`).
- Gate and lint: Requires zero new external dependencies; imports `DaVinciResolveScript` dynamically with graceful fallback.
