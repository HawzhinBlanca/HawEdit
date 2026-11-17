# Default Champion Held-Input Repair

```yaml
commit: dd43dda696f8c82cb3eae83f20f6dcef9a5e333c
media_sha256: a09d4eef57cd8a88c92b24bb48860a3143a64fface86e1ad8fe9da179b30288c
host: HawaPC01 - Windows 11 build 26200 / WSL Linux 6.18.40.1 / 2x RTX 3090 Ti
command: .venv/Scripts/python.exe -B C:/Users/Wareen/run_hawedit_champion_held_20261007.py model
```

Engineering verification, not accepted release, qualified VEX or native accuracy.
Implementation commits: `2e449302b8144eb5d5c615ea34cf76fbe62f038d` and
`dd43dda696f8c82cb3eae83f20f6dcef9a5e333c`; D-285, BLUEPRINT sections 3/7,
BLOCKED #24. No model/decoder/timeout/validator-routing change, cloud call or publication.

## Grounding And Red Evidence

Actual installed Serena LSP definitions/references at unchanged 36c2d01 and 2e44930:
`C:/Users/Wareen/AppData/Local/HawEditEvidence/adapted-load-map-36c-20261006/serena-map.json`
and `champion-card-map-2e44930-20261007/serena-map.json` under the same evidence root.
Test-first native result: seven failures, including the actual adapted import before
canonical verification. Subsequent direct-card regression failed at the real global
store lookup. No existing assertion was weakened; the stock construction order was
restored when its existing regression detected a change.

## Closed Source-Current Tests

Source package `c1397cc2a7910e4ddfcf8aac539c7dadf1de0b4b260fb4911362351107376db8`.
All subsequent records below at dd43dda were source-frozen and unchanged. Every owned
native/Linux process was confirmed absent before closing its controller session.

Immutable base: `C:/Users/Wareen/AppData/Local/HawEditEvidence/champion-held-assets-direct-cards-20261007`.
Commands: `.venv/Scripts/python.exe -B C:/Users/Wareen/run_hawedit_champion_held_20261007.py`
with sequential modes `components`, `prepare`, `linux-files`, `model`; then
`.venv/Scripts/python.exe -B C:/Users/Wareen/run_hawedit_champion_linux_tests_20261007.py`.
Exact commands, inputs, installed inventory and receipt paths are in each terminal JSON.

- `components/terminal.json`: exit 0, 240 tests, no failures/errors/skips;
  JUnit 39.147 seconds / controller 41.5128933 seconds. Complete ten affected files.
  JUnit SHA256 `a887d8f756abc6d8d5ea8573bfe52519d675616afcc23ef65c757f37217d2ff1`.
  HawaPC01, Windows build 26200, Python 3.12.10, pytest 9.1.1, ruff 0.9.6,
  mypy 1.15.0, DBOS 2.29.0. Full-scope lint/type checks pass, not the full gate.
- `prepare/terminal.json`: supported `python -B -m hawedit.wsl_setup`, exit 0;
  141.2466878 seconds, reused pinned environment, new source-bound receipt. This
  readiness check is not inference or security approval.
- `linux-files/terminal.json`: exit 1, pinned ASR environment has no pytest. This
  failed attempt is retained; it is not narrated as a passing Linux suite.
- `linux-tests-isolated/terminal.json`: exit 0, all eight new regressions on Linux,
  no failures/errors/skips; JUnit 2.308 seconds / controller 31.994571 seconds.
  JUnit SHA256 `eb306c3819eaa719a89dd5b8d5074e36d282a5ca7d0bb99ee5db936323eef2f6`.
  Temporary private test tools selected from the existing hash-locked Linux host
  requirements: pytest 9.1.1, pluggy 1.6.0, iniconfig 2.3.0, Pygments 2.20.0.
  `pip --require-hashes --no-deps --target` installed only into a fresh /tmp directory;
  it was removed after testing. No protected environment or requirements changed.
  The selection, original-lock/test hashes and wheel provenance are retained locally.

## Real Model And Decoded Development Media

`model/terminal.json`: exit 0, controller 339.2328611 seconds, unchanged source.
`model/linux-result.json` SHA256
`932bc4dfcfdaef62efd1a141504794effb055991fd0d5571d81f3a384f8e7bde`.

HawaPC01, two NVIDIA RTX 3090 Ti, driver 610.88; WSL Linux 6.18.40.1, Python
3.12.0, torch 2.8.0/CUDA 12.8, fairseq2 0.6, omnilingual-asr 0.2.0,
PEFT 0.19.1, Transformers 4.57.6, safetensors 0.8.0. Raw GPU observations are
retained; no isolated VRAM peak or p50/p95 claim is inferred from them.

Champion `lora:dfa6237a3b287b7ca6ef88d848a3540ffbf052f8900bd88e99b5e3495d65809d`.
Observed external loader arguments were forwarded unchanged to real pinned consumers.
Both canonical checkpoint URIs, both tokenizers and all three PEFT bundle members
pointed at held /proc/self/fd aliases. Actual JSON/PEFT configuration and safetensors
consumers read original bytes after deliberate pathname replacement of a synthetic
bundle; context exit refused the changed original and removed its aliases.

Actual champion plus CTC construction: 147.7594850 seconds. All 560 loaded LoRA
tensors matched saved tensors exactly after dtype conversion; both vocabularies
were 10288. Alias directories were removed after construction. These observations
do not authorize a model or defend against privileged/same-UID in-place writers.

Decoded ZAR38 development input: `speech-0000.wav`, 16.476 seconds, mono 16 kHz,
SHA256 `a09d4eef57cd8a88c92b24bb48860a3143a64fface86e1ad8fe9da179b30288c`.
Derived from `ZAR38MinTest.mp4`, source SHA256
`bd004519e4ed0254f5c4f5197aa501acc56ce957829f62ac0bdc4d7190ec1dd2`, in the
previous closed source-bound run. Existing PCM and historical operation bytes were
read only, never used to admit an old production binding into the new runtime.

Unchanged decoder/CTC inference: 84.1581717 seconds. Transcript text, CTC text and
all word values/timings exactly match that window's historical draft. This is
mechanical preservation, not improved CER, meaning fidelity, a native-editor
judgment, a full episode, a delivered reel or a performance pass. Inference is
slower than the input duration on this one instrumented development observation;
throughput remains an engineering problem. No holdout or paid route was used.

## Remaining Verification

The exact full `bash scripts/verify.sh` at 379c7c8 finished with exit 1:
4941 passed / two failures / zero errors or skips, 4943 total. Source and tracked
inputs stayed unchanged. JUnit 2282.529 seconds / controller 2290.5693804 seconds,
same recorded native hardware/library inventory. JUnit SHA256
`d9b4bae40f372765ed73c65b934c6e663130c48174c7fbcab9b5ff158fc0eeaa`;
immutable `gate/terminal.json` and `gate/gate.xml` under the above base.
All exact owned PIDs were absent before closing the controller session.
Failures: this note lacked the required structured evidence header, now supplied
with actual model-test provenance; the historical qualified VEX policy still
binds an older source digest. The complete claims test file then passed in the
295-test lifecycle/affected diagnostic (not a replacement gate).
The previous 36c2d01 gate is historical, not acceptance for this package.
The qualified review date/expiry and policy digest have not been rewritten.
Required current-SHA CI, full studio generation/review/revision/export, real
independent editorial and reliability/performance studies and sustained use remain
unevidenced. No task ledger row is promoted and no 10/10 verdict is issued.
