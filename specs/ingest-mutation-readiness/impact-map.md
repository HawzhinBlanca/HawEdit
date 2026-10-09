# Impact Map

- Existing edit target tests/test_ingest_cache.py:test_actual_ffmpeg_byte_drift_invalidates_ingest_cache, actual Serena0static refs; pytest dynamic collection. Only replace the deliberate copied-binary mutation call. Preserve EVERY existing decode/recovery/config-event/timestamp/hash/installed-binary assertion.
- New tests/ingest_mutation_support.py:replace_test_executable, test-only; bounded Windows5/32permission retry, no general runtime filesystem abstraction. Caller is the byte-drift test and new control module.
- New tests/test_ingest_mutation_support.py controls use actual files. Windows held/released lease reuses unchanged native_process._libraries/_path/_open_image. Other platforms exercise genuine ordinary mutation and refusal, not fabricated Windows claims.
- initial and ingest._run mapped and reused unchanged; no CLI/server/pipeline/ASR/DBOS/publication behavior or signature touched. No new dependency or protected enforcement surface edits.
- Regression scope: complete ingest-cache and new mutation-control modules; source-package unchanged; exact clean committed gate and same-SHA CI remain required before ledger promotion.

Fresh pre-body-change actual2pair Serena map, unchanged at975ec4a:
C:/Users/Wareen/HawEditIngestMutationSupport-20261009/serena-map.json,
c618bfdeea7b89267ef66a4b8e5088935339fffabb32c4cb637c6d407fabc84f.
replace_test_executable has7static control-call references; existing byte-drift
test0refs/pytest collection. Real immediate-behavior baseline9cases2pass/7fail
reproduces released-lock, held-budget and5invalid-budget failures. Initial
relative-import collection error retained separately, not behavioral evidence.
