# Specification — WSL receipt newline portability

## Acceptance criteria

- WHEN the same reviewed Python and checkpoint metadata are materialized with LF or CRLF, THE WSL
  receipt validator SHALL accept the existing source-bound snapshot.
- WHEN checkpoint metadata differs after universal-newline normalization, THE WSL receipt validator
  SHALL refuse it.
- WHEN snapshot metadata is linked, missing, extra, unstable, or outside the exact allowlist, THE
  WSL receipt validator SHALL retain the existing refusal behavior.

These criteria implement the cross-platform source identity required by the approved
true-10/10 acceptance program and do not change `BLUEPRINT.md` behavior.
