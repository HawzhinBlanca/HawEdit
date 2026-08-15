# Specification — WSL runtime-root override

## Acceptance criteria

- **AC-1:** WHEN `--runtime-root` is provided to `hawedit-asr-setup`, THE setup command SHALL pass
  that exact absolute host path to `provision_wsl_runtime`.
- **AC-2:** WHEN no explicit root is provided and `HAWEDIT_WSL_RUNTIME` contains an absolute path,
  THE setup command and `WslOmniAsrProducer` SHALL resolve the same path.
- **AC-3:** WHEN both an explicit root and `HAWEDIT_WSL_RUNTIME` are present, THE explicit root
  SHALL take precedence.
- **AC-4:** WHEN a configured runtime root is empty or relative, THE system SHALL refuse it before
  provisioning, receipt loading, WSL execution, or filesystem mutation.
- **AC-5:** WHEN no root is configured, THE existing platform-specific default SHALL remain
  unchanged.
- **AC-6:** WHEN the PowerShell wrapper receives `-RuntimeRoot`, THE wrapper SHALL forward it as
  `--runtime-root` without rewriting the path.
- **AC-7:** WHEN a root is accepted, THE existing root, receipt, source-snapshot, generation, lock,
  and reparse validations SHALL remain authoritative.
