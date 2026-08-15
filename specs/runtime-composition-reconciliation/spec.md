# Specification — runtime composition reconciliation

- WHEN HawEdit invokes a command inside WSL, THE system SHALL construct the distribution and
  `--exec` prefix through one public `wsl_prefix` function.
- WHEN the live WSL VEX gate probes uv or creates its scanner, THE system SHALL use that shared
  function rather than a locally duplicated prefix builder.
- WHEN no distribution is selected, THE shared prefix SHALL be exactly
  `wsl.exe --exec`; WHEN a distribution is selected, it SHALL be exactly
  `wsl.exe --distribution <name> --exec`.
- WHEN a shared-prefix regression changes or bypasses that function, THE setup, Stage 1, and live
  VEX command-seam tests SHALL fail.
- WHEN this reconciliation is complete, THE already-landed ASR gap preservation, raw frame-count
  guard, dual-GPU wiring, and sequential cleanup behavior SHALL remain unchanged and green.
