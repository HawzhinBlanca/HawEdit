# Research

Baseline ae26afe9fe03457bb5a02d1ddc1fba52c191fe6f, 2026-10-08. Actual Serena
find_symbol/find_referencing_symbols: five pairs, unchanged files, map SHA256
d1e57e99ad54e56f8ad684b44e942dfbe3b5beba2de3289f958e3a8a3a6170d7.
Evidence: C:/Users/Wareen/AppData/Local/HawEditEvidence/
scanner-cleanup-map-ae26afe-20261008/serena-map.json.

_run_hash_locked_audit invokes forbidden recursive shell deletion. Requirements
materialization happens outside its cleanup finally, leaking storage on refusal.
run_live_gate is its sole production caller. Existing protocol tests simulate
scanner subprocesses, not actual filesystem cleanup or current qualified VEX.

Use the pinned runtime's isolated stdlib interpreter for directory creation and
cleanup. Capture original device/inode/UID before provisioning; reject unsafe
names, changed identity, foreign ownership, nonprivate roots and symlinks. Hold
directory descriptors while removing contents; never recursively follow paths
or links. Bound depth/entry count and the outer process timeout. No new dependency.
This is execution hygiene for BLUEPRINT sections 2-5 and 8.1-8.3, not changed
neural policy or security disposition. BLOCKED #24 remains qualified-review work.

Vault context: Projects/HawEdit ZAR ASR final result 2026-10-08.md; D-303 repairs
are adopted but no complete studio integration, current CI or acceptance exists.
