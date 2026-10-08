# Verification

Baseline ae26afe, actual five-pair Serena map unchanged before implementation.
Test-first lifecycle run: 16 pass / 3 fail, no errors/skips. RED failures reproduce
missing cleanup after lock-write refusal, absent secondary diagnostics, and
failure to refuse unsuccessful cleanup. Raw report red-lifecycle.xml under
C:/Users/Wareen/AppData/Local/HawEditEvidence/scanner-cleanup-map-ae26afe-20261008.
Initial new-module collection failed because the implementation did not exist;
invalid test-literal escapes were corrected before code was written.

Initial repaired native modules: 35 pass, no errors/skips (2.357s pytest elapsed).
On Windows, subprocess filesystem cases assert actual Linux-only refusal, not
positive Linux cleanup coverage. Subsequent recursion regression still pending.
Strict mypy exposed missing explicit constant re-export; corrected without
changing runtime behavior or assertions. Unused test import and formatting fixed.

Actual pinned Linux CPython3.12.0 / WSL kernel6.18.40.1 / glibc2.43 / UID1000:
six real filesystem observations passed, 2.4939780210115714s diagnostic elapsed.
Nested real files removed; child symlink target untouched; wrong inode, root
symlink, actual replacement inode, nonprivate root and four unsafe paths refused.
Module SHA e21391b865b4cc7d4b0a4d338c7770241139b0ed383bd91fbeab82f60e5ea63d;
script SHA 8c3fbf0375b364d8bb90b50332c3df47283bfe5309e913b061a661c5385dcee1.
External script C:/Users/Wareen/observe_hawedit_scanner_storage_20261008.py;
raw linux-observation.json beside the reports. No installed runtime files edited.

Final whole affected modules:36 pass, zero failures/errors/skips; report
native-final-tests.xml SHA256
64eb5190611ec0a897c4f813a84370b76f36de97a8e1b375ebee23e70a162757.
Final pinned-Linux observation also proves a real130-level tree refuses at the
recursion limit and retains the remaining tree; seven observations,
2.9696565630001714s diagnostic elapsed, same module/script hashes. Final raw
linux-final-observation.json retained alongside the initial six-case record.
Strict mypy on all four changed code/test files, ruff lint/format and diff check
pass. Native platform branches remain refusal coverage, not positive Linux tests.

Exact committed gate and current CI remain pending. No ledger promotion,
qualified-policy repair, worker adoption, publication, fidelity or release verdict.
