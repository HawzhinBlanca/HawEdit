# Billed smoke video preflight — 2026-08-10

The documented live smoke promised Path A and pixel-grounded Stage 4 but omitted its required
`--video`. The old order made both Path A calls before discovering that Stage 4 could not run.
That is a billed failure with a completely knowable argv prerequisite.

Video presence and file existence now run immediately after credential presence, before the cost
estimate, confirmation prompt, model construction or transport. Missing input and nonexistent
paths return exit 2. Tests install a Path A boundary that raises if reached, prove confirmation is
not requested for an impossible run, and require an existing video to reach the boundary so a
smoke command that refuses everything cannot pass.

No matching video exists in the repository. The built-in sample spans 13 seconds; the available
4.162-second Kurdish fixture is unrelated. `BLOCKED.md` #19 therefore requires a real recording
of the sample rather than silently shortening text or using synthetic/unrelated pixels.

The production change rotates the receipt/VEX source identity to
`df74ba00dcae757e7e5f04670811898a61acb847a8c107f321b0c0e562ce8efb`; live WSL acceptance must
use a receipt for that exact snapshot before this policy can pass.
