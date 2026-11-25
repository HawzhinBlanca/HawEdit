# Bound Ingest Verification

2026-10-03. Approved T3 engineering repair, not release/CI/reel quality acceptance.
Baseline45e3726cbadc65b82049e5370fda56ecd57aafbc; eleven actual Serena pre-edit
definition/reference queries retained in ingest-cache-before-map.json and
ingest-extract-before-map.json. Existing public pipeline/ingest/extractor signatures,
canonical ASR, model choice, fixtures, harness and original assertions remain unchanged.

## Diagnostic History

External raw evidence: C:/Users/Wareen/AppData/Local/HawEditEvidence.
Test-first ingest-cache-red-20261003.xml/log:10 cases,9 failures/one pass,14.030s.
Two integration cases initially fail (held/path timestamp comparison and diarizer path),
and both standalone same-length/legacy extraction cases fail before extractor changes.
Retain all red evidence; do not retrospectively attribute it to the repaired source.

First implementation exposed native Windows CRT/path ctime differences; the following
attempt exposed .EXE mode differences. Separate full stat baselines correct both without
removing later identity/size/timestamp/link checks. Read-only actual tool/model probe retained.
Third run:20 cases,19 passes,one silent-audio failure,115.644s. That failure found nested
size-only _extract_once reuse; schema2 now binds actual output bytes. Stage0 invalidation
retains media/metadata/extraction sidecars/checkpoint before invalidating extraction reuse.

First complete three-module diagnostic:79 cases,78 passes/one failure,131.139s. Windows
refused an in-place append to the disposable FFmpeg executable during test setup. The
unchanged assertions now use a prebuilt changed executable, replacing the same test path;
installed tool bytes remain unchanged. This is not a suppressed failure or runtime diagnosis.

## Final Focused Evidence

Command: .venv/Scripts/python.exe -m pytest tests/test_ingest_cache.py
tests/test_checkpoint.py tests/test_ingest.py -q --junitxml=<external final2 XML>.
Exit0:79 cases,79 passes,zero failures/errors/skips,133.759s. Source/tests unchanged
through the run. ProducerSHA256:
4ba71b63f68ece3a83199c2a1cfa32867cd8528fd2e604cf4ab83f259873c672.

- ingest-cache-final2-focused-20261003.xml SHA256584a1895b1fc8987883a662d3f74a39ef5250100ba5dd3b110a156c00de6f74a.
- ingest-cache-final2-focused-20261003.log SHA256d5b64567bb95b49fedc49e7ff072e20d49c661106233b021f587972b6edbbbb7.

Native HAWAPC01 Windows11build26200/CPython3.12.10 MSC1943 AMD64/SQLite3.49.1/
pytest9.1.1/DBOS2.29.0/ruff0.9.6/mypy1.15.0. Threadripper3990X64cores/128logical,
RAM274741166080 bytes, Torch2.13.0+cpu, Silero-vad5.1.2/ONNXRuntime1.20.1/
numpy2.2.1/scenedetect0.6.5/OpenCV-headless4.12.0.88. Actual Gyan FFmpeg8.1.1
SHA25609948d4cdd0650da6ff5a87577469f2a218dc2615ae379f8f734d24c49de0f73.
Diagnostic elapsed time is not a throughput/latency benchmark or pinned-release result.

Actual decoded media and Silero ONNX VAD run; no canonical ASR/LLM/judge/vision or paid
provider. Diarizer dispatch probes are explicitly test producers, not speaker accuracy/DER
evidence. Observed byte bindings are not authenticated review or an atomic loader snapshot.
Full corpus/editor/AA/reliability/performance/sustained acceptance remains unfulfilled.

## Next Required Evidence

Reviewed local commit only, clean freeze, exact bash scripts/verify.sh across all affected
pipeline/episode/event/revision/durable callers. Preserve any current VEX refusal and fresh
terminal source-bound XML/log/result externally. No ledger promotion unless gate0 and
required same-SHA CI. Private DBOS startup and ID-only protected worker/attempt/billing/
session/revision/signed review/export remain required; generation still refuses admission.

## Clean-Commit Gate And Inventory Correction

Exact bash scripts/verify.sh at clean frozen b49211cfa58f767175b876ad17f9c0aedc3ebb55
finished2026-10-03T15:25:54Z, exit1. Lint, strict mypy and format pass for309 source files.
4523 cases:4520 passes,three failures,zero errors/skips,1915.91s. Failures:

- tests.test_claims.test_the_module_map_covers_every_module: missing ingest_cache.py.
- tests.test_claims.test_the_ledger_accounts_for_every_module: missing ingest_cache.py.
- tests.test_vex.test_checked_in_policy_binds_current_lock_and_assets_and_closes_report:
  reviewed source81f6f606f89115ddedcba38941aad0b3f86cc59187a52b21b2a8a4f609bc5eba
  differs from current producer4ba71b63f68ece3a83199c2a1cfa32867cd8528fd2e604cf4ab83f259873c672.

Native runtime/hardware above applies. The final frozen report, actual exit, source/runtime
manifests, log and independently copied canonical XML are preserved externally under
C:/Users/Wareen/AppData/Local/HawEditEvidence/studio-commit-b49211cfa58f767175b876ad17f9c0aedc3ebb55.
test-evidence.json binds their hashes. No source/docs edits overlapped this gate, no ledger
promotion or CI/gate-pass claim. A separate two-test diagnostic confirmed both omissions;
ingest-cache-inventory-red-20261003.xml/log remains intact.

Correction adds the README module row and M9.53 WIP inventory row, not weaker assertions
or a completed status. Exact gate must run again from the corrected clean commit. The VEX
policy is untouched: current qualified source-specific review and applicable same-SHA CI
remain required. Producer bytes are unchanged by this documentation correction.

Complete tests/test_claims.py diagnostic after correction:exit0,67 passes,zero failures/
errors/skips,10.788s on the same recorded native runtime. No source/tests edits overlapped
the run. External ingest-cache-inventory-corrected-20261003.xml SHA256
41684fa864f6dc5c5eaab9e3287ca3d9b30493fbe6202270f7c3548d534bab5a;
log SHA256e15e1ea00cc99972a8dd72a70f32d5d0d5834ff793fa24b1c8ee31182eae87df.
This diagnostic is not the exact full gate or same-SHA hosted CI.
