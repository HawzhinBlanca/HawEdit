# Specification — credentials panel

## Acceptance criteria

- **AC-1:** WHEN `hawedit-setup` is run on a machine with a display, THE system SHALL open one
  window with a masked field per credential and a Save button per credential.
- **AC-2:** WHEN no display is available, THE system SHALL fall back to the existing terminal
  prompts and SHALL NOT raise a `TclError` at the operator.
- **AC-3:** WHEN a credential is saved, THE system SHALL verify it against its provider before
  storing, and SHALL NOT store a credential that failed verification.
- **AC-4:** WHEN a credential is displayed after storing, THE system SHALL show only `mask()`
  output, never the value.
- **AC-5:** WHEN `HF_TOKEN` is stored, THE gated checkpoint fetch SHALL find it without it being
  present in the process environment.
- **AC-6:** WHEN a gated repository is downloaded, THE download SHALL receive the token as an
  explicit argument rather than relying on ambient environment state.
- **AC-7:** WHEN the panel opens, THE system SHALL show, per credential, which pipeline stages
  it unlocks and which `BLOCKED.md` number it clears.
- **AC-8:** WHEN a valid `GEMINI_API_KEY` is stored, THE panel SHALL still report that
  `gemini-2.5-pro` needs billing on the key's project (`BLOCKED.md` #3), because a valid key
  alone does not make Stage 4 routable.
- **AC-9:** WHEN the panel writes, THE target SHALL remain the owner-only file outside the
  checkout, and a non-git-ignored target SHALL be refused exactly as today.
