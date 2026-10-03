# Adapter Identity Verification

Engineering diagnostics only, 2026-10-03. Baseline commit 2cedcca65d0981544f09ab9bcb6cd1fb3e73e86e.
No gate, CI, model quality, throughput, security certification or release verdict is inferred.

Runtime: native Windows 11 build 26200, CPython 3.12.10 MSC 1943 AMD64, SQLite 3.49.1,
pytest 9.1.1, DBOS 2.29.0, ruff 0.9.6, mypy 1.15.0. Original red filesystem/bridge probe
reported seventeen failures and one passing control against the old implementation. Actual
Serena 1.7.1.dev0 LSP provided twelve initial and two constructor/class queries before edits.

## Frozen Caller Diagnostic

Command: .venv/Scripts/python.exe -m pytest tests/test_adapter_identity.py tests/test_asr.py
tests/test_transcripts.py tests/test_pipeline.py -q --junitxml=<external caller XML>.
Exit 0; 625 cases, zero failures/errors/skips, 279.848 seconds. Groups: 19 identity, 68 ASR,
222 transcript, 316 pipeline. Producer SHA256:
54bace6a7c0138aec424d26876537adcf25926f881fbec61e4ff338a578e1c4e.
Source was unchanged during this diagnostic; subsequent recovery-message/test edit is separate.

Raw external files in C:/Users/Wareen/AppData/Local/HawEditEvidence:
- adapter-identity-callers-20261003.xml SHA256 9747644697371163de36cef1cab41b4e776478b68cd9cc292cd69b395dfc9f49.
- adapter-identity-callers-20261003.log SHA256 ad311b02de529c228ea145b79c658a2f1eaf54962727329a04fcedeaf69ae283.

## Final Recovery Diagnostic

Test-first test_changed_adapter_resume_preserves_prior_request_and_output failed on the
old destructive message; adapter-resume-red-20261003.log retains that diagnostic. After
repair, both complete ASR/identity suites passed: 88 cases (19 identity, 69 ASR), zero
failures/errors/skips, 2.757 seconds; exit 0, same -q/external JUnit convention. Producer:
3de6c080ab1d7824cfdca44e61e03304f8d03db1903a6d403e3bfdd3699669e3.
- adapter-identity-final-focused-20261003.xml SHA256 7f0034aab97332c93e18bf1c6163d90ee989085649c7ad1a8e28b2a2a5e167ba.
- adapter-identity-final-focused-20261003.log SHA256 bc33c15b0003d5374d2bdf4cef8362e7affb8406dca7f8dca7b8336b34d1a14c.

Actual native PCM cut uses Gyan FFmpeg 8.1.1 from the WinGet installation, executable SHA256
09948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73; recorded in
adapter-identity-media-tool-20261003.json. Protocol doubles schedule identity faults, not
neural inference. No canonical model or speaker/editorial quality was measured. Old records
were not rewritten. AI1-AI8 stay unticked. Exact bash scripts/verify.sh on the reviewed clean
local commit and applicable same-SHA CI remain required; preserve any current VEX refusal.
