# Checkpoint Shard Metadata Repair, WIP

2026-10-07, baseline clean140d06da68342accd75637342fde122ab838b6b4.
HawaPC01/Windows11 build26300/Threadripper3990X/native Python3.12.10,
pytest9.1.1/ruff0.9.6/mypy1.15.0. Owner "do all" approves engineering repair,
not qualified VEX or publication. BLUEPRINT sections2,3,7,8.1; D-294/#24.

Actual pre-edit Serena map:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/model-security-consumers-map-20261007/serena-map.json`.
Config guard callers: QwenSoraniValidator._load, qwen_visual.load_processor_and_model,
test_asr official-loader contract and all existing model config tests. No signature
change; guard remains inside the existing verified checkpoint read lock.

Real one-weight CPU model on WSL candidate Python3.12.0/Torch2.8.0/
Accelerate1.12.0/Transformers4.57.6/safetensors0.8.0 demonstrated relative and
absolute index paths loaded temporary owned outside payloads after the old guard
accepted them. Contained control passed. This is not untrusted-model integrity
admission. Raw canonical MSIX HawEditEvidence/checkpoint-boundary-probe-20261007.
Initial launch missing PYTHONPATH failed before testing; corrected snapshot launch
passed all three observation cases. No source/model/secret bytes altered.

Native test-first entire new module:37tests/34failures/3contained controls pass,
0errors/skips/JUnit1.398s. Raw model-shard-test-first-20261007.xml.
Initial implementation complete caller suite:255pass/0errors/skips/JUnit12.995s.
Additional nonfinite JSON case:1failure/37pass before strict parser repair.
Final complete four modules:256pass/0fail/errors/skips/JUnit9.348s;
model-shard-final-regressions-20261007.xml under native HawEditEvidence root.
Unpaired Unicode path regression failed before lexical rejection:1failure/38pass.
Final39-case shard module plus complete callers:257pass/0fail/errors/skips,
JUnit9.067s/model-shard-committed-scope-regressions-20261007.xml.
Exact source/hash/command freeze and same-commit full gate still required.

Tests use genuine files, os.link and native Windows directory junction creation,
not mocked filesystem or safety checks. Opaque unit-test shard bytes establish
filesystem semantics only, not valid neural weights. Actual safetensor consumers,
Linux special files and installed index compatibility are separate checks.
The guard bounds JSON reads, rejects ambiguous maps and unsafe names, and checks
unique contained regular targets before the model stack sees an index. No silent
fallback, dependency upgrade, runtime selection switch or canonical ASR edit.

Prior T1 exact clean gate:5130pass/1historical VEX binding failure/0errors/skips,
JUnitSHA74ab01db92a2f72e579572ead45b83efcff02a1a9d17d013fdae69c65407d597,
controller2715.7224895s/source unchanged. This does not validate the new repair.
Full retained live report:141dependencies/21raw entries/15deduplicated findings;
3 newly undispositioned; old review expired and source/lock drifted. No accepted
security report, no row flipped, no CI/push/release or full ZAR reel rerun claimed.
